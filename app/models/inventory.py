"""Modelos de inventario: categorías, productos, almacenes, stock, movimientos, salidas."""

from app.extensions import db
from app.helpers import now_mx


class Categoria(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    nombre          = db.Column(db.String(100), nullable=False, unique=True)
    descripcion     = db.Column(db.String(255), nullable=True)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)


class Producto(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    nombre          = db.Column(db.String(255), nullable=False)
    codigo          = db.Column(db.String(50),  unique=True, nullable=False)
    precio_unitario = db.Column(db.Numeric(10, 2), default=0)
    imagen_url      = db.Column(db.String(255), nullable=True)
    enlace_proveedor= db.Column(db.Text,        nullable=True)
    hd_sku          = db.Column(db.String(30),  nullable=True)

    categoria_id    = db.Column(db.Integer, db.ForeignKey('categoria.id'),  nullable=True)
    categoria       = db.relationship('Categoria', backref='productos', lazy=True)
    proveedor_id    = db.Column(db.Integer, db.ForeignKey('proveedor.id'),  nullable=True)
    proveedor       = db.relationship('Proveedor', backref='productos', lazy=True)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)
    unidades_por_caja = db.Column(db.Integer, default=1)

    stocks = db.relationship('Stock', backref='producto', lazy='dynamic',
                             cascade='all, delete-orphan')

    def get_stock_total(self):
        return db.session.query(db.func.sum(Stock.cantidad)).filter_by(
            producto_id=self.id).scalar() or 0


class Almacen(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    nombre          = db.Column(db.String(100), nullable=False)
    ubicacion       = db.Column(db.String(255), nullable=True)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)

    stocks = db.relationship('Stock', backref='almacen', lazy='dynamic',
                             cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Almacen {self.nombre}>'


class Stock(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    almacen_id  = db.Column(db.Integer, db.ForeignKey('almacen.id'),  nullable=False)
    cantidad    = db.Column(db.Integer, nullable=False, default=0)
    stock_minimo= db.Column(db.Integer, nullable=False, default=5)
    stock_maximo= db.Column(db.Integer, nullable=False, default=100)
    ubicacion   = db.Column(db.String(100), nullable=True)

    __table_args__ = (
        db.UniqueConstraint('producto_id', 'almacen_id', name='_producto_almacen_uc'),
    )

    @property
    def estado_stock(self):
        if self.cantidad < self.stock_minimo:
            return 'bajo'
        if self.cantidad > self.stock_maximo:
            return 'exceso'
        return 'ok'

    def __repr__(self):
        return f'<Stock ProdID:{self.producto_id} AlmID:{self.almacen_id} Qty:{self.cantidad}>'


class Salida(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    fecha           = db.Column(db.Date,       nullable=False, default=lambda: now_mx().date())
    estado          = db.Column(db.String(20), nullable=False, default='abierta')
    creador_id      = db.Column(db.Integer, db.ForeignKey('user.id'),        nullable=False)
    cancelado_por_id= db.Column(db.Integer, db.ForeignKey('user.id'),        nullable=True)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)
    almacen_id      = db.Column(db.Integer, db.ForeignKey('almacen.id'),      nullable=True)
    almacen         = db.relationship('Almacen')

    movimientos = db.relationship('Movimiento', backref='salida', lazy='dynamic',
                                  cascade='all, delete-orphan')


class Movimiento(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    producto_id     = db.Column(db.Integer, db.ForeignKey('producto.id'),    nullable=False)
    producto        = db.relationship('Producto', backref='movimientos', lazy=True)
    cantidad        = db.Column(db.Integer,    nullable=False)
    tipo            = db.Column(db.String(20), nullable=False)
    fecha           = db.Column(db.DateTime,   nullable=False, default=now_mx)
    motivo          = db.Column(db.String(255), nullable=False)
    orden_compra_id = db.Column(db.Integer, db.ForeignKey('orden_compra.id'), nullable=True)
    salida_id       = db.Column(db.Integer, db.ForeignKey('salida.id'),       nullable=True)
    almacen_id      = db.Column(db.Integer, db.ForeignKey('almacen.id'),      nullable=True)
    almacen         = db.relationship('Almacen', foreign_keys=[almacen_id],
                                      backref='movimientos', lazy=True)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)

    def __repr__(self):
        return f'<Movimiento {self.producto_id} ({self.cantidad})>'
