from flask import Blueprint

incidents_bp = Blueprint('incidents', __name__)

from . import routes  # noqa: F401, E402
