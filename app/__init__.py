"""
Application Factory — punto de entrada del paquete app/.
create_app() inicializa Flask, extensiones, blueprints y CLI.
"""

import json
from decimal import Decimal

from flask import Flask
from flask.json.provider import DefaultJSONProvider

from .config import config
from .extensions import db, login_manager, csrf, limiter, mail


class _JSONProvider(DefaultJSONProvider):
    @staticmethod
    def default(o):
        if isinstance(o, Decimal):
            return float(o)
        return DefaultJSONProvider.default(o)


def create_app(config_name=None):
    """Crea y configura la aplicación Flask."""
    import os
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'production')

    app = Flask(
        __name__,
        template_folder='../templates',
        static_folder='../static',
    )
    app.config.from_object(config[config_name])

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)

    limiter._storage_uri = app.config.get('RATELIMIT_STORAGE_URI', 'memory://')
    limiter.init_app(app)

    app.json_provider_class = _JSONProvider
    app.json = _JSONProvider(app)

    app.jinja_env.add_extension('jinja2.ext.do')
    app.jinja_env.filters['fromjson'] = lambda s: json.loads(s) if s else {}

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor, inicia sesión para acceder a esta página.'
    login_manager.login_message_category = 'info'

    from .models.auth import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from . import models  # noqa: F401 — registra todos los modelos en SQLAlchemy

    _register_blueprints(app)

    from .cli.commands import register_commands
    register_commands(app)

    _register_security_headers(app)
    _register_context_processors(app)

    return app


def _register_blueprints(app):
    from .blueprints.main import main_bp
    app.register_blueprint(main_bp)

    from .blueprints.auth import auth_bp
    app.register_blueprint(auth_bp)

    from .blueprints.inventory import inventory_bp
    app.register_blueprint(inventory_bp)

    from .blueprints.purchasing import purchasing_bp
    app.register_blueprint(purchasing_bp)

    from .blueprints.finance import finance_bp
    app.register_blueprint(finance_bp)

    from .blueprints.admin import admin_bp
    app.register_blueprint(admin_bp)

    from .blueprints.reports import reports_bp
    app.register_blueprint(reports_bp)

    from .blueprints.api import api_bp
    app.register_blueprint(api_bp)


def _register_security_headers(app):
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=()'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net fonts.googleapis.com; "
            "font-src 'self' data: cdn.jsdelivr.net fonts.gstatic.com; "
            "img-src 'self' data: blob: https:; "
            "connect-src 'self';"
        )
        response.headers['Content-Security-Policy'] = csp
        return response


def _register_context_processors(app):
    from flask_login import current_user

    @app.context_processor
    def inject_nav_badges():
        if not current_user.is_authenticated or not current_user.organizacion_id:
            return {'nav_badges': {}, 'aprobaciones_badge': 0, 'servicios_badge': 0}
        try:
            from datetime import date
            from .models import OrdenCompra, PagoServicio, Servicio, Stock, Almacen, SolicitudAprobacion
            org_id = current_user.organizacion_id
            servicios_vencidos = PagoServicio.query.join(Servicio).filter(
                Servicio.organizacion_id == org_id,
                PagoServicio.estado.in_(['pendiente', 'vencido']),
                PagoServicio.fecha_vencimiento <= date.today()
            ).count()
            aprobaciones = SolicitudAprobacion.query.filter_by(
                organizacion_id=org_id, estado='pendiente'
            ).count()
            return {'nav_badges': {
                'oc_pendientes': OrdenCompra.query.filter_by(
                    organizacion_id=org_id, estado='aprobada').count(),
                'servicios_vencidos': servicios_vencidos,
                'aprobaciones_pendientes': aprobaciones,
                'stock_critico': Stock.query.join(Almacen).filter(
                    Almacen.organizacion_id == org_id,
                    Stock.cantidad <= Stock.stock_minimo
                ).count(),
            },
            # Compatibilidad con templates que aún usan las variables planas
            'aprobaciones_badge': aprobaciones,
            'servicios_badge': servicios_vencidos,
            }
        except Exception:
            return {'nav_badges': {}}

    @app.context_processor
    def inject_vapid_key():
        import os
        return {'vapid_public_key': os.environ.get('VAPID_PUBLIC_KEY', '')}
