"""
Migración: agregar columnas de trazabilidad a la tabla proyecto_oc
Ejecutar en el servidor: python migrate_proyecto_oc.py
"""
import os
from dotenv import load_dotenv
load_dotenv()

import psycopg2

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: No se encontró DATABASE_URL en .env")
    exit(1)

# psycopg2 no acepta el prefijo postgres://, necesita postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

migraciones = [
    ("almacen_id",      "ALTER TABLE proyecto_oc ADD COLUMN IF NOT EXISTS almacen_id INTEGER REFERENCES almacen(id);"),
    ("fecha_envio",     "ALTER TABLE proyecto_oc ADD COLUMN IF NOT EXISTS fecha_envio TIMESTAMP;"),
    ("fecha_recepcion", "ALTER TABLE proyecto_oc ADD COLUMN IF NOT EXISTS fecha_recepcion TIMESTAMP;"),
    ("recibido_por_id", 'ALTER TABLE proyecto_oc ADD COLUMN IF NOT EXISTS recibido_por_id INTEGER REFERENCES "user"(id);'),
]

for nombre, sql in migraciones:
    try:
        cur.execute(sql)
        print(f"  OK  {nombre}")
    except Exception as e:
        print(f"  ERROR en {nombre}: {e}")

cur.close()
conn.close()
print("\nMigración completada.")
