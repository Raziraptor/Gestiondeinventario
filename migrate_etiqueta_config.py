"""
Agrega columnas de configuración de etiquetas a la tabla organizacion.

Ejecutar en el servidor (con el env correcto):
  source /etc/systemd/system/inventario.service.d/override.conf 2>/dev/null || true
  DATABASE_URL="postgresql://Raz:l4r4z12002@localhost/mi_inventario_db" python migrate_etiqueta_config.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

db_url = os.environ.get('DATABASE_URL', '')
if not db_url or 'sqlite' in db_url.lower():
    print("ERROR: DATABASE_URL no apunta a PostgreSQL.")
    print("Ejecuta así:")
    print('  DATABASE_URL="postgresql://Raz:l4r4z12002@localhost/mi_inventario_db" python migrate_etiqueta_config.py')
    sys.exit(1)

from app import app, db

COLUMNS = [
    ("etiqueta_fuente",       "VARCHAR(50)",  "'Inter'"),
    ("etiqueta_color_fondo",  "VARCHAR(7)",   "'#FFFFFF'"),
    ("etiqueta_color_texto",  "VARCHAR(7)",   "'#1a1a1a'"),
    ("etiqueta_color_sku",    "VARCHAR(7)",   "'#1f4e79'"),
    ("etiqueta_estilo",       "VARCHAR(20)",  "'moderno'"),
    ("etiqueta_mostrar_logo", "BOOLEAN",      "TRUE"),
]

with app.app_context():
    with db.engine.connect() as conn:
        # Obtener columnas existentes en PostgreSQL
        result = conn.execute(db.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'organizacion';"
        ))
        existing = {row[0] for row in result}

        for col, col_type, default in COLUMNS:
            if col in existing:
                print(f"  — {col} (ya existe, omitida)")
                continue
            try:
                conn.execute(db.text(
                    f"ALTER TABLE organizacion ADD COLUMN {col} {col_type} DEFAULT {default};"
                ))
                print(f"  ✓ {col}")
            except Exception as e:
                print(f"  ✗ {col}: {e}")
        conn.commit()

print("\nMigración completada.")
