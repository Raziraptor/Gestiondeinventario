"""Centralized notification services: push notifications and stock alerts."""

import os
import json
import re
from threading import Thread

import requests

from app.extensions import db
from app.models import (Organizacion, Almacen, Stock, PushSubscription, User, Notificacion,
                        Departamento, DepartamentoMiembro)
from app.helpers import now_mx


# ---------------------------------------------------------------------------
# PUSH NOTIFICATIONS
# ---------------------------------------------------------------------------

def _webpush_http_status(ex):
    """Extrae el HTTP status de un WebPushException (ex.response puede ser None)."""
    if ex.response is not None:
        return ex.response.status_code
    m = re.search(r'(\d{3})', str(ex))
    return int(m.group(1)) if m else None


# Códigos HTTP del push service que indican suscripción inválida/caducada → borrar
_PUSH_STALE_CODES = {400, 403, 404, 410}


def enviar_push(org_id, titulo, cuerpo, url='/dashboard', user_ids=None):
    """Envía Web Push a todos los suscriptores activos de la organización.

    Con user_ids solo a las suscripciones de esos usuarios; sin él, a toda la org como siempre.

    No lanza excepciones — fallo silencioso por diseño (las notificaciones
    nunca deben interrumpir el flujo principal).
    """
    from flask import current_app

    vapid_private = os.environ.get('VAPID_PRIVATE_KEY')
    vapid_email   = os.environ.get('VAPID_CLAIMS_EMAIL', 'notifications@inventario.app')
    if not vapid_private:
        current_app.logger.debug('[Push] VAPID_PRIVATE_KEY no configurada — push omitido')
        return
    try:
        from pywebpush import webpush, WebPushException
        q = PushSubscription.query.filter_by(organizacion_id=org_id)
        if user_ids is not None:
            q = q.filter(PushSubscription.user_id.in_(list(user_ids) or [-1]))
        subs = q.all()
        if not subs:
            return
        payload = json.dumps({'title': titulo, 'body': cuerpo, 'url': url,
                              'icon': '/static/icons/icon-192.png'})
        to_delete = []
        for sub in subs:
            try:
                webpush(
                    subscription_info=json.loads(sub.subscription_json),
                    data=payload,
                    vapid_private_key=vapid_private,
                    vapid_claims={"sub": f"mailto:{vapid_email}"},
                    timeout=10,  # un push service colgado no debe dejar el hilo vivo para siempre
                )
            except WebPushException as ex:
                code = _webpush_http_status(ex)
                current_app.logger.warning(
                    f'[Push] WebPushException HTTP {code} sub_id={sub.id}: {ex}'
                )
                if code in _PUSH_STALE_CODES:
                    to_delete.append(sub)
        for sub in to_delete:
            db.session.delete(sub)
        if to_delete:
            db.session.commit()
    except ImportError:
        current_app.logger.error('[Push] pywebpush no instalado')
    except Exception as e:
        current_app.logger.error(f'[Push] Error inesperado: {e}')


# ---------------------------------------------------------------------------
# NOTIFICACIONES IN-APP (campana) + push dirigido
# ---------------------------------------------------------------------------

def admins_de_org(org_id):
    """Ids de usuarios con rol 'admin' activos de la org (super_admin sin org queda fuera)."""
    return [u.id for u in User.query.filter_by(organizacion_id=org_id, rol='admin', is_active=True)]


def _enviar_push_aparte(org_id, titulo, cuerpo, url, user_ids):
    """Push sin hacer esperar al usuario: en un hilo con su propio contexto de app.

    shortcut: hilo por llamada, sin cola; sirve para unos cuantos avisos por minuto.
    Con mucho más volumen conviene un worker. Los tests lo apagan (PUSH_EN_SEGUNDO_PLANO=False).
    """
    from flask import current_app
    if not current_app.config.get('PUSH_EN_SEGUNDO_PLANO', True):
        enviar_push(org_id, titulo, cuerpo, url, user_ids=user_ids)
        return
    app = current_app._get_current_object()

    def _tarea():
        with app.app_context():
            enviar_push(org_id, titulo, cuerpo, url, user_ids=user_ids)
    Thread(target=_tarea, daemon=True).start()


def notificar(org_id, user_ids, titulo, cuerpo, url=None, actor_id=None):
    """Crea una Notificacion por destinatario y luego intenta push a esos mismos usuarios.

    Llamar DESPUÉS del commit de la operación de negocio: hace su propio commit.
    Excluye al actor, deduplica e ignora ids que no son de la org. Nunca lanza:
    devuelve cuántas notificaciones creó (0 si algo falló).
    """
    from flask import current_app
    try:
        ids = {int(u) for u in user_ids if u} - {actor_id}
        if not ids:
            return 0
        validos = [u.id for u in User.query.filter(
            User.id.in_(ids), User.organizacion_id == org_id, User.is_active.is_(True))]
        for uid in validos:
            db.session.add(Notificacion(organizacion_id=org_id, user_id=uid,
                                        titulo=titulo[:150], cuerpo=cuerpo[:500], url=url))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'[Notificar] Error al guardar notificaciones: {e}')
        return 0
    _enviar_push_aparte(org_id, titulo, cuerpo, url or '/notificaciones', validos)
    return len(validos)


def _miembros(departamento_id, rol=None):
    q = DepartamentoMiembro.query.filter_by(departamento_id=departamento_id)
    if rol:
        q = q.filter_by(rol=rol)
    return [m.user_id for m in q]


def notificar_asignacion(inc, pendientes, actor_id):
    """Evento (a): pendientes asignados a un departamento -> encargado + auxiliares de ese departamento."""
    por_depto = {}
    for p in pendientes:
        if p.departamento_id:
            por_depto.setdefault(p.departamento_id, []).append(p)
    for depto_id, lista in por_depto.items():
        depto = db.session.get(Departamento, depto_id)
        notificar(inc.organizacion_id, _miembros(depto_id),
                  f'Nuevo pendiente asignado — {inc.folio}',
                  f'{len(lista)} pendiente(s) para {depto.nombre}: {inc.titulo}',
                  f'/incidencias/{inc.id}', actor_id=actor_id)


def notificar_eventos(inc, eventos, actor_id):
    """Eventos (b)(c)(d) devueltos por app.services.incidencias.registrar_avance."""
    base = [inc.creador_id] + admins_de_org(inc.organizacion_id)
    url = f'/incidencias/{inc.id}'
    for tipo, depto_id in eventos:
        if tipo == 'iniciada':
            extra = _miembros(depto_id, 'encargado') if depto_id else []
            notificar(inc.organizacion_id, base + extra, f'Incidencia en proceso — {inc.folio}',
                      f'Se registró el primer avance: {inc.titulo}', url, actor_id=actor_id)
        elif tipo == 'departamento_completado':
            depto = db.session.get(Departamento, depto_id)
            notificar(inc.organizacion_id, base + _miembros(depto_id, 'encargado'),
                      f'{depto.nombre} completó su parte — {inc.folio}',
                      f'{depto.nombre} terminó todos sus pendientes: {inc.titulo}', url, actor_id=actor_id)
        elif tipo == 'completada':
            encargados = []
            for d in {p.departamento_id for p in inc.pendientes if p.departamento_id}:
                encargados += _miembros(d, 'encargado')
            notificar(inc.organizacion_id, base + encargados, f'Incidencia completada — {inc.folio}',
                      f'Todos los pendientes llegaron a 100%: {inc.titulo}', url, actor_id=actor_id)


# ---------------------------------------------------------------------------
# STOCK ALERTS
# ---------------------------------------------------------------------------

def _send_whatsapp_message(to_number, body):
    """Envía un mensaje de texto vía Meta WhatsApp Cloud API."""
    token    = os.environ.get('WHATSAPP_TOKEN')
    phone_id = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
    if not token or not phone_id:
        return False
    numero = to_number.replace('+', '').replace(' ', '').replace('-', '')
    url     = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": body, "preview_url": False}
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"[WhatsApp] Error al enviar: {e}")
        return False


def check_and_alert_stock(org_id, almacen_id):
    """Verifica stock bajo en el almacén y envía alertas (WhatsApp + Push).

    No lanza excepciones — fallo silencioso por diseño.
    """
    try:
        org     = Organizacion.query.get(org_id)
        almacen = Almacen.query.get(almacen_id)
        if not org or not almacen or not org.whatsapp_notify:
            return

        items_bajo = Stock.query.filter(
            Stock.almacen_id == almacen_id,
            Stock.stock_minimo != None,
            Stock.stock_minimo > 0,
            Stock.cantidad < Stock.stock_minimo
        ).all()

        if not items_bajo:
            return

        # Mensaje WhatsApp — máximo 10 productos listados
        lineas = [f"⚠️ *ALERTA DE STOCK BAJO*\n",
                  f"🏢 *{org.nombre}*",
                  f"🏪 Almacén: {almacen.nombre}\n"]

        for item in items_bajo[:10]:
            lineas.append(
                f"• *{item.producto.nombre}*  "
                f"Stock: {item.cantidad} / Mín: {item.stock_minimo}"
            )

        if len(items_bajo) > 10:
            lineas.append(f"\n...y {len(items_bajo) - 10} productos más.")

        lineas.append(f"\n_{now_mx().strftime('%d/%m/%Y %H:%M')}_")
        _send_whatsapp_message(org.whatsapp_notify, "\n".join(lineas))

        # Push notification — independiente del WhatsApp
        nombres = [i.producto.nombre for i in items_bajo[:3]]
        extra   = f' y {len(items_bajo) - 3} más' if len(items_bajo) > 3 else ''
        enviar_push(
            org_id=org_id,
            titulo=f'⚠️ Stock bajo — {almacen.nombre}',
            cuerpo=', '.join(nombres) + extra,
            url='/dashboard'
        )

    except Exception as e:
        print(f"[WhatsApp] Error en check_and_alert_stock: {e}")
