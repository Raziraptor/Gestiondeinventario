"""
Finance Blueprint — rutas del módulo financiero del ERP.

Incluye:
  - Dashboard financiero (KPIs, variación mes, aging, transacciones)
  - Gastos: lista, nuevo, editar, exportar Excel (multi-mes con gráficos)
  - Centros de Costo: lista, nuevo, editar, cerrar, detalle
  - Presupuestos: lista, nuevo, editar, eliminar
  - Facturas de proveedores (Cuentas por Pagar): lista, nueva, editar, marcar pagada, eliminar
  - Servicios: lista, nuevo, editar, eliminar, detalle
  - Pagos de servicio: nuevo, marcar pagado, eliminar
  - OCR de recibo (api)
"""

import os
import io
import secrets
import calendar
from datetime import datetime, timedelta, date
from decimal import Decimal

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table as ExcelTable, TableStyleInfo
from openpyxl.chart import BarChart, Reference
from openpyxl.drawing.image import Image as XlImage

from sqlalchemy import extract
from flask import (
    render_template, request, redirect, url_for,
    flash, jsonify, make_response, current_app,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from . import finance_bp
from app.extensions import db
from app.helpers import (
    now_mx,
    _flash_err,
    check_org_permission,
    admin_required,
    check_permission,
    get_item_or_404,
    CATEGORIAS_GASTO,
    MESES_ES,
)
from app.models import (
    Gasto,
    Servicio,
    PagoServicio,
    FacturaProveedor,
    CentroCosto,
    Presupuesto,
    Proveedor,
    OrdenCompra,
    OrdenCompraDetalle,
    Almacen,
    Organizacion,
    User,
    AuditLog,
)


# ==============================================================================
# HELPERS LOCALES
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


def _semaforo(pct):
    """Devuelve (clase_bootstrap, etiqueta) según porcentaje gastado."""
    if pct >= 90:
        return 'danger', 'Crítico'
    if pct >= 70:
        return 'warning', 'Alerta'
    return 'success', 'OK'


def _real_por_categoria(org_id, categoria, anio, mes):
    """Suma de gastos reales de una categoría en un período dado."""
    q = Gasto.query.filter_by(organizacion_id=org_id, categoria=categoria)
    q = q.filter(extract('year', Gasto.fecha) == anio)
    if mes:
        q = q.filter(extract('month', Gasto.fecha) == mes)
    return sum(g.monto for g in q.all())


# Constantes de servicios (locales al blueprint — no expuestas en helpers globales)
TIPOS_SERVICIO = {
    'luz':      ('bi-lightning-charge-fill', '#f59e0b', 'Electricidad / Luz'),
    'agua':     ('bi-droplet-fill',          '#3b82f6', 'Agua'),
    'gas':      ('bi-fire',                  '#ef4444', 'Gas'),
    'internet': ('bi-wifi',                  '#8b5cf6', 'Internet'),
    'telefono': ('bi-telephone-fill',        '#10b981', 'Teléfono'),
    'renta':    ('bi-building',              '#64748b', 'Renta'),
    'otro':     ('bi-receipt',               '#94a3b8', 'Otro'),
}

_TIPO_A_CATEGORIA_GASTO = {
    'luz':       'Energía Eléctrica',
    'agua':      'Agua y Drenaje',
    'gas':       'Gas',
    'internet':  'Internet',
    'telefono':  'Telefonía',
    'renta':     'Renta',
    'limpieza':  'Limpieza',
    'otro':      'Servicios',
}


def _registrar_gasto_servicio(pago):
    """Crea un Gasto automáticamente al marcar un PagoServicio como pagado."""
    s = pago.servicio
    if not s:
        return
    categoria = _TIPO_A_CATEGORIA_GASTO.get(s.tipo or 'otro', 'Servicios')
    from datetime import datetime as _dt
    fecha_dt = _dt.combine(pago.fecha_pago, _dt.min.time())
    gasto = Gasto(
        descripcion=f"Servicio: {s.nombre}",
        monto=pago.monto,
        categoria=categoria,
        fecha=fecha_dt,
        organizacion_id=s.organizacion_id,
    )
    db.session.add(gasto)


def _actualizar_estados_pagos(org_id):
    """Marca como 'vencido' los pagos pendientes con fecha_vencimiento ya pasada."""
    hoy = now_mx().date()
    serv_ids = db.session.query(Servicio.id).filter_by(organizacion_id=org_id).subquery()
    PagoServicio.query.filter(
        PagoServicio.servicio_id.in_(serv_ids),
        PagoServicio.estado == 'pendiente',
        PagoServicio.fecha_vencimiento < hoy
    ).update({'estado': 'vencido'}, synchronize_session=False)
    db.session.commit()


def _enviar_push_notificacion(org_id, titulo, cuerpo, url='/dashboard'):
    """Delega al helper global del app sin importar el módulo circular."""
    try:
        from app import enviar_push_notificacion  # importado aquí para evitar circular
        enviar_push_notificacion(org_id=org_id, titulo=titulo, cuerpo=cuerpo, url=url)
    except Exception:
        pass


# ==============================================================================
# DASHBOARD FINANCIERO
# ==============================================================================

@finance_bp.route('/finanzas')
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def finanzas_dashboard():
    org_id = current_user.organizacion_id
    ahora  = now_mx()
    mes_actual = ahora.month
    ano_actual = ahora.year

    # Mes anterior
    mes_ant = mes_actual - 1 if mes_actual > 1 else 12
    ano_ant = ano_actual if mes_actual > 1 else ano_actual - 1

    def _sum_gastos(mes, ano):
        val = db.session.query(db.func.sum(Gasto.monto)).filter(
            Gasto.organizacion_id == org_id,
            db.extract('month', Gasto.fecha) == mes,
            db.extract('year',  Gasto.fecha) == ano
        ).scalar()
        return val or Decimal(0)

    def _sum_ocs(mes, ano):
        val = db.session.query(
            db.func.sum(
                OrdenCompraDetalle.cantidad_solicitada * OrdenCompraDetalle.costo_unitario_estimado
            )
        ).join(OrdenCompra).filter(
            OrdenCompra.organizacion_id == org_id,
            OrdenCompra.estado == 'recibida',
            db.extract('month', OrdenCompra.fecha_recepcion) == mes,
            db.extract('year',  OrdenCompra.fecha_recepcion) == ano
        ).scalar()
        return val or Decimal(0)

    def _sum_servicios(mes, ano):
        val = db.session.query(db.func.sum(PagoServicio.monto)).join(Servicio).filter(
            Servicio.organizacion_id == org_id,
            PagoServicio.estado == 'pagado',
            db.extract('month', PagoServicio.fecha_pago) == mes,
            db.extract('year',  PagoServicio.fecha_pago) == ano
        ).scalar()
        return val or Decimal(0)

    # KPIs mes actual
    gastos_mes    = _sum_gastos(mes_actual, ano_actual)
    ocs_mes       = _sum_ocs(mes_actual, ano_actual)
    servicios_mes = _sum_servicios(mes_actual, ano_actual)
    total_mes     = gastos_mes + ocs_mes + servicios_mes

    # KPI mes anterior (para variación %)
    total_mes_ant = (
        _sum_gastos(mes_ant, ano_ant)
        + _sum_ocs(mes_ant, ano_ant)
        + _sum_servicios(mes_ant, ano_ant)
    )
    variacion = ((total_mes - total_mes_ant) / total_mes_ant * 100) if total_mes_ant > 0 else None

    # OCs comprometidas (estado=enviada, aún no recibidas)
    ocs_en_transito = db.session.query(
        db.func.coalesce(db.func.sum(
            OrdenCompraDetalle.cantidad_solicitada * OrdenCompraDetalle.costo_unitario_estimado
        ), 0.0)
    ).join(OrdenCompra).filter(
        OrdenCompra.organizacion_id == org_id,
        OrdenCompra.estado == 'enviada'
    ).scalar()

    # Servicios por vencer próximos 15 días
    limite_aviso = ahora.date() + timedelta(days=15)
    servicios_por_vencer = (
        PagoServicio.query.join(Servicio)
        .filter(Servicio.organizacion_id == org_id,
                PagoServicio.estado == 'pendiente',
                PagoServicio.fecha_vencimiento <= limite_aviso)
        .order_by(PagoServicio.fecha_vencimiento)
        .all()
    )
    monto_por_vencer = sum(p.monto for p in servicios_por_vencer)

    # Gastos por categoría (mes actual)
    gastos_por_cat = db.session.query(
        db.func.coalesce(Gasto.categoria, 'Sin categoría'),
        db.func.sum(Gasto.monto)
    ).filter(
        Gasto.organizacion_id == org_id,
        db.extract('month', Gasto.fecha) == mes_actual,
        db.extract('year',  Gasto.fecha) == ano_actual
    ).group_by(Gasto.categoria).all()

    # Últimas transacciones unificadas
    ultimos_gastos = (
        Gasto.query
        .filter_by(organizacion_id=org_id)
        .order_by(Gasto.fecha.desc()).limit(8).all()
    )
    ultimas_ocs = (
        OrdenCompra.query
        .filter_by(organizacion_id=org_id, estado='recibida')
        .order_by(OrdenCompra.fecha_recepcion.desc()).limit(8).all()
    )
    ultimos_pagos = (
        PagoServicio.query.join(Servicio)
        .filter(Servicio.organizacion_id == org_id,
                PagoServicio.estado == 'pagado')
        .order_by(PagoServicio.fecha_pago.desc()).limit(8).all()
    )

    # Mezcla y ordena por fecha descendente
    transacciones = []
    for g in ultimos_gastos:
        transacciones.append({
            'fecha': g.fecha.date() if hasattr(g.fecha, 'date') else g.fecha,
            'tipo': 'Gasto',
            'descripcion': g.descripcion,
            'categoria': g.categoria or 'Sin categoría',
            'monto': g.monto,
            'badge_class': 'badge-borrador',
            'icon': 'bi-cash-coin',
        })
    for oc in ultimas_ocs:
        transacciones.append({
            'fecha': oc.fecha_recepcion.date() if oc.fecha_recepcion and hasattr(oc.fecha_recepcion, 'date') else oc.fecha_recepcion,
            'tipo': 'Compra',
            'descripcion': f'OC #{oc.id} — {oc.proveedor.nombre}',
            'categoria': 'Inventario',
            'monto': oc.costo_total,
            'badge_class': 'badge-recibida',
            'icon': 'bi-cart-check-fill',
        })
    for p in ultimos_pagos:
        transacciones.append({
            'fecha': p.fecha_pago,
            'tipo': 'Servicio',
            'descripcion': p.servicio.nombre,
            'categoria': p.servicio.tipo.capitalize() if p.servicio.tipo else 'Servicio',
            'monto': p.monto,
            'badge_class': 'badge-enviada',
            'icon': 'bi-lightning-charge-fill',
        })
    transacciones.sort(key=lambda x: x['fecha'] if x['fecha'] else date.min, reverse=True)
    transacciones = transacciones[:15]

    return render_template('finanzas_dashboard.html',
        titulo='Dashboard Financiero',
        total_mes=total_mes,
        gastos_mes=gastos_mes,
        ocs_mes=ocs_mes,
        servicios_mes=servicios_mes,
        ocs_en_transito=ocs_en_transito,
        monto_por_vencer=monto_por_vencer,
        variacion=variacion,
        total_mes_ant=total_mes_ant,
        servicios_por_vencer=servicios_por_vencer,
        gastos_por_cat=gastos_por_cat,
        transacciones=transacciones,
        ahora=ahora,
        mes_actual=mes_actual,
        ano_actual=ano_actual,
        now=ahora,
    )


# ==============================================================================
# GASTOS
# ==============================================================================

@finance_bp.route('/gastos')
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def lista_gastos():
    mes = request.args.get('mes', type=int)
    ano = request.args.get('ano', type=int)
    ahora = now_mx()
    if not mes:
        mes = ahora.month
    if not ano:
        ano = ahora.year
    meses_lista = [
        (1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'), (4, 'Abril'),
        (5, 'Mayo'), (6, 'Junio'), (7, 'Julio'), (8, 'Agosto'),
        (9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre')
    ]

    if current_user.rol == 'super_admin':
        query_gastos = Gasto.query
    else:
        query_gastos = Gasto.query.filter_by(organizacion_id=current_user.organizacion_id)

    query_gastos = query_gastos.filter(
        extract('month', Gasto.fecha) == mes,
        extract('year', Gasto.fecha) == ano
    ).order_by(Gasto.fecha.desc())

    if current_user.rol == 'super_admin':
        total_gastos = db.session.query(db.func.sum(Gasto.monto)).filter(
            extract('month', Gasto.fecha) == mes,
            extract('year', Gasto.fecha) == ano
        ).scalar() or 0
    else:
        total_gastos = db.session.query(db.func.sum(Gasto.monto)).filter(
            Gasto.organizacion_id == current_user.organizacion_id,
            extract('month', Gasto.fecha) == mes,
            extract('year', Gasto.fecha) == ano
        ).scalar() or 0

    page = request.args.get('page', 1, type=int)
    pagination = query_gastos.paginate(page=page, per_page=15, error_out=False)

    return render_template('gastos.html',
                           gastos=pagination.items,
                           pagination=pagination,
                           total_gastos=total_gastos,
                           mes_seleccionado=mes,
                           ano_seleccionado=ano,
                           meses_lista=meses_lista)


@finance_bp.route('/gasto/nuevo', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def nuevo_gasto():
    org_id = current_user.organizacion_id
    ordenes = OrdenCompra.query.filter_by(organizacion_id=org_id).order_by(OrdenCompra.fecha_creacion.desc()).all()
    centros = CentroCosto.query.filter_by(organizacion_id=org_id).order_by(CentroCosto.nombre).all()

    if request.method == 'POST':
        try:
            monto_val = float(request.form['monto'])
            if monto_val <= 0:
                flash('El monto debe ser mayor a cero.', 'danger')
                return redirect(url_for('finance.nuevo_gasto'))
            categoria_val = request.form['categoria']
            if categoria_val not in CATEGORIAS_GASTO:
                flash('Categoría no válida.', 'danger')
                return redirect(url_for('finance.nuevo_gasto'))
            fecha_gasto = datetime.strptime(request.form['fecha'], '%Y-%m-%d')
            oc_id = request.form.get('orden_compra_id')
            if oc_id == "":
                oc_id = None
            cc_id = request.form.get('centro_costo_id') or None

            g = Gasto(
                descripcion=request.form['descripcion'],
                monto=monto_val,
                categoria=categoria_val,
                fecha=fecha_gasto,
                orden_compra_id=oc_id,
                centro_costo_id=cc_id,
                organizacion_id=current_user.organizacion_id
            )
            db.session.add(g)
            db.session.flush()
            log_actividad(
                'crear', 'gasto',
                f'Gasto registrado: {g.descripcion} — ${g.monto:,.2f} ({g.categoria})',
                entidad_id=g.id
            )
            db.session.commit()
            flash('Gasto registrado exitosamente', 'success')
            return redirect(url_for('finance.lista_gastos'))
        except Exception as e:
            db.session.rollback()
            _flash_err('Error al registrar el gasto.', e)

    return render_template('gasto_form.html',
                           titulo="Registrar Nuevo Gasto",
                           ordenes=ordenes,
                           centros=centros,
                           now=now_mx())


@finance_bp.route('/gasto/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@check_permission('perm_view_gastos')
def editar_gasto(id):
    """Edita un gasto existente."""
    gasto = get_item_or_404(Gasto, id)
    org_id = current_user.organizacion_id
    ordenes = OrdenCompra.query.filter_by(organizacion_id=org_id).order_by(OrdenCompra.fecha_creacion.desc()).all()
    centros = CentroCosto.query.filter_by(organizacion_id=org_id).order_by(CentroCosto.nombre).all()

    if request.method == 'POST':
        try:
            monto_val = float(request.form['monto'])
            if monto_val <= 0:
                flash('El monto debe ser mayor a cero.', 'danger')
                return redirect(url_for('finance.editar_gasto', id=id))
            categoria_val = request.form['categoria']
            if categoria_val not in CATEGORIAS_GASTO:
                flash('Categoría no válida.', 'danger')
                return redirect(url_for('finance.editar_gasto', id=id))
            fecha_gasto = datetime.strptime(request.form['fecha'], '%Y-%m-%d')
            oc_id = request.form.get('orden_compra_id')
            if oc_id == "" or oc_id == "None":
                oc_id = None
            cc_id = request.form.get('centro_costo_id') or None

            monto_anterior = gasto.monto
            gasto.descripcion = request.form['descripcion']
            gasto.monto = monto_val
            gasto.categoria = categoria_val
            gasto.fecha = fecha_gasto
            gasto.orden_compra_id = oc_id
            gasto.centro_costo_id = cc_id

            log_actividad(
                'editar', 'gasto',
                f'Gasto editado: {gasto.descripcion} — antes ${monto_anterior:,.2f} → ahora ${gasto.monto:,.2f} ({gasto.categoria})',
                entidad_id=gasto.id
            )
            db.session.commit()
            flash('Gasto actualizado exitosamente', 'success')
            return redirect(url_for('finance.lista_gastos'))

        except Exception as e:
            db.session.rollback()
            _flash_err('Error al actualizar el gasto.', e)

    return render_template('gasto_form.html',
                           titulo="Editar Gasto",
                           ordenes=ordenes,
                           centros=centros,
                           gasto=gasto)


# ==============================================================================
# EXPORTAR GASTOS EXCEL (multi-mes con gráficos)
# ==============================================================================

@finance_bp.route('/gastos/exportar_excel')
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def exportar_gastos_excel():
    ahora = now_mx()
    org   = Organizacion.query.get(current_user.organizacion_id)

    # ── Rango de meses ────────────────────────────────────────────────────────
    mes_desde = request.args.get('mes_desde', type=int)
    ano_desde = request.args.get('ano_desde', type=int)
    mes_hasta = request.args.get('mes_hasta', type=int)
    ano_hasta = request.args.get('ano_hasta', type=int)
    if not mes_desde:
        mes_desde = mes_hasta = request.args.get('mes', type=int) or ahora.month
        ano_desde = ano_hasta = request.args.get('ano', type=int) or ahora.year

    periodos = []
    y, m = ano_desde, mes_desde
    while (y < ano_hasta) or (y == ano_hasta and m <= mes_hasta):
        periodos.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    if not periodos:
        periodos = [(ano_desde, mes_desde)]

    base_query = (
        Gasto.query if current_user.rol == 'super_admin'
        else Gasto.query.filter_by(organizacion_id=current_user.organizacion_id)
    )

    # ── Configuración de diseño ───────────────────────────────────────────────
    def _argb(h):
        return 'FF' + (h or '#000000').lstrip('#').upper()

    col_hdr     = _argb(getattr(org, 'excel_color_header',  '#1f4e79'))
    col_acc     = _argb(getattr(org, 'excel_color_accent',  '#dbeafe'))
    fuente      = getattr(org, 'excel_fuente',         'Calibri') or 'Calibri'
    show_logo   = getattr(org, 'excel_mostrar_logo',   True)
    show_id     = getattr(org, 'excel_mostrar_id',     True)
    show_oc     = getattr(org, 'excel_mostrar_oc',     True)
    show_origen = getattr(org, 'excel_mostrar_origen', True)
    empresa     = (org.header_titulo or org.nombre) if org else 'Empresa'

    # ── Columnas dinámicas ────────────────────────────────────────────────────
    COLS = ['Fecha', 'Descripción', 'Categoría', 'Monto']
    if show_id:     COLS = ['ID'] + COLS
    if show_oc:     COLS.append('OC Asociada')
    if show_origen: COLS.append('Origen')
    N         = len(COLS)
    monto_idx = COLS.index('Monto') + 1   # 1-based
    last_col  = get_column_letter(N)

    # ── Estilos ───────────────────────────────────────────────────────────────
    fill_hdr = PatternFill('solid', fgColor=col_hdr)
    fill_acc = PatternFill('solid', fgColor=col_acc)
    fill_svc = PatternFill('solid', fgColor='FFFFF8E1')  # ámbar muy suave

    bd_s  = Side(border_style='thin',   color='CCCCCC')
    bd_m  = Side(border_style='medium', color='888888')
    bd    = Border(left=bd_s,  right=bd_s,  top=bd_s,  bottom=bd_s)
    bd_tt = Border(left=bd_m,  right=bd_m,  top=bd_m,  bottom=bd_m)  # noqa: F841

    f_title  = Font(name=fuente, size=14, bold=True,  color='FFFFFF')
    f_sub    = Font(name=fuente, size=10,             color='FFFFFF')
    f_hdr    = Font(name=fuente, size=10, bold=True,  color='FFFFFF')
    f_normal = Font(name=fuente, size=10)
    f_bold   = Font(name=fuente, size=11, bold=True)
    f_wht    = Font(name=fuente, size=11, bold=True,  color='FFFFFF')

    a_c = Alignment(horizontal='center', vertical='center')
    a_r = Alignment(horizontal='right',  vertical='center')
    a_l = Alignment(horizontal='left',   vertical='center')
    cur_fmt = '$#,##0.00'

    # ── Logo path ─────────────────────────────────────────────────────────────
    logo_path = None
    if show_logo and org and org.logo_url:
        candidate = os.path.join(current_app.config['UPLOAD_FOLDER'], org.logo_url)
        if os.path.exists(candidate):
            logo_path = candidate

    # ── Helpers internos ──────────────────────────────────────────────────────
    def _auto_width(ws, max_w=52):
        for ci, col in enumerate(ws.columns, 1):
            w = max((len(str(c.value or '')) for c in col), default=10)
            ws.column_dimensions[get_column_letter(ci)].width = min(w + 4, max_w)

    def _banner(ws, title, subtitle=''):
        ws.merge_cells(f'A1:{last_col}1')
        c = ws['A1']
        c.value, c.font, c.fill, c.alignment = title, f_title, fill_hdr, a_c
        ws.row_dimensions[1].height = 30
        ws.merge_cells(f'A2:{last_col}2')
        c2 = ws['A2']
        c2.value, c2.font, c2.fill, c2.alignment = subtitle, f_sub, fill_hdr, a_c
        ws.row_dimensions[2].height = 16
        if logo_path:
            try:
                img = XlImage(logo_path)
                img.height, img.width = 42, 42
                ws.add_image(img, 'A1')
            except Exception:
                pass

    def _col_headers(ws, row, headers):
        for ci, h in enumerate(headers, 1):
            c = ws.cell(row, ci, h)
            c.font, c.fill, c.alignment, c.border = f_hdr, fill_hdr, a_c, bd
        ws.row_dimensions[row].height = 18

    def _cat_summary(ws, gastos_list):
        """Tabla de resumen por categoría al pie de cada hoja."""
        cat_totals = {}
        for g in gastos_list:
            k = g.categoria or 'Sin categoría'
            cat_totals[k] = cat_totals.get(k, 0) + g.monto
        if not cat_totals:
            return
        ws.append([])
        sr = ws.max_row + 1
        ws.merge_cells(f'A{sr}:B{sr}')
        sh = ws[f'A{sr}']
        sh.value, sh.font, sh.fill, sh.alignment = 'Resumen por Categoría', f_hdr, fill_hdr, a_c
        ws.row_dimensions[sr].height = 16
        hr = sr + 1
        for ci, txt in enumerate(['Categoría', 'Total'], 1):
            c = ws.cell(hr, ci, txt)
            c.font, c.fill, c.alignment, c.border = f_hdr, fill_hdr, (a_l if ci == 1 else a_r), bd
        for cat, tot in sorted(cat_totals.items(), key=lambda x: -x[1]):
            r = ws.max_row + 1
            c1 = ws.cell(r, 1, cat)
            c1.font, c1.border, c1.alignment = f_normal, bd, a_l
            c2 = ws.cell(r, 2, tot)
            c2.font, c2.border, c2.alignment = f_normal, bd, a_r
            c2.number_format = cur_fmt

    def _add_month_sheet(wb, year, month, table_idx):
        gastos = base_query.filter(
            extract('month', Gasto.fecha) == month,
            extract('year',  Gasto.fecha) == year
        ).order_by(Gasto.fecha.asc()).all()

        nombre_mes = datetime(year, month, 1).strftime('%B').capitalize()
        ws = wb.create_sheet(title=f"{nombre_mes[:3]} {year}")

        _banner(ws, empresa, f'Control de Gastos — {nombre_mes} {year}')
        _col_headers(ws, 3, COLS)

        total = 0.0
        for i, g in enumerate(gastos):
            origen = 'Servicio' if g.descripcion.startswith('Servicio:') else 'Manual'
            row_data = [g.fecha.date(), g.descripcion, g.categoria or '—', g.monto]
            if show_id:     row_data = [g.id] + row_data
            if show_oc:     row_data.append(g.orden_compra_id or '—')
            if show_origen: row_data.append(origen)
            ws.append(row_data)
            r = ws.max_row
            use_acc = (i % 2 == 1)
            for ci in range(1, N + 1):
                c = ws.cell(r, ci)
                c.font, c.border = f_normal, bd
                if origen == 'Servicio':
                    c.fill = fill_svc
                elif use_acc:
                    c.fill = fill_acc
            ws.cell(r, monto_idx).number_format = cur_fmt
            ws.cell(r, monto_idx).alignment     = a_r
            total += g.monto

        if gastos:
            try:
                tbl = ExcelTable(displayName=f'Gastos{table_idx}',
                                 ref=f'A3:{last_col}{ws.max_row}')
                tbl.tableStyleInfo = TableStyleInfo(
                    name='TableStyleMedium2', showRowStripes=False)
                ws.add_table(tbl)
            except Exception:
                pass

        # Fila total
        ft = ws.max_row + 1
        pre = get_column_letter(monto_idx - 1)
        ws.merge_cells(f'A{ft}:{pre}{ft}')
        c_lbl = ws.cell(ft, 1, 'Total del Mes')
        c_lbl.font, c_lbl.fill, c_lbl.alignment, c_lbl.border = f_bold, fill_acc, a_r, bd
        c_tot = ws.cell(ft, monto_idx, total)
        c_tot.number_format = cur_fmt
        c_tot.font, c_tot.fill, c_tot.alignment, c_tot.border = f_bold, fill_acc, a_r, bd

        _cat_summary(ws, gastos)
        ws.freeze_panes = 'A4'
        _auto_width(ws)
        return total, len(gastos)

    # ── Construir workbook ────────────────────────────────────────────────────
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    ws_res = None
    if len(periodos) > 1:
        ws_res = wb.create_sheet(title='Resumen', index=0)
        nm1 = datetime(periodos[0][0],  periodos[0][1],  1).strftime('%B').capitalize()
        nm2 = datetime(periodos[-1][0], periodos[-1][1], 1).strftime('%B').capitalize()
        _banner(ws_res, empresa,
                f'Auditoría de Gastos — {nm1} {periodos[0][0]} a {nm2} {periodos[-1][0]}')
        _col_headers(ws_res, 3, ['Período', 'Registros', 'Total (MXN)', 'Con Servicios'])

    totals_resumen = []
    for idx, (year, month) in enumerate(periodos, 1):
        total_mes, count_mes = _add_month_sheet(wb, year, month, idx)
        totals_resumen.append((year, month, total_mes, count_mes))

    if ws_res is not None:
        gran_total  = 0.0
        all_g_range = []
        for year, month, total_mes, count_mes in totals_resumen:
            nombre_mes = datetime(year, month, 1).strftime('%B').capitalize()
            gastos_mes = base_query.filter(
                extract('month', Gasto.fecha) == month,
                extract('year',  Gasto.fecha) == year).all()
            all_g_range.extend(gastos_mes)
            tiene_svc = any(g.descripcion.startswith('Servicio:') for g in gastos_mes)
            ws_res.append([f'{nombre_mes} {year}', count_mes, total_mes,
                           'Sí' if tiene_svc else 'No'])
            r = ws_res.max_row
            ws_res.cell(r, 3).number_format = cur_fmt
            ws_res.cell(r, 3).alignment     = a_r
            for ci in range(1, 5):
                ws_res.cell(r, ci).font   = f_normal
                ws_res.cell(r, ci).border = bd
            gran_total += total_mes

        data_end = ws_res.max_row
        gt = data_end + 1
        ws_res.cell(gt, 1, 'GRAN TOTAL').font      = f_wht
        ws_res.cell(gt, 1).fill, ws_res.cell(gt, 1).alignment = fill_hdr, a_r
        ws_res.cell(gt, 1).border = bd
        ws_res.cell(gt, 2, sum(c for _, _, _, c in totals_resumen)).font = f_wht
        ws_res.cell(gt, 2).fill,  ws_res.cell(gt, 2).border              = fill_hdr, bd
        ws_res.cell(gt, 2).alignment = a_c
        ws_res.cell(gt, 3, gran_total).number_format = cur_fmt
        ws_res.cell(gt, 3).font, ws_res.cell(gt, 3).fill   = f_wht, fill_hdr
        ws_res.cell(gt, 3).alignment, ws_res.cell(gt, 3).border = a_r, bd

        # Tabla de categorías del período completo
        _cat_summary(ws_res, all_g_range)

        # Gráfico de barras por mes
        try:
            chart = BarChart()
            chart.type, chart.grouping = 'col', 'clustered'
            chart.title   = 'Gastos por Mes'
            chart.y_axis.title = 'Total (MXN)'
            chart.x_axis.title = 'Período'
            data_ref = Reference(ws_res, min_col=3, max_col=3,
                                 min_row=3, max_row=data_end)
            cats_ref = Reference(ws_res, min_col=1, max_col=1,
                                 min_row=4, max_row=data_end)
            chart.add_data(data_ref, titles_from_data=True)
            chart.set_categories(cats_ref)
            chart.width, chart.height = 16, 10
            ws_res.add_chart(chart, 'F3')
        except Exception:
            pass

        ws_res.freeze_panes = 'A4'
        _auto_width(ws_res)

    # ── Nombre de archivo ─────────────────────────────────────────────────────
    if len(periodos) == 1:
        nom = datetime(periodos[0][0], periodos[0][1], 1).strftime('%B').capitalize()
        filename = f"Gastos_{nom}_{periodos[0][0]}.xlsx"
    else:
        n1 = datetime(periodos[0][0],  periodos[0][1],  1).strftime('%b').capitalize()
        n2 = datetime(periodos[-1][0], periodos[-1][1], 1).strftime('%b').capitalize()
        filename = f"Gastos_{n1}{periodos[0][0]}_a_{n2}{periodos[-1][0]}.xlsx"

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    response = make_response(buffer.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    response.headers['Content-Type'] = \
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return response


# ==============================================================================
# CENTROS DE COSTO
# ==============================================================================

@finance_bp.route('/centros-costo')
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def lista_centros_costo():
    org_id = current_user.organizacion_id
    centros = CentroCosto.query.filter_by(organizacion_id=org_id).order_by(CentroCosto.creado_en.desc()).all()
    return render_template('centros_costo_lista.html',
        titulo='Centros de Costo', centros=centros, now=now_mx())


@finance_bp.route('/centro-costo/nuevo', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def nuevo_centro_costo():
    if request.method == 'POST':
        try:
            cc = CentroCosto(
                nombre          = request.form['nombre'].strip(),
                descripcion     = request.form.get('descripcion', '').strip() or None,
                presupuesto     = float(request.form['presupuesto']) if request.form.get('presupuesto') else None,
                organizacion_id = current_user.organizacion_id,
                creador_id      = current_user.id,
            )
            db.session.add(cc)
            db.session.commit()
            flash('Centro de costo creado.', 'success')
            return redirect(url_for('finance.lista_centros_costo'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {e}', 'danger')
    return render_template('centro_costo_form.html', titulo='Nuevo Centro de Costo', centro=None, now=now_mx())


@finance_bp.route('/centro-costo/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def editar_centro_costo(id):
    org_id = current_user.organizacion_id
    cc = CentroCosto.query.filter_by(id=id, organizacion_id=org_id).first_or_404()
    if request.method == 'POST':
        try:
            cc.nombre      = request.form['nombre'].strip()
            cc.descripcion = request.form.get('descripcion', '').strip() or None
            cc.presupuesto = float(request.form['presupuesto']) if request.form.get('presupuesto') else None
            db.session.commit()
            flash('Centro de costo actualizado.', 'success')
            return redirect(url_for('finance.detalle_centro_costo', id=cc.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {e}', 'danger')
    return render_template('centro_costo_form.html', titulo='Editar Centro de Costo', centro=cc, now=now_mx())


@finance_bp.route('/centro-costo/<int:id>/cerrar', methods=['POST'])
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def cerrar_centro_costo(id):
    org_id = current_user.organizacion_id
    cc = CentroCosto.query.filter_by(id=id, organizacion_id=org_id).first_or_404()
    cc.estado = 'cerrado' if cc.estado == 'activo' else 'activo'
    db.session.commit()
    flash(f'Centro de costo {"cerrado" if cc.estado == "cerrado" else "reactivado"}.', 'success')
    return redirect(url_for('finance.detalle_centro_costo', id=cc.id))


@finance_bp.route('/centro-costo/<int:id>')
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def detalle_centro_costo(id):
    org_id = current_user.organizacion_id
    cc = CentroCosto.query.filter_by(id=id, organizacion_id=org_id).first_or_404()

    # Desglose por tipo
    total_gastos    = sum(g.monto for g in cc.gastos)
    total_servicios = sum(p.monto for p in cc.pagos_servicio if p.estado == 'pagado')
    total_facturas  = sum(f.monto for f in cc.facturas)
    total           = total_gastos + total_servicios + total_facturas

    # Gastos por categoría (horizontal bar)
    cat_map = {}
    for g in cc.gastos:
        k = g.categoria or 'Sin categoría'
        cat_map[k] = cat_map.get(k, 0) + g.monto
    cat_items = sorted(cat_map.items(), key=lambda x: -x[1])

    # Feed unificado de transacciones
    txs = []
    for g in cc.gastos:
        txs.append({'fecha': g.fecha.date() if hasattr(g.fecha, 'date') else g.fecha,
                    'tipo': 'Gasto', 'desc': g.descripcion, 'cat': g.categoria or '—',
                    'monto': g.monto, 'icon': 'bi-cash-coin', 'cls': 'badge-borrador'})
    for p in cc.pagos_servicio:
        txs.append({'fecha': p.fecha_pago,
                    'tipo': 'Servicio', 'desc': p.servicio.nombre, 'cat': p.servicio.tipo or '—',
                    'monto': p.monto, 'icon': 'bi-lightning-charge-fill', 'cls': 'badge-enviada'})
    for f in cc.facturas:
        txs.append({'fecha': f.fecha_emision,
                    'tipo': 'Factura', 'desc': f.numero_factura + ' — ' + f.proveedor.nombre, 'cat': 'Proveedor',
                    'monto': f.monto, 'icon': 'bi-file-earmark-text', 'cls': 'badge-recibida'})
    txs.sort(key=lambda x: x['fecha'] if x['fecha'] else date.min, reverse=True)

    return render_template('centro_costo_detalle.html',
        titulo=cc.nombre, cc=cc,
        total=total, total_gastos=total_gastos,
        total_servicios=total_servicios, total_facturas=total_facturas,
        cat_items=cat_items, txs=txs, now=now_mx())


# ==============================================================================
# PRESUPUESTOS
# ==============================================================================

@finance_bp.route('/presupuestos')
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def lista_presupuestos():
    org_id = current_user.organizacion_id
    ahora  = now_mx()

    anio = request.args.get('anio', ahora.year, type=int)
    mes  = request.args.get('mes',  0,           type=int)   # 0 = anual

    q = Presupuesto.query.filter_by(organizacion_id=org_id, anio=anio)
    if mes:
        presupuestos = q.filter_by(mes=mes).order_by(Presupuesto.categoria).all()
    else:
        presupuestos = q.filter(Presupuesto.mes.is_(None)).order_by(Presupuesto.categoria).all()

    items = []
    for p in presupuestos:
        gastado = _real_por_categoria(org_id, p.categoria, anio, mes or None)
        pct     = min(round(gastado / p.monto * 100, 1), 999) if p.monto > 0 else 0
        cls, lbl = _semaforo(pct)
        items.append({
            'p': p,
            'gastado': gastado,
            'disponible': p.monto - gastado,
            'pct': pct,
            'pct_bar': min(pct, 100),
            'cls': cls,
            'label': lbl,
        })

    # Categorías que aún no tienen presupuesto en este período
    cats_con = {i['p'].categoria for i in items}
    cats_sin = [c for c in CATEGORIAS_GASTO if c not in cats_con]

    total_presupuestado = sum(i['p'].monto for i in items)
    total_gastado_real  = sum(i['gastado'] for i in items)
    en_riesgo           = sum(1 for i in items if i['cls'] == 'danger')
    pct_global          = min(round(total_gastado_real / total_presupuestado * 100, 1), 999) if total_presupuestado else 0

    anios_disponibles = list(range(ahora.year - 1, ahora.year + 3))

    return render_template('presupuestos_lista.html',
        titulo='Presupuestos',
        items=items,
        cats_sin=cats_sin,
        total_presupuestado=total_presupuestado,
        total_gastado=total_gastado_real,
        en_riesgo=en_riesgo,
        pct_global=pct_global,
        anio=anio, mes=mes,
        anios_disponibles=anios_disponibles,
        meses_es=MESES_ES,
        now=ahora,
    )


@finance_bp.route('/presupuesto/nuevo', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def nuevo_presupuesto():
    org_id = current_user.organizacion_id
    ahora  = now_mx()

    if request.method == 'POST':
        categoria = request.form['categoria']
        anio      = int(request.form['anio'])
        mes_raw   = request.form.get('mes', '')
        mes       = int(mes_raw) if mes_raw else None
        monto     = float(request.form['monto'])

        existente = Presupuesto.query.filter_by(
            organizacion_id=org_id, categoria=categoria, anio=anio, mes=mes
        ).first()
        if existente:
            flash(f'Ya existe un presupuesto para {categoria} en ese período.', 'warning')
        else:
            p = Presupuesto(categoria=categoria, anio=anio, mes=mes,
                            monto=monto, organizacion_id=org_id)
            db.session.add(p)
            db.session.commit()
            flash('Presupuesto creado.', 'success')
            return redirect(url_for('finance.lista_presupuestos', anio=anio, mes=mes or 0))

    return render_template('presupuesto_form.html',
        titulo='Nuevo Presupuesto',
        presupuesto=None,
        categorias=CATEGORIAS_GASTO,
        meses_es=MESES_ES,
        anio_actual=ahora.year,
        now=ahora,
    )


@finance_bp.route('/presupuesto/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def editar_presupuesto(id):
    org_id = current_user.organizacion_id
    p = Presupuesto.query.filter_by(id=id, organizacion_id=org_id).first_or_404()

    if request.method == 'POST':
        p.monto = float(request.form['monto'])
        db.session.commit()
        flash('Presupuesto actualizado.', 'success')
        return redirect(url_for('finance.lista_presupuestos', anio=p.anio, mes=p.mes or 0))

    return render_template('presupuesto_form.html',
        titulo='Editar Presupuesto',
        presupuesto=p,
        categorias=CATEGORIAS_GASTO,
        meses_es=MESES_ES,
        anio_actual=p.anio,
        now=now_mx(),
    )


@finance_bp.route('/presupuesto/<int:id>/eliminar', methods=['POST'])
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def eliminar_presupuesto(id):
    org_id = current_user.organizacion_id
    p = Presupuesto.query.filter_by(id=id, organizacion_id=org_id).first_or_404()
    anio, mes = p.anio, p.mes or 0
    db.session.delete(p)
    db.session.commit()
    flash('Presupuesto eliminado.', 'success')
    return redirect(url_for('finance.lista_presupuestos', anio=anio, mes=mes))


# ==============================================================================
# FACTURAS DE PROVEEDORES — CUENTAS POR PAGAR
# ==============================================================================

@finance_bp.route('/cuentas-por-pagar')
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def lista_facturas():
    org_id = current_user.organizacion_id
    ahora  = now_mx()

    # Actualizar estado a 'vencido' automáticamente
    vencidas = FacturaProveedor.query.filter_by(organizacion_id=org_id, estado='pendiente').filter(
        FacturaProveedor.fecha_vencimiento < ahora.date()
    ).all()
    for f in vencidas:
        f.estado = 'vencido'
    if vencidas:
        db.session.commit()

    estado_filtro    = request.args.get('estado', '')
    proveedor_filtro = request.args.get('proveedor_id', type=int, default=0)

    q = FacturaProveedor.query.filter_by(organizacion_id=org_id)
    if estado_filtro:
        q = q.filter_by(estado=estado_filtro)
    if proveedor_filtro:
        q = q.filter_by(proveedor_id=proveedor_filtro)
    facturas = q.order_by(FacturaProveedor.fecha_vencimiento.asc()).all()

    # KPIs
    todas = FacturaProveedor.query.filter_by(organizacion_id=org_id).all()
    total_pendiente = sum(f.monto for f in todas if f.estado in ('pendiente', 'vencido'))
    total_vencido   = sum(f.monto for f in todas if f.estado == 'vencido')
    total_pagado_mes = sum(
        f.monto for f in todas
        if f.estado == 'pagado'
        and f.fecha_vencimiento.month == ahora.month
        and f.fecha_vencimiento.year  == ahora.year
    )

    # Aging buckets
    aging = {
        'vigente': Decimal(0), '1-30': Decimal(0),
        '31-60': Decimal(0), '61-90': Decimal(0), '90+': Decimal(0)
    }
    for f in todas:
        if f.estado != 'pagado':
            aging[f.bucket_aging] = aging.get(f.bucket_aging, 0.0) + f.monto

    proveedores = Proveedor.query.filter_by(organizacion_id=org_id).order_by(Proveedor.nombre).all()

    return render_template('facturas_lista.html',
        titulo='Cuentas por Pagar',
        facturas=facturas,
        total_pendiente=total_pendiente,
        total_vencido=total_vencido,
        total_pagado_mes=total_pagado_mes,
        aging=aging,
        proveedores=proveedores,
        estado_filtro=estado_filtro,
        proveedor_filtro=proveedor_filtro,
        ahora=ahora,
        now=ahora,
    )


@finance_bp.route('/factura/nueva', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def nueva_factura():
    org_id = current_user.organizacion_id
    proveedores = Proveedor.query.filter_by(organizacion_id=org_id).order_by(Proveedor.nombre).all()
    ordenes     = OrdenCompra.query.filter_by(organizacion_id=org_id).order_by(OrdenCompra.fecha_creacion.desc()).all()
    centros     = CentroCosto.query.filter_by(organizacion_id=org_id).order_by(CentroCosto.nombre).all()

    if request.method == 'POST':
        try:
            monto_val = float(request.form['monto'])
            if monto_val <= 0:
                flash('El monto debe ser mayor a cero.', 'danger')
                return redirect(url_for('finance.nueva_factura'))
            factura = FacturaProveedor(
                numero_factura    = request.form['numero_factura'].strip(),
                proveedor_id      = int(request.form['proveedor_id']),
                orden_compra_id   = int(request.form['orden_compra_id']) if request.form.get('orden_compra_id') else None,
                centro_costo_id   = int(request.form['centro_costo_id']) if request.form.get('centro_costo_id') else None,
                monto             = monto_val,
                fecha_emision     = date.fromisoformat(request.form['fecha_emision']),
                fecha_vencimiento = date.fromisoformat(request.form['fecha_vencimiento']),
                notas             = request.form.get('notas', '').strip() or None,
                registrado_por_id = current_user.id,
                organizacion_id   = org_id,
            )
            db.session.add(factura)
            db.session.flush()
            log_actividad('crear', 'factura',
                f'Factura registrada: #{factura.numero_factura} — ${factura.monto:,.2f}',
                entidad_id=factura.id)
            db.session.commit()
            flash('Factura registrada correctamente.', 'success')
            return redirect(url_for('finance.lista_facturas'))
        except Exception as e:
            db.session.rollback()
            _flash_err('Error al registrar la factura.', e)

    return render_template('factura_form.html',
        titulo='Nueva Factura',
        factura=None,
        proveedores=proveedores,
        ordenes=ordenes,
        centros=centros,
        now=now_mx(),
    )


@finance_bp.route('/factura/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def editar_factura(id):
    org_id  = current_user.organizacion_id
    factura = FacturaProveedor.query.filter_by(id=id, organizacion_id=org_id).first_or_404()
    proveedores = Proveedor.query.filter_by(organizacion_id=org_id).order_by(Proveedor.nombre).all()
    ordenes     = OrdenCompra.query.filter_by(organizacion_id=org_id).order_by(OrdenCompra.fecha_creacion.desc()).all()
    centros     = CentroCosto.query.filter_by(organizacion_id=org_id).order_by(CentroCosto.nombre).all()

    if request.method == 'POST':
        try:
            monto_val = float(request.form['monto'])
            if monto_val <= 0:
                flash('El monto debe ser mayor a cero.', 'danger')
                return redirect(url_for('finance.editar_factura', id=id))
            monto_anterior = factura.monto
            factura.numero_factura    = request.form['numero_factura'].strip()
            factura.proveedor_id      = int(request.form['proveedor_id'])
            factura.orden_compra_id   = int(request.form['orden_compra_id']) if request.form.get('orden_compra_id') else None
            factura.centro_costo_id   = int(request.form['centro_costo_id']) if request.form.get('centro_costo_id') else None
            factura.monto             = monto_val
            factura.fecha_emision     = date.fromisoformat(request.form['fecha_emision'])
            factura.fecha_vencimiento = date.fromisoformat(request.form['fecha_vencimiento'])
            factura.notas             = request.form.get('notas', '').strip() or None
            log_actividad('editar', 'factura',
                f'Factura editada: #{factura.numero_factura} — antes ${monto_anterior:,.2f} → ahora ${factura.monto:,.2f}',
                entidad_id=factura.id)
            db.session.commit()
            flash('Factura actualizada.', 'success')
            return redirect(url_for('finance.lista_facturas'))
        except Exception as e:
            db.session.rollback()
            _flash_err('Error al actualizar la factura.', e)

    return render_template('factura_form.html',
        titulo='Editar Factura',
        factura=factura,
        proveedores=proveedores,
        ordenes=ordenes,
        centros=centros,
        now=now_mx(),
    )


@finance_bp.route('/factura/<int:id>/marcar-pagada', methods=['POST'])
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def marcar_factura_pagada(id):
    org_id  = current_user.organizacion_id
    factura = FacturaProveedor.query.filter_by(id=id, organizacion_id=org_id).first_or_404()
    factura.estado = 'pagado'
    log_actividad('pagar', 'factura',
        f'Factura marcada como pagada: #{factura.numero_factura} — ${factura.monto:,.2f}',
        entidad_id=factura.id)
    db.session.commit()
    flash(f'Factura #{factura.numero_factura} marcada como pagada.', 'success')
    return redirect(url_for('finance.lista_facturas'))


@finance_bp.route('/factura/<int:id>/eliminar', methods=['POST'])
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def eliminar_factura(id):
    org_id  = current_user.organizacion_id
    factura = FacturaProveedor.query.filter_by(id=id, organizacion_id=org_id).first_or_404()
    try:
        log_actividad('eliminar', 'factura',
            f'Factura eliminada: #{factura.numero_factura} — ${factura.monto:,.2f} (estado: {factura.estado})',
            entidad_id=factura.id)
        db.session.delete(factura)
        db.session.commit()
        flash('Factura eliminada.', 'success')
    except Exception as e:
        db.session.rollback()
        _flash_err('Error al eliminar la factura.', e)
    return redirect(url_for('finance.lista_facturas'))


# ==============================================================================
# SERVICIOS
# ==============================================================================

@finance_bp.route('/servicios')
@login_required
@check_org_permission
def lista_servicios():
    _actualizar_estados_pagos(current_user.organizacion_id)
    hoy = now_mx().date()
    servicios = Servicio.query.filter_by(
        organizacion_id=current_user.organizacion_id, activo=True
    ).order_by(Servicio.nombre).all()

    vencidos = PagoServicio.query.join(Servicio).filter(
        Servicio.organizacion_id == current_user.organizacion_id,
        PagoServicio.estado == 'vencido'
    ).count()
    proximos = PagoServicio.query.join(Servicio).filter(
        Servicio.organizacion_id == current_user.organizacion_id,
        PagoServicio.estado == 'pendiente',
        PagoServicio.fecha_vencimiento <= hoy + timedelta(days=7)
    ).count()
    gasto_mes = db.session.query(db.func.sum(PagoServicio.monto)).join(Servicio).filter(
        Servicio.organizacion_id == current_user.organizacion_id,
        PagoServicio.estado == 'pagado',
        db.func.extract('year',  PagoServicio.fecha_pago) == hoy.year,
        db.func.extract('month', PagoServicio.fecha_pago) == hoy.month,
    ).scalar() or 0

    return render_template('servicios_lista.html',
        servicios=servicios, tipos=TIPOS_SERVICIO,
        vencidos=vencidos, proximos=proximos,
        gasto_mes=gasto_mes, hoy=hoy)


@finance_bp.route('/servicios/nuevo', methods=['GET', 'POST'])
@login_required
@check_org_permission
def nuevo_servicio():
    if request.method == 'POST':
        s = Servicio(
            nombre           = request.form['nombre'].strip(),
            tipo             = request.form.get('tipo', 'otro'),
            proveedor_nombre = request.form.get('proveedor_nombre', '').strip() or None,
            numero_contrato  = request.form.get('numero_contrato', '').strip() or None,
            dia_vencimiento  = int(request.form['dia_vencimiento']) if request.form.get('dia_vencimiento') else None,
            dias_aviso       = int(request.form.get('dias_aviso', 5)),
            notas            = request.form.get('notas', '').strip() or None,
            organizacion_id  = current_user.organizacion_id,
        )
        db.session.add(s)
        db.session.commit()
        flash(f'Servicio "{s.nombre}" registrado.', 'success')
        return redirect(url_for('finance.lista_servicios'))
    return render_template('servicio_form.html', servicio=None, tipos=TIPOS_SERVICIO, accion='nuevo')


@finance_bp.route('/servicios/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@check_org_permission
def editar_servicio(id):
    s = Servicio.query.filter_by(id=id, organizacion_id=current_user.organizacion_id).first_or_404()
    if request.method == 'POST':
        s.nombre           = request.form['nombre'].strip()
        s.tipo             = request.form.get('tipo', 'otro')
        s.proveedor_nombre = request.form.get('proveedor_nombre', '').strip() or None
        s.numero_contrato  = request.form.get('numero_contrato', '').strip() or None
        s.dia_vencimiento  = int(request.form['dia_vencimiento']) if request.form.get('dia_vencimiento') else None
        s.dias_aviso       = int(request.form.get('dias_aviso', 5))
        s.notas            = request.form.get('notas', '').strip() or None
        db.session.commit()
        flash('Servicio actualizado.', 'success')
        return redirect(url_for('finance.detalle_servicio', id=s.id))
    return render_template('servicio_form.html', servicio=s, tipos=TIPOS_SERVICIO, accion='editar')


@finance_bp.route('/servicios/<int:id>/eliminar', methods=['POST'])
@login_required
@check_org_permission
def eliminar_servicio(id):
    if current_user.rol not in ['super_admin', 'admin']:
        flash('Sin permiso para eliminar servicios.', 'danger')
        return redirect(url_for('finance.lista_servicios'))
    s = Servicio.query.filter_by(id=id, organizacion_id=current_user.organizacion_id).first_or_404()
    nombre = s.nombre
    db.session.delete(s)
    db.session.commit()
    flash(f'Servicio "{nombre}" eliminado.', 'success')
    return redirect(url_for('finance.lista_servicios'))


@finance_bp.route('/servicios/<int:id>')
@login_required
@check_org_permission
def detalle_servicio(id):
    _actualizar_estados_pagos(current_user.organizacion_id)
    s    = Servicio.query.filter_by(id=id, organizacion_id=current_user.organizacion_id).first_or_404()
    hoy  = now_mx().date()
    info = TIPOS_SERVICIO.get(s.tipo, TIPOS_SERVICIO['otro'])
    pagados  = [p for p in s.pagos if p.estado == 'pagado'][:6]
    promedio = (sum(p.monto for p in pagados) / len(pagados)) if pagados else 0
    return render_template('servicio_detalle.html',
        servicio=s, info=info, hoy=hoy, promedio=promedio, tipos=TIPOS_SERVICIO)


@finance_bp.route('/servicios/<int:id>/pago/nuevo', methods=['GET', 'POST'])
@login_required
@check_org_permission
def nuevo_pago_servicio(id):
    s = Servicio.query.filter_by(id=id, organizacion_id=current_user.organizacion_id).first_or_404()
    centros = CentroCosto.query.filter_by(organizacion_id=current_user.organizacion_id).order_by(CentroCosto.nombre).all()

    if request.method == 'POST':
        monto_val = float(request.form['monto'])
        if monto_val <= 0:
            flash('El monto debe ser mayor a cero.', 'danger')
            return redirect(url_for('finance.nuevo_pago_servicio', id=id))
        p = PagoServicio(
            servicio_id       = s.id,
            monto             = monto_val,
            fecha_vencimiento = datetime.strptime(request.form['fecha_vencimiento'], '%Y-%m-%d').date(),
            notas             = request.form.get('notas', '').strip() or None,
            centro_costo_id   = int(request.form['centro_costo_id']) if request.form.get('centro_costo_id') else None,
            registrado_por_id = current_user.id,
        )
        if request.form.get('fecha_pago'):
            p.fecha_pago = datetime.strptime(request.form['fecha_pago'], '%Y-%m-%d').date()
            p.estado = 'pagado'
        db.session.add(p)
        db.session.flush()  # para obtener p.id antes del commit
        log_actividad('crear', 'pago_servicio',
            f'Pago registrado — {s.nombre}: ${p.monto:,.2f} (estado: {p.estado})',
            entidad_id=p.id)
        if p.estado == 'pagado':
            _registrar_gasto_servicio(p)
        # Guardar comprobante si se subió
        comp = request.files.get('comprobante')
        if comp and comp.filename:
            ext = secure_filename(comp.filename).rsplit('.', 1)[-1].lower()
            if ext in ('jpg', 'jpeg', 'png', 'pdf', 'webp'):
                carpeta = os.path.join(current_app.config['UPLOAD_FOLDER'], 'comprobantes')
                os.makedirs(carpeta, exist_ok=True)
                nombre = f"comp_{p.id}_{secrets.token_hex(6)}.{ext}"
                comp.save(os.path.join(carpeta, nombre))
                p.comprobante_url = nombre
        db.session.commit()
        if p.estado == 'pagado':
            _enviar_push_notificacion(
                org_id=s.organizacion_id,
                titulo=f'Pago registrado — {s.nombre}',
                cuerpo=f'${p.monto:,.2f} MXN · {p.fecha_pago.strftime("%d/%m/%Y")}',
                url=f'/servicios/{s.id}'
            )
        flash('Pago registrado.', 'success')
        return redirect(url_for('finance.detalle_servicio', id=s.id))

    hoy = now_mx().date()
    fecha_sugerida = ''
    if s.dia_vencimiento:
        mes  = hoy.month if hoy.day < s.dia_vencimiento else (hoy.month % 12 + 1)
        anio = hoy.year  if mes >= hoy.month else hoy.year + 1
        dia  = min(s.dia_vencimiento, calendar.monthrange(anio, mes)[1])
        fecha_sugerida = f'{anio}-{mes:02d}-{dia:02d}'
    return render_template('pago_servicio_form.html', servicio=s, fecha_sugerida=fecha_sugerida, centros=centros)


@finance_bp.route('/servicios/pago/<int:id>/marcar-pagado', methods=['POST'])
@login_required
@check_org_permission
def marcar_pago_pagado(id):
    p = PagoServicio.query.join(Servicio).filter(
        PagoServicio.id == id,
        Servicio.organizacion_id == current_user.organizacion_id
    ).first_or_404()
    fecha_str = request.form.get('fecha_pago')
    p.fecha_pago = datetime.strptime(fecha_str, '%Y-%m-%d').date() if fecha_str else now_mx().date()
    p.estado = 'pagado'
    log_actividad('pagar', 'pago_servicio',
        f'Pago marcado como pagado — {p.servicio.nombre}: ${p.monto:,.2f}',
        entidad_id=p.id)
    _registrar_gasto_servicio(p)
    db.session.commit()
    _enviar_push_notificacion(
        org_id=p.servicio.organizacion_id,
        titulo=f'Pago registrado — {p.servicio.nombre}',
        cuerpo=f'${p.monto:,.2f} MXN · {p.fecha_pago.strftime("%d/%m/%Y")}',
        url=f'/servicios/{p.servicio_id}'
    )
    flash('Pago marcado como pagado. Gasto registrado automáticamente.', 'success')
    return redirect(url_for('finance.detalle_servicio', id=p.servicio_id))


@finance_bp.route('/servicios/pago/<int:id>/eliminar', methods=['POST'])
@login_required
@check_org_permission
def eliminar_pago_servicio(id):
    p = PagoServicio.query.join(Servicio).filter(
        PagoServicio.id == id,
        Servicio.organizacion_id == current_user.organizacion_id
    ).first_or_404()
    serv_id = p.servicio_id
    try:
        log_actividad('eliminar', 'pago_servicio',
            f'Pago eliminado — {p.servicio.nombre}: ${p.monto:,.2f} (estado: {p.estado})',
            entidad_id=p.id)
        # Borrar comprobante si existe
        if p.comprobante_url:
            try:
                os.remove(os.path.join(
                    current_app.config['UPLOAD_FOLDER'], 'comprobantes', p.comprobante_url
                ))
            except OSError:
                pass
        db.session.delete(p)
        db.session.commit()
        flash('Registro de pago eliminado.', 'success')
    except Exception as e:
        db.session.rollback()
        _flash_err('Error al eliminar el pago.', e)
    return redirect(url_for('finance.detalle_servicio', id=serv_id))


# ==============================================================================
# API — OCR DE RECIBO
# ==============================================================================

@finance_bp.route('/api/servicios/ocr-recibo', methods=['POST'])
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
