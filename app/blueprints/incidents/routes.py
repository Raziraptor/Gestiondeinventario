"""Rutas del módulo de reporte y seguimiento de incidencias."""

import os
import re
import uuid
from datetime import date, datetime
from io import BytesIO

from flask import (abort, current_app, flash, make_response,
                   redirect, render_template, request, url_for)
from flask_login import current_user, login_required

from . import incidents_bp
from app.extensions import db
from app.helpers import (
    _flash_err, admin_required, check_org_permission, log_actividad, now_mx,
)
from app.models import AuditLog
from app.models.incidencias import (
    _ESTADOS, _ESTADOS_CIERRE, _PRIORIDADES, _SEVERIDADES, _TIPOS_INCIDENCIA,
    Incidencia, IncidenciaAccion, IncidenciaAvance, IncidenciaCosto,
)

_EXTENSIONES_FOTO = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
_RE_FOLIO = re.compile(r'[^\w\-]')


def _allowed_foto(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in _EXTENSIONES_FOTO


def _guardar_foto_incidencia(file_storage, org_id: int):
    """Guarda una foto de incidencia; retorna ruta relativa o None."""
    if not file_storage or not file_storage.filename:
        return None
    if not _allowed_foto(file_storage.filename):
        return None
    ext = file_storage.filename.rsplit('.', 1)[1].lower()
    nombre = f'{uuid.uuid4().hex}.{ext}'
    folder = os.path.join(current_app.root_path, '..', 'static', 'uploads', 'incidencias', str(org_id))
    os.makedirs(folder, exist_ok=True)
    file_storage.save(os.path.join(folder, nombre))
    return f'uploads/incidencias/{org_id}/{nombre}'


def _generar_folio(org_id: int) -> str:
    year = now_mx().year
    prefix = f'INC-{year}-'
    n = Incidencia.query.filter(
        Incidencia.organizacion_id == org_id,
        Incidencia.folio.like(f'{prefix}%'),
    ).count()
    return f'{prefix}{n + 1:04d}'


def _parse_date(s: str):
    """Parsea string YYYY-MM-DD a date, o None."""
    try:
        return datetime.strptime(s, '%Y-%m-%d').date() if s else None
    except ValueError:
        return None


def _badge_prioridad(p: str) -> str:
    return {'Baja': 'secondary', 'Media': 'warning', 'Alta': 'danger', 'Urgente': 'danger'}.get(p, 'secondary')


def _badge_estado(e: str) -> str:
    return {
        'Abierto': 'secondary',
        'En proceso': 'primary',
        'Resuelto': 'success',
        'Cerrado sin resolver': 'dark',
        'Escalado': 'warning',
    }.get(e, 'secondary')


# ── Lista ──────────────────────────────────────────────────────────────────────

@incidents_bp.route('/incidencias/')
@login_required
@check_org_permission
def lista_incidencias():
    org_id = current_user.organizacion_id
    q = Incidencia.query.filter_by(organizacion_id=org_id)

    estado    = request.args.get('estado', '')
    prioridad = request.args.get('prioridad', '')
    tipo      = request.args.get('tipo', '')
    buscar    = request.args.get('buscar', '').strip()

    if estado:
        q = q.filter(Incidencia.estado == estado)
    if prioridad:
        q = q.filter(Incidencia.prioridad == prioridad)
    if tipo:
        q = q.filter(Incidencia.tipo == tipo)
    if buscar:
        like = f'%{buscar}%'
        q = q.filter(
            db.or_(
                Incidencia.folio.ilike(like),
                Incidencia.titulo.ilike(like),
                Incidencia.ubicacion.ilike(like),
            )
        )

    page = request.args.get('page', 1, type=int)
    incidencias = q.order_by(Incidencia.creado_en.desc()).paginate(page=page, per_page=20, error_out=False)

    return render_template(
        'incidencias/lista.html',
        incidencias=incidencias,
        estados=_ESTADOS,
        prioridades=_PRIORIDADES,
        tipos=_TIPOS_INCIDENCIA,
        filtro_estado=estado,
        filtro_prioridad=prioridad,
        filtro_tipo=tipo,
        filtro_buscar=buscar,
        badge_prioridad=_badge_prioridad,
        badge_estado=_badge_estado,
    )


# ── Nueva incidencia ───────────────────────────────────────────────────────────

@incidents_bp.route('/incidencias/nueva', methods=['GET', 'POST'])
@login_required
@check_org_permission
def nueva_incidencia():
    if request.method == 'GET':
        return render_template(
            'incidencias/form.html',
            inc=None,
            tipos=_TIPOS_INCIDENCIA,
            prioridades=_PRIORIDADES,
            severidades=_SEVERIDADES,
            titulo_pagina='Nueva Incidencia',
        )

    org_id = current_user.organizacion_id

    # Campos obligatorios
    titulo       = request.form.get('titulo', '').strip()
    fecha_str    = request.form.get('fecha', '')
    hora         = request.form.get('hora', '').strip()
    ubicacion    = request.form.get('ubicacion', '').strip()
    reportado_por = request.form.get('reportado_por', '').strip()
    tipo         = request.form.get('tipo', '').strip()
    prioridad    = request.form.get('prioridad', '').strip()
    severidad    = request.form.get('severidad', '').strip()
    descripcion  = request.form.get('descripcion', '').strip()

    errores = []
    if not titulo:       errores.append('El título es obligatorio.')
    if not fecha_str:    errores.append('La fecha es obligatoria.')
    if not hora:         errores.append('La hora es obligatoria.')
    if not ubicacion:    errores.append('La ubicación es obligatoria.')
    if not reportado_por: errores.append('Quien reporta es obligatorio.')
    if tipo not in _TIPOS_INCIDENCIA:    errores.append('Tipo de incidencia no válido.')
    if prioridad not in _PRIORIDADES:    errores.append('Prioridad no válida.')
    if severidad not in _SEVERIDADES:    errores.append('Severidad no válida.')
    if not descripcion:  errores.append('La descripción es obligatoria.')

    fecha = _parse_date(fecha_str)
    if fecha_str and not fecha:
        errores.append('Formato de fecha inválido.')

    if errores:
        for e in errores:
            flash(e, 'danger')
        return render_template(
            'incidencias/form.html',
            inc=None,
            tipos=_TIPOS_INCIDENCIA,
            prioridades=_PRIORIDADES,
            severidades=_SEVERIDADES,
            titulo_pagina='Nueva Incidencia',
        )

    try:
        folio = _generar_folio(org_id)
        inc = Incidencia(
            folio=folio,
            titulo=titulo,
            fecha=fecha,
            hora=hora,
            ubicacion=ubicacion,
            reportado_por=reportado_por,
            cargo_reporta=request.form.get('cargo_reporta', '').strip() or None,
            contacto_reporta=request.form.get('contacto_reporta', '').strip() or None,
            tipo=tipo,
            tipo_otro=request.form.get('tipo_otro', '').strip() or None,
            prioridad=prioridad,
            severidad=severidad,
            lesionados='lesionados' in request.form,
            descripcion=descripcion,
            responsable_nombre=request.form.get('responsable_nombre', '').strip() or None,
            responsable_puesto=request.form.get('responsable_puesto', '').strip() or None,
            asignado_por=request.form.get('asignado_por', '').strip() or None,
            fecha_asignacion=_parse_date(request.form.get('fecha_asignacion', '')),
            fecha_compromiso=_parse_date(request.form.get('fecha_compromiso', '')),
            contacto_responsable=request.form.get('contacto_responsable', '').strip() or None,
            mostrar_costos='mostrar_costos' in request.form,
            organizacion_id=org_id,
            creador_id=current_user.id,
        )

        # Fotos de evidencia
        for i in (1, 2, 3):
            foto = request.files.get(f'foto{i}')
            desc = request.form.get(f'foto{i}_desc', '').strip() or None
            ruta = _guardar_foto_incidencia(foto, org_id) if foto else None
            setattr(inc, f'foto{i}_path', ruta)
            setattr(inc, f'foto{i}_desc', desc)

        db.session.add(inc)
        db.session.flush()  # obtener inc.id antes de commit

        # Acciones correctivas
        acciones  = request.form.getlist('accion[]')
        resp_acc  = request.form.getlist('responsable_accion[]')
        fecha_acc = request.form.getlist('fecha_limite_accion[]')
        for j, accion in enumerate(acciones):
            accion = accion.strip()
            if not accion:
                continue
            db.session.add(IncidenciaAccion(
                incidencia_id=inc.id,
                accion=accion,
                responsable=resp_acc[j].strip() if j < len(resp_acc) else None,
                fecha_limite=_parse_date(fecha_acc[j]) if j < len(fecha_acc) else None,
            ))

        # Costos
        conceptos    = request.form.getlist('concepto[]')
        desc_costos  = request.form.getlist('descripcion_costo[]')
        montos_costo = request.form.getlist('monto_costo[]')
        for j, concepto in enumerate(conceptos):
            concepto = concepto.strip()
            if not concepto:
                continue
            try:
                monto = float(montos_costo[j]) if j < len(montos_costo) and montos_costo[j] else 0.0
            except (ValueError, TypeError):
                monto = 0.0
            db.session.add(IncidenciaCosto(
                incidencia_id=inc.id,
                concepto=concepto,
                descripcion=desc_costos[j].strip() if j < len(desc_costos) else None,
                monto=monto,
            ))

        log_actividad('crear', 'incidencia', f'Incidencia {folio}: {titulo}', entidad_id=inc.id)
        db.session.commit()
        flash(f'Incidencia {folio} creada correctamente.', 'success')
        return redirect(url_for('incidents.ver_incidencia', id=inc.id))

    except Exception as exc:
        db.session.rollback()
        _flash_err('Error al crear la incidencia.', exc)
        return render_template(
            'incidencias/form.html',
            inc=None,
            tipos=_TIPOS_INCIDENCIA,
            prioridades=_PRIORIDADES,
            severidades=_SEVERIDADES,
            titulo_pagina='Nueva Incidencia',
        )


# ── Detalle / ticket ───────────────────────────────────────────────────────────

@incidents_bp.route('/incidencias/<int:id>')
@login_required
@check_org_permission
def ver_incidencia(id):
    inc = Incidencia.query.filter_by(id=id, organizacion_id=current_user.organizacion_id).first_or_404()
    avances  = inc.avances.all()
    acciones = inc.acciones.all()
    costos   = inc.costos.all()
    historial = (
        AuditLog.query
        .filter_by(entidad='incidencia', entidad_id=id, organizacion_id=current_user.organizacion_id)
        .order_by(AuditLog.fecha.desc())
        .limit(15)
        .all()
    )
    es_admin = current_user.rol in ('admin', 'super_admin')
    es_editor = es_admin or inc.creador_id == current_user.id
    return render_template(
        'incidencias/detalle.html',
        inc=inc,
        avances=avances,
        acciones=acciones,
        costos=costos,
        historial=historial,
        estados=_ESTADOS,
        estados_cierre=_ESTADOS_CIERRE,
        es_admin=es_admin,
        es_editor=es_editor,
        badge_prioridad=_badge_prioridad,
        badge_estado=_badge_estado,
    )


# ── Editar ─────────────────────────────────────────────────────────────────────

@incidents_bp.route('/incidencias/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@check_org_permission
def editar_incidencia(id):
    inc = Incidencia.query.filter_by(id=id, organizacion_id=current_user.organizacion_id).first_or_404()
    if current_user.rol not in ('admin', 'super_admin') and inc.creador_id != current_user.id:
        abort(403)

    if request.method == 'GET':
        acciones = inc.acciones.all()
        costos   = inc.costos.all()
        return render_template(
            'incidencias/form.html',
            inc=inc,
            acciones=acciones,
            costos=costos,
            tipos=_TIPOS_INCIDENCIA,
            prioridades=_PRIORIDADES,
            severidades=_SEVERIDADES,
            estados_cierre=_ESTADOS_CIERRE,
            es_admin=current_user.rol in ('admin', 'super_admin'),
            titulo_pagina=f'Editar — {inc.folio}',
        )

    # POST — actualizar
    titulo       = request.form.get('titulo', '').strip()
    fecha_str    = request.form.get('fecha', '')
    hora         = request.form.get('hora', '').strip()
    ubicacion    = request.form.get('ubicacion', '').strip()
    reportado_por = request.form.get('reportado_por', '').strip()
    tipo         = request.form.get('tipo', '').strip()
    prioridad    = request.form.get('prioridad', '').strip()
    severidad    = request.form.get('severidad', '').strip()
    descripcion  = request.form.get('descripcion', '').strip()

    errores = []
    if not titulo:         errores.append('El título es obligatorio.')
    if tipo not in _TIPOS_INCIDENCIA:  errores.append('Tipo no válido.')
    if prioridad not in _PRIORIDADES:  errores.append('Prioridad no válida.')
    if severidad not in _SEVERIDADES:  errores.append('Severidad no válida.')
    if not descripcion:    errores.append('La descripción es obligatoria.')
    fecha = _parse_date(fecha_str)
    if fecha_str and not fecha:
        errores.append('Fecha inválida.')

    if errores:
        for e in errores:
            flash(e, 'danger')
        return redirect(url_for('incidents.editar_incidencia', id=id))

    try:
        inc.titulo        = titulo
        if fecha: inc.fecha = fecha
        inc.hora          = hora or inc.hora
        inc.ubicacion     = ubicacion
        inc.reportado_por = reportado_por
        inc.cargo_reporta = request.form.get('cargo_reporta', '').strip() or None
        inc.contacto_reporta = request.form.get('contacto_reporta', '').strip() or None
        inc.tipo          = tipo
        inc.tipo_otro     = request.form.get('tipo_otro', '').strip() or None
        inc.prioridad     = prioridad
        inc.severidad     = severidad
        inc.lesionados    = 'lesionados' in request.form
        inc.descripcion   = descripcion
        inc.responsable_nombre   = request.form.get('responsable_nombre', '').strip() or None
        inc.responsable_puesto   = request.form.get('responsable_puesto', '').strip() or None
        inc.asignado_por         = request.form.get('asignado_por', '').strip() or None
        inc.fecha_asignacion     = _parse_date(request.form.get('fecha_asignacion', ''))
        inc.fecha_compromiso     = _parse_date(request.form.get('fecha_compromiso', ''))
        inc.contacto_responsable = request.form.get('contacto_responsable', '').strip() or None
        inc.causa_raiz   = request.form.get('causa_raiz', '').strip() or None
        inc.impacto      = request.form.get('impacto', '').strip() or None
        inc.mostrar_costos = 'mostrar_costos' in request.form

        # Sección cierre — solo admin
        if current_user.rol in ('admin', 'super_admin'):
            estado_final = request.form.get('estado_final', '').strip()
            if estado_final in _ESTADOS_CIERRE:
                inc.estado_final       = estado_final
                inc.estado             = estado_final
                inc.fecha_cierre       = _parse_date(request.form.get('fecha_cierre', ''))
                inc.comentarios_cierre = request.form.get('comentarios_cierre', '').strip() or None
                inc.firma_reporto      = request.form.get('firma_reporto', '').strip() or None
                inc.firma_responsable  = request.form.get('firma_responsable', '').strip() or None
                inc.firma_vobo         = request.form.get('firma_vobo', '').strip() or None

        # Fotos nuevas (solo reemplaza si se sube algo)
        org_id = inc.organizacion_id
        for i in (1, 2, 3):
            foto = request.files.get(f'foto{i}')
            if foto and foto.filename:
                ruta = _guardar_foto_incidencia(foto, org_id)
                if ruta:
                    setattr(inc, f'foto{i}_path', ruta)
            desc = request.form.get(f'foto{i}_desc', '').strip()
            if desc:
                setattr(inc, f'foto{i}_desc', desc)

        # Reemplazar acciones
        inc.acciones.delete()
        for accion, resp, fl in zip(
            request.form.getlist('accion[]'),
            request.form.getlist('responsable_accion[]'),
            request.form.getlist('fecha_limite_accion[]'),
        ):
            accion = accion.strip()
            if not accion:
                continue
            db.session.add(IncidenciaAccion(
                incidencia_id=inc.id,
                accion=accion,
                responsable=resp.strip() or None,
                fecha_limite=_parse_date(fl),
            ))

        # Reemplazar costos
        inc.costos.delete()
        for concepto, desc_c, monto_c in zip(
            request.form.getlist('concepto[]'),
            request.form.getlist('descripcion_costo[]'),
            request.form.getlist('monto_costo[]'),
        ):
            concepto = concepto.strip()
            if not concepto:
                continue
            try:
                monto = float(monto_c) if monto_c else 0.0
            except (ValueError, TypeError):
                monto = 0.0
            db.session.add(IncidenciaCosto(
                incidencia_id=inc.id,
                concepto=concepto,
                descripcion=desc_c.strip() or None,
                monto=monto,
            ))

        log_actividad('editar', 'incidencia', f'Incidencia {inc.folio} actualizada', entidad_id=inc.id)
        db.session.commit()
        flash('Incidencia actualizada correctamente.', 'success')
    except Exception as exc:
        db.session.rollback()
        _flash_err('Error al actualizar la incidencia.', exc)

    return redirect(url_for('incidents.ver_incidencia', id=id))


# ── Agregar avance ─────────────────────────────────────────────────────────────

@incidents_bp.route('/incidencias/<int:id>/avance', methods=['POST'])
@login_required
@check_org_permission
def agregar_avance(id):
    inc = Incidencia.query.filter_by(id=id, organizacion_id=current_user.organizacion_id).first_or_404()

    texto = request.form.get('texto_avance', '').strip()
    if not texto:
        flash('El texto del avance no puede estar vacío.', 'danger')
        return redirect(url_for('incidents.ver_incidencia', id=id))

    try:
        porcentaje = int(request.form.get('porcentaje', 0))
        porcentaje = max(0, min(100, porcentaje))
    except (ValueError, TypeError):
        porcentaje = inc.progreso

    concluido = 'concluido' in request.form

    try:
        foto_path = _guardar_foto_incidencia(request.files.get('foto_avance'), inc.organizacion_id)
        avance = IncidenciaAvance(
            incidencia_id=inc.id,
            texto=texto,
            porcentaje=porcentaje,
            concluido=concluido,
            foto_path=foto_path,
            autor_id=current_user.id,
        )
        db.session.add(avance)

        inc.progreso = porcentaje
        if concluido and inc.estado not in ('Resuelto', 'Cerrado sin resolver', 'Escalado'):
            inc.estado = 'Resuelto'
        elif inc.estado == 'Abierto':
            inc.estado = 'En proceso'

        log_actividad(
            'avance', 'incidencia',
            f'{inc.folio}: avance {porcentaje}% — {"Concluido" if concluido else "En proceso"}',
            entidad_id=inc.id,
        )
        db.session.commit()
        flash('Avance registrado correctamente.', 'success')
    except Exception as exc:
        db.session.rollback()
        _flash_err('Error al registrar el avance.', exc)

    return redirect(url_for('incidents.ver_incidencia', id=id))


# ── Cambiar estado ─────────────────────────────────────────────────────────────

@incidents_bp.route('/incidencias/<int:id>/estado', methods=['POST'])
@login_required
@check_org_permission
def cambiar_estado(id):
    if current_user.rol not in ('admin', 'super_admin'):
        abort(403)
    inc = Incidencia.query.filter_by(id=id, organizacion_id=current_user.organizacion_id).first_or_404()
    nuevo_estado = request.form.get('nuevo_estado', '').strip()
    if nuevo_estado not in _ESTADOS:
        flash('Estado no válido.', 'danger')
        return redirect(url_for('incidents.ver_incidencia', id=id))
    try:
        inc.estado = nuevo_estado
        if nuevo_estado in _ESTADOS_CIERRE:
            inc.estado_final = nuevo_estado
            if not inc.fecha_cierre:
                inc.fecha_cierre = now_mx().date()
        log_actividad('cambiar_estado', 'incidencia', f'{inc.folio}: estado → {nuevo_estado}', entidad_id=inc.id)
        db.session.commit()
        flash(f'Estado actualizado a "{nuevo_estado}".', 'success')
    except Exception as exc:
        db.session.rollback()
        _flash_err('Error al cambiar el estado.', exc)
    return redirect(url_for('incidents.ver_incidencia', id=id))


# ── Eliminar ───────────────────────────────────────────────────────────────────

@incidents_bp.route('/incidencias/<int:id>/eliminar', methods=['POST'])
@login_required
@check_org_permission
@admin_required
def eliminar_incidencia(id):
    inc = Incidencia.query.filter_by(id=id, organizacion_id=current_user.organizacion_id).first_or_404()
    try:
        folio = inc.folio
        log_actividad('eliminar', 'incidencia', f'Incidencia {folio} eliminada', entidad_id=inc.id)
        db.session.delete(inc)
        db.session.commit()
        flash(f'Incidencia {folio} eliminada.', 'success')
    except Exception as exc:
        db.session.rollback()
        _flash_err('Error al eliminar la incidencia.', exc)
    return redirect(url_for('incidents.lista_incidencias'))


# ── PDF ────────────────────────────────────────────────────────────────────────

@incidents_bp.route('/incidencias/<int:id>/pdf')
@login_required
@check_org_permission
def exportar_pdf(id):
    from decimal import Decimal
    from xml.sax.saxutils import escape as _xe

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (HRFlowable, Paragraph, SimpleDocTemplate,
                                    Spacer, Table, TableStyle)

    inc = Incidencia.query.filter_by(id=id, organizacion_id=current_user.organizacion_id).first_or_404()
    avances  = inc.avances.all()
    acciones = inc.acciones.all()
    costos   = inc.costos.all()

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    s_normal = styles['Normal']
    s_h1  = ParagraphStyle('h1',  parent=styles['Heading1'],  fontSize=18, spaceAfter=4)
    s_h2  = ParagraphStyle('h2',  parent=styles['Heading2'],  fontSize=13, spaceAfter=4, spaceBefore=10)
    s_sm  = ParagraphStyle('sm',  parent=s_normal, fontSize=9,  leading=12)
    s_lbl = ParagraphStyle('lbl', parent=s_normal, fontSize=8,  textColor=colors.HexColor('#666666'), leading=10)
    s_val = ParagraphStyle('val', parent=s_normal, fontSize=10, leading=13)

    ACCENT = colors.HexColor('#4f46e5')
    LIGHT  = colors.HexColor('#f8fafc')
    GRAY   = colors.HexColor('#e2e8f0')

    def hr():
        return HRFlowable(width='100%', thickness=0.5, color=GRAY, spaceAfter=6, spaceBefore=6)

    def kv_table(rows, ncols=3):
        """Tabla de datos etiqueta:valor."""
        data = []
        row = []
        for lbl, val in rows:
            row.append(Paragraph(f'<font size="8" color="#666666">{_xe(str(lbl))}</font><br/>'
                                 f'<font size="10">{_xe(str(val or "—"))}</font>', s_normal))
            if len(row) == ncols:
                data.append(row); row = []
        if row:
            row += [Paragraph('', s_normal)] * (ncols - len(row))
            data.append(row)
        if not data:
            return []
        t = Table(data, colWidths=[doc.width / ncols] * ncols)
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        return [t]

    story = []

    # ── Encabezado
    story.append(Paragraph(f'<font color="#4f46e5">REPORTE DE INCIDENCIA</font>', s_h1))
    story.append(Paragraph(
        f'Folio: <b>{_xe(inc.folio)}</b> &nbsp;&nbsp; Estado: <b>{_xe(inc.estado)}</b> &nbsp;&nbsp; Prioridad: {_xe(inc.prioridad)}',
        s_sm,
    ))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(f'<b>{_xe(inc.titulo)}</b>', styles['Heading2']))
    story.append(hr())

    # ── 01 Datos del reporte
    story.append(Paragraph('01 · Datos del reporte', s_h2))
    story += kv_table([
        ('Fecha del incidente', inc.fecha.strftime('%d/%m/%Y') if inc.fecha else ''),
        ('Hora', inc.hora),
        ('Área / Ubicación', inc.ubicacion),
        ('Reportado por', inc.reportado_por),
        ('Cargo / Área', inc.cargo_reporta),
        ('Teléfono / Ext.', inc.contacto_reporta),
    ])

    # ── 02 Clasificación
    story.append(hr())
    story.append(Paragraph('02 · Clasificación', s_h2))
    tipo_txt = inc.tipo + (f' — {inc.tipo_otro}' if inc.tipo == 'Otro' and inc.tipo_otro else '')
    story += kv_table([
        ('Tipo', tipo_txt),
        ('Prioridad', inc.prioridad),
        ('Severidad', inc.severidad),
        ('¿Lesionados?', 'Sí' if inc.lesionados else 'No'),
    ], ncols=2)

    # ── 03 Descripción
    story.append(hr())
    story.append(Paragraph('03 · Descripción del problema', s_h2))
    story.append(Paragraph(_xe(inc.descripcion), s_val))

    # ── 04 Evidencia (referencia)
    fotos = [(inc.foto1_path, inc.foto1_desc), (inc.foto2_path, inc.foto2_desc), (inc.foto3_path, inc.foto3_desc)]
    fotos = [(p, d) for p, d in fotos if p]
    if fotos:
        story.append(hr())
        story.append(Paragraph('04 · Evidencia fotográfica', s_h2))
        story.append(Paragraph(
            f'{len(fotos)} foto(s) adjuntas. Consultar el sistema digital para visualizarlas.',
            s_sm,
        ))

    # ── 05 Asignación
    story.append(hr())
    story.append(Paragraph('05 · Asignación de seguimiento', s_h2))
    story += kv_table([
        ('Responsable asignado', inc.responsable_nombre),
        ('Puesto / Área', inc.responsable_puesto),
        ('Asignado por', inc.asignado_por),
        ('Fecha de asignación', inc.fecha_asignacion.strftime('%d/%m/%Y') if inc.fecha_asignacion else ''),
        ('Fecha compromiso', inc.fecha_compromiso.strftime('%d/%m/%Y') if inc.fecha_compromiso else ''),
        ('Contacto responsable', inc.contacto_responsable),
    ])

    # ── 06 Bitácora de seguimiento
    if avances:
        story.append(hr())
        story.append(Paragraph('06 · Bitácora de seguimiento', s_h2))
        for a in avances:
            estado_av = f'{"Concluido" if a.concluido else "En proceso"} · {a.porcentaje}%'
            story.append(Paragraph(
                f'<b>{_xe(a.autor.username if a.autor else "—")}</b> · '
                f'{a.creado_en.strftime("%d/%m/%Y %H:%M")} · '
                f'<i>{_xe(estado_av)}</i>',
                s_sm,
            ))
            story.append(Paragraph(_xe(a.texto), s_val))
            story.append(Spacer(1, 0.2*cm))

    # ── 07 Causa raíz
    if inc.causa_raiz or acciones:
        story.append(hr())
        story.append(Paragraph('07 · Causa raíz y acciones correctivas', s_h2))
        if inc.causa_raiz:
            story.append(Paragraph(f'<b>Causa raíz:</b> {_xe(inc.causa_raiz)}', s_val))
        if acciones:
            story.append(Spacer(1, 0.2*cm))
            tabla_acc = [['Acción correctiva / preventiva', 'Responsable', 'Fecha límite']]
            for a in acciones:
                tabla_acc.append([
                    Paragraph(_xe(a.accion), s_sm),
                    Paragraph(_xe(a.responsable or '—'), s_sm),
                    a.fecha_limite.strftime('%d/%m/%Y') if a.fecha_limite else '—',
                ])
            t = Table(tabla_acc, colWidths=[doc.width * 0.55, doc.width * 0.25, doc.width * 0.20])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), ACCENT),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT]),
                ('GRID', (0, 0), (-1, -1), 0.25, GRAY),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(t)

    # ── 08 Costos
    if inc.mostrar_costos and costos:
        story.append(hr())
        story.append(Paragraph('08 · Costos e impacto', s_h2))
        tabla_cos = [['Concepto', 'Descripción', 'Monto']]
        for c in costos:
            tabla_cos.append([
                Paragraph(_xe(c.concepto), s_sm),
                Paragraph(_xe(c.descripcion or ''), s_sm),
                f'${c.monto:,.2f}',
            ])
        total = sum(c.monto or Decimal(0) for c in costos)
        tabla_cos.append(['', Paragraph('<b>Total</b>', s_sm), f'<b>${total:,.2f}</b>'])
        t = Table(tabla_cos, colWidths=[doc.width * 0.35, doc.width * 0.45, doc.width * 0.20])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), ACCENT),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, LIGHT]),
            ('GRID', (0, 0), (-1, -1), 0.25, GRAY),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('FONTNAME', (-1, -1), (-1, -1), 'Helvetica-Bold'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        if inc.impacto:
            story.append(Spacer(1, 0.2*cm))
            story.append(Paragraph(f'<b>Impacto operativo:</b> {_xe(inc.impacto)}', s_val))

    # ── 09 Cierre
    story.append(hr())
    story.append(Paragraph('09 · Cierre del reporte', s_h2))
    story += kv_table([
        ('Estado final', inc.estado_final or inc.estado),
        ('Fecha de cierre', inc.fecha_cierre.strftime('%d/%m/%Y') if inc.fecha_cierre else ''),
        ('Comentarios de cierre', inc.comentarios_cierre),
    ], ncols=2)
    if inc.firma_reporto or inc.firma_responsable or inc.firma_vobo:
        story.append(Spacer(1, 0.5*cm))
        firmas = [
            ['Quien reportó', 'Responsable del seguimiento', 'Vo. Bo. Administración'],
            [
                Paragraph(_xe(inc.firma_reporto or ''), s_sm),
                Paragraph(_xe(inc.firma_responsable or ''), s_sm),
                Paragraph(_xe(inc.firma_vobo or ''), s_sm),
            ],
        ]
        tf = Table(firmas, colWidths=[doc.width / 3] * 3)
        tf.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#666666')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('LINEABOVE', (0, 1), (-1, 1), 0.5, colors.HexColor('#333333')),
            ('TOPPADDING', (0, 1), (-1, 1), 4),
        ]))
        story.append(tf)

    # ── Footer
    story.append(Spacer(1, 0.5*cm))
    story.append(hr())
    story.append(Paragraph(
        f'FOR-INC-01 · Generado el {now_mx().strftime("%d/%m/%Y %H:%M")}', s_lbl,
    ))

    doc.build(story)
    buf.seek(0)
    folio_safe = _RE_FOLIO.sub('_', inc.folio)
    resp = make_response(buf.read())
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename=incidencia-{folio_safe}.pdf'
    return resp
