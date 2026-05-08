"""
Migración: crear tablas 'servicio' y 'pago_servicio'.
Ejecutar en el servidor: python migrate_servicios.py
"""
import os
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

os.environ['DATABASE_URL'] = DATABASE_URL
print(f"Usando DB: {DATABASE_URL[:40]}...")

from app import app, db

TABLAS = [
    """
    CREATE TABLE IF NOT EXISTS servicio (
        id               SERIAL PRIMARY KEY,
        nombre           VARCHAR(100) NOT NULL,
        tipo             VARCHAR(30)  DEFAULT 'otro',
        proveedor_nombre VARCHAR(80),
        numero_contrato  VARCHAR(60),
        dia_vencimiento  INTEGER,
        dias_aviso       INTEGER      DEFAULT 5,
        notas            TEXT,
        activo           BOOLEAN      DEFAULT TRUE,
        organizacion_id  INTEGER      NOT NULL REFERENCES organizacion(id),
        creado_en        TIMESTAMP    DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pago_servicio (
        id                SERIAL PRIMARY KEY,
        servicio_id       INTEGER NOT NULL REFERENCES servicio(id) ON DELETE CASCADE,
        monto             FLOAT   NOT NULL,
        fecha_vencimiento DATE    NOT NULL,
        fecha_pago        DATE,
        estado            VARCHAR(20) DEFAULT 'pendiente',
        notas             TEXT,
        comprobante_url   VARCHAR(300),
        registrado_por_id INTEGER REFERENCES "user"(id),
        creado_en         TIMESTAMP DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_pago_servicio_servicio_id ON pago_servicio(servicio_id)",
    "CREATE INDEX IF NOT EXISTS ix_pago_servicio_estado ON pago_servicio(estado)",
]

with app.app_context():
    with db.engine.connect() as conn:
        for sql in TABLAS:
            try:
                conn.execute(db.text(sql))
                conn.commit()
                print(f"  OK  — {sql.strip()[:60]}...")
            except Exception as e:
                conn.rollback()
                print(f"  SKIP — {e}")

print("\nMigración completada.")
