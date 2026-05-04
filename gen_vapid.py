"""
Genera las claves VAPID para Web Push Notifications.
Ejecutar en el servidor:  python gen_vapid.py

Requiere: pip install pywebpush   (instala cryptography como dependencia)
"""
import os
import base64

try:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PublicFormat, PrivateFormat, NoEncryption)
except ImportError:
    print("ERROR: ejecuta primero:  pip install pywebpush")
    raise SystemExit(1)

# Generar par de claves EC P-256
private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
public_key  = private_key.public_key()

# Clave pública: punto no comprimido (65 bytes), base64url sin padding
pub_bytes = public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
VAPID_PUBLIC_KEY = base64.urlsafe_b64encode(pub_bytes).rstrip(b'=').decode()

# Clave privada: guardar como archivo PEM (más limpio que en .env)
pem_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vapid_private.pem')
priv_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption())
with open(pem_path, 'wb') as f:
    f.write(priv_pem)
os.chmod(pem_path, 0o600)

print("\n=== Claves VAPID generadas ===")
print(f"\nArchivo de clave privada guardado en:\n  {pem_path}")
print(f"\nAgrega estas líneas a tu archivo .env:\n")
print(f"VAPID_PUBLIC_KEY={VAPID_PUBLIC_KEY}")
print(f"VAPID_PRIVATE_KEY={pem_path}")
print(f"VAPID_CLAIMS_EMAIL=notifications@tudominio.com")
print()
