import io
import os

from app.extensions import db
from app.models import Incidencia, Notificacion, Pendiente, PendienteFoto
from tests.fixtures_incidencias import (
    crear_incidencia, entrar, mundo, png_bytes, uploads_tmp,  # noqa: F401
)

BASE = {
    'titulo': 'Fuga en baños', 'fecha': '2026-11-24', 'hora': '10:00', 'ubicacion': 'Planta baja',
    'tipo': 'Infraestructura', 'prioridad': 'Media', 'severidad': 'Menor', 'descripcion': 'Se rompió un tubo',
}


def _post(client, url, **extra):
    datos = dict(BASE)
    datos.update(extra)
    return client.post(url, data=datos, content_type='multipart/form-data')


def _flashes(client):
    with client.session_transaction() as s:
        return s.get('_flashes', [])


def _png(color):
    return (png_bytes(color), f'{color[0]}.png')


def test_alta_con_dos_pendientes_fotos_y_avisos(client, mundo, uploads_tmp):
    m = mundo
    entrar(client, m.creador)
    r = _post(client, '/incidencias/nueva', **{
        'pendiente_uid[]': ['n1', 'n2'],
        'pendiente_descripcion[]': ['Cerrar fuga', 'Revisar cableado'],
        'pendiente_departamento[]': [str(m.depto_a.id), ''],
        'foto_n1[]': [_png((10, 10, 10)), _png((20, 20, 20)), (io.BytesIO(b'no soy imagen'), 'c.jpg')],
        'foto_desc_n1[]': ['Fuga', 'Piso', 'x'],
    })
    assert r.status_code == 302
    inc = Incidencia.query.one()
    assert [p.descripcion for p in inc.pendientes] == ['Cerrar fuga', 'Revisar cableado']
    assert [(f.descripcion) for f in PendienteFoto.query.order_by(PendienteFoto.id)] == ['Fuga', 'Piso']
    assert len(os.listdir(uploads_tmp / 'incidencias' / str(m.org.id))) == 2
    assert any(cat == 'warning' and 'no se guardaron' in msg for cat, msg in _flashes(client))
    titulo = f'Nuevo pendiente asignado — {inc.folio}'
    for u in (m.enc_a, m.aux_a):
        assert Notificacion.query.filter_by(user_id=u.id, titulo=titulo).count() == 1
    assert Notificacion.query.filter_by(user_id=m.creador.id).count() == 0


def test_siete_fotos_en_un_pendiente(client, mundo, uploads_tmp):
    entrar(client, mundo.creador)
    fotos = [_png((i * 30, 5, 5)) for i in range(7)]
    r = _post(client, '/incidencias/nueva', **{
        'pendiente_uid[]': ['n1'], 'pendiente_descripcion[]': ['Muchas fotos'],
        'pendiente_departamento[]': [''],
        'foto_n1[]': fotos, 'foto_desc_n1[]': [f'f{i}' for i in range(7)],
    })
    assert r.status_code == 302
    assert PendienteFoto.query.count() == 7


def test_sin_pendientes_o_departamento_ajeno_no_crea(client, mundo, uploads_tmp):
    entrar(client, mundo.creador)
    r = _post(client, '/incidencias/nueva', **{
        'pendiente_uid[]': ['n1'], 'pendiente_descripcion[]': [''], 'pendiente_departamento[]': ['']})
    assert r.status_code == 200
    assert 'Agrega al menos un pendiente con descripción.' in r.get_data(as_text=True)
    assert Incidencia.query.count() == 0
    r = _post(client, '/incidencias/nueva', **{
        'pendiente_uid[]': ['n1'], 'pendiente_descripcion[]': ['X'],
        'pendiente_departamento[]': [str(mundo.depto_beta.id)]})
    assert r.status_code == 200
    assert 'Departamento no válido.' in r.get_data(as_text=True)
    assert Incidencia.query.count() == 0


def test_asignado_user_id_del_formulario_se_ignora(client, mundo, uploads_tmp):
    entrar(client, mundo.creador)
    r = _post(client, '/incidencias/nueva', **{
        'pendiente_uid[]': ['n1'], 'pendiente_descripcion[]': ['X'], 'pendiente_departamento[]': [''],
        'asignado_user_id': str(mundo.user_beta.id), 'tipo_asignacion': 'usuario'})
    assert r.status_code == 302
    assert Incidencia.query.one().asignado_user_id is None


def test_formulario_html(client, mundo):
    entrar(client, mundo.creador)
    html = client.get('/incidencias/nueva').get_data(as_text=True)
    for literal in ('name="pendiente_descripcion[]"', 'name="pendiente_departamento[]"',
                    'aria-label="Descripción de la foto"', '<label for="pdesc-n1">', 'id="pdesc-n1"',
                    '<label for="pdep-n1">', 'id="pdep-n1"', 'tpl-pendiente'):
        assert literal in html, literal


def test_plantilla_sin_asignacion_legada(app):
    ruta = os.path.join(app.root_path, '..', 'templates', 'incidencias', 'form.html')
    with open(ruta, encoding='utf-8') as f:
        html = f.read()
    assert 'asig_usuario' not in html and 'toggleAsignacion' not in html
    assert 'tpl-pendiente' in html


def test_error_en_alta_devuelve_formulario(client, mundo, uploads_tmp, monkeypatch):
    import app.blueprints.incidents.routes as routes_module
    monkeypatch.setattr(routes_module, '_generar_folio',
                        lambda org_id: (_ for _ in ()).throw(RuntimeError('x')))
    entrar(client, mundo.creador)
    r = _post(client, '/incidencias/nueva', **{
        'pendiente_uid[]': ['n1'], 'pendiente_descripcion[]': ['X'], 'pendiente_departamento[]': ['']})
    assert r.status_code == 200
    assert 'tpl-pendiente' in r.get_data(as_text=True)


def test_edicion_agrega_cambia_y_quita(client, mundo, uploads_tmp):
    m = mundo
    inc = crear_incidencia(m.org, m.creador, pendientes=[('Uno', None), ('Dos', None), ('Tres', None)])
    uno, dos, tres = inc.pendientes
    entrar(client, m.creador)
    r = _post(client, f'/incidencias/{inc.id}/editar', **{
        'pendiente_uid[]': [f'p{uno.id}', f'p{tres.id}', 'n2'],
        'pendiente_descripcion[]': ['Uno editado', 'Tres', 'Nuevo'],
        'pendiente_departamento[]': ['', '', str(m.depto_b.id)],
        'pendiente_eliminar[]': [f'p{dos.id}'],
    })
    assert r.status_code == 302
    db.session.expire_all()
    assert [p.descripcion for p in Incidencia.query.one().pendientes] == ['Uno editado', 'Tres', 'Nuevo']
    assert Pendiente.query.filter_by(id=dos.id).count() == 0


def test_no_se_quita_pendiente_con_avance(client, mundo, uploads_tmp):
    from app.services.incidencias import registrar_avance
    m = mundo
    inc = crear_incidencia(m.org, m.creador, pendientes=[('Uno', None), ('Dos', None)])
    uno, dos = inc.pendientes
    registrar_avance(dos, m.admin.id, 'algo', 10)
    db.session.commit()
    entrar(client, m.creador)
    _post(client, f'/incidencias/{inc.id}/editar', **{
        'pendiente_uid[]': [f'p{uno.id}'], 'pendiente_descripcion[]': ['Uno'],
        'pendiente_departamento[]': [''], 'pendiente_eliminar[]': [f'p{dos.id}'],
    })
    assert Pendiente.query.filter_by(id=dos.id).count() == 1


def test_editar_no_deja_la_incidencia_sin_pendientes(client, mundo, uploads_tmp):
    inc = crear_incidencia(mundo.org, mundo.creador, pendientes=[('Unico', None)])
    p = inc.pendientes[0]
    entrar(client, mundo.creador)
    r = _post(client, f'/incidencias/{inc.id}/editar', **{'pendiente_eliminar[]': [f'p{p.id}']})
    assert r.status_code == 302
    assert any('al menos un pendiente' in msg for _, msg in _flashes(client))
    assert Pendiente.query.filter_by(id=p.id).count() == 1


def test_editar_puede_cambiar_un_pendiente_por_otro_nuevo(client, mundo, uploads_tmp):
    inc = crear_incidencia(mundo.org, mundo.creador, pendientes=[('Viejo', None)])
    p = inc.pendientes[0]
    entrar(client, mundo.creador)
    _post(client, f'/incidencias/{inc.id}/editar', **{
        'pendiente_eliminar[]': [f'p{p.id}'], 'pendiente_uid[]': ['n1'],
        'pendiente_descripcion[]': ['Nuevo'], 'pendiente_departamento[]': ['']})
    db.session.expire_all()
    assert [x.descripcion for x in Incidencia.query.one().pendientes] == ['Nuevo']


def test_subida_grande_con_varias_fotos(app, client, mundo, uploads_tmp):
    from PIL import Image
    assert app.config['MAX_CONTENT_LENGTH'] >= 64 * 1024 * 1024

    def grande(i):  # PNG de ruido: ~6 MB cada una, 3 juntas pasan de los 16 MB de antes
        buf = io.BytesIO()
        Image.frombytes('RGB', (1500, 1400), os.urandom(1500 * 1400 * 3)).save(buf, format='PNG', compress_level=0)
        buf.seek(0)
        return (buf, f'g{i}.png')

    entrar(client, mundo.creador)
    r = _post(client, '/incidencias/nueva', **{
        'pendiente_uid[]': ['n1'], 'pendiente_descripcion[]': ['Fotos grandes'], 'pendiente_departamento[]': [''],
        'foto_n1[]': [grande(i) for i in range(3)], 'foto_desc_n1[]': ['a', 'b', 'c']})
    assert r.status_code == 302
    assert PendienteFoto.query.count() == 3
