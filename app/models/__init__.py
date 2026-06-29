"""
Exportación centralizada de todos los modelos del ERP.
Importar desde aquí en blueprints y servicios para evitar imports dispersos.
"""

from .auth import Organizacion, User, TokenUsado
from .inventory import Categoria, Producto, Almacen, Stock, Movimiento, Salida
from .purchasing import (Proveedor, ProveedorIntegracion, HDSesion, FormatoProveedor,
                         OrdenCompra, OrdenCompraDetalle,
                         ProyectoOC, ProyectoOCDetalle)
from .finance import (Gasto, Servicio, PagoServicio, FacturaProveedor,
                      CentroCosto, Presupuesto)
from .system import AuditLog, PushSubscription, SolicitudAprobacion

__all__ = [
    'Organizacion', 'User', 'TokenUsado',
    'Categoria', 'Producto', 'Almacen', 'Stock', 'Movimiento', 'Salida',
    'Proveedor', 'ProveedorIntegracion', 'HDSesion', 'FormatoProveedor',
    'OrdenCompra', 'OrdenCompraDetalle',
    'ProyectoOC', 'ProyectoOCDetalle',
    'Gasto', 'Servicio', 'PagoServicio', 'FacturaProveedor',
    'CentroCosto', 'Presupuesto',
    'AuditLog', 'PushSubscription', 'SolicitudAprobacion',
]
