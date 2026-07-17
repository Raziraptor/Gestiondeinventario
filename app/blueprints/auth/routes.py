"""
Blueprint de autenticación — registro, login, logout, reset de contraseña y cuenta.
"""

import os
import hashlib
import logging
from datetime import datetime, timedelta
from threading import Thread
from urllib.parse import urlparse

import requests
from flask import (
    render_template, redirect, url_for, flash, request, current_app
)
from flask_login import (
    login_user, logout_user, login_required, current_user
)
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from itsdangerous.url_safe import URLSafeTimedSerializer
from werkzeug.security import generate_password_hash
from wtforms import (
    StringField, PasswordField, SubmitField, BooleanField
)
from wtforms.validators import (
    DataRequired, Email, EqualTo, Length, ValidationError
)

from . import auth_bp
from app.extensions import db, limiter
from app.models import User, Organizacion, TokenUsado
from app.helpers import now_mx, _flash_err, save_picture, allowed_file


# ── WTForms ───────────────────────────────────────────────────────────────────

class RegistrationForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired(), Length(min=4, max=80)])
    email = StringField('E-mail', validators=[DataRequired(), Email(message='E-mail no válido.')])
    password = PasswordField('Contraseña', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Contraseña',
                                     validators=[DataRequired(), EqualTo('password', message='Las contraseñas deben coincidir.')])

    # --- LÍNEA AÑADIDA ---
    codigo_invitacion = StringField('Código de Invitación (Opcional)')

    submit = SubmitField('Registrarse')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Ese nombre de usuario ya existe. Por favor, elige otro.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Ese e-mail ya está registrado. Por favor, usa otro.')


class LoginForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    submit = SubmitField('Iniciar Sesión')


class UpdateAccountForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired(), Length(min=4, max=80)])
    email = StringField('E-mail', validators=[DataRequired(), Email(message='E-mail no válido.')])
    picture = FileField('Actualizar Foto de Perfil', validators=[FileAllowed(['jpg', 'png', 'jpeg'])])
    submit_account = SubmitField('Actualizar Datos')

    def validate_username(self, username):
        if username.data != current_user.username:
            user = User.query.filter_by(username=username.data).first()
            if user:
                raise ValidationError('Ese nombre de usuario ya existe. Por favor, elige otro.')

    def validate_email(self, email):
        if email.data != current_user.email:
            user = User.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError('Ese e-mail ya está registrado. Por favor, usa otro.')


class ChangePasswordForm(FlaskForm):
    old_password = PasswordField('Contraseña Actual', validators=[DataRequired()])
    password = PasswordField('Nueva Contraseña', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Nueva Contraseña',
                                     validators=[DataRequired(), EqualTo('password', message='Las contraseñas deben coincidir.')])
    submit_password = SubmitField('Cambiar Contraseña')


class RequestResetForm(FlaskForm):
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    submit = SubmitField('Solicitar Reseteo de Contraseña')


class ResetPasswordForm(FlaskForm):
    password = PasswordField('Nueva Contraseña', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Nueva Contraseña',
                                     validators=[DataRequired(), EqualTo('password', message='Las contraseñas deben coincidir.')])
    submit = SubmitField('Restablecer Contraseña')


class AdminPermissionForm(FlaskForm):
    perm_view_dashboard = BooleanField('Ver Inventario')
    perm_view_management = BooleanField('Ver Gestión (Cat/Prov)')
    perm_edit_management = BooleanField('Editar Gestión (Cat/Prov/Prod)')
    perm_create_oc_standard = BooleanField('Crear OC Normal')
    perm_create_oc_proyecto = BooleanField('Crear OC Proyecto')
    perm_do_salidas = BooleanField('Registrar Salidas')
    perm_view_gastos = BooleanField('Ver/Crear Gastos')
    submit = SubmitField('Guardar Permisos')


# ── Helpers de correo ─────────────────────────────────────────────────────────

def enviar_correo_api(destinatario, reset_url):
    """
    Envía correo de recuperación via Brevo API.
    Devuelve (True, None) en éxito o (False, mensaje_error) en fallo.
    """
    API_KEY = os.environ.get("BREVO_API_KEY")
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
        "content-type": "application/json"
    }

    try:
        response = requests.post("https://api.brevo.com/v3/smtp/email",
                                 json=payload, headers=headers, timeout=10)
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


def send_reset_email(user):
    """Genera token y lanza hilo para enviar correo de reset en segundo plano."""
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    token = s.dumps(user.email, salt='password-reset-salt')
    reset_url = url_for('auth.reset_password', token=token, _external=True)
    Thread(target=enviar_correo_api, args=(user.email, reset_url)).start()


# ── Rutas ─────────────────────────────────────────────────────────────────────

@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("10 per minute; 30 per hour")
def register():
    """Página de Registro de nuevos usuarios (con códigos de invitación)."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = RegistrationForm()
    if form.validate_on_submit():

        # --- LÓGICA DE CÓDIGO DE INVITACIÓN ---
        org_id_asignada = None
        rol_asignado = 'user'  # Por defecto es 'user'

        codigo = form.codigo_invitacion.data
        if codigo:
            org = Organizacion.query.filter_by(codigo_invitacion=codigo.upper()).first()

            if not org:
                flash('El código de invitación no es válido.', 'danger')
                return render_template('register.html', titulo="Registro", form=form)
            else:
                org_id_asignada = org.id
                rol_asignado = 'user'
        # --- FIN DE LÓGICA ---

        try:
            new_user = User(
                username=form.username.data,
                email=form.email.data,
                organizacion_id=org_id_asignada,
                rol=rol_asignado
            )
            new_user.set_password(form.password.data)

            db.session.add(new_user)
            db.session.commit()

            if org_id_asignada:
                flash(f'¡Cuenta creada! Has sido añadido a la organización {org.nombre}.', 'success')
            else:
                flash('¡Cuenta creada! Pide a un Super Admin que te asigne a una organización.', 'success')

            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            _flash_err('Error al crear la cuenta. Intenta de nuevo.', e)

    return render_template('register.html', titulo="Registro", form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute; 50 per hour")
def login():
    """Página de Inicio de Sesión."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()

        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash('Esta cuenta ha sido desactivada. Contacta al administrador.', 'warning')
                return render_template('login.html', titulo="Inicio de Sesión", form=form)
            login_user(user)
            next_page = request.args.get('next')
            flash('Inicio de sesión exitoso.', 'success')
            if (next_page
                    and next_page.startswith('/')
                    and not next_page.startswith('//')
                    and not next_page.startswith('/\\')
                    and urlparse(next_page).netloc == ''):
                return redirect(next_page)
            return redirect(url_for('main.index'))
        else:
            flash('Inicio de sesión fallido. Verifica tu usuario y contraseña.', 'danger')

    return render_template('login.html', titulo="Inicio de Sesión", form=form)


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('Has cerrado la sesión.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("5 per minute; 20 per hour")
def forgot_password():
    """Página para solicitar el reseteo de contraseña."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_reset_email(user)
        # Siempre mismo mensaje para no revelar si un email está registrado
        flash('Si existe una cuenta con ese e-mail, recibirás un correo con las instrucciones.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('forgot_password.html', titulo="Recuperar Contraseña", form=form)


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def reset_password(token):
    """Página para ingresar la nueva contraseña (accedida desde el e-mail)."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    _s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])

    try:
        email = _s.loads(token, salt='password-reset-salt', max_age=1800)
    except Exception:
        flash('El enlace de reseteo no es válido o ha expirado.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    # AUTH-02: rechazar tokens ya utilizados (single-use)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    ya_usado = TokenUsado.query.filter_by(token_hash=token_hash).first()
    if ya_usado:
        flash('Este enlace de reseteo ya fue utilizado. Solicita uno nuevo.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    user = User.query.filter_by(email=email).first()
    if user is None:
        flash('Usuario no encontrado.', 'danger')
        return redirect(url_for('auth.login'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        try:
            user.password_hash = generate_password_hash(form.password.data)
            # Marcar token como usado antes de commit para que sean atómicos
            expira_en = datetime.utcnow() + timedelta(seconds=1800)
            db.session.add(TokenUsado(token_hash=token_hash, expira_en=expira_en))
            db.session.commit()
            flash('¡Tu contraseña ha sido actualizada! Ya puedes iniciar sesión.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            _flash_err('Error al actualizar la contraseña.', e)

    return render_template('reset_password.html', titulo="Restablecer Contraseña", form=form, token=token)


@auth_bp.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    """Página de configuración de la cuenta del usuario."""
    form_account = UpdateAccountForm()
    form_password = ChangePasswordForm()

    if form_account.submit_account.data and form_account.validate_on_submit():
        try:
            if form_account.picture.data:
                profile_pics_dir = os.path.join(
                    current_app.root_path, 'static/uploads/profile_pics'
                )
                if current_user.image_file != 'default.jpg':
                    old_pic_path = os.path.join(profile_pics_dir, current_user.image_file)
                    if os.path.exists(old_pic_path):
                        os.remove(old_pic_path)
                picture_file = save_picture(form_account.picture.data, profile_pics_dir)
                current_user.image_file = picture_file

            current_user.username = form_account.username.data
            current_user.email = form_account.email.data
            db.session.commit()
            flash('¡Tu cuenta ha sido actualizada!', 'success')
            return redirect(url_for('auth.account'))
        except Exception as e:
            db.session.rollback()
            _flash_err('Error al actualizar la cuenta.', e)

    if form_password.submit_password.data and form_password.validate_on_submit():
        try:
            if current_user.check_password(form_password.old_password.data):
                current_user.set_password(form_password.password.data)
                db.session.commit()
                flash('¡Tu contraseña ha sido cambiada!', 'success')
                return redirect(url_for('auth.account'))
            else:
                flash('La contraseña actual es incorrecta.', 'danger')
        except Exception as e:
            db.session.rollback()
            _flash_err('Error al cambiar la contraseña.', e)

    if request.method == 'GET':
        form_account.username.data = current_user.username
        form_account.email.data = current_user.email

    image_url = url_for('static', filename='uploads/profile_pics/' + current_user.image_file)

    return render_template('account.html',
                           titulo="Configuración de Cuenta",
                           image_url=image_url,
                           form_account=form_account,
                           form_password=form_password)


@auth_bp.route('/account/delete_picture', methods=['POST'])
@login_required
def delete_picture():
    """Elimina la foto de perfil del usuario y la revierte a 'default.jpg'."""
    if current_user.image_file != 'default.jpg':
        try:
            picture_path = os.path.join(
                current_app.root_path, 'static/uploads/profile_pics', current_user.image_file
            )
            if os.path.exists(picture_path):
                os.remove(picture_path)
            current_user.image_file = 'default.jpg'
            db.session.commit()
            flash('Tu foto de perfil ha sido eliminada.', 'success')
        except Exception as e:
            db.session.rollback()
            _flash_err('Error al eliminar la foto.', e)

    return redirect(url_for('auth.account'))
