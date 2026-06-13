"""
Blueprint admin — rutas de administración, super-admin y operaciones de sincronización.

Cubre (en orden de aparición original en app.py):
  - lista_usuarios            GET  /usuarios
  - admin_reset_password      POST /admin/usuario/<id>/reset_password
  - configurar_plantilla      GET/POST /configuracion/plantilla
  - super_admin               GET  /superadmin
  - nueva_organizacion        POST /superadmin/organizacion/nueva
  - asignar_usuario           POST /superadmin/usuario/asignar/<user_id>
  - test_email                GET  /admin/test-email
  - admin_panel               GET  /admin_panel
  - update_user_permissions   POST /admin_panel/update/<user_id>
  - manual_usuario            GET  /admin/manual
  - api_sync                  POST /api/sync
  - api_toggle_permiso        POST /api/permisos/<user_id>
"""

import os
import logging
import secrets
from functools import wraps

import requests
from flask import (
    current_app, flash, jsonify, redirect, render_template,
    request, url_for,
)
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy.orm import joinedload
from wtforms import BooleanField, SubmitField
from wtforms.validators import DataRequired

from . import admin_bp
from app.extensions import db
from app.helpers import (
    admin_required,
    allowed_file,
    check_org_permission,
    log_actividad,
    now_mx,
    _flash_err,
)
from app.models import (
    Almacen,
    Gasto,
    Movimiento,
    Organizacion,
    Salida,
    Stock,
    User,
)

# ---------------------------------------------------------------------------
# AdminPermissionForm — definido localmente para no depender del blueprint auth
# ---------------------------------------------------------------------------

class AdminPermissionForm(FlaskForm):
    perm_view_dashboard      = BooleanField('Ver Inventario')
    perm_view_management     = BooleanField('Ver Gestión (Cat/Prov)')
    perm_edit_management     = BooleanField('Editar Gestión (Cat/Prov/Prod)')
    perm_create_oc_standard  = BooleanField('Crear OC Normal')
    perm_create_oc_proyecto  = BooleanField('Crear OC Proyecto')
    perm_do_salidas          = BooleanField('Registrar Salidas')
    perm_view_gastos         = BooleanField('Ver/Crear Gastos')
    submit                   = SubmitField('Guardar Permisos')


# ---------------------------------------------------------------------------
# Decorador super_admin_required (copiado de app.py líneas 1124-1131)
# ---------------------------------------------------------------------------

def super_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol != 'super_admin':
            flash('Acceso denegado. Se requieren privilegios de Super Administrador.', 'danger')
            return redirect(url_for('admin.super_admin'))
        return f(*args, **kwargs)
    return decorated_function


# ---------------------------------------------------------------------------
# enviar_correo_api — helper Brevo (copiado de app.py líneas 1303-1369)
# ---------------------------------------------------------------------------

def enviar_correo_api(destinatario, reset_url):
    """
    Envía correo de recuperación via Brevo API.
    Devuelve (True, None) en éxito o (False, mensaje_error) en fallo.
    """
    API_KEY      = os.environ.get("BREVO_API_KEY")
    SENDER_EMAIL = os.environ.get("BREVO_SENDER_EMAIL", "deinventarioc@gmail.com")
    SENDER_NAME  = os.environ.get("BREVO_SENDER_NAME",  "Soporte Inventario")

    if not API_KEY:
        logging.error("[BREVO] Falta BREVO_API_KEY en el entorno del servidor.")
        return False, "BREVO_API_KEY no configurada"

    payload = {
        "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
        "to": [{"email": destinatario}],
        "subject": "Restablecimiento de Contraseña — Gestor de Inventario",
        "htmlContent": f"""
            <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;
                        border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;">
                <div style="background:#4f46e5;padding:24px;text-align:center;">
                    <h2 style="margin:0;color:#fff;font-size:20px;">🔑 Gestor de Inventario</h2>
                </div>
                <div style="padding:32px;background:#f8fafc;text-align:center;">
                    <p style="font-size:16px;color:#1e293b;">
                        Recibimos una solicitud para restablecer la contraseña de tu cuenta.
                    </p>
                    <a href="{reset_url}"
                       style="display:inline-block;padding:14px 32px;margin:20px 0;
                              background:#4f46e5;color:#fff;text-decoration:none;
                              border-radius:8px;font-weight:bold;font-size:15px;">
                        Restablecer contraseña
                    </a>
                    <p style="font-size:13px;color:#64748b;">
                        El enlace expira en <strong>1 hora</strong>.<br>
                        Si no solicitaste este cambio, ignora este correo.
                    </p>
                </div>
                <div style="padding:16px;text-align:center;background:#f1f5f9;">
                    <p style="font-size:11px;color:#94a3b8;margin:0;">
                        Enviado desde: {SENDER_EMAIL}
                    </p>
                </div>
            </div>
        """
    }

    headers = {
        "accept": "application/json",
        "api-key": API_KEY,
        "content-type": "application/json",
    }

    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload, headers=headers, timeout=10,
        )
        if response.status_code in (200, 201):
            logging.info(f"[BREVO] OK — correo enviado a {destinatario}")
            return True, None
        else:
            detail = response.text[:500]
            logging.error(f"[BREVO] HTTP {response.status_code} — {detail}")
            return False, f"HTTP {response.status_code}: {detail}"
    except Exception as e:
        logging.error(f"[BREVO] Excepción: {e}")
        return False, str(e)


def _check_and_alert_stock_bajo(org_id, almacen_id):
    try:
        from app.services.notifications import check_and_alert_stock
        check_and_alert_stock(org_id, almacen_id)
    except Exception as exc:
        current_app.logger.warning("check_and_alert falló: %s", exc)


# ==============================================================================
# GESTIÓN DE USUARIOS Y CONTRASEÑAS (ADMIN)
# ==============================================================================

@admin_bp.route('/usuarios')
@login_required
def lista_usuarios():
    """Muestra la lista de todos los usuarios registrados (Solo Admins)."""
    if current_user.rol not in ['super_admin', 'admin']:
        flash('Acceso restringido a administradores.', 'danger')
        return redirect(url_for('main.index'))

    if current_user.rol == 'super_admin':
        usuarios = User.query.options(joinedload(User.organizacion)).order_by(User.username).all()
    else:
        usuarios = (
            User.query
            .filter_by(organizacion_id=current_user.organizacion_id)
            .options(joinedload(User.organizacion))
            .order_by(User.username)
            .all()
        )

    return render_template('usuarios.html', usuarios=usuarios)


@admin_bp.route('/admin/usuario/<int:id>/reset_password', methods=['POST'])
@login_required
def admin_reset_password(id):
    """Acción para que un Admin fuerce el cambio de contraseña de otro usuario."""
    # 1. Seguridad: Solo Admins
    if current_user.rol not in ['super_admin', 'admin']:
        flash('No tienes permisos para realizar esta acción.', 'danger')
        return redirect(url_for('main.index'))

    # 2. Buscar usuario
    usuario_objetivo = User.query.get_or_404(id)

    if (current_user.rol != 'super_admin'
            and usuario_objetivo.organizacion_id != current_user.organizacion_id):
        flash('No tienes permisos para realizar esta acción.', 'danger')
        return redirect(url_for('admin.lista_usuarios'))

    # 3. Obtener nueva contraseña del form
    nueva_password = request.form.get('new_password')

    if not nueva_password or len(nueva_password) < 8:
        flash('La contraseña es muy corta (mínimo 8 caracteres).', 'warning')
        return redirect(url_for('admin.lista_usuarios'))

    try:
        usuario_objetivo.password_hash = generate_password_hash(nueva_password)
        db.session.commit()
        flash(
            f'Contraseña actualizada correctamente para: {usuario_objetivo.username}',
            'success',
        )
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar: {e}', 'danger')

    return redirect(url_for('admin.lista_usuarios'))


# ==============================================================================
# CONFIGURACIÓN DE PLANTILLA (ADMIN)
# ==============================================================================

@admin_bp.route('/configuracion/plantilla', methods=['GET', 'POST'])
@login_required
@admin_required
def configurar_plantilla():
    organizacion = current_user.organizacion

    if request.method == 'POST':
        try:
            # Logo
            if 'logo' in request.files:
                file = request.files['logo']
                if file.filename != '' and allowed_file(file.filename):
                    filename = secure_filename(
                        f"logo_org_{organizacion.id}_{file.filename}"
                    )
                    file.save(
                        os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                    )
                    organizacion.logo_url = filename
            if request.form.get('eliminar_logo') == '1':
                organizacion.logo_url = None

            # Identidad
            organizacion.nombre           = request.form.get('nombre', organizacion.nombre).strip()
            organizacion.header_titulo    = request.form.get('header_titulo',   '').strip() or None
            organizacion.header_subtitulo = request.form.get('header_subtitulo', '').strip() or None
            organizacion.rfc              = request.form.get('rfc',    '').strip() or None
            organizacion.correo_empresa   = request.form.get('correo_empresa', '').strip() or None
            organizacion.direccion        = request.form.get('direccion', '').strip() or None
            organizacion.telefono         = request.form.get('telefono', '').strip() or None

            # Diseño
            organizacion.color_primario   = request.form.get('color_primario',   '#333333')
            organizacion.color_secundario = request.form.get('color_secundario', '#f1f5f9')
            organizacion.tipo_letra       = request.form.get('tipo_letra', 'Helvetica')

            # Documentos PDF
            organizacion.footer_texto  = request.form.get('footer_texto', '').strip() or None
            organizacion.pdf_mostrar_qr = request.form.get('pdf_mostrar_qr') == '1'

            # Notificaciones
            organizacion.whatsapp_notify = request.form.get('whatsapp_notify', '').strip() or None

            db.session.commit()
            flash('Configuración de marca actualizada.', 'success')

        except Exception as e:
            db.session.rollback()
            flash(f'Error al guardar: {e}', 'danger')

        return redirect(url_for('admin.configurar_plantilla'))

    return render_template('plantilla_config.html', org=organizacion)


# ==============================================================================
# RUTAS DEL SUPER ADMIN
# ==============================================================================

@admin_bp.route('/superadmin', methods=['GET'])
@login_required
@super_admin_required
def super_admin():
    """Panel principal del Super Admin para gestionar Organizaciones y Usuarios."""
    organizaciones = Organizacion.query.order_by(Organizacion.nombre).all()
    usuarios = User.query.options(joinedload(User.organizacion)).order_by(User.username).all()

    return render_template(
        'super_admin.html',
        titulo="Super Admin Panel",
        organizaciones=organizaciones,
        usuarios=usuarios,
    )


@admin_bp.route('/superadmin/organizacion/nueva', methods=['POST'])
@login_required
@super_admin_required
def nueva_organizacion():
    """Crea una nueva organización y le genera un código de invitación."""
    nombre = request.form.get('nombre')
    if not nombre:
        flash('El nombre de la organización no puede estar vacío.', 'danger')
        return redirect(url_for('admin.super_admin'))

    existente = Organizacion.query.filter_by(nombre=nombre).first()
    if existente:
        flash(f'La organización "{nombre}" ya existe.', 'warning')
        return redirect(url_for('admin.super_admin'))

    try:
        codigo = None
        while codigo is None or Organizacion.query.filter_by(codigo_invitacion=codigo).first():
            codigo = secrets.token_urlsafe(6).upper()

        nueva_org = Organizacion(nombre=nombre, codigo_invitacion=codigo)
        db.session.add(nueva_org)
        db.session.commit()
        flash(
            f'Organización "{nombre}" creada. Código de invitación: {codigo}',
            'success',
        )
    except Exception as e:
        db.session.rollback()
        flash(f'Error al crear la organización: {e}', 'danger')

    return redirect(url_for('admin.super_admin'))


@admin_bp.route('/superadmin/usuario/asignar/<int:user_id>', methods=['POST'])
@login_required
@super_admin_required
def asignar_usuario(user_id):
    """Asigna un rol y una organización a un usuario."""
    user = User.query.get_or_404(user_id)
    nuevo_rol    = request.form.get('rol')
    nueva_org_id = request.form.get('organizacion_id')

    if not nuevo_rol:
        flash('Error: No se seleccionó un rol.', 'danger')
        return redirect(url_for('admin.super_admin'))

    try:
        user.rol = nuevo_rol

        if nueva_org_id == '0':
            user.organizacion_id = None
        else:
            user.organizacion_id = int(nueva_org_id)

        if user.rol == 'super_admin':
            user.organizacion_id = None

        db.session.commit()
        flash(f'Usuario "{user.username}" actualizado.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar el usuario: {e}', 'danger')

    return redirect(url_for('admin.super_admin'))


# ==============================================================================
# DIAGNÓSTICO DE CORREO
# ==============================================================================

@admin_bp.route('/admin/test-email')
@login_required
def test_email():
    """Diagnóstico Brevo: envía un correo de prueba y muestra el resultado real."""
    if current_user.rol not in ['super_admin', 'admin']:
        return "Acceso denegado", 403

    API_KEY      = os.environ.get("BREVO_API_KEY", "")
    SENDER_EMAIL = os.environ.get("BREVO_SENDER_EMAIL", "deinventarioc@gmail.com")
    destinatario = current_user.email
    test_url     = url_for('main.index', _external=True)

    if not API_KEY:
        return (
            "<h3>BREVO_API_KEY no está definida</h3>"
            "<p>Agrégala en <code>/etc/systemd/system/inventario.service.d/override.conf</code> "
            "con <code>Environment=BREVO_API_KEY=tu_clave</code> y haz "
            "<code>systemctl daemon-reload && systemctl restart inventario</code></p>"
        ), 500

    ok, error = enviar_correo_api(destinatario, test_url)

    if ok:
        return (
            f"<h3 style='color:green'>Correo enviado correctamente</h3>"
            f"<p>Enviado a: <strong>{destinatario}</strong><br>"
            f"Remitente configurado: <strong>{SENDER_EMAIL}</strong></p>"
            f"<p>Si no llega en 2 minutos:</p>"
            f"<ol>"
            f"<li>Revisa la carpeta de <strong>Spam / No deseado</strong></li>"
            f"<li>Verifica en Brevo → <em>Settings → Senders &amp; IP → Senders</em> "
            f"que <strong>{SENDER_EMAIL}</strong> esté verificado (ícono verde)</li>"
            f"<li>Si el remitente no está verificado, Brevo puede aceptar la llamada "
            f"API pero NO entregar el correo</li>"
            f"</ol>"
        )
    else:
        return (
            f"<h3 style='color:red'>Error al enviar</h3>"
            f"<p>Remitente: <strong>{SENDER_EMAIL}</strong><br>"
            f"Destinatario: <strong>{destinatario}</strong></p>"
            f"<pre style='background:#fee;padding:12px;border-radius:6px;'>{error}</pre>"
            f"<h4>Causas comunes:</h4>"
            f"<ol>"
            f"<li><strong>Sender not verified</strong> — Ve a Brevo → Settings → Senders &amp; IP → Senders "
            f"y agrega/verifica <code>{SENDER_EMAIL}</code></li>"
            f"<li><strong>API Key inválida</strong> — Ve a Brevo → Settings → API Keys y regenera la clave</li>"
            f"<li><strong>Plan gratuito agotado</strong> — Brevo Free permite 300 correos/día</li>"
            f"</ol>"
        ), 500


# ==============================================================================
# PANEL DE ADMINISTRADOR (gestión de permisos de usuarios de la org)
# ==============================================================================

@admin_bp.route('/admin_panel')
@login_required
@admin_required
def admin_panel():
    """Panel para que un Admin gestione los usuarios de SU organización."""
    if current_user.rol == 'super_admin':
        return redirect(url_for('admin.super_admin'))

    usuarios = User.query.filter_by(
        organizacion_id=current_user.organizacion_id
    ).order_by(User.username).all()

    forms = {}
    for user in usuarios:
        form = AdminPermissionForm()
        form.perm_view_dashboard.data     = user.perm_view_dashboard
        form.perm_view_management.data    = user.perm_view_management
        form.perm_edit_management.data    = user.perm_edit_management
        form.perm_create_oc_standard.data = user.perm_create_oc_standard
        form.perm_create_oc_proyecto.data = user.perm_create_oc_proyecto
        form.perm_do_salidas.data         = user.perm_do_salidas
        form.perm_view_gastos.data        = user.perm_view_gastos
        forms[user.id] = form

    return render_template(
        'admin_panel.html',
        titulo="Panel de Administrador",
        usuarios=usuarios,
        forms=forms,
    )


@admin_bp.route('/admin_panel/update/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def update_user_permissions(user_id):
    user_to_update = User.query.get_or_404(user_id)

    if (current_user.rol == 'admin'
            and user_to_update.organizacion_id != current_user.organizacion_id):
        flash('No tienes permiso para editar a este usuario.', 'danger')
        return redirect(url_for('admin.admin_panel'))

    if user_to_update.id == current_user.id and current_user.rol != 'super_admin':
        flash('No puedes editar tus propios permisos.', 'warning')
        return redirect(url_for('admin.admin_panel'))

    form = AdminPermissionForm()
    if form.validate_on_submit():
        try:
            user_to_update.perm_view_dashboard     = form.perm_view_dashboard.data
            user_to_update.perm_view_management    = form.perm_view_management.data
            user_to_update.perm_edit_management    = form.perm_edit_management.data
            user_to_update.perm_create_oc_standard = form.perm_create_oc_standard.data
            user_to_update.perm_create_oc_proyecto = form.perm_create_oc_proyecto.data
            user_to_update.perm_do_salidas         = form.perm_do_salidas.data
            user_to_update.perm_view_gastos        = form.perm_view_gastos.data
            db.session.commit()
            flash(f'Permisos para {user_to_update.username} actualizados.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar permisos: {e}', 'danger')
    else:
        flash('Error de validación del formulario.', 'danger')

    return redirect(url_for('admin.admin_panel'))


# ==============================================================================
# MANUAL DE USUARIO
# ==============================================================================

@admin_bp.route('/admin/manual')
@login_required
@admin_required
def manual_usuario():
    """Manual de uso del sistema, descargable como PDF por admins."""
    return render_template(
        'manual_usuario.html',
        org=current_user.organizacion,
        now=now_mx(),
    )


# ==============================================================================
# SYNC OFFLINE — procesa la cola de operaciones realizadas sin conexión
# ==============================================================================

@admin_bp.route('/api/sync', methods=['POST'])
@login_required
@check_org_permission
def api_sync():
    """
    Recibe una lista de operaciones offline y las ejecuta en orden.
    Responde con el resultado de cada una (ok / error).
    Estrategia estricta: valida stock antes de ejecutar.
    """
    data = request.get_json(silent=True) or {}
    operations = data.get('operations', [])
    if not isinstance(operations, list):
        return jsonify(ok=False, error='Payload inválido'), 400

    org_id  = current_user.organizacion_id
    results = []

    for op in operations:
        op_id   = op.get('id')
        op_type = op.get('type')
        payload = op.get('payload', {})

        try:
            if op_type == 'gasto':
                result = _sync_gasto(payload, org_id)
            elif op_type == 'salida':
                result = _sync_salida(payload, org_id)
            else:
                result = {'ok': False, 'error': f'Tipo desconocido: {op_type}'}
        except Exception as e:
            db.session.rollback()
            result = {'ok': False, 'error': str(e)}

        result['id'] = op_id
        results.append(result)

    return jsonify(ok=True, results=results)


def _sync_gasto(payload, org_id):
    from datetime import datetime as _dt

    fecha_str   = payload.get('fecha')
    descripcion = payload.get('descripcion', '').strip()
    monto_str   = payload.get('monto')
    categoria   = payload.get('categoria', '').strip()
    oc_id       = payload.get('orden_compra_id') or None

    if not fecha_str or not descripcion or not monto_str or not categoria:
        return {'ok': False, 'error': 'Gasto: faltan campos obligatorios'}

    try:
        fecha = _dt.strptime(fecha_str, '%Y-%m-%d')
        monto = float(monto_str)
    except (ValueError, TypeError):
        return {'ok': False, 'error': 'Gasto: fecha o monto inválidos'}

    gasto = Gasto(
        fecha           = fecha,
        descripcion     = descripcion,
        monto           = monto,
        categoria       = categoria,
        orden_compra_id = int(oc_id) if oc_id else None,
        organizacion_id = org_id,
    )
    db.session.add(gasto)
    db.session.commit()
    log_actividad(
        'crear', 'gasto',
        f'Gasto offline sincronizado: {descripcion} ${monto:.2f}',
        entidad_id=gasto.id,
    )
    return {'ok': True}


def _sync_salida(payload, org_id):
    almacen_id = payload.get('almacen_id')
    items      = payload.get('items', [])

    if not almacen_id or not items:
        return {'ok': False, 'error': 'Salida: faltan almacén o items'}

    almacen = Almacen.query.filter_by(id=almacen_id, organizacion_id=org_id).first()
    if not almacen:
        return {'ok': False, 'error': 'Salida: almacén no válido'}

    # ── Fase de validación ────────────────────────────────────────────────
    para_ejecutar = []
    for item in items:
        prod_id  = item.get('producto_id')
        cantidad = item.get('cantidad')
        motivo   = item.get('motivo', 'Offline')

        if not prod_id or not cantidad:
            return {'ok': False, 'error': 'Salida: item con datos incompletos'}

        try:
            cantidad = int(cantidad)
        except (ValueError, TypeError):
            return {'ok': False, 'error': f'Salida: cantidad inválida para producto {prod_id}'}

        if cantidad <= 0:
            return {'ok': False, 'error': 'Salida: cantidades deben ser positivas'}

        stock_item = Stock.query.filter_by(
            producto_id=prod_id, almacen_id=almacen_id
        ).first()

        if not stock_item:
            return {'ok': False, 'error': f'Salida: producto {prod_id} sin stock en este almacén'}
        if stock_item.producto.organizacion_id != org_id:
            return {'ok': False, 'error': f'Salida: producto {prod_id} no autorizado'}

        if stock_item.cantidad < cantidad:
            return {
                'ok':    False,
                'error': (
                    f'Stock insuficiente para "{stock_item.producto.nombre}": '
                    f'disponible {stock_item.cantidad}, solicitado {cantidad}'
                ),
            }

        para_ejecutar.append((stock_item, cantidad, motivo))

    # ── Fase de ejecución ─────────────────────────────────────────────────
    today = now_mx().date()
    salida_del_dia = Salida.query.filter_by(
        fecha=today, organizacion_id=org_id, almacen_id=almacen_id
    ).first()
    if not salida_del_dia:
        salida_del_dia = Salida(
            fecha=today,
            creador_id=current_user.id,
            organizacion_id=org_id,
            almacen_id=almacen_id,
        )
        db.session.add(salida_del_dia)
        db.session.flush()

    for stock_item, cantidad, motivo in para_ejecutar:
        stock_item.cantidad -= cantidad
        db.session.add(stock_item)
        db.session.add(Movimiento(
            producto_id     = stock_item.producto_id,
            cantidad        = -cantidad,
            tipo            = 'salida',
            fecha           = now_mx(),
            motivo          = f'[Offline] {motivo}',
            salida          = salida_del_dia,
            almacen_id      = almacen_id,
            organizacion_id = org_id,
        ))

    db.session.commit()
    total_uds = sum(v[1] for v in para_ejecutar)
    log_actividad(
        'salida', 'salida',
        (
            f'Salida offline sincronizada: {len(para_ejecutar)} producto(s), '
            f'{total_uds} uds — {almacen.nombre}'
        ),
        entidad_id=salida_del_dia.id,
    )
    _check_and_alert_stock_bajo(org_id, almacen_id)
    return {'ok': True}


# ==============================================================================
# API — toggle permiso individual (AJAX auto-guardar)
# ==============================================================================

@admin_bp.route('/api/permisos/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def api_toggle_permiso(user_id):
    """API para auto-guardar un permiso individual vía AJAX."""
    PERMS_VALIDOS = {
        'perm_view_dashboard', 'perm_view_management', 'perm_edit_management',
        'perm_create_oc_standard', 'perm_create_oc_proyecto',
        'perm_do_salidas', 'perm_view_gastos',
    }

    # IDOR oracle: buscar por org ANTES del rol-check
    if current_user.rol == 'super_admin':
        user_to_update = User.query.get_or_404(user_id)
    else:
        user_to_update = User.query.filter_by(
            id=user_id,
            organizacion_id=current_user.organizacion_id,
        ).first_or_404()

    if (current_user.rol == 'admin'
            and user_to_update.organizacion_id != current_user.organizacion_id):
        return jsonify(ok=False, error='Sin permiso'), 403

    if user_to_update.id == current_user.id and current_user.rol != 'super_admin':
        return jsonify(ok=False, error='No puedes editar tus propios permisos'), 403

    if user_to_update.rol != 'user':
        return jsonify(ok=False, error='Solo se pueden editar permisos de usuarios base'), 400

    data  = request.get_json(silent=True) or {}
    perm  = data.get('perm')
    value = data.get('value')

    if perm not in PERMS_VALIDOS or not isinstance(value, bool):
        return jsonify(ok=False, error='Datos inválidos'), 400

    try:
        setattr(user_to_update, perm, value)
        db.session.commit()
        return jsonify(ok=True, username=user_to_update.username, perm=perm, value=value)
    except Exception as e:
        db.session.rollback()
        return jsonify(ok=False, error=str(e)), 500
