"""
Configuración de la aplicación separada por entorno.
Extraída de app.py para centralizar todos los parámetros de configuración.
"""

import os
import secrets
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


class Config:
    # ── Seguridad ──────────────────────────────────────────────────────────────
    _secret = os.environ.get('SECRET_KEY')
    if not _secret:
        import sys
        print("ADVERTENCIA: SECRET_KEY no está definida. Las sesiones se invalidarán en cada reinicio.",
              file=sys.stderr)
        _secret = secrets.token_hex(32)
    SECRET_KEY = _secret

    # ── Base de datos ──────────────────────────────────────────────────────────
    _db_url = os.environ.get('DATABASE_URL')
    if _db_url:
        SQLALCHEMY_DATABASE_URI = _db_url
    else:
        import sys
        print("ADVERTENCIA: No se encontró DATABASE_URL. Usando SQLite local.", file=sys.stderr)
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'inventario.db')

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    # ── Archivos ───────────────────────────────────────────────────────────────
    UPLOAD_FOLDER = os.path.join(basedir, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

    # ── Cookies de sesión ──────────────────────────────────────────────────────
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_HTTPONLY = True

    # ── TWA / AssetLinks ──────────────────────────────────────────────────────
    ASSETLINKS = []

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATELIMIT_STORAGE_URI = os.environ.get('REDIS_URL', 'memory://')

    # ── WTF ───────────────────────────────────────────────────────────────────
    WTF_CSRF_ENABLED = True

    # ── Límite de campos de formulario ────────────────────────────────────────
    # Werkzeug 2.3+ default = 1000. OC Proyecto usa 8 campos × N artículos;
    # con 125+ artículos se supera el límite y el parse falla antes del CSRF.
    MAX_FORM_PARTS = 5000


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    SQLALCHEMY_ECHO = False  # Cambiar a True para debug de queries SQL


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    # Flask-Login: sin esto TESTING=True desactiva @login_required automáticamente
    LOGIN_DISABLED = False
    # Flask-Limiter: deshabilitar rate limiting en tests para evitar contaminación
    RATELIMIT_ENABLED = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': ProductionConfig,
}
