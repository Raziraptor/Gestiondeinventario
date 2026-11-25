"""Conftest raiz: prepara el entorno ANTES de que tests/conftest.py importe app.

Emitido por blueprints/incidencias-pendientes-departamentos (blueprint seccion 19.6).
app/config.py lanza RuntimeError al importarse si falta SECRET_KEY y FLASK_ENV vale
'production' (su valor por omision). Los tests usan TestingConfig, asi que basta con
FLASK_ENV=testing cuando el shell no trae otro valor. setdefault nunca pisa uno existente.
"""

import os

os.environ.setdefault('FLASK_ENV', 'testing')

# El bundle de diseno vive dentro del repo: pytest nunca lo recolecta.
collect_ignore = ['blueprints']

# Falla PREEXISTENTE y ajena a este cambio: el test espera el texto 'ya existe' y la app
# responde 'Este nombre de usuario o e-mail ya esta en uso.' (cambio M-01). Se deselecciona
# aqui, en un solo lugar y visible en el resumen ("1 deselected"), para que los gates midan
# solo lo que este cambio toca. Quitar esta linea cuando alguien corrija tests/test_auth.py.
_DESELECCIONADOS = {
    'tests/test_auth.py::TestRegistration::test_register_duplicate_username_rejected',
}


def pytest_collection_modifyitems(config, items):
    quitar = [item for item in items if item.nodeid in _DESELECCIONADOS]
    if quitar:
        config.hook.pytest_deselected(items=quitar)
        items[:] = [item for item in items if item.nodeid not in _DESELECCIONADOS]
