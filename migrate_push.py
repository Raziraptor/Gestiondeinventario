"""
Migración: crea la tabla push_subscription en PostgreSQL.
Ejecutar en el servidor:
    DATABASE_URL=... python migrate_push.py
"""
import os, sys

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: la variable de entorno DATABASE_URL no está definida.")
    print("Uso: DATABASE_URL='postgresql://...' python migrate_push.py")
    sys.exit(1)

try:
    import psycopg2
except ImportError:
    print("ERROR: instala psycopg2-binary primero:  pip install psycopg2-binary")
    sys.exit(1)

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

# Verificar si la tabla ya existe
cur.execute("""
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name   = 'push_subscription'
    )
""")
exists = cur.fetchone()[0]

if exists:
    print("OK: la tabla push_subscription ya existe, no se requiere cambio.")
else:
    cur.execute("""
        CREATE TABLE push_subscription (
            id               SERIAL PRIMARY KEY,
            user_id          INTEGER NOT NULL REFERENCES "user"(id)         ON DELETE CASCADE,
            organizacion_id  INTEGER NOT NULL REFERENCES organizacion(id)   ON DELETE CASCADE,
            endpoint         TEXT NOT NULL UNIQUE,
            subscription_json TEXT NOT NULL,
            creada_en        TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX ix_push_subscription_org
            ON push_subscription (organizacion_id)
    """)
    print("OK: tabla push_subscription creada con índice por organización.")

cur.close()
conn.close()
print("Migración completa.")
