"""
Blueprint main — stub de verificación.
Expone una ruta /health para confirmar que la nueva estructura arranca.
Las rutas reales (dashboard, index) se migran en Fase 3.
"""

from flask import jsonify
from . import main_bp


@main_bp.get('/health')
def health():
    """Verificación de que la nueva estructura de paquetes arranca correctamente."""
    return jsonify({'status': 'ok', 'package': 'app (Blueprint structure)'})
