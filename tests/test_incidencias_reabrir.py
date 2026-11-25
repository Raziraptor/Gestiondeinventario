import pytest

from app.extensions import db
from app.models import Incidencia, Notificacion, Pendiente
from app.services.incidencias import registrar_avance
from tests.fixtures_incidencias import crear_incidencia, entrar, mundo  # noqa: F401


def _resuelta(m, pendientes=None):
    inc = crear_incidencia(m.org, m.creador, pendientes=pendientes or [('A1', m.depto_a), ('B1', m.depto_b)])
    for p in inc.pendientes:
        registrar_avance(p, m.admin.id, 'ok', 100)
    db.session.commit()
    assert inc.estado == 'Resuelto' and inc.expira_en is not None
    return inc


def _flashes(client):
    with client.session_transaction() as s:
        return s.get('_flashes', [])


def test_reabrir_pendientes_elegidos(client, mundo):
    m = mundo
    inc = _resuelta(m)
    a1 = inc.pendientes[0]
    entrar(client, m.creador)
    r = client.post(f'/incidencias/{inc.id}/reabrir', data={'reabrir_pendiente[]': [a1.id]})
    assert r.status_code == 302
    db.session.expire_all()
    assert a1.progreso == 0 and inc.estado == 'En proceso'
    assert inc.fecha_cierre is None and inc.expira_en is None


def test_reabrir_con_pendiente_nuevo_notifica(client, mundo):
    m = mundo
    inc = _resuelta(m, pendientes=[('Solo', None)])
    entrar(client, m.creador)
    r = client.post(f'/incidencias/{inc.id}/reabrir', data={
        'nuevo_pendiente_descripcion': 'Repintar', 'nuevo_pendiente_departamento': m.depto_b.id})
    assert r.status_code == 302
    db.session.expire_all()
    assert Pendiente.query.filter_by(incidencia_id=inc.id, descripcion='Repintar').count() == 1
    assert Notificacion.query.filter_by(user_id=m.enc_b.id, titulo=f'Nuevo pendiente asignado — {inc.folio}').count() == 1


def test_permisos_de_reabrir(client, mundo):
    m = mundo
    inc = _resuelta(m)
    entrar(client, m.aux_a)
    assert client.post(f'/incidencias/{inc.id}/reabrir', data={'reabrir_pendiente[]': [inc.pendientes[0].id]}).status_code == 403
    client.post('/logout')
    entrar(client, m.ajeno)
    assert client.post(f'/incidencias/{inc.id}/reabrir', data={}).status_code == 404
    db.session.expire_all()
    assert inc.estado == 'Resuelto'


def test_reabrir_sin_nada_elegido(client, mundo):
    m = mundo
    inc = _resuelta(m)
    entrar(client, m.creador)
    client.post(f'/incidencias/{inc.id}/reabrir', data={})
    assert any(cat == 'danger' for cat, _ in _flashes(client))
    db.session.expire_all()
    assert inc.estado == 'Resuelto'


def test_estado_manual(client, mundo):
    m = mundo
    inc = crear_incidencia(m.org, m.creador)
    entrar(client, m.admin)
    client.post(f'/incidencias/{inc.id}/estado', data={'nuevo_estado': 'Cerrado sin resolver'})
    db.session.expire_all()
    assert inc.estado == 'Cerrado sin resolver' and inc.expira_en is not None
    otra = crear_incidencia(m.org, m.creador)
    client.post(f'/incidencias/{otra.id}/estado', data={'nuevo_estado': 'Resuelto'})
    db.session.expire_all()
    assert otra.estado == 'Abierto'
    assert any(cat == 'danger' for cat, _ in _flashes(client))
    client.post('/logout')
    entrar(client, m.creador)
    assert client.post(f'/incidencias/{otra.id}/estado', data={'nuevo_estado': 'Escalado'}).status_code == 403


def test_campos_de_cierre_se_guardan_sin_cambiar_estado(client, mundo):
    m = mundo
    inc = crear_incidencia(m.org, m.creador)
    entrar(client, m.creador)
    r = client.post(f'/incidencias/{inc.id}/editar', data={
        'titulo': 'T', 'fecha': '2026-11-24', 'hora': '10:00', 'ubicacion': 'U', 'tipo': 'Infraestructura',
        'prioridad': 'Media', 'severidad': 'Menor', 'descripcion': 'D', 'causa_raiz': 'Tubo viejo',
        'comentarios_cierre': 'Listo', 'firma_reporto': 'Ana', 'firma_responsable': 'Beto', 'firma_vobo': 'Cleo',
        'pendiente_uid[]': [f'p{inc.pendientes[0].id}'], 'pendiente_descripcion[]': ['Pendiente 1'],
        'pendiente_departamento[]': [''],
    })
    assert r.status_code == 302
    db.session.expire_all()
    assert (inc.causa_raiz, inc.comentarios_cierre) == ('Tubo viejo', 'Listo')
    assert (inc.firma_reporto, inc.firma_responsable, inc.firma_vobo) == ('Ana', 'Beto', 'Cleo')
    assert inc.estado == 'Abierto'


def test_modal_de_reabrir_va_despues_de_main(client, mundo):
    m = mundo
    inc = _resuelta(m)
    entrar(client, m.creador)
    html = client.get(f'/incidencias/{inc.id}').get_data(as_text=True)
    assert 'id="modalReabrir"' in html
    assert html.index('id="modalReabrir"') > html.index('</main>')
