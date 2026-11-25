"""
Exportación centralizada de todos los modelos del ERP.
Importar desde aquí en blueprints y servicios para evitar imports dispersos.
"""

from .auth import Organizacion, User, TokenUsado
from .inventory import Categoria, Producto, Almacen, Stock, Movimiento, Salida
from .purchasing import (Proveedor, ProveedorIntegracion, HDSesion, FormatoProveedor,
                         EncabezadoOCProveedor,
                         OrdenCompra, OrdenCompraDetalle,
                         ProyectoOC, ProyectoOCDetalle)
from .finance import (Gasto, Servicio, PagoServicio, FacturaProveedor,
                      CentroCosto, Presupuesto)
from .system import AuditLog, PushSubscription, SolicitudAprobacion, Notificacion
from .incidencias import (Incidencia, IncidenciaAvance, IncidenciaAccion, IncidenciaCosto,
                          Departamento, DepartamentoMiembro, Pendiente, PendienteFoto)
from .chatbot import ChatConversacion, ChatMensaje, SoporteReporte

__all__ = [
    'Organizacion', 'User', 'TokenUsado',
    'Categoria', 'Producto', 'Almacen', 'Stock', 'Movimiento', 'Salida',
    'Proveedor', 'ProveedorIntegracion', 'HDSesion', 'FormatoProveedor',
    'EncabezadoOCProveedor',
    'OrdenCompra', 'OrdenCompraDetalle',
    'ProyectoOC', 'ProyectoOCDetalle',
    'Gasto', 'Servicio', 'PagoServicio', 'FacturaProveedor',
    'CentroCosto', 'Presupuesto',
    'AuditLog', 'PushSubscription', 'SolicitudAprobacion', 'Notificacion',
    'Incidencia', 'IncidenciaAvance', 'IncidenciaAccion', 'IncidenciaCosto',
    'Departamento', 'DepartamentoMiembro', 'Pendiente', 'PendienteFoto',
    'ChatConversacion', 'ChatMensaje', 'SoporteReporte',
]
