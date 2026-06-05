"""
Finance business logic service.

Extracted from app/blueprints/finance/routes.py — functions that:
  - contain no Flask request/response concerns, OR
  - are called from 2+ routes and contain reusable business logic.

Rules:
  - No `request`, `flash`, `redirect` here.
  - Service functions do NOT commit to DB unless they are explicit batch operations
    (update_payment_statuses is the sole exception — it acts as a batch job).
  - Callers own db.session.commit() for all other functions.
"""

from datetime import datetime as _dt
from decimal import Decimal

from sqlalchemy import extract

from app.extensions import db
from app.models import Gasto, Presupuesto, PagoServicio, Servicio
from app.helpers import now_mx


# ---------------------------------------------------------------------------
# INTERNAL HELPERS
# ---------------------------------------------------------------------------

def _real_por_categoria(org_id: int, categoria: str, anio: int, mes) -> Decimal:
    """Suma de gastos reales de una categoría para un año/mes dado.

    Args:
        org_id:    ID de la organización.
        categoria: Nombre de la categoría de gasto.
        anio:      Año del período.
        mes:       Mes (1-12) o None para acumulado anual.

    Returns:
        Decimal con el total gastado; Decimal('0') si no hay registros.

    Source: finance/routes.py lines 98-104 (_real_por_categoria).
    """
    q = Gasto.query.filter_by(organizacion_id=org_id, categoria=categoria)
    q = q.filter(extract('year', Gasto.fecha) == anio)
    if mes:
        q = q.filter(extract('month', Gasto.fecha) == mes)
    return sum(g.monto for g in q.all()) or Decimal('0')


def _semaforo(pct: float):
    """Devuelve (clase_bootstrap, etiqueta) según porcentaje gastado.

    Returns:
        Tuple[str, str]: (bootstrap_class, label)
          - ('danger',  'Crítico') when pct >= 90
          - ('warning', 'Alerta')  when 70 <= pct < 90
          - ('success', 'OK')      otherwise

    Source: finance/routes.py lines 89-95 (_semaforo).
    """
    if pct >= 90:
        return 'danger', 'Crítico'
    if pct >= 70:
        return 'warning', 'Alerta'
    return 'success', 'OK'


# ---------------------------------------------------------------------------
# PUBLIC SERVICE FUNCTIONS
# ---------------------------------------------------------------------------

_TIPO_A_CATEGORIA_GASTO = {
    'luz':       'Energía Eléctrica',
    'agua':      'Agua y Drenaje',
    'gas':       'Gas',
    'internet':  'Internet',
    'telefono':  'Telefonía',
    'renta':     'Renta',
    'limpieza':  'Limpieza',
    'otro':      'Servicios',
}


def get_budget_semaphore(presupuesto_id: int, org_id: int) -> dict:
    """Calcula el estado semáforo de un presupuesto individual.

    Queries the Presupuesto record, computes actual spend via _real_por_categoria,
    and returns a summary dict ready for template rendering.

    Args:
        presupuesto_id: Primary key of the Presupuesto record.
        org_id:         Organization ID (enforces multi-tenant isolation).

    Returns:
        dict with keys:
          - presupuesto  : Presupuesto ORM object (or None if not found)
          - gastado      : Decimal — amount already spent in the period
          - disponible   : Decimal — presupuesto.monto minus gastado
          - pct          : float  — utilization percentage (capped at 999)
          - pct_bar      : float  — same value capped at 100 for progress bars
          - estado       : str    — 'ok' | 'warn' | 'danger' (semantic key)
          - cls          : str    — Bootstrap color class ('success'|'warning'|'danger')
          - label        : str    — Human-readable label ('OK'|'Alerta'|'Crítico')

    Returns a dict with presupuesto=None and zeroed values if the record is not found.

    Source: finance/routes.py lines 89-95 (_semaforo), 98-104 (_real_por_categoria),
            and the per-item calculation block at lines 647-659 (lista_presupuestos).
    """
    p = Presupuesto.query.filter_by(id=presupuesto_id, organizacion_id=org_id).first()
    if p is None:
        return {
            'presupuesto': None,
            'gastado': Decimal('0'),
            'disponible': Decimal('0'),
            'pct': 0.0,
            'pct_bar': 0.0,
            'estado': 'ok',
            'cls': 'success',
            'label': 'OK',
        }

    gastado = _real_por_categoria(org_id, p.categoria, p.anio, p.mes)
    pct = min(round(float(gastado) / float(p.monto) * 100, 1), 999) if p.monto > 0 else 0.0
    cls, label = _semaforo(pct)

    # Map Bootstrap class name to a short semantic key for programmatic use
    estado_map = {'success': 'ok', 'warning': 'warn', 'danger': 'danger'}

    return {
        'presupuesto': p,
        'gastado': gastado,
        'disponible': p.monto - gastado,
        'pct': pct,
        'pct_bar': min(pct, 100),
        'estado': estado_map[cls],
        'cls': cls,
        'label': label,
    }


def update_payment_statuses(org_id: int) -> int:
    """Marca como 'vencido' los PagoServicio pendientes cuya fecha_vencimiento ya pasó.

    This is a batch operation. Unlike other service functions it calls
    db.session.commit() itself, because it is always used as a "refresh before
    render" side-effect called at the top of two GET routes.

    Args:
        org_id: Organization ID — only touches payments that belong to this org's
                services (filters via subquery join to Servicio.organizacion_id).

    Returns:
        int: Number of rows updated (0 if none were overdue).

    Does NOT raise on failure — any exception is swallowed so that a stale
    payment state never blocks page rendering.

    Source: finance/routes.py lines 148-157 (_actualizar_estados_pagos).
    Called from: lista_servicios (line 971), detalle_servicio (line 1059).
    """
    try:
        hoy = now_mx().date()
        serv_ids = db.session.query(Servicio.id).filter_by(organizacion_id=org_id).subquery()
        updated = PagoServicio.query.filter(
            PagoServicio.servicio_id.in_(serv_ids),
            PagoServicio.estado == 'pendiente',
            PagoServicio.fecha_vencimiento < hoy,
        ).update({'estado': 'vencido'}, synchronize_session=False)
        db.session.commit()
        return updated
    except Exception:
        db.session.rollback()
        return 0


def registrar_gasto_servicio(pago: PagoServicio) -> None:
    """Crea un Gasto automáticamente al marcar un PagoServicio como pagado.

    Maps the service type to the appropriate expense category and adds a new
    Gasto record to the session. Does NOT commit — the calling route owns the
    commit so that the Gasto and the payment status change are atomic.

    Args:
        pago: PagoServicio ORM instance that has just been set to estado='pagado'.
              pago.servicio must be loaded (not None).

    Returns:
        None. No-ops silently if pago.servicio is None.

    Source: finance/routes.py lines 130-145 (_registrar_gasto_servicio).
    Called from: nuevo_pago_servicio (line 1098), marcar_pago_pagado (line 1144).
    """
    s = pago.servicio
    if not s:
        return
    categoria = _TIPO_A_CATEGORIA_GASTO.get(s.tipo or 'otro', 'Servicios')
    fecha_dt = _dt.combine(pago.fecha_pago, _dt.min.time())
    gasto = Gasto(
        descripcion=f"Servicio: {s.nombre}",
        monto=pago.monto,
        categoria=categoria,
        fecha=fecha_dt,
        organizacion_id=s.organizacion_id,
    )
    db.session.add(gasto)
