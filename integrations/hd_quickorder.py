"""
HD Pro Quick Order — generación de CSV para bulk upload.

HD Pro acepta una lista SKU+cantidad que llena el carrito sin reingreso manual.
Columnas requeridas: Item Number, Quantity
"""

import io
import csv


def generar_csv(orden) -> tuple[bytes, list[str]]:
    """
    Genera el CSV para HD Pro Quick Order a partir de una OrdenCompra.

    Usa producto.hd_sku si existe; si no, usa producto.codigo.
    Excluye detalles sin producto válido o sin cantidad.

    Returns:
        (csv_bytes, omitidos) — bytes UTF-8 sin BOM y lista de nombres omitidos.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['Item Number', 'Quantity'])

    omitidos = []
    for detalle in orden.detalles:
        if not detalle.producto:
            omitidos.append(f'Detalle #{detalle.id} sin producto')
            continue
        cantidad = detalle.cantidad_solicitada or 0
        if cantidad <= 0:
            omitidos.append(detalle.producto.nombre)
            continue
        sku = detalle.producto.hd_sku or detalle.producto.codigo
        writer.writerow([sku, int(cantidad)])

    return buf.getvalue().encode('utf-8'), omitidos
