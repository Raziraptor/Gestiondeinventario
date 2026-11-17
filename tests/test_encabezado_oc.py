"""
Tests del encabezado PDF de OC por proveedor: normalización de campos,
placeholders, rutas de configuración (permisos / multi-tenant) y PDF con AcroForm.
"""

import io
from datetime import datetime
from types import SimpleNamespace

import pytest
from werkzeug.datastructures import MultiDict

from app.extensions import db as _db
from app.models.purchasing import EncabezadoOCProveedor
from integrations.encabezado_oc import (
    CAMPOS_PLANTILLA, MAX_EXTRAS, MAX_ETIQUETA, MAX_VALOR,
    campos_por_defecto, normalizar_campos, resolver_valor, contexto_orden,
)
from tests.conftest import do_login
from tests.test_purchasing import _make_proveedor, _make_almacen, _make_orden


# ── Helpers ───────────────────────────────────────────────────────────────────

def _form_de(campos):
    """MultiDict como el que manda el formulario para una lista de campos."""
    md = MultiDict()
    for c in campos:
        md.add('campo_clave[]', c['clave'])
        md.add(f"etiqueta_{c['clave']}", c.get('etiqueta', ''))
        md.add(f"valor_{c['clave']}", c.get('valor', ''))
        if c.get('activo'):
            md.add(f"activo_{c['clave']}", '1')
        if c.get('multilinea'):
            md.add(f"multilinea_{c['clave']}", '1')
    return md


def _guardar(client, prv_id, campos=None, **extra):
    data = _form_de(campos if campos is not None else campos_por_defecto())
    data.add('enc_activo', '1')
    for k, v in extra.items():
        data.add(k, v)
    return client.post(f'/proveedor/{prv_id}/encabezado-oc', data=data,
                       content_type='multipart/form-data', follow_redirects=False)


# ── normalizar_campos ─────────────────────────────────────────────────────────

class TestNormalizarCampos:
    def test_por_defecto_ida_y_vuelta(self):
        res = normalizar_campos(_form_de(campos_por_defecto()))
        assert [c['clave'] for c in res] == [c['clave'] for c in CAMPOS_PLANTILLA]
        assert all(c['activo'] for c in res)

    def test_claves_desconocidas_se_ignoran(self):
        res = normalizar_campos(_form_de([
            {'clave': 'hackeo', 'etiqueta': 'X', 'activo': True},
            {'clave': 'extra_99', 'etiqueta': 'No existe', 'activo': True},
        ]))
        claves = {c['clave'] for c in res}
        assert 'hackeo' not in claves and 'extra_99' not in claves
        # Los del catálogo siempre quedan, apagados si no venían.
        assert claves == {c['clave'] for c in CAMPOS_PLANTILLA}
        assert not any(c['activo'] for c in res)

    def test_limites_de_longitud(self):
        res = normalizar_campos(_form_de([
            {'clave': 'no_cuenta', 'etiqueta': 'E' * 300, 'valor': 'V' * 5000, 'activo': True},
        ]))
        c = next(c for c in res if c['clave'] == 'no_cuenta')
        assert len(c['etiqueta']) == MAX_ETIQUETA
        assert len(c['valor']) == MAX_VALOR

    def test_etiqueta_vacia_en_catalogo_usa_la_original(self):
        res = normalizar_campos(_form_de([{'clave': 'fecha', 'etiqueta': '   ', 'activo': True}]))
        assert next(c for c in res if c['clave'] == 'fecha')['etiqueta'] == 'FECHA'

    def test_valor_de_una_linea_se_aplana(self):
        res = normalizar_campos(_form_de([{'clave': 'no_cuenta', 'valor': 'A\r\nB', 'activo': True}]))
        assert '\n' not in next(c for c in res if c['clave'] == 'no_cuenta')['valor']

    def test_extras_nuevos_reciben_clave_del_servidor_y_tope(self):
        nuevos = [{'clave': f'nuevo_{i}', 'etiqueta': f'Extra {i}', 'activo': True}
                  for i in range(MAX_EXTRAS + 3)]
        nuevos.append({'clave': 'nuevo_500', 'etiqueta': '', 'activo': True})  # sin etiqueta: fuera
        res = normalizar_campos(_form_de(nuevos))
        extras = [c for c in res if c['clave'].startswith('extra_')]
        assert len(extras) == MAX_EXTRAS
        assert len({c['clave'] for c in extras}) == MAX_EXTRAS
        assert not any(c['clave'].startswith('nuevo_') for c in res)

    def test_extra_existente_conserva_clave_y_nuevo_no_choca(self):
        actuales = [{'clave': 'extra_1', 'etiqueta': 'Viejo'}]
        res = normalizar_campos(_form_de([
            {'clave': 'extra_1', 'etiqueta': 'Viejo editado', 'activo': True},
            {'clave': 'nuevo_1', 'etiqueta': 'Otro', 'activo': True},
        ]), actuales)
        extras = {c['clave']: c['etiqueta'] for c in res if c['clave'].startswith('extra_')}
        assert extras == {'extra_1': 'Viejo editado', 'extra_2': 'Otro'}

    def test_respeta_orden_del_formulario(self):
        orden = list(reversed(campos_por_defecto()))
        res = normalizar_campos(_form_de(orden))
        assert [c['clave'] for c in res] == [c['clave'] for c in orden]


# ── Placeholders ──────────────────────────────────────────────────────────────

class TestPlaceholders:
    def _orden(self):
        return SimpleNamespace(
            id=42, fecha_creacion=datetime(2026, 10, 13),
            proveedor=SimpleNamespace(nombre='PC Trade', contacto_telefono='555-1234',
                                      contacto_email='ventas@pc.mx'),
            almacen=SimpleNamespace(nombre='Bodega Centro'),
        )

    def test_sustituye_lista_blanca(self):
        ctx = contexto_orden(self._orden(), 7)
        txt = '{id}|{consecutivo}|{fecha}|{proveedor}|{telefono}|{email}|{almacen}'
        assert resolver_valor(txt, ctx) == '42|007|13-Oct-2026|PC Trade|555-1234|ventas@pc.mx|Bodega Centro'

    def test_no_evalua_atributos(self):
        ctx = contexto_orden(self._orden(), 1)
        for malo in ('{orden.__class__}', '{0}', '{proveedor.__init__}', '{id!r}'):
            assert resolver_valor(malo, ctx) == malo

    def test_multilinea_quita_lineas_vacias(self):
        orden = self._orden()
        orden.proveedor.contacto_telefono = None
        ctx = contexto_orden(orden, 1)
        assert resolver_valor('{proveedor}\n{telefono}', ctx) == 'PC Trade'


# ── Rutas de configuración ────────────────────────────────────────────────────

class TestRutasEncabezado:
    def test_admin_guarda(self, client, admin_user, org):
        prv = _make_proveedor('PC Trade', org.id)
        _db.session.commit()
        do_login(client, admin_user.username)
        campos = campos_por_defecto()
        campos.append({'clave': 'nuevo_1', 'etiqueta': 'Proyecto', 'valor': 'LDC', 'activo': True})
        r = _guardar(client, prv.id, campos, enc_titulo='PC TRADE SA DE CV')
        assert r.status_code == 302
        enc = EncabezadoOCProveedor.query.filter_by(proveedor_id=prv.id).one()
        assert enc.activo and enc.titulo == 'PC TRADE SA DE CV'
        assert any(c['clave'] == 'extra_1' and c['valor'] == 'LDC' for c in enc.campos)

    def test_editar_proveedor_muestra_tarjeta(self, client, admin_user, org):
        prv = _make_proveedor('PC Trade', org.id)
        _db.session.commit()
        do_login(client, admin_user.username)
        r = client.get(f'/proveedor/editar/{prv.id}')
        assert r.status_code == 200
        assert b'Encabezado PDF de OC' in r.data
        assert b'name="etiqueta_no_cuenta"' in r.data

    def test_usuario_regular_bloqueado(self, client, regular_user, org):
        prv = _make_proveedor('PC Trade', org.id)
        _db.session.commit()
        do_login(client, regular_user.username)
        _guardar(client, prv.id)
        assert EncabezadoOCProveedor.query.count() == 0

    def test_proveedor_de_otra_org_404(self, client, beta_admin, org):
        prv = _make_proveedor('PC Trade', org.id)
        _db.session.commit()
        do_login(client, beta_admin.username)
        assert _guardar(client, prv.id).status_code == 404
        r = client.post(f'/proveedor/{prv.id}/encabezado-oc/eliminar')
        assert r.status_code == 404
        assert client.get(f'/proveedor/{prv.id}/encabezado-oc/vista-previa').status_code == 404
        assert EncabezadoOCProveedor.query.count() == 0

    def test_logo_falso_rechazado(self, client, admin_user, org, app, tmp_path):
        app.config['UPLOAD_FOLDER'] = str(tmp_path)
        prv = _make_proveedor('PC Trade', org.id)
        _db.session.commit()
        do_login(client, admin_user.username)
        r = _guardar(client, prv.id, enc_logo=(io.BytesIO(b'<?php echo 1; ?>'), 'logo.png'))
        assert r.status_code == 302
        assert EncabezadoOCProveedor.query.count() == 0
        assert not (tmp_path / 'encabezados').exists() or not any((tmp_path / 'encabezados').iterdir())

    def test_logo_valido_se_guarda_y_se_borra(self, client, admin_user, org, app, tmp_path):
        from PIL import Image
        app.config['UPLOAD_FOLDER'] = str(tmp_path)
        prv = _make_proveedor('PC Trade', org.id)
        _db.session.commit()
        do_login(client, admin_user.username)
        png = io.BytesIO()
        Image.new('RGB', (20, 10), 'red').save(png, 'PNG')
        png.seek(0)
        _guardar(client, prv.id, enc_logo=(png, 'logo.png'))
        enc = EncabezadoOCProveedor.query.one()
        assert enc.logo_url.startswith('encabezados/')
        archivo = tmp_path / enc.logo_url
        assert archivo.is_file()

        client.post(f'/proveedor/{prv.id}/encabezado-oc/eliminar')
        assert EncabezadoOCProveedor.query.count() == 0
        assert not archivo.exists()

    def test_vista_previa_sin_ordenes_redirige(self, client, admin_user, org):
        prv = _make_proveedor('PC Trade', org.id)
        _db.session.commit()
        do_login(client, admin_user.username)
        r = client.get(f'/proveedor/{prv.id}/encabezado-oc/vista-previa')
        assert r.status_code == 302


# ── PDF de la OC ──────────────────────────────────────────────────────────────

class TestPdfOC:
    def _orden(self, org, admin_user):
        prv = _make_proveedor('PC Trade', org.id)
        alm = _make_almacen('Bodega Centro', org.id)
        return prv, _make_orden(org.id, prv.id, alm.id, admin_user.id)

    def test_sin_encabezado_no_tiene_formulario(self, client, admin_user, org):
        _, orden = self._orden(org, admin_user)
        do_login(client, admin_user.username)
        r = client.get(f'/orden/{orden.id}/pdf')
        assert r.status_code == 200 and r.mimetype == 'application/pdf'
        assert b'/AcroForm' not in r.data

    def test_con_encabezado_tiene_campos_editables(self, client, admin_user, org):
        prv, orden = self._orden(org, admin_user)
        do_login(client, admin_user.username)
        campos = campos_por_defecto()
        for c in campos:
            if c['clave'] == 'departamento':
                c['valor'] = 'Martínez — Compras'
            if c['clave'] == 'fecha_entrega':
                c['activo'] = False
        _guardar(client, prv.id, campos)
        r = client.get(f'/orden/{orden.id}/pdf')
        assert r.status_code == 200
        assert b'/AcroForm' in r.data
        assert b'enc_no_cuenta' in r.data and b'enc_firma' in r.data
        assert b'enc_fecha_entrega' not in r.data

    def test_encabezado_inactivo_no_se_usa_pero_vista_previa_si(self, client, admin_user, org):
        prv, orden = self._orden(org, admin_user)
        do_login(client, admin_user.username)
        data = _form_de(campos_por_defecto())  # sin enc_activo
        client.post(f'/proveedor/{prv.id}/encabezado-oc', data=data,
                    content_type='multipart/form-data')
        assert EncabezadoOCProveedor.query.one().activo is False
        assert b'/AcroForm' not in client.get(f'/orden/{orden.id}/pdf').data
        r = client.get(f'/proveedor/{prv.id}/encabezado-oc/vista-previa')
        assert r.status_code == 200 and b'/AcroForm' in r.data
