"""Modelos de compras: proveedores, órdenes de compra, OC proyectos, HD Pro."""

import os
import json

from app.extensions import db
from app.helpers import now_mx


class Proveedor(db.Model):
    id                = db.Column(db.Integer, primary_key=True)
    nombre            = db.Column(db.String(100), nullable=False, unique=True)
    contacto_email    = db.Column(db.String(100), nullable=True)
    contacto_telefono = db.Column(db.String(50),  nullable=True)
    organizacion_id   = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)


class ProveedorIntegracion(db.Model):
    """Credenciales cifradas para integraciones con proveedores externos."""
    __tablename__ = 'proveedor_integracion'
    id              = db.Column(db.Integer, primary_key=True)
    proveedor_id    = db.Column(db.Integer, db.ForeignKey('proveedor.id'),    nullable=False)
    proveedor       = db.relationship('Proveedor', backref=db.backref('integracion', uselist=False))
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)
    tipo            = db.Column(db.String(30), nullable=False, default='homedepot')
    _credenciales   = db.Column('credenciales', db.Text, nullable=True)
    activo          = db.Column(db.Boolean, default=True, nullable=False)

    @property
    def credenciales(self):
        if not self._credenciales:
            return {}
        from cryptography.fernet import Fernet, InvalidToken
        key = os.environ.get('FERNET_KEY', '').encode()
        if not key:
            return {}
        try:
            return json.loads(Fernet(key).decrypt(self._credenciales.encode()).decode())
        except (InvalidToken, Exception):
            return {}

    @credenciales.setter
    def credenciales(self, value):
        from cryptography.fernet import Fernet
        key = os.environ.get('FERNET_KEY', '').encode()
        if not key:
            raise ValueError('FERNET_KEY no configurada en variables de entorno')
        self._credenciales = Fernet(key).encrypt(json.dumps(value).encode()).decode()


class HDSesion(db.Model):
    """Sesión persistente de HD Pro: cookies cifradas, TTL 7 días."""
    __tablename__ = 'hd_sesion'
    id           = db.Column(db.Integer,  primary_key=True)
    org_id       = db.Column(db.Integer,  db.ForeignKey('organizacion.id'), nullable=False)
    proveedor_id = db.Column(db.Integer,  db.ForeignKey('proveedor.id'),    nullable=False)
    _cookies     = db.Column('cookies_json_cifrado', db.Text, nullable=True)
    expira_en    = db.Column(db.DateTime, nullable=False)
    creada_en    = db.Column(db.DateTime, nullable=False, default=now_mx)


class OrdenCompra(db.Model):
    id                   = db.Column(db.Integer, primary_key=True)
    fecha_creacion       = db.Column(db.DateTime, nullable=False, default=now_mx)
    fecha_recepcion      = db.Column(db.DateTime, nullable=True)
    estado               = db.Column(db.String(20), nullable=False, default='borrador')
    proveedor_id         = db.Column(db.Integer, db.ForeignKey('proveedor.id'),    nullable=False)
    proveedor            = db.relationship('Proveedor', backref='ordenes_compra',  lazy=True)
    almacen_id           = db.Column(db.Integer, db.ForeignKey('almacen.id'),      nullable=True)
    almacen              = db.relationship('Almacen', foreign_keys='OrdenCompra.almacen_id')
    creador_id           = db.Column(db.Integer, db.ForeignKey('user.id'),         nullable=False)
    cancelado_por_id     = db.Column(db.Integer, db.ForeignKey('user.id'),         nullable=True)
    organizacion_id      = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)
    integracion_status   = db.Column(db.String(20), nullable=True)
    integracion_resultado= db.Column(db.Text,       nullable=True)

    detalles = db.relationship('OrdenCompraDetalle', backref='orden', lazy=True,
                               cascade='all, delete-orphan')

    @property
    def costo_total(self):
        return sum(d.subtotal for d in self.detalles)


class OrdenCompraDetalle(db.Model):
    id                       = db.Column(db.Integer, primary_key=True)
    orden_id                 = db.Column(db.Integer, db.ForeignKey('orden_compra.id'), nullable=False)
    producto_id              = db.Column(db.Integer, db.ForeignKey('producto.id'),     nullable=False)
    producto                 = db.relationship('Producto')
    almacen_id               = db.Column(db.Integer, db.ForeignKey('almacen.id'),     nullable=True)
    almacen                  = db.relationship('Almacen')
    cantidad_solicitada      = db.Column(db.Integer,      nullable=False, default=1)
    cajas                    = db.Column(db.Float,        nullable=True,  default=0.0)
    costo_unitario_estimado  = db.Column(db.Numeric(10, 2), nullable=True, default=0)
    enlace_proveedor         = db.Column(db.Text,         nullable=True)

    @property
    def subtotal(self):
        return self.cantidad_solicitada * (self.costo_unitario_estimado or 0)


class ProyectoOC(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    nombre_proyecto = db.Column(db.String(255), nullable=False)
    fecha_creacion  = db.Column(db.DateTime,    nullable=False, default=now_mx)
    estado          = db.Column(db.String(20),  nullable=False, default='borrador')
    creador_id      = db.Column(db.Integer, db.ForeignKey('user.id'),         nullable=False)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)
    almacen_id      = db.Column(db.Integer, db.ForeignKey('almacen.id'),      nullable=True)
    almacen         = db.relationship('Almacen', foreign_keys='ProyectoOC.almacen_id')
    fecha_envio     = db.Column(db.DateTime, nullable=True)
    fecha_recepcion = db.Column(db.DateTime, nullable=True)
    recibido_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    recibido_por    = db.relationship('User', foreign_keys='ProyectoOC.recibido_por_id',
                                      overlaps='proyectos_oc_creados')

    detalles = db.relationship('ProyectoOCDetalle', backref='proyecto_oc', lazy=True,
                               cascade='all, delete-orphan')

    @property
    def costo_total(self):
        return sum(d.subtotal for d in self.detalles)


class ProyectoOCDetalle(db.Model):
    id                  = db.Column(db.Integer, primary_key=True)
    proyecto_oc_id      = db.Column(db.Integer, db.ForeignKey('proyecto_oc.id'), nullable=False)
    producto_id         = db.Column(db.Integer, db.ForeignKey('producto.id'),    nullable=True)
    producto            = db.relationship('Producto')
    descripcion_nuevo   = db.Column(db.Text,         nullable=True)
    proveedor_sugerido  = db.Column(db.String(255),  nullable=True)
    cantidad            = db.Column(db.Integer,      nullable=False, default=1)
    costo_unitario      = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    enlace_proveedor    = db.Column(db.Text,         nullable=True)
    comentarios_detalle = db.Column(db.Text,         nullable=True)

    @property
    def subtotal(self):
        return self.cantidad * self.costo_unitario
