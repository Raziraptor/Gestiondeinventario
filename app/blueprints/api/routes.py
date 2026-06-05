"""
API Blueprint — rutas JSON del ERP de inventario.

Incluye:
  - Alertas y búsqueda de stock
  - Ajuste rápido de inventario
  - Integración Home Depot Pro (auto-upload + status polling)
  - Finanzas mensuales
  - AI (imagen de producto + mejora de descripción con Gemini)
  - Productos con stock por almacén
  - Charts (movimientos, estado de stock, top productos, actividad reciente)
  - Web Push (VAPID key, subscribe, unsubscribe, test)
  - OCR de recibos
"""

import os
import re
import json
import logging
from datetime import datetime
from threading import Thread

import requests
from sqlalchemy import extract
from flask import request, jsonify, url_for, current_app
from flask_login import login_required, current_user

from . import api_bp
from app.extensions import db
from app.helpers import (
    now_mx,
    check_org_permission,
    check_permission,
    get_item_or_404,
)
from app.models import (
    Organizacion,
    Producto,
    Almacen,
    Stock,
    Movimiento,
    AuditLog,
    PushSubscription,
    OrdenCompra,
    OrdenCompraDetalle,
    ProveedorIntegracion,
    Gasto,
    Servicio,
    PagoServicio,
)


# ==============================================================================
# HELPERS LOCALES (copiados de app.py — referencias a app.* corregidas)
# ==============================================================================

def log_actividad(accion, entidad, descripcion, entidad_id=None):
    """Añade una entrada al audit log. Debe llamarse ANTES del db.session.commit()."""
    try:
        org_id = current_user.organizacion_id if current_user.is_authenticated else None
        if not org_id:
            return
        entrada = AuditLog(
            usuario_id=current_user.id if current_user.is_authenticated else None,
            organizacion_id=org_id,
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
            descripcion=descripcion,
        )
        db.session.add(entrada)
    except Exception:
        pass  # El logging nunca debe romper el flujo principal


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


def _webpush_http_status(ex):
    """Extrae el HTTP status de un WebPushException (ex.response puede ser None en pywebpush)."""
    if ex.response is not None:
        return ex.response.status_code
    m = re.search(r'(\d{3})', str(ex))
    return int(m.group(1)) if m else None


# Códigos HTTP del push service que indican suscripción inválida/caducada → borrar
_PUSH_STALE_CODES = {400, 403, 404, 410}


def enviar_push_notificacion(org_id, titulo, cuerpo, url='/dashboard'):
    """Envía una Web Push Notification a todos los suscriptores activos de la organización."""
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
                current_app.logger.warning(f'[Push] WebPushException HTTP {code} sub_id={sub.id}: {ex}')
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


def check_and_alert_stock_bajo(org_id, almacen_id):
    """
    Verifica si hay productos bajo mínimo en el almacén dado y,
    si la organización tiene número de WhatsApp configurado, envía una alerta.
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

        # Push notification (independiente del WhatsApp)
        nombres = [i.producto.nombre for i in items_bajo[:3]]
        extra = f' y {len(items_bajo)-3} más' if len(items_bajo) > 3 else ''
        enviar_push_notificacion(
            org_id=org_id,
            titulo=f'⚠️ Stock bajo — {almacen.nombre}',
            cuerpo=', '.join(nombres) + extra,
            url='/dashboard'
        )

    except Exception as e:
        print(f"[WhatsApp] Error en check_and_alert_stock_bajo: {e}")


# ==============================================================================
# STOCK — ALERTAS Y BÚSQUEDA
# ==============================================================================

@api_bp.route('/api/alertas/stock-bajo')
@login_required
@check_org_permission
def api_alertas_stock_bajo():
    org_id = current_user.organizacion_id
    items = db.session.query(Stock).join(
        Almacen, Stock.almacen_id == Almacen.id
    ).join(Producto, Stock.producto_id == Producto.id).filter(
        Almacen.organizacion_id == org_id,
        Stock.stock_minimo > 0,
        Stock.cantidad < Stock.stock_minimo
    ).order_by(Stock.cantidad.asc()).limit(10).all()

    return jsonify({
        'count': len(items),
        'items': [{
            'nombre':     item.producto.nombre,
            'sku':        item.producto.codigo,
            'cantidad':   item.cantidad,
            'minimo':     item.stock_minimo,
            'almacen':    item.almacen.nombre,
            'producto_id': item.producto_id,
        } for item in items]
    })


@api_bp.route('/api/productos/buscar')
@login_required
@check_org_permission
def api_buscar_productos():
    """
    API para buscar productos por Nombre o SKU dinámicamente.
    Retorna JSON para ser consumido por JavaScript.
    """
    query = request.args.get('q', '').strip()

    if not query:
        return jsonify([])

    # Buscamos coincidencias en Nombre O Código (SKU)
    # Usamos ilike para que no importen mayúsculas/minúsculas
    productos = Producto.query.filter(
        (Producto.nombre.ilike(f'%{query}%')) |
        (Producto.codigo.ilike(f'%{query}%'))
    ).filter_by(organizacion_id=current_user.organizacion_id).limit(10).all()

    resultados = []
    for p in productos:
        resultados.append({
            'id': p.id,
            'texto_mostrar': f"{p.nombre} (SKU: {p.codigo})",  # Lo que se ve en la lista
            'nombre': p.nombre,
            'codigo': p.codigo,
            'precio': p.precio_unitario
        })

    return jsonify(resultados)


@api_bp.route('/api/stock/buscar')
@login_required
@check_org_permission
def api_stock_buscar():
    """Busca ítems de stock por nombre o SKU, devuelve contexto de almacén."""
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    org_id = current_user.organizacion_id
    items = (
        db.session.query(Stock, Producto, Almacen)
        .join(Producto, Stock.producto_id == Producto.id)
        .join(Almacen, Stock.almacen_id == Almacen.id)
        .filter(Producto.organizacion_id == org_id)
        .filter(
            (Producto.nombre.ilike(f'%{q}%')) |
            (Producto.codigo.ilike(f'%{q}%'))
        )
        .order_by(Producto.nombre)
        .limit(8)
        .all()
    )
    return jsonify([{
        'stock_id': s.id,
        'nombre':   p.nombre,
        'codigo':   p.codigo,
        'almacen':  a.nombre,
        'cantidad': s.cantidad
    } for s, p, a in items])


# ==============================================================================
# STOCK — AJUSTE RÁPIDO
# ==============================================================================

@api_bp.route('/api/ajuste/rapido', methods=['POST'])
@login_required
@check_org_permission
@check_permission('perm_edit_management')
def api_ajuste_rapido():
    """Aplica un ajuste rápido (+/-) a un ítem de stock via AJAX."""
    data     = request.get_json(silent=True) or {}
    stock_id = data.get('stock_id')
    tipo     = data.get('tipo', 'entrada')
    motivo   = (data.get('motivo') or '').strip()
    try:
        cantidad = int(data.get('cantidad', 0))
    except (ValueError, TypeError):
        return jsonify({'ok': False, 'error': 'Cantidad inválida'}), 400

    if not stock_id:
        return jsonify({'ok': False, 'error': 'stock_id requerido'}), 400
    if cantidad < 1:
        return jsonify({'ok': False, 'error': 'La cantidad debe ser ≥ 1'}), 400
    if not motivo:
        return jsonify({'ok': False, 'error': 'El motivo es obligatorio'}), 400
    if tipo not in ('entrada', 'salida'):
        return jsonify({'ok': False, 'error': 'Tipo inválido'}), 400

    org_id = current_user.organizacion_id
    stock  = Stock.query.get(stock_id)
    if not stock:
        return jsonify({'ok': False, 'error': 'Stock no encontrado'}), 404

    producto = Producto.query.get(stock.producto_id)
    if not producto or producto.organizacion_id != org_id:
        return jsonify({'ok': False, 'error': 'Sin acceso'}), 403

    delta         = cantidad if tipo == 'entrada' else -cantidad
    nueva_cantidad = stock.cantidad + delta
    if nueva_cantidad < 0:
        return jsonify({'ok': False, 'error': f'Stock insuficiente (actual: {stock.cantidad})'}), 400

    stock.cantidad = nueva_cantidad
    tipo_mov = 'ajuste-entrada' if tipo == 'entrada' else 'ajuste-salida'
    signo    = '+' if tipo == 'entrada' else '-'

    db.session.add(Movimiento(
        producto_id=stock.producto_id,
        cantidad=delta,
        tipo=tipo_mov,
        fecha=now_mx(),
        motivo=f'Ajuste Rápido: {motivo}',
        almacen_id=stock.almacen_id,
        organizacion_id=org_id
    ))
    log_actividad('ajuste', 'producto',
                  f'Ajuste rápido {signo}{cantidad} uds — {motivo}',
                  entidad_id=stock.producto_id)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500

    if tipo == 'salida':
        check_and_alert_stock_bajo(org_id, stock.almacen_id)

    return jsonify({
        'ok': True,
        'mensaje': f'Ajuste {signo}{cantidad} uds aplicado. Nuevo stock: {nueva_cantidad}.'
    })


# ==============================================================================
# HOME DEPOT PRO — AUTO UPLOAD Y STATUS
# ==============================================================================

@api_bp.route('/api/ordenes/<int:orden_id>/enviar-hd', methods=['POST'])
@login_required
@check_org_permission
def enviar_oc_homedepot(orden_id):
    """Lanza automatización Playwright para llenar carrito en Home Depot Pro."""
    org_id = current_user.organizacion_id
    orden = OrdenCompra.query.filter_by(id=orden_id, organizacion_id=org_id).first_or_404()

    if current_user.rol not in ('super_admin', 'admin'):
        return jsonify({'error': 'Sin permiso'}), 403

    if orden.integracion_status == 'procesando':
        return jsonify({'error': 'Ya hay un envío en proceso'}), 409

    integracion = ProveedorIntegracion.query.filter_by(
        proveedor_id=orden.proveedor_id,
        organizacion_id=org_id,
        tipo='homedepot',
        activo=True
    ).first()
    if not integracion:
        return jsonify({'error': 'Este proveedor no tiene integración con Home Depot configurada'}), 400

    creds = integracion.credenciales
    if not creds.get('usuario') or not creds.get('password'):
        return jsonify({'error': 'Credenciales de Home Depot incompletas'}), 400

    items = []
    for d in orden.detalles:
        if d.producto:
            items.append({
                'sku': d.producto.hd_sku or '',
                'nombre': d.producto.nombre,
                'cantidad': d.cantidad_solicitada or 1,
            })

    if not items:
        return jsonify({'error': 'La orden no tiene productos con datos válidos'}), 400

    orden.integracion_status = 'procesando'
    orden.integracion_resultado = None
    db.session.commit()

    app_ref = current_app._get_current_object()

    def _worker(app, oc_id, credenciales, items_list):
        with app.app_context():
            from integrations.homedepot import fill_cart
            try:
                resultado = fill_cart(credenciales, items_list)
            except Exception as exc:
                resultado = {'error': str(exc), 'agregados': 0, 'omitidos': items_list}
            oc = OrdenCompra.query.get(oc_id)
            if oc:
                oc.integracion_status = 'error' if resultado.get('error') else 'listo'
                oc.integracion_resultado = json.dumps(resultado, ensure_ascii=False)
                db.session.commit()

    Thread(target=_worker, args=(app_ref, orden_id, creds, items), daemon=True).start()
    return jsonify({'status': 'procesando'}), 202


@api_bp.route('/api/ordenes/<int:orden_id>/integracion-status', methods=['GET'])
@login_required
@check_org_permission
def integracion_status_oc(orden_id):
    """Polling: retorna el estado actual de la integración con Home Depot."""
    org_id = current_user.organizacion_id
    orden = OrdenCompra.query.filter_by(id=orden_id, organizacion_id=org_id).first_or_404()
    resultado = {}
    if orden.integracion_resultado:
        try:
            resultado = json.loads(orden.integracion_resultado)
        except ValueError:
            pass
    return jsonify({
        'status': orden.integracion_status,
        'resultado': resultado,
    })


# ==============================================================================
# FINANZAS — DATOS MENSUALES PARA GRÁFICA
# ==============================================================================

@api_bp.route('/api/finanzas/mensual')
@login_required
@check_org_permission
def api_finanzas_mensual():
    org_id = current_user.organizacion_id
    ahora  = now_mx()
    labels, gastos_data, ocs_data, servicios_data = [], [], [], []

    for i in range(5, -1, -1):
        m = ahora.month - i
        y = ahora.year
        if m <= 0:
            m += 12
            y -= 1

        g = db.session.query(db.func.coalesce(db.func.sum(Gasto.monto), 0.0)).filter(
            Gasto.organizacion_id == org_id,
            db.extract('month', Gasto.fecha) == m,
            db.extract('year',  Gasto.fecha) == y
        ).scalar()

        o = db.session.query(
            db.func.coalesce(db.func.sum(
                OrdenCompraDetalle.cantidad_solicitada * OrdenCompraDetalle.costo_unitario_estimado
            ), 0.0)
        ).join(OrdenCompra).filter(
            OrdenCompra.organizacion_id == org_id,
            OrdenCompra.estado == 'recibida',
            db.extract('month', OrdenCompra.fecha_recepcion) == m,
            db.extract('year',  OrdenCompra.fecha_recepcion) == y
        ).scalar()

        s = db.session.query(db.func.coalesce(db.func.sum(PagoServicio.monto), 0.0)).join(Servicio).filter(
            Servicio.organizacion_id == org_id,
            PagoServicio.estado == 'pagado',
            db.extract('month', PagoServicio.fecha_pago) == m,
            db.extract('year',  PagoServicio.fecha_pago) == y
        ).scalar()

        import calendar
        labels.append(calendar.month_abbr[m] + f' {y}')
        gastos_data.append(round(float(g), 2))
        ocs_data.append(round(float(o), 2))
        servicios_data.append(round(float(s), 2))

    return jsonify({'labels': labels, 'gastos': gastos_data, 'ocs': ocs_data, 'servicios': servicios_data})


# ==============================================================================
# AI — IMAGEN DE PRODUCTO Y MEJORA DE DESCRIPCIÓN
# ==============================================================================

@api_bp.route('/api/ai/generar-imagen-producto')
@login_required
def ai_generar_imagen_producto():
    import uuid as _uuid
    nombre = request.args.get('nombre', '').strip()
    seed   = request.args.get('seed', '42')
    if not nombre:
        return jsonify({'error': 'Proporciona un nombre de producto'}), 400
    prompt = f"{nombre}, product photography, white background, professional studio, clean, high quality"
    poll_url = (
        f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}"
        f"?width=512&height=512&nologo=true&seed={seed}&model=flux"
    )
    try:
        resp = requests.get(poll_url, timeout=50)
        if not resp.ok:
            return jsonify({'error': 'Pollinations no respondió correctamente'}), 502
        filename = f"ai_{_uuid.uuid4().hex[:12]}.jpg"
        with open(os.path.join(current_app.config['UPLOAD_FOLDER'], filename), 'wb') as fh:
            fh.write(resp.content)
        return jsonify({'filename': filename,
                        'url': url_for('static', filename=f'uploads/{filename}')})
    except requests.Timeout:
        return jsonify({'error': 'La IA tardó demasiado, intenta de nuevo.'}), 504
    except Exception as e:
        return jsonify({'error': 'Error al generar imagen'}), 500


@api_bp.route('/api/ai/mejorar-descripcion', methods=['POST'])
@login_required
def ai_mejorar_descripcion():
    from google import genai
    import os as _os

    data = request.get_json()
    producto = data.get('producto', '')

    if not producto:
        return jsonify({'error': 'Producto vacío'}), 400

    API_KEY = _os.environ.get("GEMINI_API_KEY")
    if not API_KEY:
        return jsonify({'error': 'IA no configurada en el servidor (falta GEMINI_API_KEY).'}), 503

    try:
        client = genai.Client(api_key=API_KEY)

        import json as _json
        prompt = f"""Eres un experto en compras corporativas (Procurement Manager) para una empresa en México.
El usuario necesita comprar: "{producto}"

Devuelve ÚNICAMENTE un objeto JSON válido con estos dos campos (sin markdown, sin texto extra):
{{
  "especificaciones": "especificaciones técnicas breves en 3-5 viñetas con guion, listas para pegar en una OC",
  "costo_estimado_mxn": <número entero, precio unitario realista en pesos mexicanos (MXN)>
}}

Reglas:
- especificaciones: máximo 5 líneas, tono técnico, sin saludos ni introducción
- costo_estimado_mxn: precio unitario promedio de mercado en México, solo el número sin símbolo"""

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )

        text = response.text.strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        result = _json.loads(text)
        return jsonify({
            'sugerencia':          result.get('especificaciones', ''),
            'costo_estimado_mxn':  result.get('costo_estimado_mxn', 0),
        })

    except Exception as e:
        logging.error(f"Error AI Gemini: {e}")
        return jsonify({'error': 'No se pudo conectar con la IA en este momento.'}), 500


# ==============================================================================
# ALMACÉN — PRODUCTOS CON STOCK
# ==============================================================================

@api_bp.route('/api/almacen/<int:almacen_id>/productos-con-stock')
@login_required
@check_org_permission
def api_productos_con_stock(almacen_id):
    """Retorna los productos con stock > 0 en un almacén dado (para el select dinámico)."""
    org_id = current_user.organizacion_id
    almacen = Almacen.query.filter_by(id=almacen_id, organizacion_id=org_id).first_or_404()

    items = db.session.query(Stock).filter(
        Stock.almacen_id == almacen.id,
        Stock.cantidad > 0
    ).join(Producto).order_by(Producto.nombre).all()

    return jsonify([{
        'id': s.producto_id,
        'nombre': s.producto.nombre,
        'codigo': s.producto.codigo,
        'cantidad': s.cantidad
    } for s in items])


# ==============================================================================
# CHARTS — DATOS PARA DASHBOARD
# ==============================================================================

@api_bp.route('/api/charts/movimientos-mes')
@login_required
@check_org_permission
def api_chart_movimientos_mes():
    """Retorna entradas y salidas de los últimos 6 meses para la gráfica de barras."""
    org_id = current_user.organizacion_id
    hoy = now_mx()

    labels, entradas, salidas = [], [], []

    for i in range(5, -1, -1):
        mes = (hoy.month - i - 1) % 12 + 1
        ano = hoy.year if (hoy.month - i) > 0 else hoy.year - 1

        total_entrada = db.session.query(db.func.sum(Movimiento.cantidad)).filter(
            Movimiento.organizacion_id == org_id,
            Movimiento.tipo.in_(['entrada', 'entrada-inicial', 'ajuste-entrada']),
            extract('month', Movimiento.fecha) == mes,
            extract('year', Movimiento.fecha) == ano
        ).scalar() or 0

        total_salida = abs(db.session.query(db.func.sum(Movimiento.cantidad)).filter(
            Movimiento.organizacion_id == org_id,
            Movimiento.tipo == 'salida',
            extract('month', Movimiento.fecha) == mes,
            extract('year', Movimiento.fecha) == ano
        ).scalar() or 0)

        nombre_mes = datetime(ano, mes, 1).strftime('%b %Y')
        labels.append(nombre_mes)
        entradas.append(int(total_entrada))
        salidas.append(int(total_salida))

    return jsonify({'labels': labels, 'entradas': entradas, 'salidas': salidas})


@api_bp.route('/api/charts/estado-stock')
@login_required
@check_org_permission
def api_chart_estado_stock():
    """Retorna conteo de productos por estado (bajo/ok/exceso) para la gráfica de dona."""
    org_id = current_user.organizacion_id

    bajo = db.session.query(db.func.count(Stock.id)).join(Almacen).filter(
        Almacen.organizacion_id == org_id,
        Stock.cantidad < Stock.stock_minimo
    ).scalar() or 0

    exceso = db.session.query(db.func.count(Stock.id)).join(Almacen).filter(
        Almacen.organizacion_id == org_id,
        Stock.cantidad > Stock.stock_maximo
    ).scalar() or 0

    ok = db.session.query(db.func.count(Stock.id)).join(Almacen).filter(
        Almacen.organizacion_id == org_id,
        Stock.cantidad >= Stock.stock_minimo,
        Stock.cantidad <= Stock.stock_maximo
    ).scalar() or 0

    return jsonify({'bajo': int(bajo), 'ok': int(ok), 'exceso': int(exceso)})


@api_bp.route('/api/charts/top-productos')
@login_required
@check_org_permission
def api_chart_top_productos():
    """Retorna los 8 productos con más salidas en los últimos 30 días."""
    org_id = current_user.organizacion_id
    desde = now_mx().replace(day=1)

    resultados = db.session.query(
        Producto.nombre,
        db.func.sum(db.func.abs(Movimiento.cantidad)).label('total')
    ).join(Movimiento, Movimiento.producto_id == Producto.id).filter(
        Movimiento.organizacion_id == org_id,
        Movimiento.tipo == 'salida',
        Movimiento.fecha >= desde
    ).group_by(Producto.nombre).order_by(db.desc('total')).limit(8).all()

    return jsonify({
        'labels': [r.nombre[:25] for r in resultados],
        'valores': [int(r.total) for r in resultados]
    })


@api_bp.route('/api/dashboard/actividad-reciente')
@login_required
@check_org_permission
def api_actividad_reciente():
    """Retorna los últimos 10 movimientos de la organización para el feed del dashboard."""
    org_id = current_user.organizacion_id
    movs = (
        Movimiento.query
        .filter_by(organizacion_id=org_id)
        .order_by(Movimiento.fecha.desc())
        .limit(10)
        .all()
    )
    TIPO_META = {
        'entrada':         {'icon': 'bi-box-arrow-in-down', 'color': '#10b981', 'label': 'Entrada'},
        'entrada-inicial': {'icon': 'bi-database-add',      'color': '#3b82f6', 'label': 'Stock Inicial'},
        'salida':          {'icon': 'bi-box-arrow-right',   'color': '#ef4444', 'label': 'Salida'},
        'ajuste-entrada':  {'icon': 'bi-plus-circle',       'color': '#8b5cf6', 'label': 'Ajuste (+)'},
        'ajuste-salida':   {'icon': 'bi-dash-circle',       'color': '#f59e0b', 'label': 'Ajuste (-)'},
        'transferencia-entrada': {'icon': 'bi-arrow-left-right', 'color': '#06b6d4', 'label': 'Transferencia (+)'},
        'transferencia-salida':  {'icon': 'bi-arrow-left-right', 'color': '#64748b', 'label': 'Transferencia (-)'},
    }
    resultado = []
    for m in movs:
        meta = TIPO_META.get(m.tipo, {'icon': 'bi-arrow-repeat', 'color': '#64748b', 'label': m.tipo})
        almacen_nombre = m.almacen.nombre if m.almacen else '—'
        resultado.append({
            'id':       m.id,
            'tipo':     m.tipo,
            'label':    meta['label'],
            'icon':     meta['icon'],
            'color':    meta['color'],
            'cantidad': abs(m.cantidad),
            'signo':    '+' if m.cantidad >= 0 else '−',
            'producto': m.producto.nombre if m.producto else '—',
            'almacen':  almacen_nombre,
            'motivo':   m.motivo or '',
            'fecha':    m.fecha.strftime('%d/%m %H:%M'),
        })
    return jsonify(resultado)


# ==============================================================================
# WEB PUSH NOTIFICATIONS — API
# ==============================================================================

@api_bp.route('/api/push/vapid-key')
@login_required
def api_vapid_key():
    return jsonify({'publicKey': os.environ.get('VAPID_PUBLIC_KEY', '')})


@api_bp.route('/api/push/subscribe', methods=['POST'])
@login_required
def api_push_subscribe():
    data = request.get_json(silent=True)
    if not data or 'endpoint' not in data:
        return jsonify({'error': 'datos inválidos'}), 400
    endpoint = data['endpoint']
    existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if existing:
        existing.subscription_json = json.dumps(data)
        existing.user_id = current_user.id
    else:
        db.session.add(PushSubscription(
            user_id=current_user.id,
            organizacion_id=current_user.organizacion_id,
            endpoint=endpoint,
            subscription_json=json.dumps(data)
        ))
    db.session.commit()
    return jsonify({'ok': True})


@api_bp.route('/api/push/unsubscribe', methods=['POST'])
@login_required
def api_push_unsubscribe():
    data = request.get_json(silent=True)
    if not data or 'endpoint' not in data:
        return jsonify({'error': 'datos inválidos'}), 400
    sub = PushSubscription.query.filter_by(endpoint=data['endpoint'], user_id=current_user.id).first()
    if sub:
        db.session.delete(sub)
        db.session.commit()
    return jsonify({'ok': True})


@api_bp.route('/api/push/test', methods=['POST'])
@login_required
def api_push_test():
    """Envía una notificación de prueba al usuario actual para verificar la configuración."""
    subs = PushSubscription.query.filter_by(user_id=current_user.id).all()
    if not subs:
        return jsonify({'ok': False, 'error': 'Sin suscripción activa — activa las notificaciones primero'}), 400
    vapid_private = os.environ.get('VAPID_PRIVATE_KEY')
    if not vapid_private:
        return jsonify({'ok': False, 'error': 'VAPID_PRIVATE_KEY no configurada en el servidor'}), 503
    try:
        from pywebpush import webpush, WebPushException
        vapid_email = os.environ.get('VAPID_CLAIMS_EMAIL', 'notifications@inventario.app')
        payload = json.dumps({'title': 'Prueba de notificación', 'body': 'Las notificaciones push están funcionando.', 'url': '/dashboard'})
        sent, errors, to_delete = 0, [], []
        for sub in subs:
            try:
                webpush(
                    subscription_info=json.loads(sub.subscription_json),
                    data=payload,
                    vapid_private_key=vapid_private,
                    vapid_claims={"sub": f"mailto:{vapid_email}"}
                )
                sent += 1
            except WebPushException as ex:
                code = _webpush_http_status(ex)
                errors.append(f'HTTP {code}: {ex}')
                if code in _PUSH_STALE_CODES:
                    to_delete.append(sub)
        for sub in to_delete:
            db.session.delete(sub)
        if to_delete:
            db.session.commit()
        if sent > 0:
            return jsonify({'ok': True, 'sent': sent})
        return jsonify({'ok': False, 'error': '; '.join(errors) or 'Sin suscripciones válidas'}), 500
    except ImportError:
        return jsonify({'ok': False, 'error': 'pywebpush no instalado en el servidor'}), 503


# ==============================================================================
# OCR — RECIBOS DE SERVICIOS
# ==============================================================================

@api_bp.route('/api/servicios/ocr-recibo', methods=['POST'])
@login_required
def api_ocr_recibo():
    """Recibe imagen o PDF de un recibo y devuelve monto y fecha extraídos por OCR."""
    if 'archivo' not in request.files:
        return jsonify({'error': 'No se recibió ningún archivo.'}), 400
    archivo = request.files['archivo']
    if not archivo.filename:
        return jsonify({'error': 'Archivo vacío.'}), 400

    ext = archivo.filename.rsplit('.', 1)[-1].lower() if '.' in archivo.filename else ''
    if ext not in ('jpg', 'jpeg', 'png', 'webp', 'pdf'):
        return jsonify({'error': 'Formato no soportado. Usa JPG, PNG o PDF.'}), 400

    try:
        import pytesseract
        from PIL import Image
        import io as _io

        # Rutas explícitas para gunicorn (PATH reducido en systemd)
        pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
        TESSERACT_CONFIG = '--oem 1 --psm 6'  # LSTM engine, bloque uniforme de texto

        contenido = archivo.read()

        if ext == 'pdf':
            try:
                from pdf2image import convert_from_bytes
                # 150 DPI es suficiente para recibos y procesa ~2x más rápido que 200
                paginas = convert_from_bytes(
                    contenido, first_page=1, last_page=1, dpi=150,
                    poppler_path='/usr/bin'
                )
                texto = '\n'.join(
                    pytesseract.image_to_string(p, lang='spa', config=TESSERACT_CONFIG)
                    for p in paginas
                )
            except ImportError:
                return jsonify({'error': 'pdf2image no instalado en el servidor.'}), 503
        else:
            img = Image.open(_io.BytesIO(contenido))
            # Convertir a escala de grises mejora velocidad y precisión
            img = img.convert('L')
            if img.width < 1200:
                factor = 1200 / img.width
                img = img.resize((int(img.width * factor), int(img.height * factor)), Image.LANCZOS)
            texto = pytesseract.image_to_string(img, lang='spa', config=TESSERACT_CONFIG)

        from servicios_ocr import analizar_recibo
        resultado = analizar_recibo(texto)
        return jsonify(resultado)

    except ImportError:
        return jsonify({'error': 'Tesseract / pytesseract no instalado en el servidor.'}), 503
    except Exception as e:
        current_app.logger.error(f'OCR recibo: {e}')
        return jsonify({'error': f'Error al procesar el archivo: {str(e)}'}), 500
