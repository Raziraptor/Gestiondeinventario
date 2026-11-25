import pytest

from app.extensions import db
from app.models import Incidencia, IncidenciaAvance, Notificacion
from tests.fixtures_incidencias import crear_incidencia, entrar, mundo  # noqa: F401


@pytest.fixture
def esc(mundo):
    m = mundo
    inc = crear_incidencia(m.org, m.creador, pendientes=[('A1', m.depto_a), ('B1', m.depto_b)])
    a1, b1 = inc.pendientes
    return m, inc, a1, b1


def _avance(client, inc, pendiente, quien, **extra):
    client.post('/logout')
    entrar(client, quien)
    datos = {'texto_avance': 'ok', 'porcentaje': '60'}
    if pendiente is not None:
        datos['pendiente_id'] = str(pendiente.id)
    datos.update(extra)
    return client.post(f'/incidencias/{inc.id}/avance', data=datos, content_type='multipart/form-data')


def _titulos(user):
    return {n.titulo for n in Notificacion.query.filter_by(user_id=user.id)}


def test_primer_avance_calcula_y_notifica(client, esc):
    m, inc, a1, b1 = esc
    r = _avance(client, inc, a1, m.enc_a)
    assert r.status_code == 302
    av = IncidenciaAvance.query.one()
    db.session.expire_all()
    assert av.pendiente_id == a1.id and a1.progreso == 60
    assert inc.progreso == 30 and inc.estado == 'En proceso'
    titulo = f'Incidencia en proceso — {inc.folio}'
    assert titulo in _titulos(m.creador) and titulo in _titulos(m.admin)
    assert titulo not in _titulos(m.enc_a)


def test_permisos_y_validaciones(client, esc):
    m, inc, a1, b1 = esc
    assert _avance(client, inc, a1, m.enc_b).status_code == 403
    assert _avance(client, inc, a1, m.ajeno).status_code == 404
    assert IncidenciaAvance.query.count() == 0
    otra = crear_incidencia(m.org, m.creador, pendientes=[('Z', m.depto_a)])
    assert _avance(client, inc, otra.pendientes[0], m.admin).status_code == 404
    r = _avance(client, inc, None, m.admin)
    assert r.status_code == 302 and IncidenciaAvance.query.count() == 0
    with client.session_transaction() as s:
        assert any(cat == 'danger' for cat, _ in s.get('_flashes', []))
    r = _avance(client, otra, None, m.enc_a)
    assert r.status_code == 302 and IncidenciaAvance.query.count() == 1


def test_departamento_completa_y_cierra(client, esc):
    m, inc, a1, b1 = esc
    _avance(client, inc, a1, m.aux_a, porcentaje='100')
    assert f'Mantenimiento completó su parte — {inc.folio}' in _titulos(m.admin)
    _avance(client, inc, b1, m.enc_b, porcentaje='100')
    db.session.expire_all()
    assert inc.estado == 'Resuelto'
    titulo = f'Incidencia completada — {inc.folio}'
    for u in (m.enc_a, m.creador, m.admin):
        assert titulo in _titulos(u)
    antes = IncidenciaAvance.query.count()
    _avance(client, inc, a1, m.aux_a)
    assert IncidenciaAvance.query.count() == antes
    with client.session_transaction() as s:
        assert any(cat == 'warning' for cat, _ in s.get('_flashes', []))


def test_asignar_departamento(client, esc):
    m, inc, a1, b1 = esc
    entrar(client, m.creador)
    r = client.post(f'/incidencias/{inc.id}/pendientes/{b1.id}/departamento', data={'departamento_id': m.depto_a.id})
    assert r.status_code == 302
    db.session.expire_all()
    assert b1.departamento_id == m.depto_a.id
    assert f'Nuevo pendiente asignado — {inc.folio}' in _titulos(m.aux_a)
    client.post(f'/incidencias/{inc.id}/pendientes/{b1.id}/departamento', data={'departamento_id': m.depto_beta.id})
    db.session.expire_all()
    assert b1.departamento_id == m.depto_a.id
    client.post('/logout')
    entrar(client, m.aux_a)
    r = client.post(f'/incidencias/{inc.id}/pendientes/{b1.id}/departamento', data={'departamento_id': ''})
    assert r.status_code == 403
