"""Modelos de autenticación y organización."""

from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

from app.extensions import db
from app.helpers import now_mx


class Organizacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), unique=True, nullable=False)
    codigo_invitacion = db.Column(db.String(10), unique=True, nullable=True)

    logo_url         = db.Column(db.String(255), nullable=True)
    header_titulo    = db.Column(db.String(150), nullable=True)
    header_subtitulo = db.Column(db.String(200), nullable=True)
    color_primario   = db.Column(db.String(7),   default='#333333')
    color_secundario = db.Column(db.String(7),   default='#f1f5f9')
    tipo_letra       = db.Column(db.String(50),  default='Helvetica')
    direccion        = db.Column(db.Text,        nullable=True)
    telefono         = db.Column(db.String(20),  nullable=True)
    rfc              = db.Column(db.String(20),  nullable=True)
    correo_empresa   = db.Column(db.String(120), nullable=True)
    footer_texto     = db.Column(db.Text,        nullable=True)
    pdf_mostrar_qr   = db.Column(db.Boolean,     default=False)
    whatsapp_notify  = db.Column(db.String(25),  nullable=True, default=None)

    etiqueta_fuente       = db.Column(db.String(50), default='Inter')
    etiqueta_color_fondo  = db.Column(db.String(7),  default='#FFFFFF')
    etiqueta_color_texto  = db.Column(db.String(7),  default='#1a1a1a')
    etiqueta_color_sku    = db.Column(db.String(7),  default='#1f4e79')
    etiqueta_estilo       = db.Column(db.String(20), default='moderno')
    etiqueta_mostrar_logo = db.Column(db.Boolean,    default=True)

    excel_color_header   = db.Column(db.String(7),  default='#1f4e79')
    excel_color_accent   = db.Column(db.String(7),  default='#dbeafe')
    excel_fuente         = db.Column(db.String(30), default='Calibri')
    excel_mostrar_logo   = db.Column(db.Boolean,    default=True)
    excel_mostrar_id     = db.Column(db.Boolean,    default=True)
    excel_mostrar_oc     = db.Column(db.Boolean,    default=True)
    excel_mostrar_origen = db.Column(db.Boolean,    default=True)

    usuarios       = db.relationship('User',       backref='organizacion',   lazy=True)
    productos      = db.relationship('Producto',   backref='organizacion',   lazy=True)
    categorias     = db.relationship('Categoria',  backref='organizacion',   lazy=True)
    proveedores    = db.relationship('Proveedor',  backref='organizacion',   lazy=True)
    ordenes_compra = db.relationship('OrdenCompra',backref='organizacion',   lazy=True)
    salidas        = db.relationship('Salida',     backref='organizacion',   lazy=True)
    gastos         = db.relationship('Gasto',      backref='organizacion',   lazy=True)
    movimientos    = db.relationship('Movimiento', backref='organizacion',   lazy=True)
    proyectos_oc   = db.relationship('ProyectoOC', backref='organizacion',   lazy=True)
    almacenes      = db.relationship('Almacen',    backref='organizacion',   lazy=True)

    def __repr__(self):
        return f'<Organizacion {self.nombre}>'


class User(db.Model, UserMixin):
    id           = db.Column(db.Integer, primary_key=True)
    username     = db.Column(db.String(80),  unique=True, nullable=False)
    email        = db.Column(db.String(120), unique=True, nullable=False)
    image_file   = db.Column(db.String(20),  nullable=False, default='default.jpg')
    password_hash= db.Column(db.String(255), nullable=False)
    rol          = db.Column(db.String(20),  nullable=False, default='user')
    is_active    = db.Column(db.Boolean, nullable=False, default=True)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=True)

    perm_view_dashboard    = db.Column(db.Boolean, nullable=False, default=False)
    perm_view_management   = db.Column(db.Boolean, nullable=False, default=False)
    perm_edit_management   = db.Column(db.Boolean, nullable=False, default=False)
    perm_create_oc_standard= db.Column(db.Boolean, nullable=False, default=False)
    perm_create_oc_proyecto= db.Column(db.Boolean, nullable=False, default=False)
    perm_do_salidas        = db.Column(db.Boolean, nullable=False, default=False)
    perm_view_gastos       = db.Column(db.Boolean, nullable=False, default=False)

    ordenes_creadas    = db.relationship('OrdenCompra', foreign_keys='OrdenCompra.creador_id',
                                         backref='creador', lazy=True)
    ordenes_canceladas = db.relationship('OrdenCompra', foreign_keys='OrdenCompra.cancelado_por_id',
                                         backref='cancelado_por', lazy=True)
    salidas_creadas    = db.relationship('Salida', foreign_keys='Salida.creador_id',
                                         backref='creador', lazy=True)
    salidas_canceladas = db.relationship('Salida', foreign_keys='Salida.cancelado_por_id',
                                         backref='cancelado_por', lazy=True)
    proyectos_oc_creados = db.relationship('ProyectoOC', foreign_keys='ProyectoOC.creador_id',
                                           backref='creador', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


class TokenUsado(db.Model):
    """Blocklist de tokens de reset de contraseña ya utilizados (SHA-256)."""
    __tablename__ = 'token_usado'
    id         = db.Column(db.Integer,    primary_key=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    usado_en   = db.Column(db.DateTime,   nullable=False, default=now_mx)
    expira_en  = db.Column(db.DateTime,   nullable=False)
