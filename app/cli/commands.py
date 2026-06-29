"""
CLI commands del ERP — registrados en create_app().
Extraídos de app.py sección 3 (Comandos CLI).
"""

import click
from flask.cli import with_appcontext
from sqlalchemy import text, inspect


def register_commands(app):
    """Registra todos los comandos flask CLI en la app."""

    @app.cli.command('create-db')
    @with_appcontext
    def create_db():
        """Crea todas las tablas de la base de datos."""
        from app.extensions import db
        db.create_all()
        print('Base de datos y tablas creadas.')

    @app.cli.command('fix-db-proyectos')
    @with_appcontext
    def fix_db_proyectos():
        """Amplía columnas de proyecto_oc_detalle. Idempotente."""
        from app.extensions import db
        stmts = [
            "ALTER TABLE proyecto_oc_detalle ADD COLUMN IF NOT EXISTS enlace_proveedor VARCHAR(500)",
            "ALTER TABLE proyecto_oc_detalle ADD COLUMN IF NOT EXISTS comentarios_detalle TEXT",
            "ALTER TABLE proyecto_oc_detalle ALTER COLUMN descripcion_nuevo TYPE TEXT",
            "ALTER TABLE proyecto_oc_detalle ALTER COLUMN proveedor_sugerido TYPE VARCHAR(255)",
        ]
        with db.engine.connect() as conn:
            for stmt in stmts:
                try:
                    conn.execute(text(stmt)); conn.commit(); print(f'OK: {stmt[:60]}')
                except Exception as e:
                    conn.rollback(); print(f'Omitido: {e}')

    @app.cli.command('fix-float-to-numeric')
    @with_appcontext
    def fix_float_to_numeric():
        """Migra montos de DOUBLE PRECISION → NUMERIC(10,2). Idempotente."""
        from app.extensions import db
        columnas = [
            ('producto', 'precio_unitario'),
            ('orden_compra_detalle', 'costo_unitario_estimado'),
            ('gasto', 'monto'), ('pago_servicio', 'monto'),
            ('factura_proveedor', 'monto'), ('proyecto_oc_detalle', 'costo_unitario'),
        ]
        with db.engine.connect() as conn:
            for tabla, columna in columnas:
                row = conn.execute(text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name=:t AND column_name=:c"
                ), {'t': tabla, 'c': columna}).fetchone()
                if not row:
                    print(f'OMITIDO: {tabla}.{columna} no encontrada'); continue
                if row[0] != 'double precision':
                    print(f'OMITIDO: {tabla}.{columna} ya es {row[0]}'); continue
                try:
                    conn.execute(text(
                        f"ALTER TABLE {tabla} ALTER COLUMN {columna} "
                        f"TYPE NUMERIC(10,2) USING ROUND({columna}::NUMERIC, 2)"
                    )); conn.commit(); print(f'OK: {tabla}.{columna} → NUMERIC(10,2)')
                except Exception as e:
                    conn.rollback(); print(f'ERROR {tabla}.{columna}: {e}')

    @app.cli.command('fix-add-token-usado')
    @with_appcontext
    def fix_add_token_usado():
        """Crea tabla token_usado (blocklist de resets). Idempotente."""
        from app.extensions import db
        with db.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS token_usado (
                    id SERIAL PRIMARY KEY,
                    token_hash VARCHAR(64) NOT NULL UNIQUE,
                    usado_en TIMESTAMP NOT NULL DEFAULT NOW(),
                    expira_en TIMESTAMP NOT NULL
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_token_usado_token_hash ON token_usado(token_hash)"
            ))
            conn.commit()
        print('fix-add-token-usado completado.')

    @app.cli.command('limpiar-tokens-expirados')
    @with_appcontext
    def limpiar_tokens():
        """Elimina tokens de reset ya expirados."""
        from app.extensions import db
        with db.engine.connect() as conn:
            r = conn.execute(text("DELETE FROM token_usado WHERE expira_en < NOW()"))
            conn.commit()
        print(f'limpiar-tokens-expirados: {r.rowcount} registros eliminados.')

    @app.cli.command('migrate-fase-c')
    @with_appcontext
    def migrate_fase_c():
        """Añade centro_costo_id a tablas financieras. Idempotente."""
        from app.extensions import db
        stmts = [
            "ALTER TABLE gasto ADD COLUMN IF NOT EXISTS centro_costo_id INTEGER REFERENCES centro_costo(id) ON DELETE SET NULL",
            "ALTER TABLE pago_servicio ADD COLUMN IF NOT EXISTS centro_costo_id INTEGER REFERENCES centro_costo(id) ON DELETE SET NULL",
            "ALTER TABLE factura_proveedor ADD COLUMN IF NOT EXISTS centro_costo_id INTEGER REFERENCES centro_costo(id) ON DELETE SET NULL",
        ]
        with db.engine.connect() as conn:
            for stmt in stmts:
                try:
                    conn.execute(text(stmt)); conn.commit(); print(f'OK: {stmt[:60]}')
                except Exception as e:
                    conn.rollback(); print(f'Omitido: {e}')

    @app.cli.command('add-hd-integration')
    @with_appcontext
    def add_hd_integration():
        """Crea tabla proveedor_integracion y columnas HD. Idempotente."""
        from app.extensions import db
        conn = db.engine.connect()
        inspector = inspect(db.engine)
        existing = inspector.get_table_names()
        if 'proveedor_integracion' not in existing:
            conn.execute(text("""
                CREATE TABLE proveedor_integracion (
                    id SERIAL PRIMARY KEY,
                    proveedor_id INTEGER NOT NULL REFERENCES proveedor(id),
                    organizacion_id INTEGER NOT NULL REFERENCES organizacion(id),
                    tipo VARCHAR(30) NOT NULL DEFAULT 'homedepot',
                    credenciales TEXT,
                    activo BOOLEAN NOT NULL DEFAULT TRUE
                )
            """)); conn.commit()
            print('add-hd-integration: tabla proveedor_integracion creada.')
        def col_exists(t, c):
            return c in [x['name'] for x in inspector.get_columns(t)]
        for tabla, col, tipo in [
            ('producto', 'hd_sku', 'VARCHAR(30)'),
            ('orden_compra', 'integracion_status', 'VARCHAR(20)'),
            ('orden_compra', 'integracion_resultado', 'TEXT'),
        ]:
            if not col_exists(tabla, col):
                conn.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {col} {tipo}"))
                conn.commit(); print(f'add-hd-integration: {tabla}.{col} añadida.')
        conn.close()
        print('add-hd-integration completado.')

    @app.cli.command('add-hd-session-table')
    @with_appcontext
    def add_hd_session_table():
        """Crea tabla hd_sesion para cookies persistentes HD Pro. Idempotente."""
        from app.extensions import db
        conn = db.engine.connect()
        inspector = inspect(db.engine)
        if 'hd_sesion' not in inspector.get_table_names():
            conn.execute(text("""
                CREATE TABLE hd_sesion (
                    id SERIAL PRIMARY KEY,
                    org_id INTEGER NOT NULL REFERENCES organizacion(id),
                    proveedor_id INTEGER NOT NULL REFERENCES proveedor(id),
                    cookies_json_cifrado TEXT,
                    expira_en TIMESTAMP NOT NULL,
                    creada_en TIMESTAMP NOT NULL DEFAULT NOW(),
                    UNIQUE(org_id, proveedor_id)
                )
            """)); conn.commit()
            print('add-hd-session-table: tabla hd_sesion creada.')
        else:
            print('add-hd-session-table: hd_sesion ya existe.')
        conn.close()

    @app.cli.command('gen-hd-fernet-key')
    @with_appcontext
    def gen_hd_fernet_key():
        """Genera clave Fernet para cifrar credenciales de proveedores."""
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        print(f'\nFERNET_KEY={key}\n')
        print('Añade esta línea a tu .env o al servicio de systemd.')

    @app.cli.command('make-super-admin')
    @with_appcontext
    @click.argument('username')
    def make_super_admin(username):
        """Asigna rol super_admin a un usuario existente."""
        from app.extensions import db
        from app.models.auth import User
        user = User.query.filter_by(username=username).first()
        if user:
            user.rol = 'super_admin'; user.organizacion_id = None
            db.session.commit(); print(f"'{username}' ahora es Super Admin.")
        else:
            print(f"Usuario '{username}' no encontrado.")

    @app.cli.command('fix-add-cantidad-recibida')
    @with_appcontext
    def fix_add_cantidad_recibida():
        """Añade cantidad_recibida a detalles de OC para recepción parcial. Idempotente."""
        from app.extensions import db
        stmts = [
            "ALTER TABLE orden_compra_detalle ADD COLUMN IF NOT EXISTS cantidad_recibida INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE proyecto_oc_detalle ADD COLUMN IF NOT EXISTS cantidad_recibida INTEGER NOT NULL DEFAULT 0",
        ]
        with db.engine.connect() as conn:
            for stmt in stmts:
                try:
                    conn.execute(text(stmt)); conn.commit(); print(f'OK: {stmt[:70]}')
                except Exception as e:
                    conn.rollback(); print(f'Omitido: {e}')
        print('fix-add-cantidad-recibida completado.')

    @app.cli.command('fix-oc-detalle-almacen')
    @with_appcontext
    def fix_oc_detalle_almacen():
        """Añade almacen_id a orden_compra_detalle y relaja orden_compra.almacen_id a nullable. Idempotente."""
        from app.extensions import db
        stmts = [
            "ALTER TABLE orden_compra_detalle ADD COLUMN IF NOT EXISTS almacen_id INTEGER REFERENCES almacen(id) ON DELETE SET NULL",
            "ALTER TABLE orden_compra ALTER COLUMN almacen_id DROP NOT NULL",
        ]
        with db.engine.connect() as conn:
            for stmt in stmts:
                try:
                    conn.execute(text(stmt)); conn.commit(); print(f'OK: {stmt[:70]}')
                except Exception as e:
                    conn.rollback(); print(f'Omitido: {e}')
        print('fix-oc-detalle-almacen completado.')

    @app.cli.command('fix-oc-distribucion-almacenes')
    @with_appcontext
    def fix_oc_distribucion_almacenes():
        """Añade distribucion_almacenes (JSONB) a orden_compra_detalle. Idempotente."""
        from app.extensions import db
        from sqlalchemy import text
        stmt = ('ALTER TABLE orden_compra_detalle '
                'ADD COLUMN IF NOT EXISTS distribucion_almacenes JSONB')
        with db.engine.connect() as conn:
            try:
                conn.execute(text(stmt)); conn.commit(); print(f'OK: {stmt}')
            except Exception as e:
                conn.rollback(); print(f'Omitido: {e}')
        print('fix-oc-distribucion-almacenes completado.')

    @app.cli.command('limpiar-push-subs')
    @with_appcontext
    def limpiar_push_subs():
        """Elimina todas las suscripciones push (usar tras cambiar claves VAPID)."""
        from app.extensions import db
        from app.models.system import PushSubscription
        n = PushSubscription.query.delete(); db.session.commit()
        print(f'limpiar-push-subs: {n} suscripciones eliminadas.')
