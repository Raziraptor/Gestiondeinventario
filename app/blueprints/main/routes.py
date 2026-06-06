"""Blueprint main — rutas globales: index, dashboard, sw.js, actividad."""

import os
from collections import defaultdict
from datetime import timedelta

from flask import (render_template, request, redirect, url_for,
                   make_response, send_from_directory, jsonify, current_app)
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload, contains_eager

from app.extensions import db
from app.models import (Almacen, Producto, Stock, Movimiento, Categoria,
                        Proveedor, OrdenCompra, OrdenCompraDetalle, User, AuditLog)
from app.helpers import now_mx, check_org_permission, check_permission

from . import main_bp


@main_bp.get('/health')
def health():
    return jsonify({'status': 'ok', 'source': 'Blueprint main'})


@main_bp.route('/sw.js')
def service_worker():
    resp = make_response(send_from_directory(
        os.path.join(current_app.root_path, '..', 'static'), 'sw.js'
    ))
    resp.headers['Content-Type'] = 'application/javascript'
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


@main_bp.route('/offline')
def offline_page():
    return render_template('offline.html')


@main_bp.route('/.well-known/assetlinks.json')
def assetlinks():
    import json as _json
    data = current_app.config.get('ASSETLINKS', [])
    return current_app.response_class(_json.dumps(data, indent=2), mimetype='application/json')


@main_bp.route('/')
@login_required
def index():
    """Dashboard Principal (Multiusuario) con Alertas por Almacén."""
    alertas_agrupadas = {}
    pending_map_tmpl = {}

    if current_user.rol != 'super_admin' and current_user.organizacion_id:
        org_id = current_user.organizacion_id

        alertas_crudas = db.session.query(Stock).join(Almacen).join(Producto).filter(
            Almacen.organizacion_id == org_id,
            Stock.cantidad < Stock.stock_minimo
        ).options(
            contains_eager(Stock.almacen),
            contains_eager(Stock.producto).options(joinedload(Producto.proveedor)),
        ).all()

        ordenes_pendientes = db.session.query(
            OrdenCompraDetalle.producto_id,
            OrdenCompra.id,
            User.username,
            OrdenCompra.estado,
            OrdenCompra.almacen_id
        ).join(OrdenCompra, OrdenCompraDetalle.orden_id == OrdenCompra.id
        ).join(User, OrdenCompra.creador_id == User.id
        ).filter(
            OrdenCompra.estado.in_(['borrador', 'enviada']),
            OrdenCompra.organizacion_id == org_id
        ).all()

        pending_map = {}
        for prod_id, orden_id, username, estado, alm_id in ordenes_pendientes:
            pending_map[(prod_id, alm_id)] = {'orden_id': orden_id, 'username': username, 'estado': estado}

        alertas_agrupadas = defaultdict(list)
        for item_stock in alertas_crudas:
            if item_stock.producto.proveedor:
                key = (item_stock.almacen_id, item_stock.almacen.nombre,
                       item_stock.producto.proveedor_id, item_stock.producto.proveedor.nombre)
            else:
                key = (item_stock.almacen_id, item_stock.almacen.nombre, 0, "Proveedor no asignado")
            alertas_agrupadas[key].append(item_stock)

        pending_map_tmpl = {f"{k[0]}:{k[1]}": v for k, v in pending_map.items()}

    return render_template('index.html', alertas_agrupadas=alertas_agrupadas,
                           pending_map_tmpl=pending_map_tmpl, now=now_mx())


@main_bp.route('/dashboard')
@login_required
@check_org_permission
@check_permission('perm_view_dashboard')
def dashboard():
    """Dashboard de Inventario con KPIs de rotación."""
    if current_user.rol == 'super_admin':
        almacenes = Almacen.query.order_by(Almacen.id).all()
    else:
        almacenes = Almacen.query.filter_by(
            organizacion_id=current_user.organizacion_id).order_by(Almacen.id).all()

    almacen_id_solicitado = request.args.get('almacen_id', type=int)
    almacen_seleccionado = None

    if almacen_id_solicitado:
        if current_user.rol == 'super_admin':
            almacen_seleccionado = Almacen.query.get(almacen_id_solicitado)
        else:
            almacen_seleccionado = Almacen.query.filter_by(
                id=almacen_id_solicitado,
                organizacion_id=current_user.organizacion_id).first()

    if not almacen_seleccionado and almacenes:
        almacen_seleccionado = almacenes[0]

    if almacen_seleccionado:
        items_stock = db.session.query(Stock).filter_by(
            almacen_id=almacen_seleccionado.id).join(Producto).options(
            contains_eager(Stock.producto)
        ).order_by(Producto.nombre).all()
    else:
        items_stock = []

    valor_almacen = sum(
        (item.cantidad or 0) * (item.producto.precio_unitario or 0) for item in items_stock
    )
    items_por_valor = sorted(
        items_stock,
        key=lambda x: (x.cantidad or 0) * (x.producto.precio_unitario or 0),
        reverse=True
    )[:10]

    if current_user.rol == 'super_admin':
        valor_total_org = db.session.query(
            db.func.sum(Stock.cantidad * Producto.precio_unitario)
        ).join(Producto, Stock.producto_id == Producto.id).scalar() or 0
        categorias = Categoria.query.all()
        proveedores = Proveedor.query.all()
    else:
        org_id = current_user.organizacion_id
        valor_total_org = db.session.query(
            db.func.sum(Stock.cantidad * Producto.precio_unitario)
        ).join(Producto, Stock.producto_id == Producto.id
        ).join(Almacen, Stock.almacen_id == Almacen.id
        ).filter(Almacen.organizacion_id == org_id).scalar() or 0
        categorias = Categoria.query.filter_by(organizacion_id=org_id).all()
        proveedores = Proveedor.query.filter_by(organizacion_id=org_id).all()

    kpis_rotacion = {}
    if almacen_seleccionado:
        ahora = now_mx()
        hace_30d = ahora - timedelta(days=30)
        hace_60d = ahora - timedelta(days=60)

        def _sum_salidas(almacen_id, desde, hasta=None):
            q = db.session.query(
                db.func.sum(db.func.abs(Movimiento.cantidad))
            ).filter(Movimiento.almacen_id == almacen_id,
                     Movimiento.tipo == 'salida',
                     Movimiento.fecha >= desde)
            if hasta:
                q = q.filter(Movimiento.fecha < hasta)
            return q.scalar() or 0

        salidas_30d = _sum_salidas(almacen_seleccionado.id, hace_30d)
        salidas_prev_30d = _sum_salidas(almacen_seleccionado.id, hace_60d, hace_30d)

        stock_total_uds = sum(item.cantidad for item in items_stock)
        tasa_diaria = salidas_30d / 30 if salidas_30d > 0 else 0
        dias_stock = round(stock_total_uds / tasa_diaria) if tasa_diaria > 0 else None
        tendencia_pct = (
            round((salidas_30d - salidas_prev_30d) / salidas_prev_30d * 100, 1)
            if salidas_prev_30d > 0 else None
        )

        top_movers_raw = db.session.query(
            Movimiento.producto_id,
            db.func.sum(db.func.abs(Movimiento.cantidad)).label('total_salidas')
        ).filter(Movimiento.almacen_id == almacen_seleccionado.id,
                 Movimiento.tipo == 'salida',
                 Movimiento.fecha >= hace_30d
        ).group_by(Movimiento.producto_id
        ).order_by(db.func.sum(db.func.abs(Movimiento.cantidad)).desc()).limit(5).all()

        prod_map = {item.producto_id: item for item in items_stock}
        top_movers = [
            {'nombre': prod_map[r.producto_id].producto.nombre,
             'codigo': prod_map[r.producto_id].producto.codigo,
             'salidas': int(r.total_salidas),
             'stock': prod_map[r.producto_id].cantidad}
            for r in top_movers_raw if r.producto_id in prod_map
        ]

        kpis_rotacion = {
            'salidas_30d': salidas_30d, 'salidas_prev_30d': salidas_prev_30d,
            'tendencia_pct': tendencia_pct, 'dias_stock': dias_stock,
            'tasa_diaria': round(tasa_diaria, 1), 'top_movers': top_movers,
        }

    return render_template('dashboard.html', items_stock=items_stock,
                           almacenes=almacenes, almacen_seleccionado=almacen_seleccionado,
                           categorias=categorias, proveedores=proveedores,
                           valor_almacen=valor_almacen, valor_total_org=valor_total_org,
                           items_por_valor=items_por_valor, kpis_rotacion=kpis_rotacion)


@main_bp.route('/actividad')
@login_required
@check_org_permission
@check_permission('perm_view_dashboard')
def historial_actividad():
    """Timeline de actividad reciente de la organización."""
    org_id = current_user.organizacion_id
    page = request.args.get('page', 1, type=int)
    accion_filtro = request.args.get('accion', '')

    q = AuditLog.query.filter_by(organizacion_id=org_id)
    if accion_filtro:
        q = q.filter(AuditLog.accion == accion_filtro)
    pagination = q.order_by(AuditLog.fecha.desc()).paginate(page=page, per_page=25, error_out=False)

    acciones = [a[0] for a in db.session.query(AuditLog.accion).filter_by(
        organizacion_id=org_id).distinct().all()]

    return render_template('actividad.html', titulo='Historial de Actividad',
                           pagination=pagination, entradas=pagination.items,
                           acciones=acciones, accion_filtro=accion_filtro)
