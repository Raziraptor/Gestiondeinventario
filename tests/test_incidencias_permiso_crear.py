from app.extensions import db
from app.models import Incidencia, User
from tests.fixtures_incidencias import entrar, mundo  # noqa: F401


def test_sin_permiso_no_puede_crear(client, mundo):
    entrar(client, mundo.ajeno)
    r = client.get('/incidencias/nueva')
    assert r.status_code == 302 and r.headers['Location'] in ('/', 'http://localhost/')
    r = client.post('/incidencias/nueva', data={
        'titulo': 'Fuga', 'fecha': '2026-11-24', 'hora': '10:00', 'ubicacion': 'Patio',
        'reportado_por': 'Pedro', 'tipo': 'Infraestructura', 'prioridad': 'Media',
        'severidad': 'Menor', 'descripcion': 'Algo se rompio',
    })
    assert r.status_code == 302
    assert Incidencia.query.count() == 0


def test_con_permiso_o_admin_puede_abrir_el_formulario(client, mundo):
    for usuario in (mundo.creador, mundo.admin):
        client.post('/logout')
        entrar(client, usuario)
        assert client.get('/incidencias/nueva').status_code == 200, usuario.username


def test_admin_asigna_permiso_por_api(client, mundo):
    entrar(client, mundo.admin)
    r = client.post(f'/api/permisos/{mundo.ajeno.id}',
                    json={'perm': 'perm_crear_incidencias', 'value': True})
    assert r.status_code == 200 and r.get_json()['ok'] is True
    assert db.session.get(User, mundo.ajeno.id).perm_crear_incidencias is True


def test_admin_asigna_permiso_por_formulario(client, mundo):
    entrar(client, mundo.admin)
    r = client.post(f'/admin_panel/update/{mundo.ajeno.id}', data={'perm_crear_incidencias': 'y'})
    assert r.status_code in (200, 302)
    assert db.session.get(User, mundo.ajeno.id).perm_crear_incidencias is True


def test_paneles_muestran_nombre_y_toggle(client, mundo):
    entrar(client, mundo.admin)
    html = client.get('/admin_panel').get_data(as_text=True)
    assert 'data-perm="perm_crear_incidencias"' in html
    assert 'Elena Encargada' in html
    assert 'Elena Encargada' in client.get('/usuarios').get_data(as_text=True)
