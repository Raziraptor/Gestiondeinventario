"""
Migración: agregar columnas de trazabilidad a la tabla proyecto_oc
Ejecutar en el servidor: python migrate_proyecto_oc.py
Usa el contexto de Flask para leer la config igual que gunicorn.
"""
from app import app, db

migraciones = [
    ("almacen_id",      "ALTER TABLE proyecto_oc ADD COLUMN IF NOT EXISTS almacen_id INTEGER REFERENCES almacen(id)"),
    ("fecha_envio",     "ALTER TABLE proyecto_oc ADD COLUMN IF NOT EXISTS fecha_envio TIMESTAMP"),
    ("fecha_recepcion", "ALTER TABLE proyecto_oc ADD COLUMN IF NOT EXISTS fecha_recepcion TIMESTAMP"),
    ("recibido_por_id", 'ALTER TABLE proyecto_oc ADD COLUMN IF NOT EXISTS recibido_por_id INTEGER REFERENCES "user"(id)'),
]

with app.app_context():
    with db.engine.connect() as conn:
        for nombre, sql in migraciones:
            try:
                conn.execute(db.text(sql))
                conn.commit()
                print(f"  OK  {nombre}")
            except Exception as e:
                print(f"  ERROR en {nombre}: {e}")

print("\nMigración completada.")
