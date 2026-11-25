"""Backfill de datos legados para incidencias v3. ORM puro: corre igual en SQLite y PostgreSQL.

El DDL (tablas y columnas nuevas) vive en el comando `flask fix-incidencias-v3`
(app/cli/commands.py); esta función solo mueve datos y es segura de re-ejecutar.
"""

from datetime import timedelta

from app.extensions import db
from app.helpers import now_mx
from app.models.auth import User
from app.models.incidencias import (
    _ESTADOS_RETENCION, DIAS_RETENCION, Incidencia, IncidenciaAvance, Pendiente, PendienteFoto,
)
from app.services.incidencias import fecha_hora


def backfill_pendientes(ahora=None) -> dict:
    """Una incidencia sin pendientes recibe UN pendiente con sus fotos y avances legados.

    Devuelve conteos: pendientes, fotos, avances, gracia. Re-ejecutar devuelve ceros.
    """
    ahora = ahora or now_mx()
    conteo = {'pendientes': 0, 'fotos': 0, 'avances': 0, 'gracia': 0}
    for inc in Incidencia.query.order_by(Incidencia.id).all():
        if not inc.pendientes:
            resuelta = inc.estado == 'Resuelto'
            p = Pendiente(
                incidencia_id=inc.id,
                orden=0,
                descripcion=(inc.descripcion or '').strip() or inc.titulo,
                departamento_id=None,
                progreso=100 if resuelta else max(0, min(100, inc.progreso or 0)),
                completado_en=(fecha_hora(inc.fecha_cierre) if inc.fecha_cierre else ahora) if resuelta else None,
            )
            db.session.add(p)
            db.session.flush()
            for i in (1, 2, 3):
                ruta = getattr(inc, f'foto{i}_path')
                if ruta:
                    db.session.add(PendienteFoto(pendiente_id=p.id, path=ruta,
                                                 descripcion=getattr(inc, f'foto{i}_desc')))
                    conteo['fotos'] += 1
            conteo['avances'] += IncidenciaAvance.query.filter_by(
                incidencia_id=inc.id, pendiente_id=None,
            ).update({'pendiente_id': p.id}, synchronize_session=False)
            conteo['pendientes'] += 1
        if inc.estado in _ESTADOS_RETENCION and inc.expira_en is None:
            # Gracia: el historial migrado nunca se borra en la primera corrida del cron.
            inc.expira_en = ahora + timedelta(days=DIAS_RETENCION)
            inc.aviso_expiracion_enviado = False
            conteo['gracia'] += 1
    db.session.commit()
    return conteo


def conceder_permiso_crear_a_creadores() -> int:
    """Antes cualquiera creaba incidencias; ahora hace falta perm_crear_incidencias.

    Concede el permiso a quien ya creó alguna, para que nadie pierda el botón el primer día.
    El comando solo la llama cuando la columna se acaba de agregar (así un admin que
    revoque el permiso no lo ve regresar en una segunda corrida). Devuelve a cuántos concedió.
    """
    ids = {fila[0] for fila in db.session.query(Incidencia.creador_id).distinct()}
    if not ids:
        return 0
    n = User.query.filter(User.id.in_(ids), User.perm_crear_incidencias.is_(False)).update(
        {'perm_crear_incidencias': True}, synchronize_session=False)
    db.session.commit()
    return n
