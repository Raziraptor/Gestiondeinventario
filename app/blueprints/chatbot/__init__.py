from flask import Blueprint

chatbot_bp = Blueprint('chatbot', __name__)

from . import routes  # noqa: F401, E402
