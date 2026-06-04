"""Modelos financieros: gastos, servicios, facturas, centros de costo, presupuestos."""

from datetime import date

from app.extensions import db
from app.helpers import now_mx, MESES_ES


class Gasto(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    descripcion     = db.Column(db.String(255),    nullable=False)
    monto           = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    categoria       = db.Column(db.String(50),     nullable=True)
    fecha           = db.Column(db.DateTime,       nullable=False, default=now_mx)
    orden_compra_id = db.Column(db.Integer, db.ForeignKey('orden_compra.id'), nullable=True)
    orden_compra    = db.relationship('OrdenCompra', backref='gastos_asociados', lazy=True)
    centro_costo_id = db.Column(db.Integer, db.ForeignKey('centro_costo.id'), nullable=True)
    centro_costo    = db.relationship('CentroCosto', backref='gastos', lazy=True)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)

    def __repr__(self):
        return f'<Gasto {self.descripcion} - ${self.monto}>'


class Servicio(db.Model):
    __tablename__ = 'servicio'
    id               = db.Column(db.Integer,  primary_key=True)
    nombre           = db.Column(db.String(100), nullable=False)
    tipo             = db.Column(db.String(30),  default='otro')
    proveedor_nombre = db.Column(db.String(80),  nullable=True)
    numero_contrato  = db.Column(db.String(60),  nullable=True)
    dia_vencimiento  = db.Column(db.Integer,     nullable=True)
    dias_aviso       = db.Column(db.Integer,     default=5)
    notas            = db.Column(db.Text,        nullable=True)
    activo           = db.Column(db.Boolean,     default=True)
    organizacion_id  = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)
    creado_en        = db.Column(db.DateTime,    default=now_mx)

    pagos = db.relationship('PagoServicio', backref='servicio', lazy=True,
                            order_by='PagoServicio.fecha_vencimiento.desc()',
                            cascade='all, delete-orphan')


class PagoServicio(db.Model):
    __tablename__ = 'pago_servicio'
    id                = db.Column(db.Integer,      primary_key=True)
    servicio_id       = db.Column(db.Integer,      db.ForeignKey('servicio.id'),      nullable=False)
    monto             = db.Column(db.Numeric(10, 2), nullable=False)
    fecha_vencimiento = db.Column(db.Date,         nullable=False)
    fecha_pago        = db.Column(db.Date,         nullable=True)
    estado            = db.Column(db.String(20),   default='pendiente')
    notas             = db.Column(db.Text,         nullable=True)
    comprobante_url   = db.Column(db.String(300),  nullable=True)
    registrado_por_id = db.Column(db.Integer,      db.ForeignKey('user.id'),           nullable=True)
    creado_en         = db.Column(db.DateTime,     default=now_mx)
    centro_costo_id   = db.Column(db.Integer,      db.ForeignKey('centro_costo.id'),  nullable=True)
    centro_costo      = db.relationship('CentroCosto', backref='pagos_servicio', lazy=True)


class FacturaProveedor(db.Model):
    __tablename__ = 'factura_proveedor'
    id                = db.Column(db.Integer,      primary_key=True)
    numero_factura    = db.Column(db.String(80),   nullable=False)
    proveedor_id      = db.Column(db.Integer,      db.ForeignKey('proveedor.id'),      nullable=False)
    proveedor         = db.relationship('Proveedor', backref='facturas')
    orden_compra_id   = db.Column(db.Integer,      db.ForeignKey('orden_compra.id'),   nullable=True)
    orden_compra      = db.relationship('OrdenCompra', backref='facturas')
    monto             = db.Column(db.Numeric(10, 2), nullable=False)
    fecha_emision     = db.Column(db.Date,         nullable=False)
    fecha_vencimiento = db.Column(db.Date,         nullable=False)
    estado            = db.Column(db.String(20),   nullable=False, default='pendiente')
    notas             = db.Column(db.Text,         nullable=True)
    registrado_por_id = db.Column(db.Integer,      db.ForeignKey('user.id'),           nullable=True)
    registrado_por    = db.relationship('User',    foreign_keys='FacturaProveedor.registrado_por_id')
    creado_en         = db.Column(db.DateTime,     default=now_mx)
    organizacion_id   = db.Column(db.Integer,      db.ForeignKey('organizacion.id'),   nullable=False)
    centro_costo_id   = db.Column(db.Integer,      db.ForeignKey('centro_costo.id'),   nullable=True)
    centro_costo      = db.relationship('CentroCosto', backref='facturas', lazy=True)

    @property
    def dias_vencimiento(self):
        return (self.fecha_vencimiento - date.today()).days

    @property
    def esta_vencida(self):
        return self.estado == 'pendiente' and self.fecha_vencimiento < date.today()

    @property
    def bucket_aging(self):
        if self.estado == 'pagado':
            return 'pagado'
        dias = (date.today() - self.fecha_vencimiento).days
        if dias <= 0:
            return 'vigente'
        if dias <= 30:
            return '1-30'
        if dias <= 60:
            return '31-60'
        if dias <= 90:
            return '61-90'
        return '90+'


class CentroCosto(db.Model):
    __tablename__ = 'centro_costo'
    id              = db.Column(db.Integer,    primary_key=True)
    nombre          = db.Column(db.String(120), nullable=False)
    descripcion     = db.Column(db.Text,        nullable=True)
    presupuesto     = db.Column(db.Float,       nullable=True)
    estado          = db.Column(db.String(20),  nullable=False, default='activo')
    creado_en       = db.Column(db.DateTime,    default=now_mx)
    organizacion_id = db.Column(db.Integer,     db.ForeignKey('organizacion.id'), nullable=False)
    creador_id      = db.Column(db.Integer,     db.ForeignKey('user.id'),         nullable=True)
    creador         = db.relationship('User',   foreign_keys='CentroCosto.creador_id')

    @property
    def total_gastado(self):
        g = sum(x.monto for x in self.gastos)
        p = sum(x.monto for x in self.pagos_servicio if x.estado == 'pagado')
        f = sum(x.monto for x in self.facturas)
        return g + p + f

    @property
    def pct_presupuesto(self):
        if not self.presupuesto or self.presupuesto <= 0:
            return None
        return min(round(float(self.total_gastado) / self.presupuesto * 100, 1), 100)


class Presupuesto(db.Model):
    __tablename__ = 'presupuesto'
    id              = db.Column(db.Integer,    primary_key=True)
    categoria       = db.Column(db.String(50), nullable=False)
    anio            = db.Column(db.Integer,    nullable=False)
    mes             = db.Column(db.Integer,    nullable=True)
    monto           = db.Column(db.Float,      nullable=False)
    organizacion_id = db.Column(db.Integer,    db.ForeignKey('organizacion.id'), nullable=False)
    creado_en       = db.Column(db.DateTime,   default=now_mx)

    __table_args__ = (
        db.UniqueConstraint('organizacion_id', 'categoria', 'anio', 'mes',
                            name='uq_presupuesto_cat_periodo'),
    )

    @property
    def periodo_label(self):
        if self.mes:
            return f'{MESES_ES[self.mes]} {self.anio}'
        return f'Anual {self.anio}'
