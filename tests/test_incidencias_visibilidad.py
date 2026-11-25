import pytest

from app.extensions import db
from tests.fixtures_incidencias import crear_incidencia, entrar, mundo  # noqa: F401


@pytest.fixture
def escenario(mundo):
    m = mundo
    inc1 = crear_incidencia(m.org, m.creador, pendientes=[('A1', m.depto_a), ('B1', m.depto_b)])
    inc2 = crear_incidencia(m.org, m.admin, pendientes=[('B2', m.depto_b)])
    legado = crear_incidencia(m.org, m.admin, pendientes=[('L1', None)])
    return m, inc1, inc2, legado


def _folios_en_lista(client):
    html = client.get('/incidencias/').get_data(as_text=True)
    return {f for f in ('INC-T-0001', 'INC-T-0002', 'INC-T-0003') if f in html}


@pytest.mark.parametrize('quien, esperados', [
    ('admin', {'INC-T-0001', 'INC-T-0002', 'INC-T-0003'}),
    ('creador', {'INC-T-0001'}),
    ('aux_a', {'INC-T-0001'}),
    ('enc_b', {'INC-T-0001', 'INC-T-0002'}),
    ('ajeno', set()),
    ('admin_beta', set()),
])
def test_matriz_de_lista(client, escenario, quien, esperados):
    m = escenario[0]
    entrar(client, getattr(m, quien))
    assert _folios_en_lista(client) == esperados


def test_miembro_ve_solo_sus_pendientes(client, escenario):
    m, inc1, _, _ = escenario
    entrar(client, m.aux_a)
    r = client.get(f'/incidencias/{inc1.id}')
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'A1' in html and 'B1' not in html
    assert 'Avance de tu parte' in html


def test_sin_acceso_es_404(client, escenario):
    m, inc1, _, legado = escenario
    for quien in (m.ajeno, m.admin_beta):
        client.post('/logout')
        entrar(client, quien)
        for ruta in ('', '/editar', '/pdf'):
            assert client.get(f'/incidencias/{inc1.id}{ruta}').status_code == 404, (quien.username, ruta)
    for quien in (m.aux_a, m.creador):
        client.post('/logout')
        entrar(client, quien)
        assert client.get(f'/incidencias/{legado.id}').status_code == 404, quien.username


def test_miembro_no_puede_editar(client, escenario):
    m, inc1, _, _ = escenario
    entrar(client, m.aux_a)
    assert client.get(f'/incidencias/{inc1.id}/editar').status_code == 403


def test_progreso_relativo_en_la_lista(client, escenario):
    m, inc1, _, _ = escenario
    a1, b1 = inc1.pendientes
    a1.progreso, b1.progreso, inc1.progreso = 100, 0, 50
    db.session.commit()
    entrar(client, m.aux_a)
    assert 'aria-valuenow="100"' in client.get('/incidencias/').get_data(as_text=True)
    client.post('/logout')
    entrar(client, m.admin)
    html = client.get('/incidencias/').get_data(as_text=True)
    assert 'aria-valuenow="50"' in html
