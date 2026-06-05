from flask import Blueprint

finance_bp = Blueprint('finance', __name__)

from . import routes  # noqa: F401, E402
