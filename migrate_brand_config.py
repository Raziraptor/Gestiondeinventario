"""
Migración: añadir columnas de configuración de marca a la tabla organizacion.
Ejecutar en el servidor: python migrate_brand_config.py
"""
import subprocess
import sys

def get_database_url():
    try:
        result = subprocess.run(
            ['systemctl', 'show', 'inventario', '--property=Environment', '--value'],
            capture_output=True, text=True, check=True
        )
        for part in result.stdout.split():
            if part.startswith('DATABASE_URL='):
                return part.split('=', 1)[1]
    except Exception as e:
        print(f"No se pudo leer env de systemd: {e}")
    return None

DATABASE_URL = get_database_url()

if not DATABASE_URL:
    print("ERROR: No se encontró DATABASE_URL en el servicio inventario.")
    sys.exit(1)

if 'sqlite' in DATABASE_URL:
    print("ADVERTENCIA: Usando SQLite. Las columnas pueden que no apliquen IF NOT EXISTS.")

print(f"Usando DB: {DATABASE_URL[:40]}...")

from app import app, db

NUEVAS_COLUMNAS = [
    ("color_secundario", "VARCHAR(7)  DEFAULT '#f1f5f9'"),
    ("rfc",              "VARCHAR(20)"),
    ("correo_empresa",   "VARCHAR(120)"),
    ("footer_texto",     "TEXT"),
    ("pdf_mostrar_qr",   "BOOLEAN    DEFAULT FALSE"),
]

with app.app_context():
    with db.engine.connect() as conn:
        for col, definition in NUEVAS_COLUMNAS:
            try:
                conn.execute(db.text(
                    f"ALTER TABLE organizacion ADD COLUMN IF NOT EXISTS {col} {definition}"
                ))
                conn.commit()
                print(f"  OK  — columna '{col}' añadida.")
            except Exception as e:
                conn.rollback()
                print(f"  SKIP — '{col}': {e}")

print("\nMigración completada.")
