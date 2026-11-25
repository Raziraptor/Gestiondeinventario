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
    _flash_err, admin_required, check_org_permission, check_permission, log_actividad, now_mx,
    verify_image_bytes,
)
from app.models import AuditLog
from app.models.auth import User
from app.models.incidencias import (
    _ESTADOS, _ESTADOS_CIERRE, _PRIORIDADES, _SEVERIDADES, _TIPOS_INCIDENCIA,
    Departamento, Incidencia, IncidenciaAccion, IncidenciaAvance, IncidenciaCosto,
    Pendiente, PendienteFoto,
)
from app.services.departamentos import departamento_valido
from app.services.incidencias import (
    ESTADOS_MANUALES, ESTADOS_SIN_AVANCE, aplicar_estado_manual, progreso_departamento,
    recalcular_incidencia, reabrir_incidencia, registrar_avance, ruta_absoluta_foto,
)
from app.services.incidencias_acceso import (
    pendientes_visibles, progreso_para, puede_avanzar, puede_crear, puede_editar, puede_ver, query_visibles,
)
from app.services.incidencias_retencion import borrar_archivos, rutas_fotos
from app.services.notifications import notificar_asignacion, notificar_eventos

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
    if not verify_image_bytes(file_storage):
        return None
    ext = file_storage.filename.rsplit('.', 1)[1].lower()
    nombre = f'{uuid.uuid4().hex}.{ext}'
    folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'incidencias', str(org_id))
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


_RE_UID = re.compile(r'[np]\d{1,9}')
_MSG_RECHAZADAS = '{n} archivo(s) no se guardaron: solo se aceptan imágenes PNG, JPG, GIF o WEBP.'


def _departamentos_org(org_id):
    return Departamento.query.filter_by(organizacion_id=org_id, activo=True).order_by(Departamento.nombre).all()


def _render_form(inc=None):
    """Un solo render del formulario para alta, edición y caminos de error."""
    return render_template(
        'incidencias/form.html',
        inc=inc,
        acciones=inc.acciones.all() if inc else [],
        costos=inc.costos.all() if inc else [],
        pendientes=list(inc.pendientes) if inc else [],
        departamentos=_departamentos_org(current_user.organizacion_id),
        tipos=_TIPOS_INCIDENCIA,
        prioridades=_PRIORIDADES,
        severidades=_SEVERIDADES,
        estados_cierre=_ESTADOS_CIERRE,
        es_admin=current_user.rol in ('admin', 'super_admin'),
        titulo_pagina=f'Editar — {inc.folio}' if inc else 'Nueva Incidencia',
    )


def _leer_pendientes_form(org_id):
    """Filas del formulario en orden: [{'uid', 'descripcion', 'departamento_id'}] y errores."""
    uids = request.form.getlist('pendiente_uid[]')
    descs = request.form.getlist('pendiente_descripcion[]')
    deps = request.form.getlist('pendiente_departamento[]')
    filas, errores = [], []
    for i, uid in enumerate(uids):
        uid = uid.strip()
        desc = (descs[i] if i < len(descs) else '').strip()
        dep = (deps[i] if i < len(deps) else '').strip()
        if not _RE_UID.fullmatch(uid):
            errores.append('Fila de pendiente inválida.')
            continue
        if not desc:
            continue
        depto = departamento_valido(dep, org_id) if dep else None
        if dep and depto is None:
            errores.append('Departamento no válido.')
            continue
        filas.append({'uid': uid, 'descripcion': desc, 'departamento_id': depto.id if depto else None})
    return filas, errores


def _pendientes_a_quitar(inc):
    """Pendientes de ESTA incidencia marcados con 'pendiente_eliminar[]' (los ids ajenos se ignoran)."""
    ids = set()
    for valor in request.form.getlist('pendiente_eliminar[]'):
        m = re.fullmatch(r'p(\d{1,9})', valor.strip())
        if m:
            ids.add(int(m.group(1)))
    return [p for p in inc.pendientes if p.id in ids]


def _guardar_fotos_pendiente(pendiente, uid, org_id):
    """Guarda cada 'foto_<uid>[]' con su 'foto_desc_<uid>[]'. Devuelve cuántas se rechazaron."""
    archivos = request.files.getlist(f'foto_{uid}[]')
    descs = request.form.getlist(f'foto_desc_{uid}[]')
    rechazadas = 0
    for i, archivo in enumerate(archivos):
        if not archivo or not archivo.filename:
            continue
        ruta = _guardar_foto_incidencia(archivo, org_id)
        if not ruta:
            rechazadas += 1
            continue
        desc = (descs[i] if i < len(descs) else '').strip()[:300] or None
        pendiente.fotos.append(PendienteFoto(path=ruta, descripcion=desc))
    return rechazadas


def _aplicar_pendientes(inc, filas, org_id):
    """Crea o actualiza pendientes. Devuelve (pendientes recién asignados a un depto, fotos rechazadas)."""
    existentes = {f'p{p.id}': p for p in inc.pendientes}
    asignados, rechazadas = [], 0
    for orden, fila in enumerate(filas):
        p = existentes.get(fila['uid'])
        if p is None:
            if fila['uid'].startswith('p'):
                continue  # id ajeno a esta incidencia: se ignora
            p = Pendiente(descripcion=fila['descripcion'], orden=orden, progreso=0,
                          departamento_id=fila['departamento_id'])
            inc.pendientes.append(p)
            if p.departamento_id:
                asignados.append(p)
        else:
            if fila['departamento_id'] and fila['departamento_id'] != p.departamento_id:
                asignados.append(p)
            p.descripcion, p.orden, p.departamento_id = fila['descripcion'], orden, fila['departamento_id']
        rechazadas += _guardar_fotos_pendiente(p, fila['uid'], org_id)
    return asignados, rechazadas


def _incidencia_visible_or_404(id):
    inc = Incidencia.query.filter_by(id=id, organizacion_id=current_user.organizacion_id).first_or_404()
    if not puede_ver(inc, current_user):
        abort(404)
    return inc


def _etiqueta_estado(e: str) -> str:
    return 'Completado' if e == 'Resuelto' else e


# ── Lista ──────────────────────────────────────────────────────────────────────

@incidents_bp.route('/incidencias/')
@login_required
@check_org_permission
def lista_incidencias():
    q = query_visibles(current_user)

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
        progreso_de=lambda i: progreso_para(i, current_user),
        puede_crear=puede_crear(current_user),
        etiqueta_estado=_etiqueta_estado,
    )


# ── Nueva incidencia ───────────────────────────────────────────────────────────

@incidents_bp.route('/incidencias/nueva', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_crear_incidencias')
def nueva_incidencia():
    org_id = current_user.organizacion_id
    if request.method == 'GET':
        return _render_form()

    # Campos obligatorios
    titulo       = request.form.get('titulo', '').strip()
    fecha_str    = request.form.get('fecha', '')
    hora         = request.form.get('hora', '').strip()
    ubicacion    = request.form.get('ubicacion', '').strip()
    reportado_por = current_user.username  # siempre el usuario actual
    tipo         = request.form.get('tipo', '').strip()
    prioridad    = request.form.get('prioridad', '').strip()
    severidad    = request.form.get('severidad', '').strip()
    descripcion  = request.form.get('descripcion', '').strip()
    lesionados   = 'lesionados' in request.form
    desc_lesionados = request.form.get('descripcion_lesionados', '').strip() or None

    errores = []
    if not titulo:       errores.append('El título es obligatorio.')
    if not fecha_str:    errores.append('La fecha es obligatoria.')
    if not hora:         errores.append('La hora es obligatoria.')
    if not ubicacion:    errores.append('La ubicación es obligatoria.')
    if tipo not in _TIPOS_INCIDENCIA:    errores.append('Tipo de incidencia no válido.')
    if prioridad not in _PRIORIDADES:    errores.append('Prioridad no válida.')
    if severidad not in _SEVERIDADES:    errores.append('Severidad no válida.')
    if not descripcion:  errores.append('La descripción es obligatoria.')
    if lesionados and not desc_lesionados:
        errores.append('Describe brevemente qué lesiones ocurrieron.')

    fecha = _parse_date(fecha_str)
    if fecha_str and not fecha:
        errores.append('Formato de fecha inválido.')

    filas, errores_p = _leer_pendientes_form(org_id)
    errores += errores_p
    if not filas:
        errores.append('Agrega al menos un pendiente con descripción.')

    if errores:
        for e in errores:
            flash(e, 'danger')
        return _render_form()

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
            lesionados=lesionados,
            descripcion_lesionados=desc_lesionados,
            descripcion=descripcion,
            mostrar_costos='mostrar_costos' in request.form,
            organizacion_id=org_id,
            creador_id=current_user.id,
        )
        db.session.add(inc)
        db.session.flush()  # obtener inc.id antes de commit

        asignados, rechazadas = _aplicar_pendientes(inc, filas, org_id)

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

        recalcular_incidencia(inc)
        log_actividad('crear', 'incidencia', f'Incidencia {folio}: {titulo}', entidad_id=inc.id)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        _flash_err('Error al crear la incidencia.', exc)
        return _render_form()

    if rechazadas:
        flash(_MSG_RECHAZADAS.format(n=rechazadas), 'warning')
    notificar_asignacion(inc, asignados, current_user.id)
    flash(f'Incidencia {folio} creada correctamente.', 'success')
    return redirect(url_for('incidents.ver_incidencia', id=inc.id))


# ── Detalle / ticket ───────────────────────────────────────────────────────────

@incidents_bp.route('/incidencias/<int:id>')
@login_required
@check_org_permission
def ver_incidencia(id):
    inc = _incidencia_visible_or_404(id)
    es_admin = current_user.rol in ('admin', 'super_admin')
    es_editor = puede_editar(inc, current_user)
    pendientes = pendientes_visibles(inc, current_user)
    if es_editor:
        avances = inc.avances.all()
        acciones = inc.acciones.all()
        costos = inc.costos.all()
        historial = (
            AuditLog.query
            .filter_by(entidad='incidencia', entidad_id=id, organizacion_id=current_user.organizacion_id)
            .order_by(AuditLog.fecha.desc())
            .limit(15)
            .all()
        )
        vistos = {}
        for p in pendientes:
            if p.departamento_id and p.departamento_id not in vistos:
                vistos[p.departamento_id] = (p.departamento, progreso_departamento(inc, p.departamento_id))
        por_departamento = list(vistos.values())
    else:
        ids = {p.id for p in pendientes}
        avances = [a for a in inc.avances if a.pendiente_id in ids]
        acciones, costos, historial, por_departamento = [], [], [], []
    return render_template(
        'incidencias/detalle.html',
        inc=inc,
        pendientes=pendientes,
        avances=avances,
        acciones=acciones,
        costos=costos,
        historial=historial,
        por_departamento=por_departamento,
        progreso_propio=progreso_para(inc, current_user),
        puede_avanzar=lambda p: puede_avanzar(p, current_user),
        cerrada=inc.estado in ESTADOS_SIN_AVANCE,
        departamentos=_departamentos_org(inc.organizacion_id) if es_editor else [],
        estados=_ESTADOS,
        estados_manuales=ESTADOS_MANUALES,
        estados_cierre=_ESTADOS_CIERRE,
        es_admin=es_admin,
        es_editor=es_editor,
        badge_prioridad=_badge_prioridad,
        badge_estado=_badge_estado,
        etiqueta_estado=_etiqueta_estado,
    )


# ── Editar ─────────────────────────────────────────────────────────────────────

@incidents_bp.route('/incidencias/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@check_org_permission
def editar_incidencia(id):
    inc = _incidencia_visible_or_404(id)
    if not puede_editar(inc, current_user):
        abort(403)

    if request.method == 'GET':
        return _render_form(inc)

    # POST — actualizar
    titulo       = request.form.get('titulo', '').strip()
    fecha_str    = request.form.get('fecha', '')
    hora         = request.form.get('hora', '').strip()
    ubicacion    = request.form.get('ubicacion', '').strip()
    tipo         = request.form.get('tipo', '').strip()
    prioridad    = request.form.get('prioridad', '').strip()
    severidad    = request.form.get('severidad', '').strip()
    descripcion  = request.form.get('descripcion', '').strip()
    lesionados_e = 'lesionados' in request.form
    desc_les_e   = request.form.get('descripcion_lesionados', '').strip() or None

    errores = []
    if not titulo:         errores.append('El título es obligatorio.')
    if tipo not in _TIPOS_INCIDENCIA:  errores.append('Tipo no válido.')
    if prioridad not in _PRIORIDADES:  errores.append('Prioridad no válida.')
    if severidad not in _SEVERIDADES:  errores.append('Severidad no válida.')
    if not descripcion:    errores.append('La descripción es obligatoria.')
    if lesionados_e and not desc_les_e:
        errores.append('Describe brevemente qué lesiones ocurrieron.')
    fecha = _parse_date(fecha_str)
    if fecha_str and not fecha:
        errores.append('Fecha inválida.')

    cerrada = inc.estado in ESTADOS_SIN_AVANCE
    org_id = inc.organizacion_id
    filas, quitar = [], []
    if not cerrada:
        filas, errores_p = _leer_pendientes_form(org_id)
        errores += errores_p
        quitar = _pendientes_a_quitar(inc)
        quedan = [p for p in inc.pendientes if p not in quitar or p.avances]
        if not quedan and not any(f['uid'].startswith('n') for f in filas):
            errores.append('La incidencia debe conservar al menos un pendiente.')

    if errores:
        for e in errores:
            flash(e, 'danger')
        return redirect(url_for('incidents.editar_incidencia', id=id))

    asignados, rechazadas, rutas_quitadas = [], 0, []
    try:
        inc.titulo        = titulo
        if fecha: inc.fecha = fecha
        inc.hora          = hora or inc.hora
        inc.ubicacion     = ubicacion
        # reportado_por no se modifica en edición (es el creador original)
        inc.cargo_reporta    = request.form.get('cargo_reporta', '').strip() or None
        inc.contacto_reporta = request.form.get('contacto_reporta', '').strip() or None
        inc.tipo          = tipo
        inc.tipo_otro     = request.form.get('tipo_otro', '').strip() or None
        inc.prioridad     = prioridad
        inc.severidad     = severidad
        inc.lesionados             = lesionados_e
        inc.descripcion_lesionados = desc_les_e
        inc.descripcion   = descripcion

        inc.causa_raiz     = request.form.get('causa_raiz', '').strip() or None
        inc.impacto        = request.form.get('impacto', '').strip() or None
        inc.mostrar_costos = 'mostrar_costos' in request.form

        # Cierre opcional: no cambia el estado (el cierre es automático)
        inc.comentarios_cierre = request.form.get('comentarios_cierre', '').strip() or None
        inc.firma_reporto      = request.form.get('firma_reporto', '').strip() or None
        inc.firma_responsable  = request.form.get('firma_responsable', '').strip() or None
        inc.firma_vobo         = request.form.get('firma_vobo', '').strip() or None

        # Pendientes (alta, edición y baja); con la incidencia cerrada no se tocan
        if cerrada:
            if request.form.getlist('pendiente_uid[]') or request.form.getlist('pendiente_eliminar[]'):
                flash('Para cambiar pendientes, reabre la incidencia.', 'info')
        else:
            for p in quitar:
                if p.avances:
                    flash(f'El pendiente {p.orden + 1} tiene avances y no se puede quitar.', 'warning')
                else:
                    rutas_quitadas += [f.path for f in p.fotos]
                    inc.pendientes.remove(p)
            asignados, rechazadas = _aplicar_pendientes(inc, filas, org_id)
            recalcular_incidencia(inc)

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
    except Exception as exc:
        db.session.rollback()
        _flash_err('Error al actualizar la incidencia.', exc)
        return redirect(url_for('incidents.ver_incidencia', id=id))

    borrar_archivos(rutas_quitadas)  # ya sin filas: las fotos del pendiente quitado no quedan huérfanas
    if rechazadas:
        flash(_MSG_RECHAZADAS.format(n=rechazadas), 'warning')
    notificar_asignacion(inc, asignados, current_user.id)
    flash('Incidencia actualizada correctamente.', 'success')
    return redirect(url_for('incidents.ver_incidencia', id=id))


# ── Agregar avance ─────────────────────────────────────────────────────────────

@incidents_bp.route('/incidencias/<int:id>/avance', methods=['POST'])
@login_required
@check_org_permission
def agregar_avance(id):
    inc = _incidencia_visible_or_404(id)
    volver = redirect(url_for('incidents.ver_incidencia', id=id))
    pid = request.form.get('pendiente_id', '').strip()
    if pid:
        if not pid.isdigit():
            abort(404)
        pendiente = Pendiente.query.filter_by(id=int(pid), incidencia_id=inc.id).first_or_404()
    elif len(inc.pendientes) == 1:
        pendiente = inc.pendientes[0]
    else:
        flash('Elige el pendiente al que corresponde el avance.', 'danger')
        return volver
    if not puede_avanzar(pendiente, current_user):
        abort(403)
    if inc.estado in ESTADOS_SIN_AVANCE:
        flash('La incidencia está cerrada: reábrela para registrar avances.', 'warning')
        return volver
    texto = request.form.get('texto_avance', '').strip()
    if not texto:
        flash('El texto del avance no puede estar vacío.', 'danger')
        return volver
    archivo = request.files.get('foto_avance')
    foto_path = _guardar_foto_incidencia(archivo, inc.organizacion_id) if archivo and archivo.filename else None
    if archivo and archivo.filename and not foto_path:
        flash(_MSG_RECHAZADAS.format(n=1), 'warning')
    try:
        _, eventos = registrar_avance(pendiente, current_user.id, texto,
                                      request.form.get('porcentaje', 0), 'concluido' in request.form, foto_path)
        log_actividad('avance', 'incidencia',
                      f'{inc.folio}: avance {pendiente.progreso}% en pendiente {pendiente.orden + 1}', entidad_id=inc.id)
        db.session.commit()
        flash('Avance registrado correctamente.', 'success')
    except Exception as exc:
        db.session.rollback()
        _flash_err('Error al registrar el avance.', exc)
        return volver
    notificar_eventos(inc, eventos, current_user.id)
    return volver


@incidents_bp.route('/incidencias/<int:id>/pendientes/<int:pid>/departamento', methods=['POST'])
@login_required
@check_org_permission
def asignar_departamento_pendiente(id, pid):
    inc = _incidencia_visible_or_404(id)
    if not puede_editar(inc, current_user):
        abort(403)
    pendiente = Pendiente.query.filter_by(id=pid, incidencia_id=inc.id).first_or_404()
    volver = redirect(url_for('incidents.ver_incidencia', id=id))
    raw = request.form.get('departamento_id', '').strip()
    depto = departamento_valido(raw, inc.organizacion_id) if raw else None
    if raw and depto is None:
        flash('Departamento no válido.', 'danger')
        return volver
    nuevo_id = depto.id if depto else None
    if nuevo_id == pendiente.departamento_id:
        return volver
    try:
        pendiente.departamento_id = nuevo_id
        log_actividad('editar', 'incidencia',
                      f'{inc.folio}: pendiente {pendiente.orden + 1} → {depto.nombre if depto else "sin departamento"}',
                      entidad_id=inc.id)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        _flash_err('Error al asignar el departamento.', exc)
        return volver
    if depto:
        notificar_asignacion(inc, [pendiente], current_user.id)
    flash('Departamento actualizado.', 'success')
    return volver


# ── Cambiar estado ─────────────────────────────────────────────────────────────

@incidents_bp.route('/incidencias/<int:id>/estado', methods=['POST'])
@login_required
@check_org_permission
def cambiar_estado(id):
    if current_user.rol not in ('admin', 'super_admin'):
        abort(403)
    inc = Incidencia.query.filter_by(id=id, organizacion_id=current_user.organizacion_id).first_or_404()
    try:
        aplicar_estado_manual(inc, request.form.get('nuevo_estado', '').strip())
    except ValueError as e:
        db.session.rollback()
        flash(str(e), 'danger')
        return redirect(url_for('incidents.ver_incidencia', id=id))
    try:
        log_actividad('cambiar_estado', 'incidencia', f'{inc.folio}: estado → {inc.estado}', entidad_id=inc.id)
        db.session.commit()
        flash(f'Estado actualizado a "{_etiqueta_estado(inc.estado)}".', 'success')
    except Exception as exc:
        db.session.rollback()
        _flash_err('Error al cambiar el estado.', exc)
    return redirect(url_for('incidents.ver_incidencia', id=id))


@incidents_bp.route('/incidencias/<int:id>/reabrir', methods=['POST'])
@login_required
@check_org_permission
def reabrir(id):
    inc = _incidencia_visible_or_404(id)
    if not puede_editar(inc, current_user):
        abort(403)
    volver = redirect(url_for('incidents.ver_incidencia', id=id))
    raw = request.form.get('nuevo_pendiente_departamento', '').strip()
    depto = departamento_valido(raw, inc.organizacion_id) if raw else None
    if raw and depto is None:
        flash('Departamento no válido.', 'danger')
        return volver
    propios = {p.id for p in inc.pendientes}
    ids = [int(x) for x in request.form.getlist('reabrir_pendiente[]') if x.isdigit() and int(x) in propios]
    try:
        nuevo = reabrir_incidencia(inc, ids, request.form.get('nuevo_pendiente_descripcion'),
                                   depto.id if depto else None)
    except ValueError as e:
        db.session.rollback()
        flash(str(e), 'danger')
        return volver
    try:
        log_actividad('reabrir', 'incidencia', f'Incidencia {inc.folio} reabierta', entidad_id=inc.id)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        _flash_err('Error al reabrir la incidencia.', exc)
        return volver
    if nuevo is not None and nuevo.departamento_id:
        notificar_asignacion(inc, [nuevo], current_user.id)
    flash('Incidencia reabierta.', 'success')
    return volver


# ── Eliminar ───────────────────────────────────────────────────────────────────

@incidents_bp.route('/incidencias/<int:id>/eliminar', methods=['POST'])
@login_required
@check_org_permission
@admin_required
def eliminar_incidencia(id):
    inc = Incidencia.query.filter_by(id=id, organizacion_id=current_user.organizacion_id).first_or_404()
    try:
        folio = inc.folio
        rutas = rutas_fotos(inc)
        log_actividad('eliminar', 'incidencia', f'Incidencia {folio} eliminada', entidad_id=inc.id)
        db.session.delete(inc)
        db.session.commit()
        borrar_archivos(rutas)
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
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (HRFlowable, Image as RLImage, Paragraph,
                                    SimpleDocTemplate, Spacer, Table, TableStyle)

    inc = _incidencia_visible_or_404(id)
    pendientes = pendientes_visibles(inc, current_user)
    es_editor = puede_editar(inc, current_user)
    acciones = inc.acciones.all() if es_editor else []
    costos   = inc.costos.all() if es_editor else []

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

    def tabla_fotos(fotos):
        """fotos = [(ruta_relativa, descripcion)]; rejilla de 3 columnas, tantas filas como haga falta."""
        MAX_W = (doc.width - 0.6*cm) / 3
        MAX_H = 5 * cm
        celdas = []
        for p, d in fotos:
            full = ruta_absoluta_foto(p)
            if os.path.isfile(full):
                try:
                    ir = ImageReader(full)
                    iw, ih = ir.getSize()
                    ratio = min(MAX_W / iw, MAX_H / ih)
                    celdas.append([RLImage(full, width=iw * ratio, height=ih * ratio), Paragraph(_xe(d or ''), s_lbl)])
                except Exception:
                    celdas.append([Paragraph('(imagen no disponible)', s_lbl), Paragraph('', s_lbl)])
            else:
                celdas.append([Paragraph('(archivo no encontrado)', s_lbl), Paragraph('', s_lbl)])
        filas = []
        for i in range(0, len(celdas), 3):
            grupo = celdas[i:i + 3] + [[Paragraph('', s_normal), Paragraph('', s_normal)]] * (3 - len(celdas[i:i + 3]))
            filas.append([c[0] for c in grupo])
            filas.append([c[1] for c in grupo])
        t = Table(filas, colWidths=[doc.width / 3] * 3)
        t.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        return t

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

    # ── 04 Pendientes (con sus fotos y avances)
    story.append(hr())
    story.append(Paragraph('04 · Pendientes', s_h2))
    for n, p in enumerate(pendientes, 1):
        depto = p.departamento.nombre if p.departamento else 'Sin departamento'
        story.append(Paragraph(f'<b>Pendiente {n}</b> · {_xe(depto)} · {p.progreso}%', s_sm))
        story.append(Paragraph(_xe(p.descripcion), s_val))
        if p.fotos:
            story.append(tabla_fotos([(f.path, f.descripcion) for f in p.fotos]))
        for a in p.avances:
            autor = a.autor.nombre_mostrado if a.autor else '—'
            story.append(Paragraph(
                f'<i>{_xe(autor)} · {a.creado_en.strftime("%d/%m/%Y %H:%M")} · {a.porcentaje}%</i> — {_xe(a.texto)}',
                s_sm,
            ))
        story.append(Spacer(1, 0.3*cm))
    if not inc.pendientes:  # dato previo a la migración: fotos legadas
        legadas = [(inc.foto1_path, inc.foto1_desc), (inc.foto2_path, inc.foto2_desc), (inc.foto3_path, inc.foto3_desc)]
        legadas = [(p, d) for p, d in legadas if p]
        if legadas:
            story.append(tabla_fotos(legadas))

    # ── 05 Asignación (solo datos de la versión anterior)
    if any((inc.responsable_nombre, inc.responsable_puesto, inc.asignado_por, inc.fecha_asignacion,
            inc.fecha_compromiso, inc.contacto_responsable)):
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
