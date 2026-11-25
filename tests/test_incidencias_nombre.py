from app.extensions import db
from app.models import User
from tests.fixtures_incidencias import crear_usuario, entrar, mundo  # noqa: F401


def _activar(app):
    app.config['REQUIRE_NOMBRE_COMPLETO'] = True


def test_sin_nombre_redirige_al_formulario(app, client, mundo):
    _activar(app)
    entrar(client, mundo.sin_nombre)
    r = client.get('/incidencias/')
    assert r.status_code == 302
    assert '/perfil/nombre?next=' in r.headers['Location']


def test_rutas_exentas_no_redirigen(app, client, mundo):
    _activar(app)
    entrar(client, mundo.sin_nombre)
    for metodo, ruta, esperado in (('get', '/health', 200), ('get', '/sw.js', 200),
                                   ('get', '/offline', 200), ('get', '/perfil/nombre', 200)):
        r = getattr(client, metodo)(ruta)
        assert r.status_code == esperado, ruta
        assert '/perfil/nombre' not in r.headers.get('Location', ''), ruta
    r = client.post('/logout')
    assert r.status_code == 302 and '/login' in r.headers['Location']
    assert '/perfil/nombre' not in r.headers['Location']


def test_guardar_nombre_normaliza_y_redirige(app, client, mundo):
    _activar(app)
    entrar(client, mundo.sin_nombre)
    r = client.post('/perfil/nombre?next=/incidencias/', data={'nombre_completo': '  Ana   López  '})
    assert r.status_code == 302 and r.headers['Location'].endswith('/incidencias/')
    assert db.session.get(User, mundo.sin_nombre.id).nombre_completo == 'Ana López'


def test_nombre_demasiado_corto_o_largo(app, client, mundo):
    _activar(app)
    entrar(client, mundo.sin_nombre)
    for valor in ('Al', 'x' * 121):
        r = client.post('/perfil/nombre', data={'nombre_completo': valor})
        assert r.status_code == 200
        assert not (db.session.get(User, mundo.sin_nombre.id).nombre_completo or '').strip()


def test_next_externo_se_ignora(app, client, mundo):
    _activar(app)
    entrar(client, mundo.sin_nombre)
    for destino in ('//evil.example', 'https://evil.example'):
        r = client.post(f'/perfil/nombre?next={destino}', data={'nombre_completo': 'Ana López'})
        assert r.status_code == 302
        assert r.headers['Location'] in ('/', 'http://localhost/')


def test_con_nombre_pasa(app, client, mundo):
    _activar(app)
    entrar(client, mundo.enc_a)
    assert client.get('/incidencias/').status_code == 200


def test_super_admin_sin_org_y_sin_nombre(app, client, mundo):
    _activar(app)
    sa = crear_usuario('sa_sin_nombre', None, rol='super_admin', nombre=None)
    entrar(client, sa)
    r = client.get('/incidencias/')
    assert r.status_code == 302 and '/perfil/nombre' in r.headers['Location']


def test_flag_apagado_no_redirige(app, client, mundo):
    entrar(client, mundo.sin_nombre)
    assert client.get('/incidencias/').status_code == 200
