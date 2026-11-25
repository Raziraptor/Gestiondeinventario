"""Reglas de negocio de incidencias: progreso, estados automáticos, reapertura.

Único lugar que escribe Incidencia.progreso, Incidencia.estado (salvo el alta en 'Abierto'),
fecha_cierre y expira_en. Las rutas llaman aquí; nunca calculan nada de esto por su cuenta.
Ninguna función hace commit: el llamador decide (patrón del repo: log_actividad antes del commit).
"""

import os
from datetime import datetime, time, timedelta

from flask import current_app

from app.extensions import db
from app.helpers import now_mx
from app.models.incidencias import (
    _ESTADOS, _ESTADOS_CIERRE, _ESTADOS_RETENCION, DIAS_RETENCION,
    IncidenciaAvance, Pendiente,
)

# Estados que solo un admin pone a mano y que el recálculo automático nunca pisa.
ESTADOS_FIJOS = ('Cerrado sin resolver', 'Escalado')
# Estados que acepta cambiar_estado (admin). 'En proceso' solo sirve para des-escalar.
ESTADOS_MANUALES = ('Cerrado sin resolver', 'Escalado', 'En proceso')
# Con estos estados ya no se registran avances.
ESTADOS_SIN_AVANCE = ('Resuelto', 'Cerrado sin resolver')


def promedio(valores) -> int:
    """Media entera con redondeo half-up: [100, 0, 0] -> 33, [100, 100, 0] -> 67, [] -> 0."""
    valores = list(valores)
    if not valores:
        return 0
    return int(sum(valores) / len(valores) + 0.5)


def progreso_desde_avance(porcentaje, concluido) -> int:
    """Porcentaje acotado a 0..100; concluido fuerza 100."""
    if concluido:
        return 100
    try:
        p = int(porcentaje)
    except (TypeError, ValueError):
        p = 0
    return max(0, min(100, p))


def progreso_departamento(inc, departamento_id) -> int:
    return promedio(p.progreso for p in inc.pendientes if p.departamento_id == departamento_id)


def _departamento_completo(inc, departamento_id) -> bool:
    propios = [p for p in inc.pendientes if p.departamento_id == departamento_id]
    return bool(propios) and all(p.progreso >= 100 for p in propios)


def recalcular_incidencia(inc, ahora=None) -> list:
    """Recalcula la caché de progreso y cierra en automático. Devuelve eventos ('completada')."""
    ahora = ahora or now_mx()
    pendientes = list(inc.pendientes)
    inc.progreso = promedio(p.progreso for p in pendientes)
    if inc.estado in ESTADOS_FIJOS:
        return []
    if pendientes and all(p.progreso >= 100 for p in pendientes) and inc.estado != 'Resuelto':
        inc.estado = 'Resuelto'
        inc.estado_final = 'Resuelto'
        inc.fecha_cierre = ahora.date()
        inc.expira_en = ahora + timedelta(days=DIAS_RETENCION)
        inc.aviso_expiracion_enviado = False
        return ['completada']
    return []


def registrar_avance(pendiente, autor_id, texto, porcentaje, concluido=False, foto_path=None, ahora=None):
    """Crea el avance, actualiza el pendiente y la incidencia.

    Devuelve (avance, eventos). eventos es una lista de tuplas (tipo, departamento_id):
      ('iniciada', depto|None)                -> la incidencia pasó de 'Abierto' a 'En proceso'
      ('departamento_completado', depto)      -> ese departamento terminó todos sus pendientes
      ('completada', None)                    -> todos los pendientes llegaron a 100
    """
    ahora = ahora or now_mx()
    inc = pendiente.incidencia
    depto_id = pendiente.departamento_id
    depto_completo_antes = depto_id is not None and _departamento_completo(inc, depto_id)

    valor = progreso_desde_avance(porcentaje, concluido)
    avance = IncidenciaAvance(
        incidencia_id=inc.id,
        pendiente=pendiente,
        texto=texto,
        porcentaje=valor,
        concluido=valor >= 100,
        foto_path=foto_path,
        autor_id=autor_id,
        creado_en=ahora,
    )
    db.session.add(avance)
    pendiente.progreso = valor
    pendiente.completado_en = (pendiente.completado_en or ahora) if valor >= 100 else None

    eventos = []
    if inc.estado == 'Abierto':
        inc.estado = 'En proceso'
        eventos.append(('iniciada', depto_id))
    if depto_id is not None and not depto_completo_antes and _departamento_completo(inc, depto_id):
        eventos.append(('departamento_completado', depto_id))
    eventos += [(e, None) for e in recalcular_incidencia(inc, ahora)]
    return avance, eventos


def aplicar_estado_manual(inc, nuevo_estado, ahora=None):
    """cambiar_estado (solo admin). Acepta únicamente ESTADOS_MANUALES."""
    ahora = ahora or now_mx()
    if nuevo_estado not in ESTADOS_MANUALES or nuevo_estado not in _ESTADOS:
        raise ValueError('Estado no válido.')
    if nuevo_estado == 'En proceso':
        if inc.estado != 'Escalado':
            raise ValueError('Solo una incidencia escalada puede volver a "En proceso".')
        inc.estado = 'En proceso'
        inc.estado_final = None
        inc.expira_en = None
        recalcular_incidencia(inc, ahora)
        return
    inc.estado = nuevo_estado
    if nuevo_estado in _ESTADOS_CIERRE:
        inc.estado_final = nuevo_estado
        inc.fecha_cierre = inc.fecha_cierre or ahora.date()
    if nuevo_estado in _ESTADOS_RETENCION:
        inc.expira_en = ahora + timedelta(days=DIAS_RETENCION)
        inc.aviso_expiracion_enviado = False
    else:
        inc.expira_en = None


def reabrir_incidencia(inc, pendiente_ids=(), nueva_descripcion=None, nuevo_departamento_id=None, ahora=None):
    """Reabre una incidencia cerrada. Devuelve el Pendiente nuevo o None.

    'Resuelto': los pendientes elegidos vuelven a 0 y/o se agrega uno nuevo (al menos una de las dos).
    'Cerrado sin resolver': solo vuelve a 'En proceso'.
    En ambos casos se limpian fecha_cierre, estado_final y expira_en (el reloj reinicia al cerrar).
    """
    if inc.estado not in _ESTADOS_RETENCION:
        raise ValueError('Solo se puede reabrir una incidencia cerrada.')
    nuevo = None
    if inc.estado == 'Resuelto':
        ids = {int(i) for i in pendiente_ids}
        nueva_descripcion = (nueva_descripcion or '').strip()
        if not ids and not nueva_descripcion:
            raise ValueError('Elige al menos un pendiente o agrega uno nuevo.')
        for p in inc.pendientes:
            if p.id in ids:
                p.progreso = 0
                p.completado_en = None
        if nueva_descripcion:
            orden = max((p.orden for p in inc.pendientes), default=-1) + 1
            nuevo = Pendiente(descripcion=nueva_descripcion, orden=orden, progreso=0,
                              departamento_id=nuevo_departamento_id)
            inc.pendientes.append(nuevo)
    inc.estado = 'En proceso'
    inc.estado_final = None
    inc.fecha_cierre = None
    inc.expira_en = None
    inc.aviso_expiracion_enviado = False
    inc.progreso = promedio(p.progreso for p in inc.pendientes)
    return nuevo


def ruta_absoluta_foto(ruta_relativa: str) -> str:
    """Las rutas guardadas son relativas a static/ ('uploads/incidencias/<org>/<archivo>').

    static/ es el padre de UPLOAD_FOLDER (app/config.py). Leerlo de la config permite que los
    tests apunten UPLOAD_FOLDER a un directorio temporal.
    """
    static_dir = os.path.dirname(current_app.config['UPLOAD_FOLDER'])
    return os.path.join(static_dir, ruta_relativa)


def fecha_hora(d) -> datetime:
    """date -> datetime a las 00:00 (para completado_en de datos legados)."""
    return datetime.combine(d, time.min)
