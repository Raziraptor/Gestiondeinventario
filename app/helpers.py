"""
Helpers, decoradores y utilidades globales del ERP.
Extraídos de app.py — importar desde aquí en todos los blueprints.
"""

import os
import io
from functools import wraps
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal

from flask import flash, redirect, url_for, current_app
from flask_login import current_user
from PIL import Image

# ── Zona horaria ───────────────────────────────────────────────────────────────

_TZ_MX = ZoneInfo('America/Mexico_City')


def now_mx() -> datetime:
    """Hora actual en zona horaria de México (naive, lista para guardar en BD)."""
    return datetime.now(_TZ_MX).replace(tzinfo=None)


# ── Constantes de dominio ──────────────────────────────────────────────────────

CATEGORIAS_GASTO = [
    'Servicios', 'Nómina', 'Mantenimiento', 'Insumos', 'Inventario', 'Otros'
]

MESES_ES = [
    '', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
]

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


# ── Manejo de errores seguro ───────────────────────────────────────────────────

def _flash_err(user_msg: str, exc: Exception | None = None) -> None:
    """Muestra mensaje de error seguro al usuario y loguea la excepción al servidor."""
    if exc is not None:
        current_app.logger.error('%s: %s', user_msg, exc, exc_info=True)
    flash(user_msg, 'danger')


# ── Seguridad multi-tenant ─────────────────────────────────────────────────────

def get_item_or_404(model, item_id):
    """
    Obtiene un item verificando que pertenece a la organización del usuario.
    Usar siempre en lugar de Model.query.get_or_404(id) — filtra por org.
    """
    if current_user.rol == 'super_admin':
        query = model.query
    else:
        query = model.query.filter_by(organizacion_id=current_user.organizacion_id)
    return query.filter_by(id=item_id).first_or_404()


# ── Decoradores de acceso ──────────────────────────────────────────────────────

def check_org_permission(f):
    """Bloquea usuarios sin organización asignada (excepto super_admin)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.rol != 'super_admin' and not current_user.organizacion_id:
            flash(
                'No puedes realizar esta acción. '
                'Primero debes ser asignado a una organización por un Super Admin.',
                'warning'
            )
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Restringe la ruta a admin y super_admin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.rol not in ['super_admin', 'admin']:
            flash('No tienes permiso para acceder a esta página.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


def check_permission(permission_name):
    """Verifica un perm_* flag granular. admin/super_admin siempre pasan."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if current_user.rol in ['super_admin', 'admin']:
                return f(*args, **kwargs)
            if not getattr(current_user, permission_name, False):
                flash('No tienes permiso para acceder a esta función.', 'danger')
                return redirect(url_for('main.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ── Archivos / imágenes ────────────────────────────────────────────────────────

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_picture(form_picture, output_dir: str, size: tuple = (200, 200)) -> str:
    """Redimensiona y guarda una imagen subida. Retorna el nombre del archivo."""
    import secrets as _secrets
    from werkzeug.utils import secure_filename
    _, ext = os.path.splitext(form_picture.filename)
    picture_fn = _secrets.token_hex(8) + ext.lower()
    picture_path = os.path.join(output_dir, picture_fn)

    img = Image.open(form_picture)
    img.thumbnail(size)
    img.save(picture_path)
    return picture_fn
