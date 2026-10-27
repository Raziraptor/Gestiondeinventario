"""
Tests de compras: acceso a lista de OC, aislamiento cross-org en órdenes,
y validación de que rutas POST requieren autenticación.
"""

import pytest
from app.models.purchasing import OrdenCompra, Proveedor
from app.models.inventory import Almacen
from app.extensions import db as _db
from tests.conftest import do_login


# ── Helpers de fixtures de compras ─────────────────────────────────────────────

def _make_proveedor(nombre, org_id):
    p = Proveedor(nombre=nombre, organizacion_id=org_id)
    _db.session.add(p)
    _db.session.flush()
    return p


def _make_almacen(nombre, org_id):
    a = Almacen(nombre=nombre, organizacion_id=org_id)
    _db.session.add(a)
    _db.session.flush()
    return a


def _make_orden(org_id, prv_id, almacen_id, creador_id, estado='borrador'):
    o = OrdenCompra(
        organizacion_id=org_id,
        proveedor_id=prv_id,
        almacen_id=almacen_id,
        creador_id=creador_id,
        estado=estado,
    )
    _db.session.add(o)
    _db.session.commit()
    return o


# ── Lista de órdenes ───────────────────────────────────────────────────────────

class TestOrdenesListAccess:
    def test_unauthenticated_redirects(self, client):
        r = client.get('/ordenes', follow_redirects=False)
        assert r.status_code in (301, 302)
        assert 'login' in r.headers['Location'].lower()

    def test_admin_with_org_sees_list(self, client, admin_user):
        do_login(client, admin_user.username)
        r = client.get('/ordenes', follow_redirects=True)
        assert r.status_code == 200

    def test_orphan_user_blocked(self, client, orphan_user):
        do_login(client, orphan_user.username)
        r = client.get('/ordenes', follow_redirects=True)
        assert r.status_code == 200
        # check_org_permission redirige al index con warning de organización
        assert b'organiza' in r.data or b'Super Admin' in r.data


# ── Detalle de orden: aislamiento cross-org ────────────────────────────────────

class TestOrdenCrossOrgIsolation:
    def test_own_order_visible(self, client, org, admin_user):
        prv = _make_proveedor('Prov Alfa', org.id)
        alm = _make_almacen('Almacen Alfa', org.id)
        orden = _make_orden(org.id, prv.id, alm.id, admin_user.id)

        do_login(client, admin_user.username)
        r = client.get(f'/orden/{orden.id}', follow_redirects=True)
        assert r.status_code == 200

    def test_other_org_order_returns_404(self, client, org, org_beta,
                                          admin_user, beta_admin):
        prv = _make_proveedor('Prov Alfa X', org.id)
        alm = _make_almacen('Almacen Alfa X', org.id)
        orden = _make_orden(org.id, prv.id, alm.id, admin_user.id)
        orden_id = orden.id

        do_login(client, beta_admin.username)
        r = client.get(f'/orden/{orden_id}', follow_redirects=True)
        assert r.status_code == 404

    def test_super_admin_with_org_can_view_order(self, client, org, admin_user):
        # super_admin con org asignada puede ver órdenes de esa org
        # Nota: ver_orden usa filter_by(organizacion_id=...) hardcodeado, NO get_item_or_404
        # — un super_admin sin org obtiene 404 en esta ruta (bug conocido, CLAUDE.md §Helpers)
        from app.models.auth import User
        sa = User(username='sa_con_org', email='sa@org.com',
                  rol='super_admin', organizacion_id=org.id)
        sa.set_password('Pass1234!')
        _db.session.add(sa)
        _db.session.commit()

        prv = _make_proveedor('Prov SA', org.id)
        alm = _make_almacen('Almacen SA', org.id)
        orden = _make_orden(org.id, prv.id, alm.id, admin_user.id)

        do_login(client, sa.username)
        r = client.get(f'/orden/{orden.id}', follow_redirects=True)
        assert r.status_code == 200


# ── Formulario manual de nueva OC ─────────────────────────────────────────────

class TestNuevaOrdenManual:
    def test_get_form_requires_login(self, client):
        r = client.get('/orden/nueva/manual', follow_redirects=False)
        assert r.status_code in (301, 302)

    def test_get_form_loads_for_admin(self, client, org, admin_user):
        _make_proveedor('Prov Form', org.id)
        _make_almacen('Almacen Form', org.id)

        do_login(client, admin_user.username)
        r = client.get('/orden/nueva/manual', follow_redirects=True)
        assert r.status_code == 200

    def test_regular_user_without_perm_blocked(self, client, regular_user):
        # regular_user tiene perm_view_dashboard=True pero no perm_create_oc_standard
        do_login(client, regular_user.username)
        r = client.get('/orden/nueva/manual', follow_redirects=True)
        assert r.status_code == 200
        # check_permission redirige al index con flash de permiso denegado
        assert b'permiso' in r.data or b'funci' in r.data


# ── OC de Proyecto: cancelación y filtro de proveedor ─────────────────────────

def _make_proyecto_oc(org_id, creador_id, estado='borrador', proveedores=()):
    from app.models.purchasing import ProyectoOC, ProyectoOCDetalle
    poc = ProyectoOC(nombre_proyecto=f'Proy {estado}', estado=estado,
                     creador_id=creador_id, organizacion_id=org_id)
    _db.session.add(poc)
    _db.session.flush()
    for prov in proveedores:
        _db.session.add(ProyectoOCDetalle(proyecto_oc_id=poc.id, descripcion_nuevo='Item',
                                          proveedor_sugerido=prov, cantidad=2,
                                          cantidad_recibida=1 if estado == 'recibida_parcial' else 0,
                                          costo_unitario=10))
    _db.session.commit()
    return poc


class TestCancelarProyectoOC:
    @pytest.mark.parametrize('estado', ['borrador', 'pendiente_aprobacion', 'aprobada',
                                        'enviada', 'recibida_parcial'])
    def test_admin_cancela_en_estados_activos(self, client, org, admin_user, estado):
        poc = _make_proyecto_oc(org.id, admin_user.id, estado, ['Amazon'])
        do_login(client, admin_user.username)
        client.post(f'/proyecto-oc/{poc.id}/cancelar')
        _db.session.refresh(poc)
        assert poc.estado == 'cancelada'

    def test_recibida_no_se_cancela(self, client, org, admin_user):
        poc = _make_proyecto_oc(org.id, admin_user.id, 'recibida', ['Amazon'])
        do_login(client, admin_user.username)
        client.post(f'/proyecto-oc/{poc.id}/cancelar')
        _db.session.refresh(poc)
        assert poc.estado == 'recibida'

    def test_no_admin_no_puede_cancelar(self, client, org, admin_user, regular_user):
        regular_user.perm_create_oc_proyecto = True
        _db.session.commit()
        poc = _make_proyecto_oc(org.id, admin_user.id, 'enviada', ['Amazon'])
        do_login(client, regular_user.username)
        client.post(f'/proyecto-oc/{poc.id}/cancelar')
        _db.session.refresh(poc)
        assert poc.estado == 'enviada'

    def test_cancelar_cierra_solicitud_pendiente(self, client, org, admin_user):
        from app.models.system import SolicitudAprobacion
        poc = _make_proyecto_oc(org.id, admin_user.id, 'pendiente_aprobacion', ['Amazon'])
        s = SolicitudAprobacion(entidad_tipo='proyecto_oc', entidad_id=poc.id,
                                estado='pendiente', organizacion_id=org.id,
                                solicitante_id=admin_user.id)
        _db.session.add(s)
        _db.session.commit()
        do_login(client, admin_user.username)
        client.post(f'/proyecto-oc/{poc.id}/cancelar')
        _db.session.refresh(s)
        assert s.estado == 'rechazado'

    def test_otra_org_no_puede_cancelar(self, client, org, admin_user, beta_admin):
        poc = _make_proyecto_oc(org.id, admin_user.id, 'enviada', ['Amazon'])
        do_login(client, beta_admin.username)
        r = client.post(f'/proyecto-oc/{poc.id}/cancelar')
        assert r.status_code == 404
        _db.session.refresh(poc)
        assert poc.estado == 'enviada'


class TestFiltroProveedorProyectoOC:
    def test_filtra_sin_distinguir_mayusculas(self, client, org, admin_user):
        _make_proyecto_oc(org.id, admin_user.id, 'borrador', ['Home Depot', 'Amazon'])
        _make_proyecto_oc(org.id, admin_user.id, 'enviada', ['Amazon'])
        do_login(client, admin_user.username)
        r = client.get('/proyectos-oc?proveedor=home%20depot')
        html = r.data.decode('utf-8')
        assert 'Proy borrador' in html
        assert 'Proy enviada' not in html

    def test_opciones_agrupadas_y_sin_otra_org(self, client, org, org_beta, admin_user, beta_admin):
        _make_proyecto_oc(org.id, admin_user.id, 'borrador', ['Home Depot', ' home depot '])
        _make_proyecto_oc(org_beta.id, beta_admin.id, 'borrador', ['ProvSecretoBeta'])
        do_login(client, admin_user.username)
        html = client.get('/proyectos-oc').data.decode('utf-8')
        assert html.lower().count('<option value="home depot"') == 1
        assert 'ProvSecretoBeta' not in html

    def test_filtros_sin_boton_aplicar(self, client, org, admin_user):
        do_login(client, admin_user.username)
        for url in ('/proyectos-oc', '/ordenes'):
            html = client.get(url).data.decode('utf-8')
            assert 'data-autofilter' in html
            assert 'Aplicar' not in html
