"""
Migración: agrega columnas de configuración de Excel a la tabla organizacion.
Ejecutar en el servidor:
    DATABASE_URL=... python migrate_excel_config.py
"""
import os, sys

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL no definido.")
    print("Uso: DATABASE_URL='postgresql://...' python migrate_excel_config.py")
    sys.exit(1)

try:
    import psycopg2
except ImportError:
    print("ERROR: instala psycopg2-binary: pip install psycopg2-binary")
    sys.exit(1)

COLUMNS = [
    ("excel_color_header",   "VARCHAR(7)  DEFAULT '#1f4e79'"),
    ("excel_color_accent",   "VARCHAR(7)  DEFAULT '#dbeafe'"),
    ("excel_fuente",         "VARCHAR(30) DEFAULT 'Calibri'"),
    ("excel_mostrar_logo",   "BOOLEAN     DEFAULT TRUE"),
    ("excel_mostrar_id",     "BOOLEAN     DEFAULT TRUE"),
    ("excel_mostrar_oc",     "BOOLEAN     DEFAULT TRUE"),
    ("excel_mostrar_origen", "BOOLEAN     DEFAULT TRUE"),
]

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

for col_name, col_def in COLUMNS:
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'organizacion' AND column_name = %s
        )
    """, (col_name,))
    if cur.fetchone()[0]:
        print(f"  SKIP  {col_name} (ya existe)")
    else:
        cur.execute(f'ALTER TABLE organizacion ADD COLUMN {col_name} {col_def}')
        print(f"  OK    {col_name} agregada")

cur.close()
conn.close()
print("Migración completa.")
