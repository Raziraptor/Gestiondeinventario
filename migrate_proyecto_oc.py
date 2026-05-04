"""
Migración: agregar columnas de trazabilidad a la tabla proyecto_oc
Ejecutar: python migrate_proyecto_oc.py
Lee DATABASE_URL del servicio gunicorn si no está en el entorno.
"""
import os
import subprocess

# Si no está en el entorno, intentar extraerla del servicio gunicorn
if not os.environ.get('DATABASE_URL'):
    try:
        result = subprocess.run(
            ['systemctl', 'show', 'inventario', '--property=Environment', '--value'],
            capture_output=True, text=True
        )
        for token in result.stdout.split():
            if token.startswith('DATABASE_URL='):
                os.environ['DATABASE_URL'] = token[len('DATABASE_URL='):]
                break
    except Exception:
        pass

# Si aún no se encontró, buscar en EnvironmentFile del servicio
if not os.environ.get('DATABASE_URL'):
    try:
        result = subprocess.run(
            ['systemctl', 'cat', 'inventario'],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if 'EnvironmentFile' in line:
                env_file = line.split('=', 1)[-1].strip().lstrip('-')
                if os.path.exists(env_file):
                    with open(env_file) as f:
                        for fline in f:
                            fline = fline.strip()
                            if fline.startswith('DATABASE_URL='):
                                os.environ['DATABASE_URL'] = fline[len('DATABASE_URL='):].strip('"\'')
                                break

            if line.strip().startswith('Environment=') and 'DATABASE_URL' in line:
                for token in line.split('=', 1)[1].split():
                    if token.startswith('DATABASE_URL='):
                        os.environ['DATABASE_URL'] = token[len('DATABASE_URL='):]
                        break
    except Exception:
        pass

db_url = os.environ.get('DATABASE_URL', '')
if not db_url or 'sqlite' in db_url or db_url == '':
    print(f"ERROR: DATABASE_URL no encontrada o es SQLite: '{db_url}'")
    print("Pasa la URL manualmente: DATABASE_URL='postgresql://...' python migrate_proyecto_oc.py")
    exit(1)

print(f"Usando DB: {db_url[:40]}...")

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
