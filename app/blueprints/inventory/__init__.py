from flask import Blueprint

inventory_bp = Blueprint('inventory', __name__)

from . import routes  # noqa: F401, E402
