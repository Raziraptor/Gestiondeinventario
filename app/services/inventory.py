"""
Inventory business logic: stock movements, transfers, adjustments, kardex queries.

Service functions:
  - apply_stock_movement      → create Movimiento + update Stock.cantidad (core primitive)
  - get_or_create_stock       → fetch or create Stock row without committing
  - apply_transfer            → two-sided transfer between warehouses (salida + entrada)
  - apply_adjustment          → physical-count adjustment (ajuste-entrada / ajuste-salida)
  - build_kardex_query        → filtered Movimiento query for a product's history
  - get_stock_totals          → aggregate stock across warehouses for a product

Rules:
  - No Flask request context (no request, flash, redirect).
  - No db.session.commit() — caller owns the transaction.
  - Raises ValueError for invalid business inputs (caller decides how to surface errors).
"""

import secrets as _secrets

from app.extensions import db
from app.models import Stock, Movimiento, Almacen, Producto
from app.helpers import now_mx


# ==============================================================================
# PRIMITIVA: movimiento individual
# ==============================================================================

def apply_stock_movement(
    producto_id: int,
    almacen_id: int,
    cantidad: float,
    tipo: str,
    motivo: str,
    org_id: int,
    salida=None,
) -> tuple:
    """Aplica un movimiento de stock: actualiza Stock.cantidad y crea registro Movimiento.

    La cantidad puede ser positiva (entrada) o negativa (salida); el caller decide
    el signo según la semántica del tipo.

    Args:
        producto_id: ID del producto.
        almacen_id:  ID del almacén.
        cantidad:    Delta a aplicar al stock (positivo = entrada, negativo = salida).
        tipo:        Tipo de movimiento ('entrada-inicial', 'salida', 'transferencia-salida',
                     'transferencia-entrada', 'ajuste-entrada', 'ajuste-salida', etc.)
        motivo:      Descripción del movimiento.
        org_id:      ID de la organización.
        salida:      Objeto Salida relacionado (opcional, solo para tipo='salida').

    Returns:
        (stock, movimiento) — ambos añadidos a la sesión, sin commit.

    Raises:
        ValueError: Si el stock resultante sería negativo (stock insuficiente).
    """
    stock = Stock.query.filter_by(producto_id=producto_id, almacen_id=almacen_id).first()

    if stock is None:
        if cantidad < 0:
            raise ValueError(
                f"No existe stock del producto {producto_id} en el almacén {almacen_id}."
            )
        stock = Stock(
            producto_id=producto_id,
            almacen_id=almacen_id,
            cantidad=0,
            stock_minimo=5,
            stock_maximo=100,
            organizacion_id=org_id,
        )
        db.session.add(stock)

    nueva_cantidad = stock.cantidad + cantidad
    if nueva_cantidad < 0:
        raise ValueError(
            f"Stock insuficiente. Disponible: {stock.cantidad}, solicitado: {abs(cantidad)}."
        )

    stock.cantidad = nueva_cantidad

    mov = Movimiento(
        producto_id=producto_id,
        cantidad=cantidad,
        tipo=tipo,
        fecha=now_mx(),
        motivo=motivo,
        almacen_id=almacen_id,
        organizacion_id=org_id,
    )
    if salida is not None:
        mov.salida = salida

    db.session.add(stock)
    db.session.add(mov)

    return stock, mov


# ==============================================================================
# STOCK: get or create
# ==============================================================================

def get_or_create_stock(
    producto_id: int,
    almacen_id: int,
    *,
    stock_minimo: int = 5,
    stock_maximo: int = 100,
    cantidad_inicial: float = 0,
    org_id: int | None = None,
) -> tuple:
    """Devuelve (stock, created) para el par producto/almacén.

    Si no existe, crea el registro Stock con los valores por defecto indicados
    y lo añade a la sesión. No hace commit.

    Used in:
      - nueva_transferencia (destino)
      - eliminar_movimiento_salida (reversal)
      - gestionar_inventario_almacen (alta manual)
      - nuevo_producto (stock inicial)
    """
    stock = Stock.query.filter_by(producto_id=producto_id, almacen_id=almacen_id).first()
    if stock is not None:
        return stock, False

    stock = Stock(
        producto_id=producto_id,
        almacen_id=almacen_id,
        cantidad=cantidad_inicial,
        stock_minimo=stock_minimo,
        stock_maximo=stock_maximo,
    )
    if org_id is not None:
        stock.organizacion_id = org_id
    db.session.add(stock)
    return stock, True


# ==============================================================================
# TRANSFERENCIA ENTRE ALMACENES
# ==============================================================================

def apply_transfer(
    producto_id: int,
    origen_id: int,
    destino_id: int,
    cantidad: int,
    motivo: str,
    org_id: int,
) -> tuple:
    """Aplica una transferencia de stock entre dos almacenes.

    Lógica extraída de `nueva_transferencia`:
      1. Valida origen != destino, cantidad > 0.
      2. Verifica stock suficiente en origen.
      3. Descuenta en origen, añade en destino (get_or_create_stock).
      4. Crea Movimiento 'transferencia-salida' y 'transferencia-entrada' con la misma REF.

    Args:
        producto_id: ID del producto a transferir.
        origen_id:   ID del almacén origen.
        destino_id:  ID del almacén destino.
        cantidad:    Unidades a mover (> 0).
        motivo:      Descripción de la transferencia.
        org_id:      ID de la organización.

    Returns:
        (ref, mov_salida, mov_entrada) — ref es un token hex de 8 chars (e.g. 'A1B2C3D4').

    Raises:
        ValueError: Si origen == destino, cantidad <= 0 o stock insuficiente.

    Used in:
      - nueva_transferencia
    """
    if origen_id == destino_id:
        raise ValueError("El almacén de origen y destino no pueden ser el mismo.")
    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor a cero.")

    stock_origen = Stock.query.filter_by(producto_id=producto_id, almacen_id=origen_id).first()
    if not stock_origen or stock_origen.cantidad < cantidad:
        disponible = stock_origen.cantidad if stock_origen else 0
        raise ValueError(
            f"Stock insuficiente en el almacén origen. Disponible: {disponible}."
        )

    # Descuento origen
    stock_origen.cantidad -= cantidad
    db.session.add(stock_origen)

    # Alta/actualización destino
    stock_destino, created = get_or_create_stock(
        producto_id=producto_id,
        almacen_id=destino_id,
        stock_minimo=stock_origen.stock_minimo,
        stock_maximo=stock_origen.stock_maximo,
        cantidad_inicial=0,
    )
    stock_destino.cantidad += cantidad
    db.session.add(stock_destino)

    ref = _secrets.token_hex(4).upper()
    now = now_mx()

    mov_salida = Movimiento(
        producto_id=producto_id,
        cantidad=-cantidad,
        tipo='transferencia-salida',
        fecha=now,
        motivo=f'[REF:{ref}] {motivo}',
        almacen_id=origen_id,
        organizacion_id=org_id,
    )
    mov_entrada = Movimiento(
        producto_id=producto_id,
        cantidad=cantidad,
        tipo='transferencia-entrada',
        fecha=now,
        motivo=f'[REF:{ref}] {motivo}',
        almacen_id=destino_id,
        organizacion_id=org_id,
    )
    db.session.add(mov_salida)
    db.session.add(mov_entrada)

    return ref, mov_salida, mov_entrada


# ==============================================================================
# AJUSTE MANUAL DE INVENTARIO
# ==============================================================================

def apply_adjustment(
    producto_id: int,
    almacen_id: int,
    cantidad_fisica: int,
    motivo: str,
    org_id: int,
) -> tuple:
    """Aplica un ajuste de inventario por conteo físico.

    Lógica extraída de `nuevo_ajuste`:
      1. Obtiene Stock existente (debe existir — el caller ya validó).
      2. Calcula diferencia = cantidad_fisica - stock.cantidad.
      3. Si diferencia == 0, retorna (stock, None, 0) — no hay nada que hacer.
      4. Si diferencia != 0, actualiza Stock.cantidad y crea Movimiento de ajuste.

    Args:
        producto_id:     ID del producto.
        almacen_id:      ID del almacén.
        cantidad_fisica: Conteo físico real.
        motivo:          Razón del ajuste (obligatorio para auditoría).
        org_id:          ID de la organización.

    Returns:
        (stock, movimiento_or_None, diferencia)
        - movimiento es None cuando diferencia == 0 (sin cambio).

    Raises:
        ValueError: Si el Stock no existe para ese producto/almacén.

    Used in:
      - nuevo_ajuste
    """
    if not motivo:
        raise ValueError("El motivo del ajuste es obligatorio para la auditoría.")

    stock = Stock.query.filter_by(producto_id=producto_id, almacen_id=almacen_id).first()
    if not stock:
        raise ValueError(
            "No se encontró ese producto en el almacén seleccionado."
        )

    diferencia = cantidad_fisica - stock.cantidad
    if diferencia == 0:
        return stock, None, 0

    tipo_mov = 'ajuste-entrada' if diferencia > 0 else 'ajuste-salida'
    stock.cantidad = cantidad_fisica
    db.session.add(stock)

    mov = Movimiento(
        producto_id=producto_id,
        cantidad=diferencia,
        tipo=tipo_mov,
        fecha=now_mx(),
        motivo=f'Ajuste Físico: {motivo}',
        almacen_id=almacen_id,
        organizacion_id=org_id,
    )
    db.session.add(mov)

    return stock, mov, diferencia


# ==============================================================================
# KARDEX / HISTORIAL
# ==============================================================================

def build_kardex_query(producto_id: int, org_id: int, is_super_admin: bool = False):
    """Construye (sin ejecutar) el query de movimientos para el historial de un producto.

    Filtra por org_id a menos que sea super_admin.

    Args:
        producto_id:    ID del producto.
        org_id:         ID de la organización del usuario actual.
        is_super_admin: Si True, no filtra por org_id.

    Returns:
        SQLAlchemy Query object (llamar a .all(), .paginate(), etc. en el caller).

    Used in:
      - historial_producto
    """
    query = Movimiento.query.filter_by(producto_id=producto_id).order_by(Movimiento.fecha.desc())
    if not is_super_admin:
        query = query.filter(Movimiento.organizacion_id == org_id)
    return query


# ==============================================================================
# STOCK TOTALS
# ==============================================================================

def get_stock_totals(producto_id: int, org_id: int) -> tuple:
    """Retorna (stocks_list, total_global) para un producto dentro de una organización.

    Filtra stocks vía join con Almacen para respetar multi-tenant aun cuando
    Stock no tiene organizacion_id propio.

    Args:
        producto_id: ID del producto.
        org_id:      ID de la organización.

    Returns:
        (stocks_actuales, total_global) donde stocks_actuales es una lista de
        objetos Stock ordenados por Almacen.nombre.

    Used in:
      - historial_producto
    """
    stocks = (
        Stock.query
        .filter_by(producto_id=producto_id)
        .join(Almacen)
        .filter(Almacen.organizacion_id == org_id)
        .order_by(Almacen.nombre)
        .all()
    )
    total = sum(s.cantidad for s in stocks)
    return stocks, total
