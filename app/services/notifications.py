"""Centralized notification services: push notifications and stock alerts."""

import os
import json
import re

import requests

from app.extensions import db
from app.models import Organizacion, Almacen, Stock, PushSubscription
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


def enviar_push(org_id, titulo, cuerpo, url='/dashboard'):
    """Envía Web Push a todos los suscriptores activos de la organización.

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
        subs = PushSubscription.query.filter_by(organizacion_id=org_id).all()
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
                    vapid_claims={"sub": f"mailto:{vapid_email}"}
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
