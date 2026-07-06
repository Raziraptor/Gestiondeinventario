"""
Blueprint purchasing — órdenes de compra, proyectos OC, aprobaciones y exportación.

Rutas:
  lista_ordenes, nueva_orden, recibir_orden, enviar_orden, generar_oc_pdf,
  nueva_orden_manual, ver_orden, exportar_hd_csv, exportar_proyecto_hd_csv,
  subir_hd_auto, enviar_oc_homedepot, integracion_status_oc, editar_orden,
  cancelar_orden, eliminar_orden, lista_proyectos_oc, ver_proyecto_oc,
  nuevo_proyecto_oc, editar_proyecto_oc, solicitar_aprobacion_oc,
  enviar_proyecto_oc, lista_aprobaciones, aprobar_solicitud, rechazar_solicitud,
  recibir_proyecto_oc, generar_proyecto_oc_pdf, cancelar_proyecto_oc,
  exportar_proyectos_oc_excel
"""

import io
import os
import json
from threading import Thread

from flask import (
    render_template, request, redirect, url_for, flash, send_file,
    make_response, jsonify, current_app,
)
from flask_login import login_required, current_user
from sqlalchemy import extract
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.utils import secure_filename

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from xml.sax.saxutils import escape as _xml_escape
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    Image as ReportLabImage,
)

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from . import purchasing_bp
from app.extensions import db
from app.helpers import (
    now_mx, _flash_err, check_org_permission, check_permission, get_item_or_404,
    log_actividad,
)
from app.models import (
    OrdenCompra, OrdenCompraDetalle, ProyectoOC, ProyectoOCDetalle,
    SolicitudAprobacion, Producto, Proveedor, Almacen, Stock, Movimiento,
    Organizacion, AuditLog, ProveedorIntegracion, HDSesion, FormatoProveedor,
)


# ==============================================================================
# HELPERS LOCALES
# ==============================================================================

def _enviar_push_notificacion(org_id, titulo, cuerpo, url='/dashboard'):
    try:
        from app.services.notifications import enviar_push
        enviar_push(org_id=org_id, titulo=titulo, cuerpo=cuerpo, url=url)
    except Exception:
        pass


# ── PDF helpers (compartidos con inventory) ───────────────────────────────────

def _pdf_estilos(org):
    fuente = org.tipo_letra if org.tipo_letra in ['Helvetica', 'Times-Roman', 'Courier'] else 'Helvetica'
    c_pri = colors.HexColor(org.color_primario)   if org.color_primario   else colors.HexColor('#333333')
    c_sec = colors.HexColor(org.color_secundario) if org.color_secundario else colors.HexColor('#f1f5f9')
    return fuente, c_pri, c_sec


def _pdf_bold(fuente):
    return 'Times-Bold' if fuente == 'Times-Roman' else f'{fuente}-Bold'


def _pdf_header(story, org, styles):
    fuente, c_pri, _ = _pdf_estilos(org)
    s_brand = ParagraphStyle('_Brand', fontName=_pdf_bold(fuente), fontSize=20, leading=22, textColor=colors.black, spaceAfter=2)
    s_sub   = ParagraphStyle('_Sub',   fontName=fuente, fontSize=10, leading=12, textColor=colors.gray)
    s_meta  = ParagraphStyle('_Meta',  fontName=fuente, fontSize=8,  leading=10, textColor=colors.HexColor('#64748b'))

    logo_el = []
    if org.logo_url:
        logo_path = os.path.join(current_app.config['UPLOAD_FOLDER'], org.logo_url)
        if os.path.exists(logo_path):
            img = ReportLabImage(logo_path)
            max_h = 1.0 * inch
            img.drawHeight = max_h
            img.drawWidth  = max_h * (img.imageWidth / float(img.imageHeight))
            logo_el.append(img)

    text_el = [Paragraph(org.header_titulo or org.nombre, s_brand)]
    if org.header_subtitulo:
        text_el.append(Paragraph(org.header_subtitulo, s_sub))

    meta_parts = []
    if org.rfc:             meta_parts.append(f'RFC: {org.rfc}')
    if org.correo_empresa:  meta_parts.append(org.correo_empresa)
    if org.telefono:        meta_parts.append(org.telefono)
    if org.direccion:       meta_parts.append(org.direccion)
    if meta_parts:
        text_el.append(Paragraph(' · '.join(meta_parts), s_meta))

    if logo_el:
        t_hdr = Table([[logo_el, text_el]], colWidths=[1.5*inch, 4.7*inch])
    else:
        t_hdr = Table([[text_el]], colWidths=[6.2*inch])
    t_hdr.setStyle(TableStyle([
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING',   (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t_hdr)
    story.append(Table([['']], colWidths=[6.2*inch], rowHeights=[2],
                       style=TableStyle([('BACKGROUND', (0,0), (-1,-1), c_pri)])))
    story.append(Spacer(1, 0.2*inch))


def _pdf_footer(story, org, doc_url=None):
    import qrcode as _qrcode
    fuente, c_pri, _ = _pdf_estilos(org)
    s_footer = ParagraphStyle('_Foot', fontName=fuente, fontSize=8,
                               textColor=colors.HexColor('#64748b'), alignment=TA_CENTER)
    story.append(Spacer(1, 0.3*inch))
    story.append(Table([['']], colWidths=[6.2*inch], rowHeights=[1],
                       style=TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#e2e8f0'))])))
    story.append(Spacer(1, 0.1*inch))

    pie_parts = []
    if org.footer_texto:
        pie_parts.append(org.footer_texto)
    pie_parts.append(f"Generado el {now_mx().strftime('%d/%m/%Y a las %H:%M')} · {org.nombre}")
    story.append(Paragraph('<br/>'.join(pie_parts), s_footer))

    if org.pdf_mostrar_qr and doc_url:
        try:
            qr = _qrcode.QRCode(version=1, box_size=4, border=2)
            qr.add_data(doc_url)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color='black', back_color='white')
            qr_buf = io.BytesIO()
            qr_img.save(qr_buf, format='PNG')
            qr_buf.seek(0)
            rl_qr = ReportLabImage(qr_buf)
            rl_qr.drawWidth  = 0.7 * inch
            rl_qr.drawHeight = 0.7 * inch
            story.append(Spacer(1, 0.1*inch))
            t_qr = Table([[rl_qr]], colWidths=[6.2*inch])
            t_qr.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER')]))
            story.append(t_qr)
        except Exception:
            pass


def _pdf_row_styles(data_len, c_sec):
    styles = []
    for i in range(1, data_len):
        bg = c_sec if i % 2 == 0 else colors.white
        styles.append(('BACKGROUND', (0, i), (-1, i), bg))
    return styles


# ==============================================================================
# ÓRDENES DE COMPRA ESTÁNDAR
# ==============================================================================

@purchasing_bp.route('/ordenes')
@login_required
@check_org_permission
@check_permission('perm_create_oc_standard')
def lista_ordenes():
    mes = request.args.get('mes', type=int)
    ano = request.args.get('ano', type=int)
    prov_id = request.args.get('proveedor_id', type=int)

    ahora = now_mx()
    if not mes: mes = ahora.month
    if not ano: ano = ahora.year

    meses_lista = [
        (1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'), (4, 'Abril'),
        (5, 'Mayo'), (6, 'Junio'), (7, 'Julio'), (8, 'Agosto'),
        (9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre')
    ]

    if current_user.rol == 'super_admin':
        proveedores = Proveedor.query.order_by(Proveedor.nombre).all()
        query = OrdenCompra.query
    else:
        org_id = current_user.organizacion_id
        proveedores = Proveedor.query.filter_by(organizacion_id=org_id).order_by(Proveedor.nombre).all()
        query = OrdenCompra.query.filter_by(organizacion_id=org_id)

    query = query.filter(extract('month', OrdenCompra.fecha_creacion) == mes)
    query = query.filter(extract('year',  OrdenCompra.fecha_creacion) == ano)

    if prov_id and prov_id != 0:
        query = query.filter_by(proveedor_id=prov_id)

    page = request.args.get('page', 1, type=int)
    pagination = (
        query
        .options(joinedload(OrdenCompra.proveedor), joinedload(OrdenCompra.almacen))
        .order_by(OrdenCompra.fecha_creacion.desc())
        .paginate(page=page, per_page=12, error_out=False)
    )

    return render_template('ordenes.html',
                           ordenes=pagination.items,
                           pagination=pagination,
                           proveedores=proveedores,
                           meses_lista=meses_lista,
                           mes_seleccionado=mes,
                           ano_seleccionado=ano,
                           prov_seleccionado=prov_id or 0)


@purchasing_bp.route('/orden/nueva', methods=['POST'])
@login_required
@check_org_permission
@check_permission('perm_create_oc_standard')
def nueva_orden():
    try:
        from collections import Counter, defaultdict
        # Each checkbox submits "producto_id:almacen_id"
        pares = []
        for raw in request.form.getlist('item'):
            partes = raw.split(':')
            if len(partes) == 2 and partes[0].isdigit() and partes[1].isdigit():
                pares.append((int(partes[0]), int(partes[1])))

        if not pares:
            flash('No se seleccionaron productos válidos.', 'danger')
            return redirect(url_for('main.index'))

        org_id = current_user.organizacion_id
        pids = [p for p, _ in pares]
        aids = list({a for _, a in pares})

        productos_map = {p.id: p for p in Producto.query.filter(Producto.id.in_(pids)).all()}
        if current_user.rol != 'super_admin':
            for p in productos_map.values():
                if p.organizacion_id != org_id:
                    flash('Error: Intento de ordenar un producto no válido.', 'danger')
                    return redirect(url_for('main.index'))

        # Validate almacenes belong to the org; also load objects for names
        almacenes_obj = {
            a.id: a for a in Almacen.query.filter(
                Almacen.id.in_(aids), Almacen.organizacion_id == org_id
            ).all()
        }
        if current_user.rol != 'super_admin' and len(almacenes_obj) != len(aids):
            flash('Error: almacén no pertenece a tu organización.', 'danger')
            return redirect(url_for('main.index'))

        proveedores = {productos_map[pid].proveedor_id for pid, _ in pares if pid in productos_map}
        if len(proveedores) != 1:
            flash('Error: Los productos seleccionados deben ser del mismo proveedor.', 'danger')
            return redirect(url_for('main.index'))
        proveedor_id_comun = proveedores.pop()

        # Header almacen = most frequent (keeps legacy templates happy)
        alm_counter = Counter(a for _, a in pares)
        almacen_dominante_id = alm_counter.most_common(1)[0][0]

        nueva_oc = OrdenCompra(
            proveedor_id=proveedor_id_comun,
            estado='borrador',
            creador_id=current_user.id,
            organizacion_id=org_id,
            almacen_id=almacen_dominante_id,
        )
        db.session.add(nueva_oc)

        # Group by producto_id: mismo producto en distintos almacenes → 1 detalle
        # con cantidad total; distribucion_almacenes guarda el reparto por almacén.
        grupos: dict = defaultdict(dict)  # {prod_id: {alm_id: cantidad}}
        for prod_id, alm_id in pares:
            if prod_id not in productos_map:
                continue
            stock_item = Stock.query.filter_by(producto_id=prod_id, almacen_id=alm_id).first()
            cant = max(1, (stock_item.stock_maximo - stock_item.cantidad) if stock_item else 5)
            grupos[prod_id][alm_id] = grupos[prod_id].get(alm_id, 0) + cant

        for prod_id, alm_cantidades in grupos.items():
            prod = productos_map[prod_id]
            costo_unitario = getattr(prod, 'precio_unitario', getattr(prod, 'costo', 0))
            factor_empaque = getattr(prod, 'unidades_por_caja', 1) or 1
            cantidad_total = sum(alm_cantidades.values())
            items = list(alm_cantidades.items())  # [(alm_id, cantidad), ...]

            detalle = OrdenCompraDetalle(
                orden=nueva_oc,
                producto_id=prod_id,
                cantidad_solicitada=cantidad_total,
                costo_unitario_estimado=costo_unitario,
                cajas=cantidad_total / factor_empaque,
            )
            if len(items) == 1:
                detalle.almacen_id = items[0][0]
            else:
                detalle.almacen_id = None
                detalle.distribucion_almacenes = [
                    {
                        'almacen_id': aid,
                        'almacen_nombre': almacenes_obj[aid].nombre if aid in almacenes_obj else f'Almacén #{aid}',
                        'cantidad': c,
                        'recibida': 0,
                    }
                    for aid, c in items
                ]
            db.session.add(detalle)

        db.session.commit()
        flash('Nueva Orden de Compra generada en "Borrador".', 'success')
        return redirect(url_for('purchasing.lista_ordenes'))

    except Exception as e:
        db.session.rollback()
        _flash_err('Error al generar la orden.', e)
        return redirect(url_for('main.index'))


@purchasing_bp.route('/ordenes/recibir/<int:id>', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_create_oc_standard')
def recibir_orden(id):
    orden = (
        OrdenCompra.query
        .filter_by(id=id, organizacion_id=current_user.organizacion_id)
        .options(selectinload(OrdenCompra.detalles).joinedload(OrdenCompraDetalle.producto))
        .first_or_404()
    )

    if orden.estado not in ('enviada', 'recibida_parcial'):
        flash('Solo se pueden recibir órdenes en estado "Enviada" o "Recibida parcial".', 'warning')
        return redirect(url_for('purchasing.ver_orden', id=id))

    if request.method == 'GET':
        return render_template('orden_recibir.html', orden=orden)

    try:
        org_id = orden.organizacion_id
        procesados = 0
        omitidos = []

        with db.session.no_autoflush:
            for detalle in orden.detalles:
                producto = detalle.producto
                if not producto:
                    omitidos.append(f'detalle #{detalle.id} (producto eliminado)')
                    continue

                try:
                    recibir_ahora = int(request.form.get(f'recibir_{detalle.id}', 0))
                except (ValueError, TypeError):
                    recibir_ahora = 0

                pendiente = detalle.cantidad_pendiente
                recibir_ahora = max(0, min(recibir_ahora, pendiente))
                if recibir_ahora <= 0:
                    continue

                if detalle.distribucion_almacenes:
                    # Multi-warehouse: distribuir en orden (llena primer almacén, luego siguiente)
                    dist_list = [dict(d) for d in detalle.distribucion_almacenes]
                    remaining = recibir_ahora
                    for dist in dist_list:
                        if remaining <= 0:
                            break
                        pendiente_alm = dist['cantidad'] - dist.get('recibida', 0)
                        if pendiente_alm <= 0:
                            continue
                        recibir_alm = min(remaining, pendiente_alm)
                        alm = Almacen.query.filter_by(
                            id=dist['almacen_id'], organizacion_id=org_id
                        ).first()
                        if not alm:
                            omitidos.append(
                                f'{producto.nombre} → {dist.get("almacen_nombre","?")} (almacén no encontrado)'
                            )
                            continue
                        stock_item = Stock.query.filter_by(
                            producto_id=producto.id, almacen_id=alm.id
                        ).first()
                        if stock_item:
                            stock_item.cantidad += recibir_alm
                        else:
                            db.session.add(Stock(
                                producto_id=producto.id, almacen_id=alm.id,
                                cantidad=recibir_alm, stock_minimo=5, stock_maximo=100,
                            ))
                        db.session.add(Movimiento(
                            producto_id=producto.id, cantidad=recibir_alm, tipo='entrada',
                            fecha=now_mx(),
                            motivo=f'Recepción OC #{orden.id} → {alm.nombre}',
                            orden_compra_id=orden.id, organizacion_id=org_id,
                            almacen_id=alm.id,
                        ))
                        dist['recibida'] = dist.get('recibida', 0) + recibir_alm
                        remaining -= recibir_alm
                    detalle.distribucion_almacenes = dist_list
                    flag_modified(detalle, 'distribucion_almacenes')
                    detalle.cantidad_recibida = sum(d.get('recibida', 0) for d in dist_list)
                else:
                    alm_destino = detalle.almacen_id or orden.almacen_id
                    if not alm_destino:
                        omitidos.append(f'{producto.nombre} (sin almacén destino)')
                        continue
                    stock_item = Stock.query.filter_by(
                        producto_id=producto.id, almacen_id=alm_destino
                    ).first()
                    if stock_item:
                        stock_item.cantidad += recibir_ahora
                    else:
                        db.session.add(Stock(
                            producto_id=producto.id, almacen_id=alm_destino,
                            cantidad=recibir_ahora, stock_minimo=5, stock_maximo=100,
                        ))
                    db.session.add(Movimiento(
                        producto_id=producto.id, cantidad=recibir_ahora, tipo='entrada',
                        fecha=now_mx(), motivo=f'Recepción de OC #{orden.id}',
                        orden_compra_id=orden.id, organizacion_id=org_id,
                        almacen_id=alm_destino,
                    ))
                    detalle.cantidad_recibida = (detalle.cantidad_recibida or 0) + recibir_ahora
                procesados += 1

        if procesados == 0:
            flash('No se indicó ninguna cantidad a recibir.', 'warning')
            return redirect(url_for('purchasing.recibir_orden', id=id))

        nombre_alm = orden.almacen.nombre if orden.almacen else 'múltiples almacenes'
        if orden.totalmente_recibida:
            orden.estado = 'recibida'
            orden.fecha_recepcion = now_mx()
            resumen = f'{procesados} producto(s) ingresados — recepción completa'
            titulo_push = '📦 OC Recibida'
        else:
            orden.estado = 'recibida_parcial'
            resumen = f'{procesados} producto(s) ingresados parcialmente'
            titulo_push = '📦 OC Parcialmente Recibida'

        log_actividad('recibir_oc', 'orden_compra',
                      f'OC #{orden.id} — {resumen} (almacén: {nombre_alm})',
                      entidad_id=orden.id)
        db.session.commit()

        flash(f'{resumen}.', 'success')
        if omitidos:
            flash(f'Ítems omitidos: {", ".join(omitidos)}.', 'warning')

        _enviar_push_notificacion(
            org_id=org_id,
            titulo=titulo_push,
            cuerpo=f'OC #{orden.id} de {orden.proveedor.nombre} — {resumen}.',
            url=url_for('purchasing.ver_orden', id=orden.id),
        )

    except Exception as e:
        db.session.rollback()
        _flash_err('Error al recibir la orden. Verifica los datos e intenta de nuevo.', e)

    return redirect(url_for('purchasing.ver_orden', id=id))


@purchasing_bp.route('/orden/<int:id>/enviar', methods=['POST'])
@login_required
@check_permission('perm_create_oc_standard')
def enviar_orden(id):
    orden = OrdenCompra.query.filter_by(
        id=id, organizacion_id=current_user.organizacion_id
    ).first_or_404()

    if orden.estado in ['borrador', 'Pendiente']:
        try:
            orden.estado = 'enviada'
            db.session.commit()
            flash('Orden marcada como "Enviada".', 'info')
        except Exception as e:
            db.session.rollback()
            _flash_err('Error al procesar la operación.', e)

    return redirect(url_for('purchasing.lista_ordenes'))


@purchasing_bp.route('/orden/<int:id>/pdf')
@login_required
@check_permission('perm_create_oc_standard')
def generar_oc_pdf(id):
    orden = (
        OrdenCompra.query
        .filter_by(id=id, organizacion_id=current_user.organizacion_id)
        .options(
            joinedload(OrdenCompra.proveedor),
            joinedload(OrdenCompra.almacen),
            selectinload(OrdenCompra.detalles).joinedload(OrdenCompraDetalle.producto),
        )
        .first_or_404()
    )
    org = orden.organizacion
    proveedor = orden.proveedor

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=inch, leftMargin=inch,
                            topMargin=0.5*inch, bottomMargin=inch)
    story = []
    styles = getSampleStyleSheet()
    fuente, c_pri, c_sec = _pdf_estilos(org)

    s_normal = ParagraphStyle('OCNorm',  fontName=fuente, fontSize=10, leading=12)
    s_bold   = ParagraphStyle('OCBold',  fontName=_pdf_bold(fuente), fontSize=10, leading=12)
    s_brand  = ParagraphStyle('OCBrand', fontName=_pdf_bold(fuente), fontSize=18, leading=20, textColor=colors.black)
    s_th     = ParagraphStyle('OCTH',    fontName=_pdf_bold(fuente), fontSize=10, textColor=colors.white, alignment=TA_CENTER)
    s_totlbl = ParagraphStyle('OCTotL',  fontName=_pdf_bold(fuente), fontSize=11, alignment=TA_RIGHT)
    s_totval = ParagraphStyle('OCTotV',  fontName=_pdf_bold(fuente), fontSize=11, alignment=TA_RIGHT)

    _pdf_header(story, org, styles)

    p_email    = getattr(proveedor, 'contacto_email',    getattr(proveedor, 'correo',   '-'))
    p_tel      = getattr(proveedor, 'contacto_telefono', getattr(proveedor, 'telefono', '-'))
    p_contacto = getattr(proveedor, 'nombre_contacto',   getattr(proveedor, 'contacto', '-'))

    info_proveedor = [
        Paragraph("<b>PROVEEDOR:</b>", s_normal),
        Paragraph(proveedor.nombre, s_bold),
        Paragraph(f"Contacto: {p_contacto}", s_normal),
        Paragraph(f"Email: {p_email}", s_normal),
        Paragraph(f"Tel: {p_tel}", s_normal),
    ]
    info_orden = [
        Paragraph(f"<b>ORDEN DE COMPRA #{orden.id}</b>", s_brand),
        Paragraph(f"<b>Fecha:</b> {orden.fecha_creacion.strftime('%d/%m/%Y')}", s_normal),
        Paragraph(f"<b>Estado:</b> {orden.estado.upper()}", s_normal),
        Paragraph(f"<b>Almacén:</b> {orden.almacen.nombre if orden.almacen else 'General'}", s_normal),
    ]
    t_info = Table([[info_proveedor, info_orden]], colWidths=[3.5*inch, 2.7*inch])
    t_info.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('LEFTPADDING', (0,0), (-1,-1), 0)]))
    story.append(t_info)
    story.append(Spacer(1, 0.2*inch))

    data_table = [[
        Paragraph("Producto / SKU", s_th), Paragraph("Cajas", s_th),
        Paragraph("Unidades", s_th),       Paragraph("Costo U.", s_th),
        Paragraph("Subtotal", s_th),
    ]]
    total_general = 0
    for detalle in orden.detalles:
        subtotal = detalle.cantidad_solicitada * detalle.costo_unitario_estimado
        total_general += subtotal
        factor_empaque = getattr(detalle.producto, 'unidades_por_caja', 1) or 1
        cajas = getattr(detalle, 'cajas', 0)
        enlace_url = getattr(detalle, 'enlace_proveedor', None) or getattr(detalle.producto, 'enlace_proveedor', None)
        _nombre = _xml_escape(detalle.producto.nombre)
        _codigo = _xml_escape(detalle.producto.codigo or '')
        desc = (f"<b>{_nombre}</b><br/>SKU: {_codigo}<br/>"
                f"<font color='gray' size='8'>Empaque: {factor_empaque} ud(s)</font>")
        if enlace_url:
            display_url = _xml_escape((enlace_url[:50] + '...') if len(enlace_url) > 53 else enlace_url)
            desc += f"<br/><font color='blue' size='7'>{display_url}</font>"
        data_table.append([
            Paragraph(desc, s_normal),
            Paragraph(f"{cajas:g}" if cajas else "0", s_normal),
            Paragraph(str(int(detalle.cantidad_solicitada)), s_normal),
            Paragraph(f"${detalle.costo_unitario_estimado:,.2f}", s_normal),
            Paragraph(f"${subtotal:,.2f}", s_normal),
        ])
    data_table.append(['', '', '', Paragraph("TOTAL:", s_totlbl), Paragraph(f"${total_general:,.2f}", s_totval)])

    t_productos = Table(data_table, colWidths=[2.4*inch, 0.8*inch, 0.8*inch, 1.0*inch, 1.2*inch], repeatRows=1)
    row_bgs = _pdf_row_styles(len(data_table) - 1, c_sec)
    t_productos.setStyle(TableStyle([
        ('BACKGROUND',    (0,0),  (-1,0),  c_pri),
        ('TEXTCOLOR',     (0,0),  (-1,0),  colors.white),
        ('ALIGN',         (0,0),  (-1,0),  'CENTER'),
        ('VALIGN',        (0,0),  (-1,-1), 'MIDDLE'),
        ('GRID',          (0,0),  (-1,-2), 0.5, colors.HexColor('#DEE2E6')),
        ('ALIGN',         (1,1),  (2,-2),  'CENTER'),
        ('ALIGN',         (3,1),  (-1,-1), 'RIGHT'),
        ('TOPPADDING',    (0,0),  (-1,-1), 6),
        ('BOTTOMPADDING', (0,0),  (-1,-1), 6),
        ('SPAN',          (0,-1), (2,-1)),
        ('LINEABOVE',     (0,-1), (-1,-1), 1, colors.HexColor('#DEE2E6')),
        ('BACKGROUND',    (3,-1), (-1,-1), colors.whitesmoke),
        ('BOX',           (3,-1), (4,-1),  0.5, colors.HexColor('#DEE2E6')),
    ] + row_bgs))
    story.append(t_productos)

    _pdf_footer(story, org)
    doc.build(story)
    buffer.seek(0)
    filename = f"OC_{orden.id}_{secure_filename(org.nombre)}.pdf"
    return send_file(buffer, as_attachment=False, download_name=filename, mimetype='application/pdf')


@purchasing_bp.route('/orden/nueva/manual', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_create_oc_standard')
def nueva_orden_manual():
    org_id = current_user.organizacion_id

    if request.method == 'POST':
        try:
            proveedor_id = request.form.get('proveedor_id', type=int)
            almacen_id   = request.form.get('almacen_id', type=int)

            if not proveedor_id:
                flash("Debes seleccionar un proveedor.", "warning")
                return redirect(request.url)
            if not Proveedor.query.filter_by(id=proveedor_id, organizacion_id=org_id).first():
                flash("Proveedor no autorizado.", "danger")
                return redirect(request.url)
            if almacen_id and not Almacen.query.filter_by(id=almacen_id, organizacion_id=org_id).first():
                flash("Almacén no autorizado.", "danger")
                return redirect(request.url)

            nueva_oc = OrdenCompra(
                proveedor_id=proveedor_id,
                organizacion_id=org_id,
                creador_id=current_user.id,
                estado='borrador',
                almacen_id=almacen_id if almacen_id else None,
            )
            db.session.add(nueva_oc)
            db.session.flush()

            productos_ids  = request.form.getlist('producto_id[]')
            cantidades     = request.form.getlist('cantidad[]')
            costos         = request.form.getlist('costo[]')
            cajas_lista    = request.form.getlist('cajas[]')
            enlaces_lista  = request.form.getlist('enlace[]')

            for i in range(len(productos_ids)):
                pid_raw = productos_ids[i]
                if not pid_raw:
                    continue
                try:
                    pid  = int(pid_raw)
                    cant = int(float(cantidades[i]))
                except (ValueError, TypeError, IndexError):
                    continue
                if cant <= 0:
                    continue
                if not Producto.query.filter_by(id=pid, organizacion_id=org_id).first():
                    continue

                try:
                    cajas_val = float(cajas_lista[i])
                except (IndexError, ValueError, TypeError):
                    cajas_val = 0.0
                try:
                    enlace_val = enlaces_lista[i]
                except IndexError:
                    enlace_val = ''

                db.session.add(OrdenCompraDetalle(
                    orden_id=nueva_oc.id,
                    producto_id=pid,
                    cantidad_solicitada=cant,
                    costo_unitario_estimado=float(costos[i]) if i < len(costos) else 0,
                    cajas=cajas_val,
                    enlace_proveedor=enlace_val,
                ))

            db.session.commit()
            flash(f"Orden #{nueva_oc.id} creada exitosamente en estado borrador.", "success")
            return redirect(url_for('purchasing.lista_ordenes'))

        except Exception as e:
            db.session.rollback()
            _flash_err('Error al crear la orden.', e)
            return redirect(request.url)

    proveedores = Proveedor.query.filter_by(organizacion_id=org_id).all()
    almacenes   = Almacen.query.filter_by(organizacion_id=org_id).all()
    productos_lista = [
        {
            'id': p.id, 'nombre': p.nombre, 'codigo': p.codigo,
            'precio_unitario': getattr(p, 'precio_unitario', getattr(p, 'costo', 0)),
            'proveedor_id': p.proveedor_id,
            'unidades_por_caja': getattr(p, 'unidades_por_caja', 1),
            'enlace': getattr(p, 'enlace_proveedor', ''),
        }
        for p in Producto.query.filter_by(organizacion_id=org_id).all()
    ]

    return render_template('orden_form.html',
                           titulo="Nueva Orden de Compra",
                           orden=None,
                           proveedores=proveedores,
                           productos=productos_lista,
                           almacenes=almacenes)


@purchasing_bp.route('/orden/<int:id>')
@login_required
@check_org_permission
@check_permission('perm_view_dashboard')
def ver_orden(id):
    orden = (
        OrdenCompra.query
        .filter_by(id=id, organizacion_id=current_user.organizacion_id)
        .options(
            joinedload(OrdenCompra.proveedor),
            joinedload(OrdenCompra.almacen),
            selectinload(OrdenCompra.detalles).joinedload(OrdenCompraDetalle.producto),
        )
        .first_or_404()
    )
    return render_template('orden_detalle.html', orden=orden, titulo=f"Detalle de Orden #{orden.id}")


@purchasing_bp.route('/ordenes/<int:id>/exportar-hd-csv')
@login_required
@check_org_permission
def exportar_hd_csv(id):
    if current_user.rol not in ('super_admin', 'admin'):
        flash('Solo administradores pueden exportar órdenes.', 'danger')
        return redirect(url_for('purchasing.ver_orden', id=id))

    orden = OrdenCompra.query.filter_by(
        id=id, organizacion_id=current_user.organizacion_id
    ).first_or_404()

    from integrations.hd_quickorder import generar_csv
    csv_bytes, omitidos = generar_csv(orden)

    if not csv_bytes.strip().splitlines()[1:]:
        flash('La orden no tiene ítems válidos para exportar.', 'warning')
        return redirect(url_for('purchasing.ver_orden', id=id))

    response = make_response(csv_bytes)
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename="hd-quickorder-oc{id}.csv"'
    if omitidos:
        response.headers['X-HD-Omitidos'] = ', '.join(omitidos[:10])
    return response


@purchasing_bp.route('/proyecto-oc/<int:id>/exportar-hd-csv')
@login_required
@check_org_permission
@check_permission('perm_create_oc_proyecto')
def exportar_proyecto_hd_csv(id):
    if current_user.rol not in ('super_admin', 'admin'):
        flash('Solo administradores pueden exportar órdenes.', 'danger')
        return redirect(url_for('purchasing.ver_proyecto_oc', id=id))

    proyecto_oc = get_item_or_404(ProyectoOC, id)

    from integrations.hd_quickorder import generar_csv_proyecto
    csv_bytes, omitidos, exportados = generar_csv_proyecto(proyecto_oc)

    if exportados == 0:
        flash('No hay ítems válidos para exportar a HD Pro Quick Order.', 'warning')
        return redirect(url_for('purchasing.ver_proyecto_oc', id=id))

    response = make_response(csv_bytes)
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename="hd-quickorder-proy{id}.csv"'
    if omitidos:
        response.headers['X-HD-Omitidos'] = ', '.join(omitidos[:10])
    return response


@purchasing_bp.route('/ordenes/<int:id>/exportar-formato-proveedor')
@login_required
@check_org_permission
def exportar_formato_proveedor(id):
    if current_user.rol not in ('super_admin', 'admin'):
        flash('Solo administradores pueden exportar órdenes.', 'danger')
        return redirect(url_for('purchasing.ver_orden', id=id))

    org_id = current_user.organizacion_id
    orden  = OrdenCompra.query.filter_by(id=id, organizacion_id=org_id).first_or_404()

    formato = FormatoProveedor.query.filter_by(
        proveedor_id=orden.proveedor_id, organizacion_id=org_id, activo=True
    ).first()
    if not formato:
        flash('Este proveedor no tiene un formato de OC configurado o está inactivo.', 'warning')
        return redirect(url_for('purchasing.ver_orden', id=id))

    from integrations.formato_proveedor import generar_archivo
    try:
        archivo_bytes, mimetype, omitidos = generar_archivo(orden, formato)
    except ValueError as e:
        flash(str(e), 'warning')
        return redirect(url_for('purchasing.ver_orden', id=id))
    except Exception as e:
        _flash_err('Error al generar el archivo del proveedor.', e)
        return redirect(url_for('purchasing.ver_orden', id=id))

    ext = 'csv' if 'csv' in mimetype else 'xlsx'
    nombre = formato.nombre_archivo.replace('{id}', str(orden.id))
    response = make_response(archivo_bytes)
    response.headers['Content-Type'] = mimetype
    response.headers['Content-Disposition'] = f'attachment; filename="{nombre}.{ext}"'
    if omitidos:
        response.headers['X-Formato-Omitidos'] = ', '.join(omitidos[:10])
    return response


@purchasing_bp.route('/ordenes/<int:id>/subir-hd-auto', methods=['POST'])
@login_required
@check_org_permission
def subir_hd_auto(id):
    if current_user.rol not in ('super_admin', 'admin'):
        return jsonify({'error': 'Sin permiso'}), 403

    org_id = current_user.organizacion_id
    orden  = OrdenCompra.query.filter_by(id=id, organizacion_id=org_id).first_or_404()

    if orden.integracion_status == 'procesando':
        return jsonify({'error': 'Ya hay un envío en proceso'}), 409

    integracion = ProveedorIntegracion.query.filter_by(
        proveedor_id=orden.proveedor_id, organizacion_id=org_id, activo=True,
    ).first()
    if not integracion:
        return jsonify({'error': 'Este proveedor no tiene integración activa'}), 400

    creds = integracion.credenciales
    if not creds.get('usuario') or not creds.get('password'):
        return jsonify({'error': 'Credenciales de HD Pro incompletas'}), 400

    from integrations.hd_quickorder import generar_csv
    csv_bytes, omitidos_csv = generar_csv(orden)

    lineas = [l for l in csv_bytes.decode().splitlines() if l.strip()][1:]
    if not lineas:
        return jsonify({'error': 'La orden no tiene ítems válidos para subir'}), 400

    orden.integracion_status   = 'procesando'
    orden.integracion_resultado = None
    db.session.commit()

    sesion   = HDSesion.query.filter_by(org_id=org_id, proveedor_id=orden.proveedor_id).first()
    app_ref  = current_app._get_current_object()

    def _worker(app, oc_id, credenciales, csv_b, sesion_obj, org, prov_id):
        with app.app_context():
            from integrations.hd_quickorder import subir_csv_auto
            try:
                resultado = subir_csv_auto(
                    credenciales=credenciales, csv_bytes=csv_b,
                    sesion=sesion_obj, db=db, HDSesion=HDSesion,
                    org_id=org, proveedor_id=prov_id,
                )
            except Exception as exc:
                resultado = {'ok': False, 'error': str(exc), 'items_agregados': 0, 'items_omitidos': []}
            oc = OrdenCompra.query.get(oc_id)
            if oc:
                if resultado.get('ok'):
                    oc.integracion_status   = 'listo'
                    oc.integracion_resultado = json.dumps({
                        'agregados': resultado.get('items_agregados', 0),
                        'omitidos':  resultado.get('items_omitidos', []),
                        'cart_url':  resultado.get('carrito_url', ''),
                    }, ensure_ascii=False)
                else:
                    oc.integracion_status   = 'error'
                    oc.integracion_resultado = json.dumps({'error': resultado.get('error', 'desconocido')})
                db.session.commit()

    Thread(
        target=_worker,
        args=(app_ref, id, creds, csv_bytes, sesion, org_id, orden.proveedor_id),
        daemon=True,
    ).start()
    return jsonify({'status': 'procesando'}), 202

# enviar_oc_homedepot e integracion_status_oc viven en api/routes.py (rutas /api/…)


@purchasing_bp.route('/orden/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_create_oc_standard')
def editar_orden(id):
    orden = OrdenCompra.query.filter_by(
        id=id, organizacion_id=current_user.organizacion_id
    ).first_or_404()

    if orden.estado != 'borrador':
        flash('Solo se pueden editar órdenes en estado "Borrador".', 'warning')
        return redirect(url_for('purchasing.ver_orden', id=id))

    org_id     = orden.organizacion_id
    proveedores = Proveedor.query.filter_by(organizacion_id=org_id).all()
    almacenes   = Almacen.query.filter_by(organizacion_id=org_id).all()
    productos_lista = [
        {
            'id': p.id, 'nombre': p.nombre, 'codigo': p.codigo,
            'precio_unitario': getattr(p, 'precio_unitario', getattr(p, 'costo', 0)),
            'proveedor_id': p.proveedor_id,
            'unidades_por_caja': getattr(p, 'unidades_por_caja', 1),
            'enlace': getattr(p, 'enlace_proveedor', ''),
        }
        for p in Producto.query.filter_by(organizacion_id=org_id).all()
    ]

    if request.method == 'POST':
        try:
            orden.proveedor_id = request.form.get('proveedor_id')
            OrdenCompraDetalle.query.filter_by(orden_id=orden.id).delete()

            productos_ids = request.form.getlist('producto_id[]')
            cantidades    = request.form.getlist('cantidad[]')
            costos        = request.form.getlist('costo[]')
            cajas_lista   = request.form.getlist('cajas[]')
            enlaces_lista = request.form.getlist('enlace[]')

            if not productos_ids:
                flash('La orden debe tener al menos un producto.', 'danger')
                db.session.rollback()
                return render_template('orden_form.html',
                                       titulo=f"Editar Orden de Compra #{orden.id}",
                                       proveedores=proveedores, productos=productos_lista,
                                       almacenes=almacenes, orden=orden)

            for i in range(len(productos_ids)):
                prod_id = productos_ids[i]
                cant    = cantidades[i]
                cost    = costos[i]
                if not prod_id or not cant or not cost:
                    continue
                if not Producto.query.filter_by(id=int(prod_id), organizacion_id=org_id).first():
                    continue

                try:
                    cajas_val = float(cajas_lista[i])
                except (IndexError, ValueError, TypeError):
                    cajas_val = 0.0
                try:
                    enlace_val = enlaces_lista[i]
                except IndexError:
                    enlace_val = ''

                db.session.add(OrdenCompraDetalle(
                    orden_id=orden.id,
                    producto_id=int(prod_id),
                    cantidad_solicitada=int(cant),
                    costo_unitario_estimado=float(cost),
                    cajas=cajas_val,
                    enlace_proveedor=enlace_val,
                ))

            db.session.commit()
            flash('Orden de Compra actualizada exitosamente.', 'success')
            return redirect(url_for('purchasing.ver_orden', id=id))

        except Exception as e:
            db.session.rollback()
            _flash_err('Error al actualizar la orden.', e)
            return render_template('orden_form.html',
                                   titulo=f"Editar Orden de Compra #{orden.id}",
                                   proveedores=proveedores, productos=productos_lista,
                                   almacenes=almacenes, orden=orden)

    return render_template('orden_form.html',
                           titulo=f"Editar Orden de Compra #{orden.id}",
                           proveedores=proveedores, productos=productos_lista,
                           almacenes=almacenes, orden=orden)


@purchasing_bp.route('/orden/<int:id>/cancelar', methods=['POST'])
@login_required
@check_permission('perm_create_oc_standard')
def cancelar_orden(id):
    orden = get_item_or_404(OrdenCompra, id)

    if orden.estado != 'borrador':
        flash('Error: Solo se pueden cancelar órdenes en estado "Borrador".', 'danger')
        return redirect(url_for('purchasing.lista_ordenes'))

    try:
        orden.estado = 'cancelada'
        orden.cancelado_por_id = current_user.id
        db.session.commit()
        flash('Orden de Compra cancelada exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        _flash_err('Error al cancelar la orden.', e)

    return redirect(url_for('purchasing.lista_ordenes'))


@purchasing_bp.route('/orden/<int:id>/eliminar', methods=['POST'])
@login_required
@check_permission('perm_create_oc_standard')
def eliminar_orden(id):
    orden = OrdenCompra.query.filter_by(
        id=id, organizacion_id=current_user.organizacion_id
    ).first_or_404()

    if orden.estado in ('recibida', 'recibida_parcial'):
        flash('No se pueden eliminar órdenes ya recibidas (el stock ya fue ingresado).', 'danger')
        return redirect(url_for('purchasing.lista_ordenes'))

    estado_anterior = orden.estado
    try:
        OrdenCompraDetalle.query.filter_by(orden_id=orden.id).delete()
        db.session.delete(orden)
        db.session.commit()
        if estado_anterior == 'Pendiente':
            flash(f'Orden #{id} cancelada y eliminada correctamente.', 'success')
        else:
            flash(f'Orden #{id} eliminada del historial.', 'info')
    except Exception as e:
        db.session.rollback()
        _flash_err('Error al eliminar la orden.', e)

    return redirect(url_for('purchasing.lista_ordenes'))


# ==============================================================================
# ÓRDENES DE COMPRA DE PROYECTO
# ==============================================================================

@purchasing_bp.route('/proyectos-oc')
@login_required
@check_org_permission
@check_permission('perm_create_oc_proyecto')
def lista_proyectos_oc():
    org_id = current_user.organizacion_id
    query  = ProyectoOC.query if current_user.rol == 'super_admin' else ProyectoOC.query.filter_by(organizacion_id=org_id)

    mes           = request.args.get('mes',    type=int)
    ano           = request.args.get('ano',    type=int)
    estado_filtro = request.args.get('estado', '')

    if mes:           query = query.filter(extract('month', ProyectoOC.fecha_creacion) == mes)
    if ano:           query = query.filter(extract('year',  ProyectoOC.fecha_creacion) == ano)
    if estado_filtro: query = query.filter(ProyectoOC.estado == estado_filtro)

    proyectos_oc = query.order_by(ProyectoOC.fecha_creacion.desc()).all()
    proyectos = (
        ProyectoOC.query.filter_by(organizacion_id=org_id)
                  .with_entities(ProyectoOC.id, ProyectoOC.nombre_proyecto).distinct().all()
        if current_user.rol != 'super_admin' else
        ProyectoOC.query.with_entities(ProyectoOC.id, ProyectoOC.nombre_proyecto).all()
    )

    return render_template('proyecto_oc_lista.html',
                           proyectos_oc=proyectos_oc, proyectos=proyectos,
                           mes_sel=mes, ano_sel=ano, estado_sel=estado_filtro,
                           titulo="OC de Proyectos")


@purchasing_bp.route('/proyecto-oc/<int:id>')
@login_required
@check_org_permission
@check_permission('perm_create_oc_proyecto')
def ver_proyecto_oc(id):
    org_id = current_user.organizacion_id
    proyecto_oc = (
        ProyectoOC.query
        .filter_by(id=id, organizacion_id=org_id)
        .options(
            joinedload(ProyectoOC.almacen),
            selectinload(ProyectoOC.detalles).joinedload(ProyectoOCDetalle.producto),
        )
        .first_or_404()
    )
    solicitud_pendiente = SolicitudAprobacion.query.filter_by(
        entidad_tipo='proyecto_oc',
        entidad_id=proyecto_oc.id,
        estado='pendiente',
        organizacion_id=proyecto_oc.organizacion_id,
    ).first()
    return render_template('proyecto_oc_detalle.html',
                           proyecto_oc=proyecto_oc,
                           solicitud_pendiente=solicitud_pendiente,
                           titulo=f"OC Proyecto #{proyecto_oc.id} — {proyecto_oc.nombre_proyecto}")


@purchasing_bp.route('/proyecto-oc/nueva', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_create_oc_proyecto')
def nuevo_proyecto_oc():
    org_id = current_user.organizacion_id

    productos_lista = [
        {'id': p.id, 'nombre': p.nombre, 'codigo': p.codigo,
         'precio_unitario': p.precio_unitario or getattr(p, 'costo', 0) or 0}
        for p in Producto.query.filter_by(organizacion_id=org_id).all()
    ]
    proveedores_lista = [
        {'id': p.id, 'nombre': p.nombre}
        for p in Proveedor.query.filter_by(organizacion_id=org_id).order_by(Proveedor.nombre).all()
    ]
    almacenes = Almacen.query.filter_by(organizacion_id=org_id).all()

    if request.method == 'POST':
        try:
            nombre_proyecto = request.form.get('nombre_proyecto')
            almacen_id      = request.form.get('almacen_id')

            if not nombre_proyecto:
                flash("El nombre del proyecto es obligatorio.", "danger")
                return render_template('proyecto_oc_form.html',
                                       titulo="Crear OC de Proyecto",
                                       productos=productos_lista,
                                       proveedores=proveedores_lista,
                                       almacenes=almacenes, orden=None)

            nueva_orden = ProyectoOC(
                nombre_proyecto=nombre_proyecto,
                creador_id=current_user.id,
                organizacion_id=org_id,
                almacen_id=int(almacen_id) if (almacen_id and almacen_id.isdigit()) else None,
                estado='borrador',
            )
            db.session.add(nueva_orden)
            db.session.flush()

            tipos                    = request.form.getlist('tipo_item[]')
            productos_existentes_ids = request.form.getlist('producto_id_existente[]')
            descripciones_nuevas     = request.form.getlist('descripcion_nuevo[]')
            cantidades               = request.form.getlist('cantidad[]')
            costos                   = request.form.getlist('costo_unitario[]')
            proveedores_sugeridos    = request.form.getlist('proveedor_sugerido[]')
            enlaces                  = request.form.getlist('enlace_proveedor[]')
            comentarios              = request.form.getlist('comentarios_detalle[]')

            for i in range(len(tipos)):
                if not cantidades[i] or float(cantidades[i]) <= 0:
                    continue
                detalle = ProyectoOCDetalle(
                    proyecto_oc_id=nueva_orden.id,
                    cantidad=float(cantidades[i]),
                    costo_unitario=float(costos[i]) if costos[i] else 0.0,
                    proveedor_sugerido=proveedores_sugeridos[i] if i < len(proveedores_sugeridos) else None,
                    enlace_proveedor=enlaces[i] if i < len(enlaces) else None,
                    comentarios_detalle=comentarios[i] if i < len(comentarios) else None,
                    descripcion_nuevo=descripciones_nuevas[i] if i < len(descripciones_nuevas) else "Sin descripción",
                )
                if tipos[i] == 'existente':
                    pid_raw = productos_existentes_ids[i] if i < len(productos_existentes_ids) else '0'
                    if pid_raw.isdigit() and int(pid_raw) > 0:
                        detalle.producto_id = int(pid_raw)
                db.session.add(detalle)

            db.session.commit()
            flash(f'OC de Proyecto #{nueva_orden.id} creada exitosamente.', 'success')
            return redirect(url_for('purchasing.lista_proyectos_oc'))

        except Exception as e:
            db.session.rollback()
            _flash_err('Error al guardar la OC de proyecto. Intenta de nuevo.', e)

    return render_template('proyecto_oc_form.html',
                           titulo="Crear OC de Proyecto",
                           productos=productos_lista,
                           proveedores=proveedores_lista,
                           almacenes=almacenes, orden=None)


@purchasing_bp.route('/proyecto-oc/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@check_permission('perm_create_oc_proyecto')
def editar_proyecto_oc(id):
    proyecto_oc = get_item_or_404(ProyectoOC, id)
    org_id = proyecto_oc.organizacion_id

    if proyecto_oc.estado != 'borrador':
        flash('Solo se pueden editar Órdenes de Proyecto en estado "Borrador".', 'warning')
        return redirect(url_for('purchasing.ver_proyecto_oc', id=id))

    if request.method == 'POST':
        try:
            proyecto_oc.nombre_proyecto = request.form.get('nombre_proyecto')
            almacen_id_val = request.form.get('almacen_id', type=int)
            proyecto_oc.almacen_id = almacen_id_val if almacen_id_val else None

            ProyectoOCDetalle.query.filter_by(proyecto_oc_id=id).delete()

            tipos                    = request.form.getlist('tipo_item[]')
            productos_existentes_ids = request.form.getlist('producto_id_existente[]')
            descripciones_nuevas     = request.form.getlist('descripcion_nuevo[]')
            cantidades               = request.form.getlist('cantidad[]')
            costos                   = request.form.getlist('costo_unitario[]')
            proveedores_sugeridos    = request.form.getlist('proveedor_sugerido[]')
            enlaces                  = request.form.getlist('enlace_proveedor[]')
            comentarios              = request.form.getlist('comentarios_detalle[]')

            for i in range(len(tipos)):
                if not cantidades[i] or float(cantidades[i]) <= 0:
                    continue
                detalle = ProyectoOCDetalle(
                    proyecto_oc_id=id,
                    cantidad=float(cantidades[i]),
                    costo_unitario=float(costos[i]) if costos[i] else 0.0,
                    proveedor_sugerido=proveedores_sugeridos[i] if i < len(proveedores_sugeridos) else None,
                    enlace_proveedor=enlaces[i] if i < len(enlaces) else None,
                    comentarios_detalle=comentarios[i] if i < len(comentarios) else None,
                    descripcion_nuevo=descripciones_nuevas[i] if i < len(descripciones_nuevas) else "Sin descripción",
                )
                if tipos[i] == 'existente':
                    prod_id_val = int(productos_existentes_ids[i]) if productos_existentes_ids[i].isdigit() else 0
                    if prod_id_val > 0:
                        detalle.producto_id = prod_id_val
                db.session.add(detalle)

            db.session.commit()
            flash(f'OC de Proyecto #{proyecto_oc.id} actualizada.', 'success')
            return redirect(url_for('purchasing.ver_proyecto_oc', id=id))

        except Exception as e:
            db.session.rollback()
            _flash_err('Error al actualizar la OC de Proyecto. Intenta de nuevo.', e)
            return redirect(url_for('purchasing.editar_proyecto_oc', id=id))

    productos_lista = [
        {'id': p.id, 'nombre': p.nombre, 'codigo': p.codigo,
         'precio_unitario': getattr(p, 'precio_unitario', getattr(p, 'costo', 0))}
        for p in Producto.query.filter_by(organizacion_id=org_id).all()
    ]
    proveedores_lista = [
        {'id': p.id, 'nombre': p.nombre}
        for p in Proveedor.query.filter_by(organizacion_id=org_id).order_by(Proveedor.nombre).all()
    ]
    almacenes = Almacen.query.filter_by(organizacion_id=org_id).all()
    detalles_json = [
        {
            'tipo': 'existente' if d.producto_id else 'nuevo',
            'producto_id': d.producto_id,
            'descripcion_nuevo': d.descripcion_nuevo,
            'cantidad': d.cantidad,
            'costo_unitario': d.costo_unitario,
            'proveedor_sugerido': d.proveedor_sugerido,
            'enlace_proveedor': d.enlace_proveedor,
            'comentarios_detalle': d.comentarios_detalle,
        }
        for d in proyecto_oc.detalles
    ]

    return render_template('proyecto_oc_form.html',
                           titulo=f"Editar OC de Proyecto #{proyecto_oc.id}",
                           productos=productos_lista,
                           proveedores=proveedores_lista,
                           almacenes=almacenes,
                           proyecto_oc=proyecto_oc,
                           detalles_json=detalles_json)


@purchasing_bp.route('/proyecto-oc/<int:id>/solicitar-aprobacion', methods=['POST'])
@login_required
@check_org_permission
@check_permission('perm_create_oc_proyecto')
def solicitar_aprobacion_oc(id):
    proyecto_oc = get_item_or_404(ProyectoOC, id)

    if proyecto_oc.estado != 'borrador':
        flash('Solo se puede solicitar aprobación desde estado Borrador.', 'danger')
        return redirect(url_for('purchasing.ver_proyecto_oc', id=id))
    if not proyecto_oc.detalles:
        flash('La OC debe tener al menos un ítem antes de solicitar aprobación.', 'warning')
        return redirect(url_for('purchasing.ver_proyecto_oc', id=id))

    try:
        proyecto_oc.estado = 'pendiente_aprobacion'
        db.session.add(SolicitudAprobacion(
            entidad_tipo='proyecto_oc',
            entidad_id=proyecto_oc.id,
            solicitante_id=current_user.id,
            organizacion_id=proyecto_oc.organizacion_id,
        ))
        log_actividad('solicitar_aprobacion', 'proyecto_oc',
                      f'OC Proyecto #{proyecto_oc.id} enviada a aprobación por {current_user.username}.',
                      entidad_id=proyecto_oc.id)
        db.session.commit()
        _enviar_push_notificacion(
            org_id=proyecto_oc.organizacion_id,
            titulo='Aprobación requerida',
            cuerpo=f'{current_user.username} solicita aprobar OC-PROY-{proyecto_oc.id}: {proyecto_oc.nombre_proyecto}',
            url='/aprobaciones',
        )
        flash('Solicitud de aprobación enviada. Un administrador revisará la OC.', 'success')
    except Exception as e:
        db.session.rollback()
        _flash_err('Error al procesar la operación.', e)

    return redirect(url_for('purchasing.ver_proyecto_oc', id=id))


@purchasing_bp.route('/proyecto-oc/<int:id>/enviar', methods=['POST'])
@login_required
@check_org_permission
@check_permission('perm_create_oc_proyecto')
def enviar_proyecto_oc(id):
    proyecto_oc = get_item_or_404(ProyectoOC, id)
    es_admin = current_user.rol in ['super_admin', 'admin']

    if not es_admin:
        flash('Solo los administradores pueden marcar una OC como enviada.', 'danger')
        return redirect(url_for('purchasing.ver_proyecto_oc', id=id))

    estados_validos = ['aprobada', 'borrador']
    if proyecto_oc.estado not in estados_validos:
        flash('La OC debe estar en borrador o aprobada antes de enviarse al proveedor.', 'danger')
        return redirect(url_for('purchasing.ver_proyecto_oc', id=id))

    try:
        proyecto_oc.estado     = 'enviada'
        proyecto_oc.fecha_envio = now_mx()
        log_actividad('enviar', 'proyecto_oc',
                      f'OC de Proyecto #{proyecto_oc.id} "{proyecto_oc.nombre_proyecto}" marcada como enviada.',
                      entidad_id=proyecto_oc.id)
        db.session.commit()
        flash(f'OC #{proyecto_oc.id} marcada como enviada al proveedor.', 'success')
    except Exception as e:
        db.session.rollback()
        _flash_err('Error al procesar la operación.', e)

    return redirect(url_for('purchasing.ver_proyecto_oc', id=id))


# ==============================================================================
# FLUJOS DE APROBACIÓN
# ==============================================================================

@purchasing_bp.route('/aprobaciones')
@login_required
@check_org_permission
def lista_aprobaciones():
    if current_user.rol not in ['super_admin', 'admin']:
        flash('No tienes permiso para ver las aprobaciones.', 'danger')
        return redirect(url_for('main.dashboard'))

    org_id        = current_user.organizacion_id
    estado_filtro = request.args.get('estado', 'pendiente')

    q = SolicitudAprobacion.query.filter_by(organizacion_id=org_id)
    if estado_filtro:
        q = q.filter_by(estado=estado_filtro)
    solicitudes = q.order_by(SolicitudAprobacion.creado_en.desc()).all()

    # Batch-fetch all referenced ProyectoOC objects to avoid N+1
    poc_ids = [s.entidad_id for s in solicitudes if s.entidad_tipo == 'proyecto_oc']
    ocs_map = (
        {p.id: p for p in ProyectoOC.query.filter(
            ProyectoOC.id.in_(poc_ids),
            ProyectoOC.organizacion_id == org_id,
        ).all()}
        if poc_ids else {}
    )

    items = []
    for s in solicitudes:
        ent, ent_url = None, '#'
        if s.entidad_tipo == 'proyecto_oc':
            ent     = ocs_map.get(s.entidad_id)
            ent_url = url_for('purchasing.ver_proyecto_oc', id=s.entidad_id)
        items.append({'s': s, 'ent': ent, 'ent_url': ent_url})

    pendientes = SolicitudAprobacion.query.filter_by(organizacion_id=org_id, estado='pendiente').count()

    return render_template('aprobaciones_inbox.html',
                           titulo='Aprobaciones', items=items,
                           estado_filtro=estado_filtro, pendientes=pendientes,
                           now=now_mx())


@purchasing_bp.route('/aprobacion/<int:id>/aprobar', methods=['POST'])
@login_required
@check_org_permission
def aprobar_solicitud(id):
    if current_user.rol not in ['super_admin', 'admin']:
        flash('No tienes permiso.', 'danger')
        return redirect(url_for('main.dashboard'))

    s = SolicitudAprobacion.query.filter_by(
        id=id, organizacion_id=current_user.organizacion_id
    ).first_or_404()

    if s.estado != 'pendiente':
        flash('Esta solicitud ya fue resuelta.', 'warning')
        return redirect(url_for('purchasing.lista_aprobaciones'))

    try:
        s.estado       = 'aprobado'
        s.aprobador_id = current_user.id
        s.resuelto_en  = now_mx()

        if s.entidad_tipo == 'proyecto_oc':
            oc = ProyectoOC.query.get(s.entidad_id)
            if oc:
                oc.estado = 'aprobada'
                log_actividad('aprobar', 'proyecto_oc',
                              f'OC Proyecto #{oc.id} aprobada por {current_user.username}.',
                              entidad_id=oc.id)

        db.session.commit()
        _enviar_push_notificacion(
            org_id=current_user.organizacion_id,
            titulo='OC Aprobada',
            cuerpo='Tu solicitud fue aprobada. Ya puede enviarse al proveedor.',
            url=f'/proyecto-oc/{s.entidad_id}' if s.entidad_tipo == 'proyecto_oc' else '/aprobaciones',
        )
        flash('Solicitud aprobada. La OC ya puede enviarse al proveedor.', 'success')
    except Exception as e:
        db.session.rollback()
        _flash_err('Error al procesar la operación.', e)

    return redirect(url_for('purchasing.lista_aprobaciones'))


@purchasing_bp.route('/aprobacion/<int:id>/rechazar', methods=['POST'])
@login_required
@check_org_permission
def rechazar_solicitud(id):
    if current_user.rol not in ['super_admin', 'admin']:
        flash('No tienes permiso.', 'danger')
        return redirect(url_for('main.dashboard'))

    s = SolicitudAprobacion.query.filter_by(
        id=id, organizacion_id=current_user.organizacion_id
    ).first_or_404()

    if s.estado != 'pendiente':
        flash('Esta solicitud ya fue resuelta.', 'warning')
        return redirect(url_for('purchasing.lista_aprobaciones'))

    try:
        comentario     = request.form.get('comentario', '').strip()
        s.estado       = 'rechazado'
        s.aprobador_id = current_user.id
        s.resuelto_en  = now_mx()
        s.comentario   = comentario or None

        if s.entidad_tipo == 'proyecto_oc':
            oc = ProyectoOC.query.get(s.entidad_id)
            if oc:
                oc.estado = 'borrador'
                log_actividad('rechazar', 'proyecto_oc',
                              f'OC Proyecto #{oc.id} rechazada por {current_user.username}. Motivo: {comentario}',
                              entidad_id=oc.id)

        db.session.commit()
        _enviar_push_notificacion(
            org_id=current_user.organizacion_id,
            titulo='OC Rechazada',
            cuerpo=f'Tu solicitud fue rechazada. {comentario[:80] if comentario else "Revisa los detalles."}',
            url=f'/proyecto-oc/{s.entidad_id}' if s.entidad_tipo == 'proyecto_oc' else '/aprobaciones',
        )
        flash('Solicitud rechazada. La OC vuelve a estado Borrador.', 'warning')
    except Exception as e:
        db.session.rollback()
        _flash_err('Error al procesar la operación.', e)

    return redirect(url_for('purchasing.lista_aprobaciones'))


@purchasing_bp.route('/proyecto-oc/<int:id>/recibir', methods=['GET', 'POST'])
@login_required
@check_permission('perm_create_oc_proyecto')
def recibir_proyecto_oc(id):
    proyecto_oc = get_item_or_404(ProyectoOC, id)
    org_id      = proyecto_oc.organizacion_id

    if proyecto_oc.estado not in ('enviada', 'recibida_parcial'):
        flash('Solo se puede registrar la recepción de órdenes en estado "Enviada" o "Recibida parcial".', 'danger')
        return redirect(url_for('purchasing.ver_proyecto_oc', id=id))

    almacenes = Almacen.query.filter_by(organizacion_id=org_id).order_by(Almacen.nombre).all()

    if request.method == 'GET':
        return render_template('proyecto_oc_recibir.html', proyecto_oc=proyecto_oc, almacenes=almacenes)

    # POST
    almacen_id_dest = request.form.get('almacen_id', type=int)
    if not almacen_id_dest:
        flash('Debes seleccionar un almacén destino.', 'danger')
        return render_template('proyecto_oc_recibir.html', proyecto_oc=proyecto_oc, almacenes=almacenes)

    almacen_dest = Almacen.query.filter_by(id=almacen_id_dest, organizacion_id=org_id).first()
    if not almacen_dest:
        flash('Almacén no válido.', 'danger')
        return render_template('proyecto_oc_recibir.html', proyecto_oc=proyecto_oc, almacenes=almacenes)

    try:
        procesados = 0
        omitidos   = []

        with db.session.no_autoflush:
            for detalle in proyecto_oc.detalles:
                try:
                    recibir_ahora = int(request.form.get(f'recibir_{detalle.id}', 0))
                except (ValueError, TypeError):
                    recibir_ahora = 0

                pendiente     = detalle.cantidad_pendiente
                recibir_ahora = max(0, min(recibir_ahora, pendiente))
                if recibir_ahora <= 0:
                    continue

                if detalle.producto_id:
                    stock_item = Stock.query.filter_by(
                        producto_id=detalle.producto_id, almacen_id=almacen_id_dest
                    ).first()
                    if stock_item:
                        stock_item.cantidad += recibir_ahora
                    else:
                        db.session.add(Stock(
                            producto_id=detalle.producto_id,
                            almacen_id=almacen_id_dest,
                            organizacion_id=org_id,
                            cantidad=recibir_ahora,
                            stock_minimo=5, stock_maximo=100,
                        ))
                    db.session.add(Movimiento(
                        producto_id=detalle.producto_id,
                        cantidad=recibir_ahora,
                        tipo='entrada',
                        fecha=now_mx(),
                        motivo=f'Recepción OC Proyecto #{proyecto_oc.id} — {proyecto_oc.nombre_proyecto}',
                        almacen_id=almacen_id_dest,
                        organizacion_id=org_id,
                    ))
                else:
                    omitidos.append(detalle.descripcion_nuevo or f'detalle #{detalle.id}')

                detalle.cantidad_recibida = (detalle.cantidad_recibida or 0) + recibir_ahora
                procesados += 1

        if procesados == 0:
            flash('No se indicó ninguna cantidad a recibir.', 'warning')
            return redirect(url_for('purchasing.recibir_proyecto_oc', id=id))

        proyecto_oc.almacen_id      = almacen_id_dest
        proyecto_oc.recibido_por_id = current_user.id

        if proyecto_oc.totalmente_recibida:
            proyecto_oc.estado          = 'recibida'
            proyecto_oc.fecha_recepcion = now_mx()
            resumen = f'{procesados} artículo(s) ingresados — recepción completa'
        else:
            proyecto_oc.estado = 'recibida_parcial'
            resumen = f'{procesados} artículo(s) ingresados parcialmente en "{almacen_dest.nombre}"'

        log_actividad('recibir', 'proyecto_oc',
                      f'OC Proyecto #{proyecto_oc.id} — {resumen}.',
                      entidad_id=proyecto_oc.id)
        db.session.commit()

        flash(f'{resumen}.', 'success')
        if omitidos:
            flash(f'Artículos externos (sin ingreso a stock): {", ".join(omitidos)}.', 'info')

    except Exception as e:
        db.session.rollback()
        _flash_err('Error al registrar la recepción. Verifica los datos e intenta de nuevo.', e)

    return redirect(url_for('purchasing.ver_proyecto_oc', id=id))


@purchasing_bp.route('/proyecto-oc/<int:id>/pdf')
@login_required
@check_permission('perm_create_oc_proyecto')
def generar_proyecto_oc_pdf(id):
    org_id = current_user.organizacion_id
    proyecto_oc = (
        ProyectoOC.query
        .filter_by(id=id, organizacion_id=org_id)
        .options(
            joinedload(ProyectoOC.almacen),
            selectinload(ProyectoOC.detalles).joinedload(ProyectoOCDetalle.producto),
        )
        .first_or_404()
    )
    org = Organizacion.query.get(proyecto_oc.organizacion_id)

    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(buffer, pagesize=A4,
                               rightMargin=inch, leftMargin=inch,
                               topMargin=0.5*inch, bottomMargin=inch)
    story  = []
    styles = getSampleStyleSheet()
    fuente, c_pri, c_sec = _pdf_estilos(org)

    s_normal = ParagraphStyle('PONorm',  fontName=fuente, fontSize=10, leading=12)
    s_bold   = ParagraphStyle('POBold',  fontName=_pdf_bold(fuente), fontSize=10, leading=12)
    s_brand  = ParagraphStyle('POBrand', fontName=_pdf_bold(fuente), fontSize=18, leading=20, textColor=colors.black)
    s_th     = ParagraphStyle('POTH',    fontName=_pdf_bold(fuente), fontSize=9, textColor=colors.white, alignment=TA_CENTER)
    s_cell   = ParagraphStyle('POCell',  fontName=fuente, fontSize=9, leading=11)
    s_cellr  = ParagraphStyle('POCellR', fontName=fuente, fontSize=9, leading=11, alignment=TA_RIGHT)
    s_totlbl = ParagraphStyle('POTotL',  fontName=_pdf_bold(fuente), fontSize=10, alignment=TA_RIGHT)
    s_totval = ParagraphStyle('POTotV',  fontName=_pdf_bold(fuente), fontSize=11, alignment=TA_RIGHT, textColor=c_pri)

    _pdf_header(story, org, styles)

    estado_color = {'borrador':'#D97706','enviada':'#0891B2','recibida':'#059669','cancelada':'#64748B'}.get(proyecto_oc.estado, '#64748B')
    info_proyecto = [
        Paragraph('<b>PROYECTO:</b>', s_normal),
        Paragraph(proyecto_oc.nombre_proyecto, s_bold),
        Paragraph(f'Creado por: {proyecto_oc.creador.username}', s_normal),
        Paragraph(f'Fecha: {proyecto_oc.fecha_creacion.strftime("%d/%m/%Y")}', s_normal),
    ]
    if proyecto_oc.fecha_envio:
        info_proyecto.append(Paragraph(f'Enviado: {proyecto_oc.fecha_envio.strftime("%d/%m/%Y")}', s_normal))
    if proyecto_oc.fecha_recepcion:
        info_proyecto.append(Paragraph(f'Recibido: {proyecto_oc.fecha_recepcion.strftime("%d/%m/%Y")}', s_normal))
    if proyecto_oc.recibido_por:
        info_proyecto.append(Paragraph(f'Recibido por: {proyecto_oc.recibido_por.username}', s_normal))

    info_oc = [
        Paragraph(f'<b>OC-PROY-{proyecto_oc.id}</b>', s_brand),
        Paragraph(f'<font color="{estado_color}"><b>{proyecto_oc.estado.upper()}</b></font>', s_bold),
    ]
    if proyecto_oc.almacen:
        info_oc.append(Paragraph(f'Almacén: {proyecto_oc.almacen.nombre}', s_normal))

    t_info = Table([[info_proyecto, info_oc]], colWidths=[3.5*inch, 2.7*inch])
    t_info.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('LEFTPADDING', (0,0), (-1,-1), 0)]))
    story.append(t_info)
    story.append(Spacer(1, 0.25*inch))

    data = [[
        Paragraph('Descripción / SKU', s_th), Paragraph('Proveedor Sug.', s_th),
        Paragraph('Cant.', s_th), Paragraph('Costo Unit.', s_th), Paragraph('Subtotal', s_th),
    ]]
    total = 0
    for d in proyecto_oc.detalles:
        if d.producto_id and d.producto:
            desc_html = f'<b>{_xml_escape(d.producto.nombre)}</b><br/><font size="8" color="gray">SKU: {_xml_escape(d.producto.codigo or "")}</font>'
        else:
            desc_html = f'<b>{_xml_escape(d.descripcion_nuevo or "Sin descripción")}</b><br/><font size="8" color="gray">Artículo externo</font>'
        if d.enlace_proveedor:
            short = _xml_escape((d.enlace_proveedor[:45] + '...') if len(d.enlace_proveedor) > 48 else d.enlace_proveedor)
            desc_html += f'<br/><font size="7" color="blue">{short}</font>'
        if d.comentarios_detalle:
            desc_html += f'<br/><font size="7" color="gray">{_xml_escape(d.comentarios_detalle)}</font>'
        sub = d.cantidad * d.costo_unitario
        total += sub
        data.append([
            Paragraph(desc_html, s_cell), Paragraph(d.proveedor_sugerido or '—', s_cell),
            Paragraph(str(d.cantidad), s_cellr), Paragraph(f'${d.costo_unitario:,.2f}', s_cellr),
            Paragraph(f'${sub:,.2f}', s_cellr),
        ])
    data.append(['', '', '', Paragraph('TOTAL ESTIMADO:', s_totlbl), Paragraph(f'${total:,.2f}', s_totval)])

    t_art = Table(data, colWidths=[2.6*inch, 1.4*inch, 0.5*inch, 0.9*inch, 0.9*inch], repeatRows=1)
    row_bgs = _pdf_row_styles(len(data) - 1, c_sec)
    t_art.setStyle(TableStyle([
        ('BACKGROUND',    (0,0),  (-1,0),  c_pri),
        ('TEXTCOLOR',     (0,0),  (-1,0),  colors.white),
        ('GRID',          (0,0),  (-1,-2), 0.5, colors.HexColor('#DEE2E6')),
        ('VALIGN',        (0,0),  (-1,-1), 'MIDDLE'),
        ('ALIGN',         (2,0),  (-1,-1), 'RIGHT'),
        ('TOPPADDING',    (0,0),  (-1,-1), 6),
        ('BOTTOMPADDING', (0,0),  (-1,-1), 6),
        ('SPAN',          (0,-1), (2,-1)),
        ('LINEABOVE',     (0,-1), (-1,-1), 1, colors.HexColor('#DEE2E6')),
        ('BOX',           (3,-1), (4,-1),  0.5, colors.HexColor('#DEE2E6')),
    ] + row_bgs))
    story.append(t_art)

    _pdf_footer(story, org)
    doc.build(story)
    buffer.seek(0)
    filename = f"OC-Proyecto-{proyecto_oc.id}_{proyecto_oc.fecha_creacion.strftime('%Y-%m-%d')}.pdf"
    return send_file(buffer, as_attachment=False, download_name=filename, mimetype='application/pdf')


@purchasing_bp.route('/proyecto-oc/<int:id>/cancelar', methods=['POST'])
@login_required
@check_permission('perm_create_oc_proyecto')
def cancelar_proyecto_oc(id):
    proyecto_oc = get_item_or_404(ProyectoOC, id)

    if proyecto_oc.estado in ['recibida', 'recibida_parcial', 'cancelada']:
        flash('No se puede cancelar una orden ya recibida (parcial o total) o previamente cancelada.', 'danger')
        return redirect(url_for('purchasing.ver_proyecto_oc', id=id))

    try:
        proyecto_oc.estado = 'cancelada'
        log_actividad('cancelar', 'proyecto_oc',
                      f'OC de Proyecto #{proyecto_oc.id} "{proyecto_oc.nombre_proyecto}" cancelada.',
                      entidad_id=proyecto_oc.id)
        db.session.commit()
        flash(f'OC de Proyecto #{proyecto_oc.id} cancelada.', 'warning')
    except Exception as e:
        db.session.rollback()
        _flash_err('Error al cancelar la orden.', e)

    return redirect(url_for('purchasing.lista_proyectos_oc'))


# exportar_proyectos_oc_excel vive en reports/routes.py
