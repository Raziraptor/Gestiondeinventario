"""
Purchasing business logic: OC reception, ProyectoOC reception, approval workflow.

Rules:
  - No Flask request context (no request, flash, redirect, url_for).
  - No db.session.commit() — caller owns the transaction.
  - Raises ValueError for invalid business inputs.

Functions:
  - receive_oc_items          → ingresa stock para una OC estándar recibida
  - receive_proyecto_oc_items → ingresa stock para ítems seleccionados de un ProyectoOC
  - resolve_solicitud         → aprueba o rechaza una SolicitudAprobacion
"""

from app.extensions import db
from app.models import Stock, Movimiento, SolicitudAprobacion, ProyectoOC
from app.helpers import now_mx


# ==============================================================================
# RECEPCIÓN DE OC ESTÁNDAR
# ==============================================================================

def receive_oc_items(orden, org_id: int) -> tuple:
    """Ingresa al inventario todos los detalles de una OrdenCompra recibida.

    Crea o actualiza Stock y genera un Movimiento 'entrada' por cada detalle.
    Ítems con producto eliminado o cantidad inválida se omiten (no abortan la
    operación completa — patrón no_autoflush + omitidos).

    Args:
        orden:  OrdenCompra ORM instance. Debe tener estado='enviada' y almacen_id.
        org_id: ID de la organización (para el registro del Movimiento).

    Returns:
        (procesados: int, omitidos: list[str])
        — omitidos contiene descripciones de los ítems saltados.

    Does NOT set orden.estado ni commit — el caller hace ambas cosas.

    Raises:
        ValueError: Si la orden no tiene almacen_id asignado.

    Source: purchasing/routes.py lines 314–347 (recibir_orden).
    """
    if not orden.almacen_id:
        raise ValueError('La orden no tiene un almacén asignado.')

    procesados = 0
    omitidos = []

    with db.session.no_autoflush:
        for detalle in orden.detalles:
            producto = detalle.producto
            cantidad = detalle.cantidad_solicitada

            if not producto:
                omitidos.append(f'detalle #{detalle.id} (producto eliminado)')
                continue
            if not cantidad or cantidad <= 0:
                omitidos.append(f'{producto.nombre} (cantidad inválida: {cantidad})')
                continue

            stock_item = Stock.query.filter_by(
                producto_id=producto.id, almacen_id=orden.almacen_id
            ).first()
            if stock_item:
                stock_item.cantidad += cantidad
            else:
                db.session.add(Stock(
                    producto_id=producto.id,
                    almacen_id=orden.almacen_id,
                    cantidad=cantidad,
                    stock_minimo=5,
                    stock_maximo=100,
                ))

            db.session.add(Movimiento(
                producto_id=producto.id,
                cantidad=cantidad,
                tipo='entrada',
                fecha=now_mx(),
                motivo=f'Recepción de OC #{orden.id}',
                orden_compra_id=orden.id,
                organizacion_id=org_id,
                almacen_id=orden.almacen_id,
            ))

            if hasattr(producto, 'cantidad_stock'):
                producto.cantidad_stock = (producto.cantidad_stock or 0) + cantidad

            procesados += 1

    return procesados, omitidos


# ==============================================================================
# RECEPCIÓN DE OC PROYECTO
# ==============================================================================

def receive_proyecto_oc_items(proyecto_oc, almacen_id: int, items_ids: set, org_id: int) -> int:
    """Ingresa al inventario los ítems seleccionados de un ProyectoOC.

    Solo procesa detalles cuyo producto_id esté en items_ids. Detalles
    sin producto_id (ítems externos) se ignoran silenciosamente.

    Args:
        proyecto_oc: ProyectoOC ORM instance. Debe tener estado='enviada'.
        almacen_id:  ID del almacén destino (ya validado por el caller).
        items_ids:   set[int] de producto_ids a ingresar.
        org_id:      ID de la organización.

    Returns:
        items_ingresados: int — cantidad de ítems efectivamente ingresados.

    Does NOT set proyecto_oc.estado, proyecto_oc.almacen_id, ni commit.

    Source: purchasing/routes.py lines 1314–1339 (recibir_proyecto_oc).
    """
    items_ingresados = 0

    for detalle in proyecto_oc.detalles:
        if not detalle.producto_id or detalle.producto_id not in items_ids:
            continue

        stock_item = Stock.query.filter_by(
            producto_id=detalle.producto_id, almacen_id=almacen_id
        ).first()
        if stock_item:
            stock_item.cantidad += detalle.cantidad
        else:
            db.session.add(Stock(
                producto_id=detalle.producto_id,
                almacen_id=almacen_id,
                organizacion_id=org_id,
                cantidad=detalle.cantidad,
                stock_minimo=5,
                stock_maximo=100,
            ))

        db.session.add(Movimiento(
            producto_id=detalle.producto_id,
            cantidad=detalle.cantidad,
            tipo='entrada',
            fecha=now_mx(),
            motivo=f'Recepción OC Proyecto #{proyecto_oc.id} — {proyecto_oc.nombre_proyecto}',
            almacen_id=almacen_id,
            organizacion_id=org_id,
        ))
        items_ingresados += 1

    return items_ingresados


# ==============================================================================
# FLUJO DE APROBACIÓN
# ==============================================================================

def resolve_solicitud(
    solicitud: SolicitudAprobacion,
    decision: str,
    aprobador_id: int,
    comentario: str = None,
) -> None:
    """Aprueba o rechaza una SolicitudAprobacion y actualiza la entidad vinculada.

    Para entidades tipo 'proyecto_oc':
      - 'aprobado' → ProyectoOC.estado = 'aprobada'
      - 'rechazado' → ProyectoOC.estado = 'borrador'

    Args:
        solicitud:    SolicitudAprobacion ORM instance. Debe tener estado='pendiente'.
        decision:     'aprobado' | 'rechazado'
        aprobador_id: ID del usuario que resuelve la solicitud.
        comentario:   Texto de motivo de rechazo (opcional).

    Does NOT commit — el caller hace log_actividad + commit.

    Raises:
        ValueError: Si decision no es 'aprobado' ni 'rechazado'.
        ValueError: Si solicitud.estado != 'pendiente'.

    Source: purchasing/routes.py lines 1213–1232 (aprobar_solicitud),
            lines 1257–1278 (rechazar_solicitud).
    """
    if decision not in ('aprobado', 'rechazado'):
        raise ValueError(f"Decisión inválida: '{decision}'. Debe ser 'aprobado' o 'rechazado'.")
    if solicitud.estado != 'pendiente':
        raise ValueError('Esta solicitud ya fue resuelta.')

    solicitud.estado = decision
    solicitud.aprobador_id = aprobador_id
    solicitud.resuelto_en = now_mx()
    solicitud.comentario = comentario or None

    if solicitud.entidad_tipo == 'proyecto_oc':
        oc = ProyectoOC.query.get(solicitud.entidad_id)
        if oc:
            oc.estado = 'aprobada' if decision == 'aprobado' else 'borrador'
