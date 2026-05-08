"""
Agrega columnas de configuración de etiquetas a la tabla organizacion.
Ejecutar: python migrate_etiqueta_config.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from app import app, db

COLUMNS = [
    ("etiqueta_fuente",       "VARCHAR(50)  DEFAULT 'Inter'"),
    ("etiqueta_color_fondo",  "VARCHAR(7)   DEFAULT '#FFFFFF'"),
    ("etiqueta_color_texto",  "VARCHAR(7)   DEFAULT '#1a1a1a'"),
    ("etiqueta_color_sku",    "VARCHAR(7)   DEFAULT '#1f4e79'"),
    ("etiqueta_estilo",       "VARCHAR(20)  DEFAULT 'moderno'"),
    ("etiqueta_mostrar_logo", "BOOLEAN      DEFAULT TRUE"),
]

with app.app_context():
    with db.engine.connect() as conn:
        for col, definition in COLUMNS:
            try:
                conn.execute(db.text(
                    f"ALTER TABLE organizacion ADD COLUMN IF NOT EXISTS {col} {definition};"
                ))
                print(f"  ✓ {col}")
            except Exception as e:
                print(f"  ✗ {col}: {e}")
        conn.commit()

print("\nMigración completada.")
