"""Retención de incidencias cerradas: aviso a 5 días y borrado al vencer `expira_en`.

Lo ejecuta `flask limpiar-incidencias-cerradas [--dry-run]` desde un cron diario.
Orden por incidencia: juntar rutas de fotos -> borrar filas (commit) -> borrar archivos.
Así un fallo a mitad deja, como mucho, archivos huérfanos (se registran), nunca filas sin foto.
"""

import os
from datetime import timedelta

from flask import current_app

from app.extensions import db
from app.helpers import now_mx
from app.models.incidencias import _ESTADOS_RETENCION, DIAS_AVISO, Incidencia
from app.models.system import AuditLog
from app.services.incidencias import ruta_absoluta_foto
from app.services.notifications import admins_de_org, notificar


def rutas_fotos(inc) -> list:
    """Toda foto ligada a la incidencia: legadas, de pendientes y de avances. Sin duplicados."""
    rutas = [getattr(inc, f'foto{i}_path') for i in (1, 2, 3)]
    for p in inc.pendientes:
        rutas += [f.path for f in p.fotos]
    rutas += [a.foto_path for a in inc.avances]
    return list(dict.fromkeys(r for r in rutas if r))


def borrar_archivo_seguro(ruta_relativa) -> str:
    """'borrado' | 'no_existe' | 'rechazado' (fuera de UPLOAD_FOLDER: guardia anti path-traversal)."""
    raiz = os.path.realpath(current_app.config['UPLOAD_FOLDER'])
    real = os.path.realpath(ruta_absoluta_foto(ruta_relativa))
    try:
        dentro = os.path.commonpath([raiz, real]) == raiz
    except ValueError:  # otra unidad en Windows
        dentro = False
    if not dentro:
        return 'rechazado'
    if not os.path.isfile(real):
        return 'no_existe'
    os.remove(real)
    return 'borrado'


def borrar_archivos(rutas) -> tuple:
    """Borra cada ruta con la guardia anti path-traversal. Devuelve (borrados, rechazados); nunca lanza."""
    borrados = rechazados = 0
    for ruta in rutas:
        try:
            estado = borrar_archivo_seguro(ruta)
        except OSError as exc:
            estado = 'error'
            current_app.logger.error('[Retención] archivo %s: %s', ruta, exc)
        if estado == 'borrado':
            borrados += 1
        elif estado == 'rechazado':
            rechazados += 1
            current_app.logger.warning('[Retención] ruta fuera de UPLOAD_FOLDER ignorada: %s', ruta)
    return borrados, rechazados


def ejecutar_retencion(ahora=None, dry_run=False, echo=print) -> dict:
    ahora = ahora or now_mx()
    r = {'por_avisar': 0, 'avisadas': 0, 'por_eliminar': 0, 'eliminadas': 0,
         'archivos_borrados': 0, 'archivos_rechazados': 0, 'errores': 0}

    por_avisar = Incidencia.query.filter(
        Incidencia.estado.in_(_ESTADOS_RETENCION),
        Incidencia.expira_en.isnot(None),
        Incidencia.expira_en > ahora,
        Incidencia.expira_en <= ahora + timedelta(days=DIAS_AVISO),
        Incidencia.aviso_expiracion_enviado.is_(False),
    ).order_by(Incidencia.id).all()
    for inc in por_avisar:
        r['por_avisar'] += 1
        echo(f'AVISO {inc.folio} org={inc.organizacion_id} se eliminará el {inc.expira_en:%d/%m/%Y}')
        if dry_run:
            continue
        try:
            inc.aviso_expiracion_enviado = True
            db.session.commit()
            notificar(
                inc.organizacion_id, [inc.creador_id] + admins_de_org(inc.organizacion_id),
                f'Se eliminará el {inc.expira_en:%d/%m/%Y} — {inc.folio}',
                f'{inc.folio}: se eliminará el {inc.expira_en:%d/%m}; descarga el PDF si lo necesitas.',
                f'/incidencias/{inc.id}',
            )
            r['avisadas'] += 1
        except Exception as exc:
            db.session.rollback()
            r['errores'] += 1
            current_app.logger.error('[Retención] aviso %s: %s', inc.folio, exc)

    vencidas = Incidencia.query.filter(
        Incidencia.estado.in_(_ESTADOS_RETENCION),
        Incidencia.expira_en.isnot(None),
        Incidencia.expira_en < ahora,
    ).order_by(Incidencia.id).all()
    for inc in vencidas:
        r['por_eliminar'] += 1
        folio = inc.folio
        try:
            rutas = rutas_fotos(inc)
            echo(f'ELIMINAR {folio} org={inc.organizacion_id} fotos={len(rutas)}')
            if dry_run:
                continue
            db.session.add(AuditLog(
                usuario_id=None, organizacion_id=inc.organizacion_id, accion='eliminar',
                entidad='incidencia', entidad_id=inc.id,
                descripcion=f'Incidencia {folio} eliminada por vigencia',
            ))
            db.session.delete(inc)
            db.session.commit()
            r['eliminadas'] += 1
        except Exception as exc:
            db.session.rollback()
            r['errores'] += 1
            current_app.logger.error('[Retención] eliminar %s: %s', folio, exc)
            continue
        borrados, rechazados = borrar_archivos(rutas)
        r['archivos_borrados'] += borrados
        r['archivos_rechazados'] += rechazados
    return r
