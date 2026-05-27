"""
Gestión de sesión persistente para HD Pro.

Guarda cookies de Playwright en la BD (cifradas con Fernet) y las restaura
para evitar re-login en cada OC. Típicamente las cookies duran ~7 días.
"""

import json
import os
from datetime import datetime, timedelta


HD_SESSION_TTL_DAYS = 7


def guardar_sesion(page, db, HDSesion, org_id: int, proveedor_id: int):
    """
    Extrae las cookies actuales de Playwright y las guarda en BD (cifradas).
    Reemplaza cualquier sesión previa del mismo org+proveedor.
    """
    from cryptography.fernet import Fernet

    key = os.environ.get('FERNET_KEY', '').encode()
    if not key:
        raise ValueError('FERNET_KEY no configurada')

    cookies = page.context.cookies()
    cookies_json = json.dumps(cookies)
    cookies_cifrado = Fernet(key).encrypt(cookies_json.encode()).decode()

    # Reemplazar sesión anterior si existe
    sesion = HDSesion.query.filter_by(
        org_id=org_id, proveedor_id=proveedor_id
    ).first()

    ahora = datetime.utcnow()
    if sesion is None:
        sesion = HDSesion(
            org_id=org_id,
            proveedor_id=proveedor_id,
            _cookies=cookies_cifrado,
            expira_en=ahora + timedelta(days=HD_SESSION_TTL_DAYS),
            creada_en=ahora,
        )
        db.session.add(sesion)
    else:
        sesion._cookies = cookies_cifrado
        sesion.expira_en = ahora + timedelta(days=HD_SESSION_TTL_DAYS)
        sesion.creada_en = ahora

    db.session.commit()
    return sesion


def restaurar_sesion(page, sesion) -> bool:
    """
    Carga las cookies guardadas en el contexto de Playwright.

    Returns:
        True si se restauraron correctamente, False si las cookies están vacías.
    """
    from cryptography.fernet import Fernet, InvalidToken

    key = os.environ.get('FERNET_KEY', '').encode()
    if not key or not sesion._cookies:
        return False

    try:
        cookies_json = Fernet(key).decrypt(sesion._cookies.encode()).decode()
        cookies = json.loads(cookies_json)
    except (InvalidToken, json.JSONDecodeError):
        return False

    if not cookies:
        return False

    page.context.add_cookies(cookies)
    return True


def sesion_valida(sesion) -> bool:
    """Retorna True si la sesión existe y no ha expirado."""
    if sesion is None:
        return False
    return sesion.expira_en > datetime.utcnow()
