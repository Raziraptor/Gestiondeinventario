"""
Flask extension instances — importar desde aquí en todos los blueprints y modelos.
Se inicializan con init_app() en create_app(), no con la app directamente.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
mail = Mail()

# Limiter se configura en create_app() con storage_uri del entorno
limiter = Limiter(key_func=get_remote_address, default_limits=[])
