"""
Ejecutar en el servidor:  python gen_vapid.py
Requiere: pip install pywebpush
"""
try:
    from py_vapid import Vapid
except ImportError:
    print("ERROR: ejecuta primero:  pip install pywebpush")
    raise SystemExit(1)

v = Vapid()
v.generate_keys()

pub  = v.public_key_urlsafe_b64
priv = v.private_key_urlsafe_b64
if isinstance(pub,  bytes): pub  = pub.decode()
if isinstance(priv, bytes): priv = priv.decode()

print("\n=== Copia estas líneas a tu archivo .env ===\n")
print(f"VAPID_PUBLIC_KEY={pub}")
print(f"VAPID_PRIVATE_KEY={priv}")
print(f"VAPID_CLAIMS_EMAIL=notifications@tudominio.com")
print()
