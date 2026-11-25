import pywebpush

from app.extensions import db
from app.models import Notificacion, PushSubscription
from app.services.incidencias import registrar_avance
from app.services.notifications import (
    admins_de_org, enviar_push, notificar, notificar_asignacion, notificar_eventos,
)
from tests.fixtures_incidencias import crear_incidencia, crear_usuario, entrar, mundo  # noqa: F401


def _para(user):
    return {(n.titulo) for n in Notificacion.query.filter_by(user_id=user.id)}


def test_notificar_excluye_actor_deduplica_y_filtra_org(mundo):
    n = notificar(mundo.org.id, [mundo.enc_a.id, mundo.enc_a.id, mundo.admin.id, mundo.user_beta.id],
                  'T', 'C', '/x', actor_id=mundo.admin.id)
    assert n == 1
    assert [x.user_id for x in Notificacion.query.all()] == [mundo.enc_a.id]


def test_admins_de_org(mundo, super_admin):
    inactivo = crear_usuario('inc_admin_off', mundo.org, rol='admin', is_active=False)
    assert admins_de_org(mundo.org.id) == [mundo.admin.id]
    assert inactivo.id not in admins_de_org(mundo.org.id)


def test_push_dirigido_y_compatible(mundo, monkeypatch):
    enviados = []
    monkeypatch.setenv('VAPID_PRIVATE_KEY', 'x')
    monkeypatch.setattr(pywebpush, 'webpush', lambda subscription_info, **kw: enviados.append(subscription_info['endpoint']))
    for u in (mundo.enc_a, mundo.enc_b):
        db.session.add(PushSubscription(user_id=u.id, organizacion_id=mundo.org.id,
                                        endpoint=f'https://push/{u.id}',
                                        subscription_json=f'{{"endpoint": "https://push/{u.id}"}}'))
    db.session.commit()
    enviar_push(mundo.org.id, 't', 'c', '/', user_ids=[mundo.enc_a.id])
    assert enviados == [f'https://push/{mundo.enc_a.id}']
    enviar_push(mundo.org.id, 't', 'c', '/')
    assert len(enviados) == 3


def test_falla_push_no_rompe(mundo, monkeypatch):
    monkeypatch.setenv('VAPID_PRIVATE_KEY', 'x')

    def explota(**kw):
        raise RuntimeError('push caido')
    monkeypatch.setattr(pywebpush, 'webpush', explota)
    db.session.add(PushSubscription(user_id=mundo.enc_a.id, organizacion_id=mundo.org.id,
                                    endpoint='https://push/e', subscription_json='{"endpoint": "https://push/e"}'))
    db.session.commit()
    assert notificar(mundo.org.id, [mundo.enc_a.id], 'T', 'C') == 1


def test_destinatarios_por_evento(mundo):
    m = mundo
    inc = crear_incidencia(m.org, m.creador, pendientes=[('A1', m.depto_a), ('B1', m.depto_b)])
    a1, b1 = inc.pendientes
    notificar_asignacion(inc, inc.pendientes, actor_id=m.creador.id)
    assert 'Nuevo pendiente asignado — ' + inc.folio in _para(m.aux_a)
    assert _para(m.creador) == set() and _para(m.ajeno) == set()
    _, ev = registrar_avance(a1, m.enc_a.id, 'ok', 100)
    db.session.commit()
    notificar_eventos(inc, ev, actor_id=m.enc_a.id)
    assert f'Incidencia en proceso — {inc.folio}' in _para(m.creador)
    assert f'Mantenimiento completó su parte — {inc.folio}' in _para(m.admin)
    assert f'Incidencia en proceso — {inc.folio}' not in _para(m.enc_a)  # actor excluido
    _, ev = registrar_avance(b1, m.aux_a.id, 'ok', 100)
    db.session.commit()
    notificar_eventos(inc, ev, actor_id=m.aux_a.id)
    for u in (m.creador, m.admin, m.enc_a, m.enc_b):
        assert f'Incidencia completada — {inc.folio}' in _para(u)
    assert f'Incidencia completada — {inc.folio}' not in _para(m.ajeno)


def _notif(user, url=None, titulo='T'):
    n = Notificacion(organizacion_id=user.organizacion_id, user_id=user.id, titulo=titulo, cuerpo='C', url=url)
    db.session.add(n)
    db.session.commit()
    return n


def test_campana_y_pagina(client, mundo):
    _notif(mundo.enc_a)
    _notif(mundo.enc_a)
    entrar(client, mundo.enc_a)
    r = client.get('/notificaciones')
    assert r.status_code == 200
    assert 'aria-label="Notificaciones (2 sin leer)"' in r.get_data(as_text=True)


def test_leer_notificacion_ajena_404_y_redireccion_segura(client, mundo):
    ajena = _notif(mundo.enc_b)
    propia = _notif(mundo.enc_a, url='/incidencias/')
    externa = _notif(mundo.enc_a, url='//evil.example')
    entrar(client, mundo.enc_a)
    assert client.post(f'/notificaciones/{ajena.id}/leer').status_code == 404
    r = client.post(f'/notificaciones/{propia.id}/leer')
    assert r.status_code == 302 and r.headers['Location'].endswith('/incidencias/')
    assert db.session.get(Notificacion, propia.id).leida is True
    r = client.post(f'/notificaciones/{externa.id}/leer')
    assert r.status_code == 302 and r.headers['Location'].endswith('/notificaciones')


def test_leer_todas(client, mundo):
    _notif(mundo.enc_a)
    _notif(mundo.enc_a)
    entrar(client, mundo.enc_a)
    client.post('/notificaciones/leer-todas')
    assert Notificacion.query.filter_by(user_id=mundo.enc_a.id, leida=False).count() == 0


def test_push_en_segundo_plano_no_frena_la_peticion(app, mundo, monkeypatch):
    import threading
    from app.services import notifications
    app.config['PUSH_EN_SEGUNDO_PLANO'] = True
    liberar, llamado = threading.Event(), threading.Event()
    hilos = []

    class HiloRegistrado(threading.Thread):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            hilos.append(self)

    def push_lento(*a, **kw):
        llamado.set()
        liberar.wait(5)

    monkeypatch.setattr(notifications, 'Thread', HiloRegistrado)
    monkeypatch.setattr(notifications, 'enviar_push', push_lento)
    assert notificar(mundo.org.id, [mundo.enc_a.id], 'T', 'C') == 1  # vuelve sin esperar al push
    assert Notificacion.query.filter_by(user_id=mundo.enc_a.id).count() == 1
    assert llamado.wait(2) and hilos[0].is_alive()
    liberar.set()
    hilos[0].join(2)
