"""Chatbot de soporte — chat IA + tickets de reporte para admins."""

import os
import logging

from flask import request, jsonify, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from . import chatbot_bp
from app.extensions import db
from app.helpers import check_org_permission, admin_required, log_actividad, now_mx
from app.models import ChatConversacion, ChatMensaje, SoporteReporte

_SYSTEM_PROMPT = (
    'Eres el asistente de soporte del ERP "Gestión de Inventario". '
    'Ayudas a los usuarios con: inventario, almacenes, órdenes de compra, '
    'finanzas (gastos, facturas, servicios), incidencias, reportes y configuración. '
    'Responde en español, de forma concisa y amigable. '
    'Si el usuario describe un error técnico, pídele que use el botón '
    '"Reportar fallo" para registrarlo con los admins.'
)

logger = logging.getLogger(__name__)


@chatbot_bp.route('/soporte')
@login_required
@check_org_permission
def chat_page():
    return render_template('soporte/chat.html')


@chatbot_bp.route('/api/chat/mensaje', methods=['POST'])
@login_required
@check_org_permission
def chat_mensaje():
    from google import genai

    data = request.get_json(silent=True) or {}
    mensaje = (data.get('mensaje') or '').strip()
    if not mensaje:
        return jsonify({'error': 'Mensaje vacío'}), 400

    conv_id = data.get('conversacion_id')
    org_id = current_user.organizacion_id

    # Obtener o crear conversación
    conv = None
    if conv_id:
        conv = ChatConversacion.query.filter_by(
            id=conv_id, organizacion_id=org_id, usuario_id=current_user.id
        ).first()
    if not conv:
        conv = ChatConversacion(organizacion_id=org_id, usuario_id=current_user.id)
        db.session.add(conv)
        db.session.flush()

    # Guardar mensaje del usuario
    msg_user = ChatMensaje(conversacion_id=conv.id, rol='user', contenido=mensaje)
    db.session.add(msg_user)
    db.session.flush()

    # Recuperar historial (últimos 10 mensajes excluyendo el que acabamos de agregar)
    historial = (
        ChatMensaje.query
        .filter_by(conversacion_id=conv.id)
        .filter(ChatMensaje.id != msg_user.id)
        .order_by(ChatMensaje.creado_en.asc())
        .limit(10)
        .all()
    )

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        db.session.rollback()
        return jsonify({'error': 'IA no configurada en el servidor (falta GEMINI_API_KEY).'}), 503

    try:
        client = genai.Client(api_key=api_key)

        # Construir contenido con historial
        contenidos = [_SYSTEM_PROMPT]
        for h in historial:
            prefijo = 'Usuario' if h.rol == 'user' else 'Asistente'
            contenidos.append(f'{prefijo}: {h.contenido}')
        contenidos.append(f'Usuario: {mensaje}')
        prompt_completo = '\n'.join(contenidos)

        _MODELS = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash']
        response = None
        last_exc = None
        for model_id in _MODELS:
            try:
                response = client.models.generate_content(
                    model=model_id,
                    contents=prompt_completo,
                )
                break
            except Exception as exc:
                last_exc = exc
                status = getattr(exc, 'status_code', None) or getattr(exc, 'code', None)
                if status not in (403, 404, 400):
                    raise
        if response is None:
            raise last_exc or RuntimeError('Sin respuesta de Gemini')
        respuesta = response.text.strip()
    except Exception as e:
        logger.exception('Error llamando a Gemini en chatbot')
        db.session.rollback()
        return jsonify({'error': 'Error al contactar la IA. Intenta de nuevo.'}), 502

    # Guardar respuesta del asistente
    msg_bot = ChatMensaje(conversacion_id=conv.id, rol='assistant', contenido=respuesta)
    db.session.add(msg_bot)
    db.session.commit()

    return jsonify({'conversacion_id': conv.id, 'respuesta': respuesta})


@chatbot_bp.route('/api/chat/reporte', methods=['POST'])
@login_required
@check_org_permission
def chat_reporte():
    data = request.get_json(silent=True) or {}
    titulo = (data.get('titulo') or '').strip()
    descripcion = (data.get('descripcion') or '').strip()
    conv_id = data.get('conversacion_id')

    if not titulo or not descripcion:
        return jsonify({'error': 'Título y descripción son requeridos'}), 400

    org_id = current_user.organizacion_id

    reporte = SoporteReporte(
        organizacion_id=org_id,
        usuario_id=current_user.id,
        titulo=titulo[:300],
        descripcion=descripcion,
        conversacion_id=conv_id,
        estado='abierto',
    )
    db.session.add(reporte)
    log_actividad('crear', 'soporte_reporte', f'Reporte: {titulo[:100]}')
    db.session.commit()

    return jsonify({'ok': True, 'reporte_id': reporte.id})


@chatbot_bp.route('/soporte/admin')
@login_required
@check_org_permission
@admin_required
def admin_reportes():
    org_id = current_user.organizacion_id
    estado_filtro = request.args.get('estado', '')

    q = SoporteReporte.query.filter_by(organizacion_id=org_id)
    if estado_filtro in ('abierto', 'en_revision', 'resuelto'):
        q = q.filter_by(estado=estado_filtro)

    reportes = q.order_by(SoporteReporte.creado_en.desc()).paginate(
        page=request.args.get('page', 1, type=int), per_page=20, error_out=False
    )
    pendientes = SoporteReporte.query.filter_by(
        organizacion_id=org_id, estado='abierto'
    ).count()

    return render_template(
        'soporte/admin.html',
        reportes=reportes,
        estado_filtro=estado_filtro,
        pendientes=pendientes,
    )


@chatbot_bp.route('/soporte/admin/<int:reporte_id>/estado', methods=['POST'])
@login_required
@check_org_permission
@admin_required
def actualizar_estado(reporte_id):
    org_id = current_user.organizacion_id
    reporte = SoporteReporte.query.filter_by(
        id=reporte_id, organizacion_id=org_id
    ).first_or_404()

    nuevo_estado = request.form.get('estado', '').strip()
    nota = (request.form.get('nota_admin') or '').strip()

    if nuevo_estado not in ('abierto', 'en_revision', 'resuelto'):
        flash('Estado inválido.', 'danger')
        return redirect(url_for('chatbot.admin_reportes'))

    reporte.estado = nuevo_estado
    if nota:
        reporte.nota_admin = nota
    reporte.actualizado_en = now_mx()
    log_actividad('editar', 'soporte_reporte',
                  f'Estado → {nuevo_estado}. Reporte #{reporte_id}', entidad_id=reporte_id)
    db.session.commit()
    flash('Reporte actualizado.', 'success')
    return redirect(url_for('chatbot.admin_reportes'))
