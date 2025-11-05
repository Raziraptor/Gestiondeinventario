# ==============================================================================
# 1. IMPORTACIONES
# ==============================================================================

# --- Núcleo de Python ---
import os
import io
import csv
import secrets
from functools import wraps
from datetime import datetime
from collections import defaultdict

# --- Flask y Extensiones ---
from flask import (Flask, render_template, request, redirect, url_for, flash, 
                   send_file, make_response)
from flask.cli import with_appcontext
import click
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user, logout_user, 
                         login_required, current_user)
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from flask_mail import Mail, Message

# --- Formularios (WTForms) ---
from wtforms import StringField, PasswordField, SubmitField, BooleanField # <-- AÑADIDO BooleanField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, Email

# --- Utilidades y Herramientas ---
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import extract
from itsdangerous.url_safe import URLSafeTimedSerializer
from PIL import Image
import qrcode

# --- Reportes (PDF y Excel) ---
import openpyxl
from openpyxl.styles import (Font, PatternFill, Alignment, NamedStyle, Border, 
                             Side)
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table as ExcelTable, TableStyleInfo
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

# ==============================================================================
# 2. CONFIGURACIÓN DE LA APLICACIÓN
# ==============================================================================

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.jinja_env.add_extension('jinja2.ext.do') # Para la lógica de 'set' en bucles

# --- Configuración de Variables de Entorno ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'una-llave-secreta-de-desarrollo-muy-dificil')

db_url = os.environ.get('DATABASE_URL')
if db_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
else:
    print("ADVERTENCIA: No se encontró DATABASE_URL. Usando SQLite local.")
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'inventario.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME'])

db = SQLAlchemy(app)
login_manager = LoginManager(app)
mail = Mail(app)

login_manager.login_view = 'login'
login_manager.login_message = 'Por favor, inicia sesión para acceder a esta página.'
login_manager.login_message_category = 'info'

s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# ==============================================================================
# 3. COMANDOS CLI (Para Despliegue)
# ==============================================================================

@app.cli.command("create-db")
@with_appcontext
def create_db_command():
    """Crea todas las tablas de la base de datos."""
    db.create_all()
    print("¡Base de datos y tablas creadas exitosamente!")

@app.cli.command("make-super-admin")
@with_appcontext
@click.argument("username")
def make_super_admin_command(username):
    """Asigna el rol 'super_admin' a un usuario existente."""
    user = User.query.filter_by(username=username).first()
    if user:
        user.rol = 'super_admin'
        user.organizacion_id = None 
        db.session.commit()
        print(f"¡Éxito! El usuario '{username}' ahora es Super Admin.")
    else:
        print(f"Error: No se encontró al usuario '{username}'.")

# ==============================================================================
# 4. MODELOS DE BASE DE DATOS
# ==============================================================================

# --- Modelos Principales (Padres) ---

class Organizacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), unique=True, nullable=False)
    
    usuarios = db.relationship('User', backref='organizacion', lazy=True)
    productos = db.relationship('Producto', backref='organizacion', lazy=True)
    categorias = db.relationship('Categoria', backref='organizacion', lazy=True)
    proveedores = db.relationship('Proveedor', backref='organizacion', lazy=True)
    ordenes_compra = db.relationship('OrdenCompra', backref='organizacion', lazy=True)
    salidas = db.relationship('Salida', backref='organizacion', lazy=True)
    gastos = db.relationship('Gasto', backref='organizacion', lazy=True)
    movimientos = db.relationship('Movimiento', backref='organizacion', lazy=True)
    
    # --- AÑADIDO: Relación con Proyectos OC ---
    proyectos_oc = db.relationship('ProyectoOC', backref='organizacion', lazy=True)

    def __repr__(self):
        return f'<Organizacion {self.nombre}>'

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    image_file = db.Column(db.String(20), nullable=False, default='default.jpg')
    password_hash = db.Column(db.String(255), nullable=False) 
    
    rol = db.Column(db.String(20), nullable=False, default='user')
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=True)
    
    # --- NUEVAS LÍNEAS (PERMISOS GRANULARES) ---
    # Un 'admin' o 'super_admin' ignora estos permisos (puede hacerlo todo).
    # Un 'user' es controlado por estas banderas.
    
    perm_view_dashboard = db.Column(db.Boolean, nullable=False, default=False)
    perm_view_management = db.Column(db.Boolean, nullable=False, default=False) # Ver Cat/Prov
    perm_edit_management = db.Column(db.Boolean, nullable=False, default=False) # Editar Cat/Prov/Prod
    perm_create_oc_standard = db.Column(db.Boolean, nullable=False, default=False)
    perm_create_oc_proyecto = db.Column(db.Boolean, nullable=False, default=False)
    perm_do_salidas = db.Column(db.Boolean, nullable=False, default=False)
    perm_view_gastos = db.Column(db.Boolean, nullable=False, default=False)
    # --- FIN DE NUEVAS LÍNEAS ---
    
    # Relaciones de Auditoría
    ordenes_creadas = db.relationship('OrdenCompra', foreign_keys='OrdenCompra.creador_id', backref='creador', lazy=True)
    ordenes_canceladas = db.relationship('OrdenCompra', foreign_keys='OrdenCompra.cancelado_por_id', backref='cancelado_por', lazy=True)
    salidas_creadas = db.relationship('Salida', foreign_keys='Salida.creador_id', backref='creador', lazy=True)
    salidas_canceladas = db.relationship('Salida', foreign_keys='Salida.cancelado_por_id', backref='cancelado_por', lazy=True)
    
    # --- AÑADIDO: Relación con Proyectos OC ---
    proyectos_oc_creados = db.relationship('ProyectoOC', foreign_keys='ProyectoOC.creador_id', backref='creador', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

# --- Modelos Secundarios (Hijos) ---

class Proveedor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    contacto_email = db.Column(db.String(100))
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)

class Categoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    descripcion = db.Column(db.String(255), nullable=True)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)

class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    cantidad_stock = db.Column(db.Integer, nullable=False, default=0)
    stock_minimo = db.Column(db.Integer, nullable=False, default=5)
    stock_maximo = db.Column(db.Integer, nullable=False, default=100)
    precio_unitario = db.Column(db.Float, default=0.0)
    imagen_url = db.Column(db.String(255), nullable=True)
    
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=True)
    categoria = db.relationship('Categoria', backref='productos', lazy=True)
    
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'), nullable=True)
    proveedor = db.relationship('Proveedor', backref='productos', lazy=True)
    
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)
    
    @property
    def estado_stock(self):
        if self.cantidad_stock < self.stock_minimo:
            return 'bajo'
        elif self.cantidad_stock > self.stock_maximo:
            return 'exceso'
        return 'ok'

class OrdenCompra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.now)
    fecha_recepcion = db.Column(db.DateTime, nullable=True)
    estado = db.Column(db.String(20), nullable=False, default='borrador')
    
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'), nullable=False)
    
    detalles = db.relationship('OrdenCompraDetalle', backref='orden', lazy=True, cascade="all, delete-orphan")
    
    creador_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cancelado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)
    
    @property
    def costo_total(self):
        return sum(detalle.subtotal for detalle in self.detalles)

class OrdenCompraDetalle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    orden_id = db.Column(db.Integer, db.ForeignKey('orden_compra.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    producto = db.relationship('Producto')
    cantidad_solicitada = db.Column(db.Integer, nullable=False, default=1)
    costo_unitario_estimado = db.Column(db.Float, nullable=True, default=0.0)

    @property
    def subtotal(self):
        return self.cantidad_solicitada * (self.costo_unitario_estimado or 0.0)

class Gasto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descripcion = db.Column(db.String(255), nullable=False)
    monto = db.Column(db.Float, nullable=False, default=0.0)
    categoria = db.Column(db.String(50), nullable=True)
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.now)
    
    orden_compra_id = db.Column(db.Integer, db.ForeignKey('orden_compra.id'), nullable=True)
    orden_compra = db.relationship('OrdenCompra', backref='gastos_asociados', lazy=True)
    
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)

    def __repr__(self):
        return f'<Gasto {self.descripcion} - ${self.monto}>'
    
class Salida(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.now)
    motivo = db.Column(db.String(255), nullable=True)
    estado = db.Column(db.String(20), nullable=False, default='completada')
    
    creador_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cancelado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)    
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)
    
    movimientos = db.relationship('Movimiento', backref='salida', lazy=True, cascade="all, delete-orphan")

class Movimiento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    producto = db.relationship('Producto', backref='movimientos', lazy=True)
    
    cantidad = db.Column(db.Integer, nullable=False) 
    tipo = db.Column(db.String(20), nullable=False) 
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.now)
    motivo = db.Column(db.String(255), nullable=True) 
    
    orden_compra_id = db.Column(db.Integer, db.ForeignKey('orden_compra.id'), nullable=True)
    salida_id = db.Column(db.Integer, db.ForeignKey('salida.id'), nullable=True)
    
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)

    def __repr__(self):
        return f'<Movimiento {self.producto_id} ({self.cantidad})>'
    
class ProyectoOC(db.Model):
    """ El 'header' de una orden de compra para un proyecto específico. """
    id = db.Column(db.Integer, primary_key=True)
    nombre_proyecto = db.Column(db.String(255), nullable=False)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.now)
    estado = db.Column(db.String(20), nullable=False, default='borrador')
    
    creador_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)
    
    detalles = db.relationship('ProyectoOCDetalle', backref='proyecto_oc', lazy=True, cascade="all, delete-orphan")

    @property
    def costo_total(self):
        return sum(detalle.subtotal for detalle in self.detalles)

class ProyectoOCDetalle(db.Model):
    """ Los items de una OC de Proyecto. Pueden ser del inventario o nuevos. """
    id = db.Column(db.Integer, primary_key=True)
    proyecto_oc_id = db.Column(db.Integer, db.ForeignKey('proyecto_oc.id'), nullable=False)
    
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=True)
    producto = db.relationship('Producto')
    
    descripcion_nuevo = db.Column(db.String(255), nullable=True)
    proveedor_sugerido = db.Column(db.String(100), nullable=True)
    
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    costo_unitario = db.Column(db.Float, nullable=False, default=0.0)

    @property
    def subtotal(self):
        return self.cantidad * self.costo_unitario
        
    @property
    def descripcion(self):
        """ Devuelve la descripción del producto, sea nuevo o existente. """
        if self.producto:
            return self.producto.nombre
        else:
            return self.descripcion_nuevo

# ==============================================================================
# 5. CARGADOR DE USUARIO (FLASK-LOGIN)
# ==============================================================================

@login_manager.user_loader
def load_user(user_id):
    """Callback para recargar el objeto User desde el ID de la sesión."""
    return User.query.get(int(user_id))

# ==============================================================================
# 6. FORMULARIOS (FLASK-WTF)
# ==============================================================================

class RegistrationForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired(), Length(min=4, max=80)])
    email = StringField('E-mail', validators=[DataRequired(), Email(message='E-mail no válido.')])
    password = PasswordField('Contraseña', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Contraseña', 
                                     validators=[DataRequired(), EqualTo('password', message='Las contraseñas deben coincidir.')])
    submit = SubmitField('Registrarse')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Ese nombre de usuario ya existe. Por favor, elige otro.')
            
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Ese e-mail ya está registrado. Por favor, usa otro.')

class LoginForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    submit = SubmitField('Iniciar Sesión')

class UpdateAccountForm(FlaskForm):
    """ Formulario para actualizar username, email y foto. """
    username = StringField('Usuario', validators=[DataRequired(), Length(min=4, max=80)])
    email = StringField('E-mail', validators=[DataRequired(), Email(message='E-mail no válido.')])
    picture = FileField('Actualizar Foto de Perfil', validators=[FileAllowed(['jpg', 'png', 'jpeg'])])
    submit_account = SubmitField('Actualizar Datos')

    def validate_username(self, username):
        if username.data != current_user.username:
            user = User.query.filter_by(username=username.data).first()
            if user:
                raise ValidationError('Ese nombre de usuario ya existe. Por favor, elige otro.')
            
    def validate_email(self, email):
        if email.data != current_user.email:
            user = User.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError('Ese e-mail ya está registrado. Por favor, usa otro.')

class ChangePasswordForm(FlaskForm):
    """ Formulario para cambiar la contraseña (estando logueado). """
    old_password = PasswordField('Contraseña Actual', validators=[DataRequired()])
    password = PasswordField('Nueva Contraseña', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Nueva Contraseña', 
                                     validators=[DataRequired(), EqualTo('password', message='Las contraseñas deben coincidir.')])
    submit_password = SubmitField('Cambiar Contraseña')

class RequestResetForm(FlaskForm):
    """ Formulario para pedir un reseteo de contraseña. """
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    submit = SubmitField('Solicitar Reseteo de Contraseña')

class ResetPasswordForm(FlaskForm):
    """ Formulario para ingresar la nueva contraseña. """
    password = PasswordField('Nueva Contraseña', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Nueva Contraseña', 
                                     validators=[DataRequired(), EqualTo('password', message='Las contraseñas deben coincidir.')])
    submit = SubmitField('Restablecer Contraseña')

# ========================
# NUEVO FORMULARIO DE PERMISOS
# (CORREGIDO de db.Column a BooleanField)
# ========================
class AdminPermissionForm(FlaskForm):
    """ Formulario para que un Admin actualice los permisos de un Usuario. """
    perm_view_dashboard = BooleanField('Ver Inventario')
    perm_view_management = BooleanField('Ver Gestión (Cat/Prov)')
    perm_edit_management = BooleanField('Editar Gestión (Cat/Prov/Prod)')
    perm_create_oc_standard = BooleanField('Crear OC Normal')
    perm_create_oc_proyecto = BooleanField('Crear OC Proyecto')
    perm_do_salidas = BooleanField('Registrar Salidas')
    perm_view_gastos = BooleanField('Ver/Crear Gastos')
    submit = SubmitField('Guardar Permisos')

# ==============================================================================
# 7. FUNCIONES AUXILIARES (Decoradores, Subida de Imágenes)
# ==============================================================================

def allowed_file(filename):
    """Verifica si la extensión del archivo es válida."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_picture(form_picture):
    """Guarda y redimensiona la foto de perfil subida."""
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(app.root_path, 'static/uploads/profile_pics', picture_fn)

    output_size = (125, 125)
    i = Image.open(form_picture)
    i.thumbnail(output_size)
    i.save(picture_path)

    return picture_fn

def send_reset_email(user):
    """Función auxiliar para generar y enviar el e-mail."""
    token = s.dumps(user.email, salt='password-reset-salt')
    reset_url = url_for('reset_password', token=token, _external=True)
    msg = Message('[Gestor Inventario] Solicitud de Reseteo de Contraseña',
                  sender=app.config['MAIL_DEFAULT_SENDER'],
                  recipients=[user.email])
    msg.body = f"""Hola {user.username},

Para restablecer tu contraseña, haz clic en el siguiente enlace:
{reset_url}

Si no solicitaste este cambio, por favor ignora este e-mail.
El enlace expirará en 30 minutos.
"""
    try:
        mail.send(msg)
    except Exception as e:
        flash(f'Error al enviar el correo: {e}', 'danger')
        print(f"Error de Mail: {e}")

def super_admin_required(f):
    """
    Decorador personalizado para verificar que el usuario
    sea 'super_admin'.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.rol != 'super_admin':
            flash('No tienes permiso para acceder a esta página.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def check_org_permission(f):
    """
    Decorador para verificar que un usuario (no super_admin)
    pertenece a una organización antes de crear/ver datos.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.rol != 'super_admin' and not current_user.organizacion_id:
            flash('No puedes realizar esta acción. Primero debes ser asignado a una organización por un Super Admin.', 'warning')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def get_item_or_404(model, item_id):
    """
    Función de seguridad que obtiene un item Y verifica
    que pertenece a la organización del usuario.
    """
    if current_user.rol == 'super_admin':
        # El Super Admin puede ver todo
        query = model.query
    else:
        # El usuario normal solo puede ver items de su organización
        query = model.query.filter_by(organizacion_id=current_user.organizacion_id)
    
    item = query.filter_by(id=item_id).first_or_404()
    return item

# ========================
# NUEVOS DECORADORES DE PERMISOS
# ========================
def admin_required(f):
    """
    Decorador personalizado para verificar que el usuario
    sea 'admin' o 'super_admin'.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.rol not in ['super_admin', 'admin']:
            flash('No tienes permiso para acceder a esta página.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def check_permission(permission_name):
    """
    Decorador personalizado que verifica si un usuario tiene un permiso específico.
    Los 'admin' y 'super_admin' siempre tienen permiso.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Si el usuario es un 'admin' o 'super_admin', tiene acceso a todo.
            if current_user.rol in ['super_admin', 'admin']:
                return f(*args, **kwargs)
            
            # Si es un 'user', revisamos su permiso específico.
            if not getattr(current_user, permission_name, False):
                flash('No tienes permiso para acceder a esta función.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ==============================================================================
# 8. RUTAS DE LA APLICACIÓN
# ==============================================================================

# --- Rutas Principales (Dashboard) ---

@app.route('/')
@login_required
def index():
    """ Dashboard Principal (Multiusuario). """
    
    # --- MULTIUSUARIO: Lógica de Filtro Base ---
    if current_user.rol == 'super_admin':
        productos = Producto.query.all()
        categorias = Categoria.query.all()
        proveedores = Proveedor.query.all()
        query_pendientes = db.session.query(
            OrdenCompraDetalle.producto_id, 
            OrdenCompra.id, 
            User.username,
            OrdenCompra.estado
        ).join(
            OrdenCompra, OrdenCompraDetalle.orden_id == OrdenCompra.id
        ).join(
            User, OrdenCompra.creador_id == User.id
        ).filter(
            OrdenCompra.estado.in_(['borrador', 'enviada'])
        )
    else:
        org_id = current_user.organizacion_id
        productos = Producto.query.filter_by(organizacion_id=org_id).all()
        categorias = Categoria.query.filter_by(organizacion_id=org_id).all()
        proveedores = Proveedor.query.filter_by(organizacion_id=org_id).all()
        query_pendientes = db.session.query(
            OrdenCompraDetalle.producto_id, 
            OrdenCompra.id, 
            User.username,
            OrdenCompra.estado
        ).join(
            OrdenCompra, OrdenCompraDetalle.orden_id == OrdenCompra.id
        ).join(
            User, OrdenCompra.creador_id == User.id
        ).filter(
            OrdenCompra.estado.in_(['borrador', 'enviada']),
            OrdenCompra.organizacion_id == org_id
        )
    # --- Fin Lógica de Filtro Base ---

    alertas_crudas = [p for p in productos if p.estado_stock == 'bajo']
    alertas_agrupadas = defaultdict(list)
    proveedor_desconocido = Proveedor(id=0, nombre="Proveedor no asignado")

    for alerta in alertas_crudas:
        if alerta.proveedor:
            alertas_agrupadas[alerta.proveedor.nombre].append(alerta)
        else:
            alertas_agrupadas[proveedor_desconocido.nombre].append(alerta)
            
    ordenes_pendientes = query_pendientes.all()
    pending_map = {} 
    for prod_id, orden_id, username, estado in ordenes_pendientes:
        pending_map[prod_id] = {
            'orden_id': orden_id, 
            'username': username,
            'estado': estado
        }

    return render_template('index.html', 
                           productos=productos, 
                           alertas_agrupadas=alertas_agrupadas,
                           categorias=categorias,
                           proveedores=proveedores,
                           pending_map=pending_map)

@app.route('/dashboard')
@login_required
@check_org_permission
@check_permission('perm_view_dashboard')
def dashboard():
    """ 
    Página del Dashboard de Inventario (Filtros y Tabla).
    Reutiliza la misma lógica que el index.
    """
    
    # --- MULTIUSUARIO: Lógica de Filtro Base ---
    if current_user.rol == 'super_admin':
        productos = Producto.query.all()
        categorias = Categoria.query.all()
        proveedores = Proveedor.query.all()
        query_pendientes = db.session.query(
            OrdenCompraDetalle.producto_id, 
            OrdenCompra.id, 
            User.username,
            OrdenCompra.estado
        ).join(
            OrdenCompra, OrdenCompraDetalle.orden_id == OrdenCompra.id
        ).join(
            User, OrdenCompra.creador_id == User.id
        ).filter(
            OrdenCompra.estado.in_(['borrador', 'enviada'])
        )
    else:
        org_id = current_user.organizacion_id
        productos = Producto.query.filter_by(organizacion_id=org_id).all()
        categorias = Categoria.query.filter_by(organizacion_id=org_id).all()
        proveedores = Proveedor.query.filter_by(organizacion_id=org_id).all()
        query_pendientes = db.session.query(
            OrdenCompraDetalle.producto_id, 
            OrdenCompra.id, 
            User.username,
            OrdenCompra.estado
        ).join(
            OrdenCompra, OrdenCompraDetalle.orden_id == OrdenCompra.id
        ).join(
            User, OrdenCompra.creador_id == User.id
        ).filter(
            OrdenCompra.estado.in_(['borrador', 'enviada']),
            OrdenCompra.organizacion_id == org_id
        )
    # --- Fin Lógica de Filtro Base ---

    alertas_crudas = [p for p in productos if p.estado_stock == 'bajo']
    alertas_agrupadas = defaultdict(list)
    proveedor_desconocido = Proveedor(id=0, nombre="Proveedor no asignado")

    for alerta in alertas_crudas:
        if alerta.proveedor:
            alertas_agrupadas[alerta.proveedor.nombre].append(alerta)
        else:
            alertas_agrupadas[proveedor_desconocido.nombre].append(alerta)
            
    ordenes_pendientes = query_pendientes.all()
    pending_map = {} 
    for prod_id, orden_id, username, estado in ordenes_pendientes:
        pending_map[prod_id] = {
            'orden_id': orden_id, 
            'username': username,
            'estado': estado
        }

    # --- CAMBIO CLAVE: Renderiza el nuevo template 'dashboard.html' ---
    return render_template('dashboard.html', 
                           productos=productos, 
                           alertas_agrupadas=alertas_agrupadas,
                           categorias=categorias,
                           proveedores=proveedores,
                           pending_map=pending_map)

# --- Rutas de Productos ---

@app.route('/producto/nuevo', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_edit_management')
def nuevo_producto():
    """ Formulario para crear un nuevo producto (Multiusuario). """
    org_id = current_user.organizacion_id
    proveedores = Proveedor.query.filter_by(organizacion_id=org_id).all()
    categorias = Categoria.query.filter_by(organizacion_id=org_id).all()
    
    if request.method == 'POST':
        imagen_filename = None
        
        def repoblar_formulario_con_error():
            producto_temporal = Producto(
                nombre=request.form.get('nombre'),
                codigo=request.form.get('codigo'),
                categoria_id=int(request.form.get('categoria_id') or 0) or None,
                cantidad_stock=int(request.form.get('cantidad_stock') or 0),
                stock_minimo=int(request.form.get('stock_minimo') or 5),
                stock_maximo=int(request.form.get('stock_maximo') or 100),
                precio_unitario=float(request.form.get('precio_unitario') or 0.0),
                proveedor_id=int(request.form.get('proveedor_id') or 0) or None
            )
            return render_template('producto_form.html', 
                                   titulo="Nuevo Producto", 
                                   proveedores=proveedores,
                                   categorias=categorias,
                                   producto=producto_temporal)
            
        if 'imagen' in request.files:
            file = request.files['imagen']
            if file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                imagen_filename = filename
            elif file.filename != '' and not allowed_file(file.filename):
                flash('Tipo de archivo de imagen no permitido. Los demás datos se han conservado.', 'danger')
                return repoblar_formulario_con_error()
        
        try:
            nuevo_prod = Producto(
                nombre=request.form['nombre'],
                codigo=request.form['codigo'],
                categoria_id=request.form.get('categoria_id') or None,
                cantidad_stock=int(request.form['cantidad_stock']),
                stock_minimo=int(request.form['stock_minimo']),
                stock_maximo=int(request.form['stock_maximo']),
                precio_unitario=float(request.form['precio_unitario']),
                imagen_url=imagen_filename,
                proveedor_id=request.form.get('proveedor_id') or None,
                organizacion_id=current_user.organizacion_id
            )
            db.session.add(nuevo_prod)
            db.session.commit()
            flash('Producto creado exitosamente', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear producto (quizás el SKU ya existe). Los datos se han conservado.', 'danger')
            return repoblar_formulario_con_error()
            
    return render_template('producto_form.html', 
                           titulo="Nuevo Producto", 
                           proveedores=proveedores,
                           categorias=categorias,
                           producto=None)

@app.route('/producto/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@check_permission('perm_edit_management')
def editar_producto(id):
    """ Edita un producto (Multiusuario). """
    producto = get_item_or_404(Producto, id)
    org_id = producto.organizacion_id
        
    proveedores = Proveedor.query.filter_by(organizacion_id=org_id).all()
    categorias = Categoria.query.filter_by(organizacion_id=org_id).all()

    if request.method == 'POST':
        try:
            if 'imagen' in request.files:
                file = request.files['imagen']
                if file.filename != '' and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    producto.imagen_url = filename 
                elif file.filename != '' and not allowed_file(file.filename):
                    flash('Tipo de archivo de imagen no permitido', 'danger')
                    return render_template('producto_form.html', 
                                           titulo="Editar Producto", 
                                           producto=producto,
                                           proveedores=proveedores,
                                           categorias=categorias)

            producto.nombre = request.form['nombre']
            producto.codigo = request.form['codigo']
            producto.categoria_id = request.form.get('categoria_id') or None
            producto.cantidad_stock = int(request.form['cantidad_stock'])
            producto.stock_minimo = int(request.form['stock_minimo'])
            producto.stock_maximo = int(request.form['stock_maximo'])
            producto.precio_unitario = float(request.form['precio_unitario'])
            producto.proveedor_id = request.form.get('proveedor_id') or None

            db.session.commit()
            flash('Producto actualizado exitosamente', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar producto: {e}', 'danger')

    return render_template('producto_form.html', 
                           titulo="Editar Producto", 
                           producto=producto,
                           proveedores=proveedores,
                           categorias=categorias)

@app.route('/producto/<int:id>/etiqueta')
@login_required
@check_permission('perm_view_dashboard')
def generar_etiqueta(id):
    """ Genera una etiqueta PDF (Multiusuario). """
    producto = get_item_or_404(Producto, id)

    try:
        buffer = io.BytesIO()
        label_width = 4 * inch
        label_height = 2.5 * inch
        c = canvas.Canvas(buffer, pagesize=(label_width, label_height))
        
        qr_img = qrcode.make(producto.codigo)
        qr_img_path = io.BytesIO()
        qr_img.save(qr_img_path, format='PNG')
        qr_img_path.seek(0)
        qr_para_pdf = ImageReader(qr_img_path)
        c.drawImage(qr_para_pdf, label_width - (1.6 * inch), 0.6 * inch,
                    width=(1.4 * inch), height=(1.4 * inch), preserveAspectRatio=True)

        text_x = 0.25 * inch
        text_y = label_height - (0.5 * inch)
        c.setFont('Helvetica-Bold', 12)
        c.drawString(text_x, text_y, producto.nombre[:25])
        c.setFont('Helvetica', 10)
        c.drawString(text_x, text_y - (0.3 * inch), f"SKU: {producto.codigo}")
        c.setFont('Helvetica', 10)
        c.drawString(text_x, text_y - (0.6 * inch), f"Precio: ${producto.precio_unitario:.2f}")

        if producto.imagen_url:
            img_path = os.path.join(app.config['UPLOAD_FOLDER'], producto.imagen_url)
            if os.path.exists(img_path):
                try:
                    prod_img = ImageReader(img_path)
                    c.drawImage(prod_img, 0.1 * inch, 0.2 * inch,
                                width=1.5 * inch, height=1.0 * inch,
                                preserveAspectRatio=True)
                except Exception as img_err:
                    print(f"Error al dibujar imagen en PDF: {img_err}")

        c.showPage()
        c.save()
        buffer.seek(0)
        nombre_base = secure_filename(producto.nombre) 
        fecha_str = datetime.now().strftime("%Y-%m-%d")
        nombre_archivo = f"{nombre_base}_{fecha_str}.pdf"

        return send_file(
            buffer,
            as_attachment=False, 
            download_name=nombre_archivo,
            mimetype='application/pdf'
        )
    except Exception as e:
        flash(f'Error al generar etiqueta: {e}', 'danger')
        return redirect(url_for('index'))

@app.route('/producto/<int:id>/historial')
@login_required
@check_permission('perm_view_dashboard')
def historial_producto(id):
    """ Muestra el Kardex (Multiusuario). """
    producto = get_item_or_404(Producto, id)
    movimientos = sorted(producto.movimientos, key=lambda m: m.fecha, reverse=True)
    
    return render_template('historial_producto.html', 
                           producto=producto, 
                           movimientos=movimientos)

# --- Rutas de Categorías ---

@app.route('/categorias')
@login_required
@check_org_permission
@check_permission('perm_view_management')
def lista_categorias():
    """ Muestra la lista de categorías (Multiusuario). """
    if current_user.rol == 'super_admin':
        categorias = Categoria.query.all()
    else:
        categorias = Categoria.query.filter_by(organizacion_id=current_user.organizacion_id).all()
    return render_template('categorias.html', categorias=categorias)

@app.route('/categoria/nueva', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_edit_management')
def nueva_categoria():
    """ Formulario para crear una nueva categoría (Multiusuario). """
    if request.method == 'POST':
        try:
            nueva_cat = Categoria(
                nombre=request.form['nombre'],
                descripcion=request.form.get('descripcion'),
                organizacion_id=current_user.organizacion_id
            )
            db.session.add(nueva_cat)
            db.session.commit()
            flash('Categoría creada exitosamente', 'success')
            return redirect(url_for('lista_categorias'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear la categoría (quizás el nombre ya existe): {e}', 'danger')
            
    return render_template('categoria_form.html', titulo="Nueva Categoría", categoria=None)

@app.route('/categoria/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@check_permission('perm_edit_management')
def editar_categoria(id):
    """ Edita una categoría (Multiusuario). """
    categoria = get_item_or_404(Categoria, id)
    
    if request.method == 'POST':
        try:
            categoria.nombre = request.form['nombre']
            categoria.descripcion = request.form.get('descripcion')
            db.session.commit()
            flash('Categoría actualizada exitosamente', 'success')
            return redirect(url_for('lista_categorias'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar la categoría: {e}', 'danger')

    return render_template('categoria_form.html', 
                           titulo="Editar Categoría", 
                           categoria=categoria)

@app.route('/categoria/eliminar/<int:id>', methods=['POST'])
@login_required
@check_permission('perm_edit_management')
def eliminar_categoria(id):
    """ Elimina una categoría (Multiusuario). """
    categoria_a_eliminar = get_item_or_404(Categoria, id)
    
    try:
        org_id = categoria_a_eliminar.organizacion_id
        productos_afectados = Producto.query.filter_by(categoria_id=categoria_a_eliminar.id, organizacion_id=org_id).all()
        
        for producto in productos_afectados:
            producto.categoria_id = None
        
        db.session.delete(categoria_a_eliminar)
        db.session.commit()
        
        flash(f'Categoría "{categoria_a_eliminar.nombre}" eliminada. Los productos asociados fueron des-asignados.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar la categoría: {e}', 'danger')

    return redirect(url_for('lista_categorias'))

# --- Rutas de Proveedores ---

@app.route('/proveedores')
@login_required
@check_org_permission
@check_permission('perm_view_management')
def lista_proveedores():
    """ Muestra la lista de proveedores (Multiusuario). """
    if current_user.rol == 'super_admin':
        proveedores = Proveedor.query.all()
    else:
        proveedores = Proveedor.query.filter_by(organizacion_id=current_user.organizacion_id).all()
    return render_template('proveedores.html', proveedores=proveedores)

@app.route('/proveedor/nuevo', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_edit_management')
def nuevo_proveedor():
    """ Crea un nuevo proveedor (Multiusuario). """
    if request.method == 'POST':
        try:
            nuevo_prov = Proveedor(
                nombre=request.form['nombre'],
                contacto_email=request.form['contacto_email'],
                organizacion_id=current_user.organizacion_id
            )
            db.session.add(nuevo_prov)
            db.session.commit()
            flash('Proveedor creado exitosamente', 'success')
            return redirect(url_for('lista_proveedores'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear proveedor: {e}', 'danger')
            
    return render_template('proveedor_form.html', titulo="Nuevo Proveedor")

#<---------SALIDA DE PRODUCTOS----------->

@app.route('/salidas')
@login_required
@check_org_permission
@check_permission('perm_do_salidas')
def historial_salidas():
    """ Muestra el historial de Salidas (Multiusuario). """
    mes = request.args.get('mes', type=int)
    ano = request.args.get('ano', type=int)
    ahora = datetime.now()
    if not mes: mes = ahora.month
    if not ano: ano = ahora.year
    meses_lista = [
        (1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'), (4, 'Abril'), 
        (5, 'Mayo'), (6, 'Junio'), (7, 'Julio'), (8, 'Agosto'), 
        (9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre')
    ]

    if current_user.rol == 'super_admin':
        query = Salida.query
    else:
        query = Salida.query.filter_by(organizacion_id=current_user.organizacion_id)

    query = query.filter(
        extract('month', Salida.fecha) == mes,
        extract('year', Salida.fecha) == ano
    )
    salidas = query.order_by(Salida.fecha.desc()).all()
    
    return render_template('salidas.html', 
                           salidas=salidas,
                           meses_lista=meses_lista,
                           mes_seleccionado=mes,
                           ano_seleccionado=ano)

@app.route('/salida/<int:id>')
@login_required
@check_permission('perm_do_salidas')
def ver_salida(id):
    """ Muestra el detalle de una Salida (Multiusuario). """
    salida = get_item_or_404(Salida, id)
    return render_template('salida_detalle.html', salida=salida)

# --- RUTAS DE ÓRDENES DE COMPRA (OC) ---

@app.route('/ordenes')
@login_required
@check_org_permission
@check_permission('perm_create_oc_standard')
def lista_ordenes():
    """ Muestra la lista de Órdenes de Compra (Multiusuario). """
    mes = request.args.get('mes', type=int)
    ano = request.args.get('ano', type=int)
    prov_id = request.args.get('proveedor_id', type=int)
    
    ahora = datetime.now()
    if not mes: mes = ahora.month
    if not ano: ano = ahora.year

    meses_lista = [
        (1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'), (4, 'Abril'), 
        (5, 'Mayo'), (6, 'Junio'), (7, 'Julio'), (8, 'Agosto'), 
        (9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre')
    ]

    if current_user.rol == 'super_admin':
        proveedores = Proveedor.query.order_by(Proveedor.nombre).all()
        query = OrdenCompra.query
    else:
        org_id = current_user.organizacion_id
        proveedores = Proveedor.query.filter_by(organizacion_id=org_id).order_by(Proveedor.nombre).all()
        query = OrdenCompra.query.filter_by(organizacion_id=org_id)

    query = query.filter(extract('month', OrdenCompra.fecha_creacion) == mes)
    query = query.filter(extract('year', OrdenCompra.fecha_creacion) == ano)

    if prov_id and prov_id != 0:
        query = query.filter_by(proveedor_id=prov_id)

    ordenes = query.order_by(OrdenCompra.fecha_creacion.desc()).all()
    
    return render_template('ordenes.html', 
                           ordenes=ordenes,
                           proveedores=proveedores,
                           meses_lista=meses_lista,
                           mes_seleccionado=mes,
                           ano_seleccionado=ano,
                           prov_seleccionado=prov_id or 0)

@app.route('/orden/nueva', methods=['POST'])
@login_required
@check_org_permission
@check_permission('perm_create_oc_standard')
def nueva_orden():
    """ Crea una OC automática (Multiusuario). """
    try:
        ids_productos_a_ordenar = request.form.getlist('producto_id')
        if not ids_productos_a_ordenar:
            flash('No se seleccionaron productos para la orden.', 'warning')
            return redirect(url_for('index'))

        productos = Producto.query.filter(Producto.id.in_(ids_productos_a_ordenar)).all()
        
        if current_user.rol != 'super_admin':
            for p in productos:
                if p.organizacion_id != current_user.organizacion_id:
                    flash('Error: Intento de ordenar un producto no válido.', 'danger')
                    return redirect(url_for('index'))

        proveedor_id_comun = productos[0].proveedor_id
        if not all(p.proveedor_id == proveedor_id_comun for p in productos):
            flash('Error: Los productos seleccionados deben ser del mismo proveedor.', 'danger')
            return redirect(url_for('index'))

        nueva_oc = OrdenCompra(
            proveedor_id=proveedor_id_comun,
            estado='borrador',
            creador_id=current_user.id,
            organizacion_id=current_user.organizacion_id
        )
        db.session.add(nueva_oc)
        
        for prod in productos:
            cantidad_sugerida = prod.stock_maximo - prod.cantidad_stock
            detalle = OrdenCompraDetalle(
                orden=nueva_oc,
                producto_id=prod.id,
                cantidad_solicitada=max(1, cantidad_sugerida),
                costo_unitario_estimado=prod.precio_unitario
            )
            db.session.add(detalle)
        
        db.session.commit()
        flash('Nueva Orden de Compra generada en "Borrador".', 'success')
        return redirect(url_for('lista_ordenes'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error al generar la orden: {e}', 'danger')
        return redirect(url_for('index'))

@app.route('/orden/<int:id>/recibir', methods=['POST'])
@login_required
@check_permission('perm_create_oc_standard')
def recibir_orden(id):
    """ Marca una orden como 'recibida' (Multiusuario). """
    orden = get_item_or_404(OrdenCompra, id)
    
    if orden.estado == 'recibida':
        flash('Esta orden ya fue recibida anteriormente.', 'warning')
        return redirect(url_for('lista_ordenes'))

    try:
        org_id = orden.organizacion_id
        for detalle in orden.detalles:
            producto = detalle.producto
            producto.cantidad_stock += detalle.cantidad_solicitada
            db.session.add(producto)
            
            movimiento = Movimiento(
                producto_id=producto.id,
                cantidad=detalle.cantidad_solicitada,
                tipo='entrada',
                fecha=datetime.now(),
                motivo=f'Recepción de OC #{orden.id}',
                orden_compra_id=orden.id,
                organizacion_id=org_id
            )
            db.session.add(movimiento)
        
        orden.estado = 'recibida'
        orden.fecha_recepcion = datetime.now()
        db.session.add(orden)
        
        db.session.commit()
        flash('¡Orden recibida! El stock ha sido actualizado.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al recibir la orden: {e}', 'danger')
    
    return redirect(url_for('lista_ordenes'))

@app.route('/orden/<int:id>/enviar', methods=['POST'])
@login_required
@check_permission('perm_create_oc_standard')
def enviar_orden(id):
    """ Cambia el estado de la orden a 'enviada' (Multiusuario). """
    orden = get_item_or_404(OrdenCompra, id)

    if orden.estado == 'borrador':
        try:
            orden.estado = 'enviada'
            db.session.commit()
            flash('Orden marcada como "Enviada".', 'info')
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {e}', 'danger')
    
    return redirect(url_for('lista_ordenes'))

@app.route('/orden/<int:id>/pdf')
@login_required
@check_permission('perm_create_oc_standard')
def generar_oc_pdf(id):
    """ Genera un PDF de OC (Multiusuario). """
    orden = get_item_or_404(OrdenCompra, id)
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                            rightMargin=inch, leftMargin=inch,
                            topMargin=inch, bottomMargin=inch)
    story = []
    styles = getSampleStyleSheet()
    
    style_body = ParagraphStyle(name='Body', parent=styles['BodyText'], fontName='Helvetica', fontSize=10)
    style_right = ParagraphStyle(name='BodyRight', parent=style_body, alignment=TA_RIGHT)
    style_left = ParagraphStyle(name='BodyLeft', parent=style_body, alignment=TA_LEFT)
    style_header = ParagraphStyle(name='Header', parent=style_body, fontName='Helvetica-Bold', alignment=TA_CENTER, textColor=colors.black)
    style_total_label = ParagraphStyle(name='TotalLabel', parent=style_body, fontName='Helvetica-Bold', alignment=TA_RIGHT)
    style_total_value = ParagraphStyle(name='TotalValue', parent=style_body, fontName='Helvetica-Bold', alignment=TA_RIGHT)
    
    story.append(Paragraph(f"ORDEN DE COMPRA #{orden.id}", styles['h1']))
    story.append(Paragraph(f"<b>Estado:</b> {orden.estado.capitalize()}", styles['h3']))
    story.append(Spacer(1, 0.25 * inch))
    info_proveedor = f"""
        <b>Proveedor:</b> {orden.proveedor.nombre}<br/>
        <b>Email Contacto:</b> {orden.proveedor.contacto_email}<br/>
        <b>Fecha Creación:</b> {orden.fecha_creacion.strftime('%Y-%m-%d')}
    """
    story.append(Paragraph(info_proveedor, styles['BodyText']))
    story.append(Spacer(1, 0.5 * inch))

    data = [[
        Paragraph('Producto (SKU)', style_header), 
        Paragraph('Cantidad', style_header), 
        Paragraph('Costo Unit. (Est.)', style_header), 
        Paragraph('Subtotal (Est.)', style_header)
    ]]
    for detalle in orden.detalles:
        producto_sku = Paragraph(f"{detalle.producto.nombre} ({detalle.producto.codigo})", style_left)
        cantidad = Paragraph(str(detalle.cantidad_solicitada), style_right)
        costo_unit = Paragraph(f"${detalle.costo_unitario_estimado:.2f}", style_right)
        subtotal = Paragraph(f"${detalle.subtotal:.2f}", style_right)
        data.append([producto_sku, cantidad, costo_unit, subtotal])
    data.append([
        '', '', 
        Paragraph('TOTAL (Est.):', style_total_label), 
        Paragraph(f"${orden.costo_total:.2f}", style_total_value)
    ])

    style = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E9ECEF")),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 8),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, colors.HexColor("#F8F9FA")]), 
        ('GRID', (0,0), (-1,-2), 1, colors.HexColor("#DEE2E6")),
        ('BOX', (0,0), (-1,-2), 1, colors.HexColor("#DEE2E6")),
        ('BACKGROUND', (0,-1), (3,-1), colors.white),
        ('GRID', (2,-1), (3,-1), 1, colors.HexColor("#DEE2E6")),
        ('SPAN', (0,-1), (1,-1)),
    ])
    
    tabla_oc = Table(data, colWidths=[2.75*inch, 1.0*inch, 1.25*inch, 1.25*inch])
    tabla_oc.setStyle(style)
    story.append(tabla_oc)
    doc.build(story)
    
    fecha_str = orden.fecha_creacion.strftime("%Y-%m-%d")
    filename = f"OC#{orden.id}_{fecha_str}.pdf"

    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=False,
        download_name=filename,
        mimetype='application/pdf'
    )

@app.route('/salida', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_do_salidas')
def registrar_salida():
    """ Registra una Salida (Multiusuario). """
    org_id = current_user.organizacion_id
    productos_query = Producto.query.filter_by(organizacion_id=org_id).all()
    productos_lista = []
    for p in productos_query:
        productos_lista.append({
            'id': p.id,
            'nombre': p.nombre,
            'codigo': p.codigo,
            'stock_actual': p.cantidad_stock 
        })

    if request.method == 'POST':
        try:
            productos_ids = request.form.getlist('producto_id[]')
            cantidades = request.form.getlist('cantidad[]')
            motivo_general = request.form['motivo'] 

            if not productos_ids:
                flash('Debes añadir al menos un producto a la salida.', 'danger')
                return render_template('salida_form.html', 
                                       titulo="Registrar Salida", 
                                       productos=productos_lista)

            productos_para_actualizar = [] 
            for prod_id, cant_str in zip(productos_ids, cantidades):
                if not prod_id or not cant_str: continue
                cantidad_salida = int(cant_str)
                
                producto = Producto.query.filter_by(id=prod_id, organizacion_id=org_id).first()
                if not producto:
                    flash(f'Error: Producto no válido o no pertenece a tu organización.', 'danger')
                    db.session.rollback()
                    return render_template('salida_form.html', titulo="Registrar Salida", productos=productos_lista)

                if cantidad_salida <= 0:
                    flash('Todas las cantidades deben ser positivas.', 'danger')
                    db.session.rollback() 
                    return render_template('salida_form.html', titulo="Registrar Salida", productos=productos_lista)
                
                if producto.cantidad_stock < cantidad_salida:
                    flash(f'Error: Stock insuficiente para "{producto.nombre}". Stock actual: {producto.cantidad_stock}, Solicitado: {cantidad_salida}', 'danger')
                    db.session.rollback()
                    return render_template('salida_form.html', titulo="Registrar Salida", productos=productos_lista)
                
                productos_para_actualizar.append((producto, cantidad_salida))

            nueva_salida = Salida(
                fecha=datetime.now(),
                motivo=motivo_general,
                creador_id=current_user.id,
                organizacion_id=org_id
            )
            db.session.add(nueva_salida)

            for producto, cantidad_salida in productos_para_actualizar:
                producto.cantidad_stock -= cantidad_salida
                db.session.add(producto)
                
                movimiento = Movimiento(
                    producto_id=producto.id,
                    cantidad= -cantidad_salida,
                    tipo='salida',
                    fecha=datetime.now(),
                    motivo=motivo_general,
                    salida=nueva_salida,
                    organizacion_id=org_id
                )
                db.session.add(movimiento)
            
            db.session.commit()
            flash(f'Salida #{nueva_salida.id} registrada con {len(productos_para_actualizar)} productos.', 'success')
            return redirect(url_for('historial_salidas'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar la salida: {e}', 'danger')
    
    return render_template('salida_form.html', 
                           titulo="Registrar Salida", 
                           productos=productos_lista)

@app.route('/salida/<int:id>/cancelar', methods=['POST'])
@login_required
@check_permission('perm_do_salidas')
def cancelar_salida(id):
    """ Cancela una Salida (Multiusuario). """
    salida = get_item_or_404(Salida, id)
    
    if salida.estado == 'cancelada':
        flash('Esta salida ya ha sido cancelada.', 'warning')
        return redirect(url_for('historial_salidas'))

    try:
        org_id = salida.organizacion_id
        
        salida.estado = 'cancelada'
        salida.cancelado_por_id = current_user.id
        db.session.add(salida)
        
        for mov in salida.movimientos:
            producto = mov.producto
            cantidad_a_devolver = abs(mov.cantidad)
            
            producto.cantidad_stock += cantidad_a_devolver
            db.session.add(producto)
            
            mov_ajuste = Movimiento(
                producto_id=producto.id,
                cantidad=cantidad_a_devolver,
                tipo='ajuste-entrada',
                fecha=datetime.now(),
                motivo=f'Cancelación de Salida #{salida.id}',
                organizacion_id=org_id
            )
            db.session.add(mov_ajuste)

        db.session.commit()
        flash(f'Salida #{salida.id} cancelada. El stock ha sido reingresado.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al cancelar la salida: {e}', 'danger')

    return redirect(url_for('historial_salidas'))


@app.route('/salida/<int:id>/pdf')
@login_required
@check_permission('perm_do_salidas')
def generar_salida_pdf(id):
    """ Genera un PDF de Salida (Multiusuario). """
    salida = get_item_or_404(Salida, id)
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                            rightMargin=inch, leftMargin=inch,
                            topMargin=inch, bottomMargin=inch)
    story = []
    styles = getSampleStyleSheet()

    style_body = ParagraphStyle(name='Body', parent=styles['BodyText'], fontName='Helvetica', fontSize=10)
    style_right = ParagraphStyle(name='BodyRight', parent=style_body, alignment=TA_RIGHT)
    style_left = ParagraphStyle(name='BodyLeft', parent=style_body, alignment=TA_LEFT)
    style_header = ParagraphStyle(name='Header', parent=style_body, fontName='Helvetica-Bold', alignment=TA_CENTER, textColor=colors.black)

    story.append(Paragraph(f"COMPROBANTE DE SALIDA #{salida.id}", styles['h1']))
    story.append(Spacer(1, 0.25 * inch))
    info_salida = f"""
        <b>Motivo:</b> {salida.motivo}<br/>
        <b>Fecha:</b> {salida.fecha.strftime('%Y-%m-%d %H:%M')}<br/>
        <b>Estado:</b> <font color="{'red' if salida.estado == 'cancelada' else 'green'}">
            {salida.estado.capitalize()}
        </font>
    """
    story.append(Paragraph(info_salida, styles['BodyText']))
    story.append(Spacer(1, 0.5 * inch))

    data = [[
        Paragraph('Producto', style_header), 
        Paragraph('SKU', style_header), 
        Paragraph('Cantidad Retirada', style_header)
    ]]
    for mov in salida.movimientos:
        producto = Paragraph(mov.producto.nombre, style_left)
        sku = Paragraph(mov.producto.codigo, style_left)
        cantidad = Paragraph(str(abs(mov.cantidad)), style_right)
        data.append([producto, sku, cantidad])

    style = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E9ECEF")),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 8),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8F9FA")]), 
        ('GRID', (0,0), (-1,-1), 1, colors.HexColor("#DEE2E6")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#DEE2E6")),
    ])

    tabla_salida = Table(data, colWidths=[3*inch, 2*inch, 1.25*inch])
    tabla_salida.setStyle(style)
    story.append(tabla_salida)
    doc.build(story)
    
    fecha_str = salida.fecha.strftime("%Y-%m-%d")
    filename = f"Salida_#{salida.id}_{fecha_str}.pdf"

    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=False,
        download_name=filename,
        mimetype='application/pdf'
    )

@app.route('/orden/<int:id>')
@login_required
@check_permission('perm_create_oc_standard')
def ver_orden(id):
    """ Muestra el detalle de una OC (Multiusuario). """
    orden = get_item_or_404(OrdenCompra, id)
    return render_template('orden_detalle.html', orden=orden, titulo=f"Detalle OC #{orden.id}")

@app.route('/orden/nueva_manual', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_create_oc_standard')
def nueva_orden_manual():
    """ Crea una OC manual (Multiusuario). """
    org_id = current_user.organizacion_id
    proveedores = Proveedor.query.filter_by(organizacion_id=org_id).all()
    productos_query = Producto.query.filter_by(organizacion_id=org_id).all()
    productos_lista = []
    for p in productos_query:
        productos_lista.append({
            'id': p.id,
            'nombre': p.nombre,
            'codigo': p.codigo,
            'precio_unitario': p.precio_unitario,
            'proveedor_id': p.proveedor_id
        })

    if request.method == 'POST':
        try:
            proveedor_id = request.form.get('proveedor_id')
            if not proveedor_id:
                flash('Debes seleccionar un proveedor.', 'danger')
                return render_template('orden_form.html',
                                       titulo="Crear Orden de Compra Manual",
                                       proveedores=proveedores,
                                       productos=productos_lista,
                                       orden=None) 

            nueva_oc = OrdenCompra(
                proveedor_id=proveedor_id,
                estado='borrador',
                creador_id=current_user.id,
                organizacion_id=current_user.organizacion_id
            )
            db.session.add(nueva_oc)
            
            productos_ids = request.form.getlist('producto_id[]')
            cantidades = request.form.getlist('cantidad[]')
            costos = request.form.getlist('costo[]')

            if not productos_ids:
                 flash('Debes añadir al menos un producto a la orden.', 'danger')
                 return render_template('orden_form.html',
                                       titulo="Crear Orden de Compra Manual",
                                       proveedores=proveedores,
                                       productos=productos_lista,
                                       orden=None)

            for prod_id, cant, cost in zip(productos_ids, cantidades, costos):
                if not prod_id or not cant or not cost:
                    continue 
                
                detalle = OrdenCompraDetalle(
                    orden=nueva_oc,
                    producto_id=int(prod_id),
                    cantidad_solicitada=int(cant),
                    costo_unitario_estimado=float(cost)
                )
                db.session.add(detalle)
            
            db.session.commit()
            flash('Orden de Compra manual creada en "Borrador".', 'success')
            return redirect(url_for('lista_ordenes')) 

        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear la orden: {e}', 'danger')
            return render_template('orden_form.html',
                                   titulo="Crear Orden de Compra Manual",
                                   proveedores=proveedores,
                                   productos=productos_lista,
                                   orden=None)
    
    return render_template('orden_form.html', 
                           titulo="Crear Orden de Compra Manual",
                           proveedores=proveedores,
                           productos=productos_lista,
                           orden=None)

@app.route('/orden/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@check_permission('perm_create_oc_standard')
def editar_orden(id):
    """ Edita una OC (Multiusuario). """
    orden = get_item_or_404(OrdenCompra, id)

    if orden.estado != 'borrador':
        flash('Solo se pueden editar órdenes en estado "Borrador".', 'warning')
        return redirect(url_for('ver_orden', id=id))

    org_id = orden.organizacion_id
    proveedores = Proveedor.query.filter_by(organizacion_id=org_id).all()
    productos_query = Producto.query.filter_by(organizacion_id=org_id).all()
    productos_lista = []
    for p in productos_query:
        productos_lista.append({
            'id': p.id,
            'nombre': p.nombre,
            'codigo': p.codigo,
            'precio_unitario': p.precio_unitario,
            'proveedor_id': p.proveedor_id
        })
    
    if request.method == 'POST':
        try:
            OrdenCompraDetalle.query.filter_by(orden_id=orden.id).delete()
            
            productos_ids = request.form.getlist('producto_id[]')
            cantidades = request.form.getlist('cantidad[]')
            costos = request.form.getlist('costo[]')

            if not productos_ids:
                 flash('La orden debe tener al menos un producto.', 'danger')
                 db.session.rollback()
                 return render_template('orden_form.html',
                                       titulo=f"Editar Orden de Compra #{orden.id}",
                                       proveedores=proveedores,
                                       productos=productos_lista,
                                       orden=orden)
            
            for prod_id, cant, cost in zip(productos_ids, cantidades, costos):
                if not prod_id or not cant or not cost:
                    continue 
                
                detalle = OrdenCompraDetalle(
                    orden_id=orden.id,
                    producto_id=int(prod_id),
                    cantidad_solicitada=int(cant),
                    costo_unitario_estimado=float(cost)
                )
                db.session.add(detalle)
            
            db.session.commit()
            flash('Orden de Compra actualizada exitosamente.', 'success')
            return redirect(url_for('ver_orden', id=id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar la orden: {e}', 'danger')
            return render_template('orden_form.html',
                                   titulo=f"Editar Orden de Compra #{orden.id}",
                                   proveedores=proveedores,
                                   productos=productos_lista,
                                   orden=orden)

    return render_template('orden_form.html', 
                           titulo=f"Editar Orden de Compra #{orden.id}",
                           proveedores=proveedores,
                           productos=productos_lista,
                           orden=orden)

@app.route('/orden/<int:id>/cancelar', methods=['POST'])
@login_required
@check_permission('perm_create_oc_standard')
def cancelar_orden(id):
    """ Cancela una OC (Multiusuario). """
    orden = get_item_or_404(OrdenCompra, id)
    
    if orden.estado != 'borrador':
        flash('Error: Solo se pueden cancelar órdenes en estado "Borrador".', 'danger')
        return redirect(url_for('lista_ordenes'))

    try:
        orden.estado = 'cancelada'
        orden.cancelado_por_id = current_user.id
        db.session.commit()
        flash('Orden de Compra cancelada exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al cancelar la orden: {e}', 'danger')
    
    return redirect(url_for('lista_ordenes'))

# =============================================
# NUEVAS RUTAS PARA OC DE PROYECTO
# =============================================

@app.route('/proyectos-oc')
@login_required
@check_org_permission
@check_permission('perm_create_oc_proyecto')
def lista_proyectos_oc():
    """ Muestra la lista de Órdenes de Compra de Proyectos. """
    if current_user.rol == 'super_admin':
        query = ProyectoOC.query
    else:
        query = ProyectoOC.query.filter_by(organizacion_id=current_user.organizacion_id)
        
    proyectos_oc = query.order_by(ProyectoOC.fecha_creacion.desc()).all()
    
    return render_template('proyecto_oc_lista.html', 
                           proyectos_oc=proyectos_oc,
                           titulo="OC de Proyectos")

@app.route('/proyecto-oc/<int:id>')
@login_required
@check_permission('perm_create_oc_proyecto')
def ver_proyecto_oc(id):
    """ Muestra el detalle de una OC de Proyecto. """
    proyecto_oc = get_item_or_404(ProyectoOC, id)
    return render_template('proyecto_oc_detalle.html', 
                           proyecto_oc=proyecto_oc, 
                           titulo=f"Detalle OC Proyecto #{proyecto_oc.id}")

@app.route('/proyecto-oc/nueva', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_create_oc_proyecto')
def nuevo_proyecto_oc():
    """ Formulario para crear una nueva OC de Proyecto. """
    
    org_id = current_user.organizacion_id
    
    productos_query = Producto.query.filter_by(organizacion_id=org_id).all()
    productos_lista = []
    for p in productos_query:
        productos_lista.append({
            'id': p.id,
            'nombre': p.nombre,
            'codigo': p.codigo,
            'precio_unitario': p.precio_unitario,
        })
        
    proveedores = Proveedor.query.filter_by(organizacion_id=org_id).order_by(Proveedor.nombre).all()

    if request.method == 'POST':
        try:
            nombre_proyecto = request.form.get('nombre_proyecto')
            if not nombre_proyecto:
                flash('El nombre del proyecto es obligatorio.', 'danger')
                raise Exception("Nombre de proyecto vacío")

            nueva_proyecto_oc = ProyectoOC(
                nombre_proyecto=nombre_proyecto,
                creador_id=current_user.id,
                organizacion_id=org_id
            )
            db.session.add(nueva_proyecto_oc)

            tipos = request.form.getlist('tipo_item[]')
            productos_existentes = request.form.getlist('producto_id_existente[]')
            productos_nuevos = request.form.getlist('producto_nuevo_descripcion[]')
            cantidades = request.form.getlist('cantidad[]')
            costos = request.form.getlist('costo[]')
            proveedores_sugeridos = request.form.getlist('proveedor_sugerido[]')

            for i in range(len(tipos)):
                if not cantidades[i] or not costos[i]:
                    continue 

                detalle = ProyectoOCDetalle(
                    proyecto_oc=nueva_proyecto_oc,
                    cantidad=int(cantidades[i]),
                    costo_unitario=float(costos[i]),
                    proveedor_sugerido=proveedores_sugeridos[i]
                )
                
                if tipos[i] == 'existente':
                    detalle.producto_id = int(productos_existentes[i])
                else: 
                    detalle.descripcion_nuevo = productos_nuevos[i]
                
                db.session.add(detalle)

            db.session.commit()
            flash(f'OC de Proyecto #{nueva_proyecto_oc.id} creada en "Borrador".', 'success')
            return redirect(url_for('lista_proyectos_oc'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear la OC de Proyecto: {e}', 'danger')
    
    return render_template('proyecto_oc_form.html', 
                           titulo="Crear OC de Proyecto",
                           productos=productos_lista,
                           proveedores=proveedores)

# --- RUTAS DE CONTROL DE GASTOS ---
@app.route('/gastos')
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def lista_gastos():
    """ Muestra la lista de Gastos (Multiusuario). """
    mes = request.args.get('mes', type=int)
    ano = request.args.get('ano', type=int)
    ahora = datetime.now()
    if not mes: mes = ahora.month
    if not ano: ano = ahora.year
    meses_lista = [
        (1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'), (4, 'Abril'), 
        (5, 'Mayo'), (6, 'Junio'), (7, 'Julio'), (8, 'Agosto'), 
        (9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre')
    ]
    
    if current_user.rol == 'super_admin':
        query_gastos = Gasto.query
    else:
        query_gastos = Gasto.query.filter_by(organizacion_id=current_user.organizacion_id)

    query_gastos = query_gastos.filter(
        extract('month', Gasto.fecha) == mes,
        extract('year', Gasto.fecha) == ano
    ).order_by(Gasto.fecha.desc())
    
    gastos = query_gastos.all()
    total_gastos = sum(g.monto for g in gastos)
    
    return render_template('gastos.html', 
                           gastos=gastos, 
                           total_gastos=total_gastos,
                           mes_seleccionado=mes,
                           ano_seleccionado=ano,
                           meses_lista=meses_lista)

@app.route('/gasto/nuevo', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def nuevo_gasto():
    """ Crea un nuevo gasto (Multiusuario). """
    org_id = current_user.organizacion_id
    ordenes = OrdenCompra.query.filter_by(organizacion_id=org_id).order_by(OrdenCompra.fecha_creacion.desc()).all()

    if request.method == 'POST':
        try:
            fecha_gasto = datetime.strptime(request.form['fecha'], '%Y-%m-%d')
            oc_id = request.form.get('orden_compra_id')
            if oc_id == "": oc_id = None

            nuevo_gasto = Gasto(
                descripcion=request.form['descripcion'],
                monto=float(request.form['monto']),
                categoria=request.form['categoria'],
                fecha=fecha_gasto,
                orden_compra_id=oc_id,
                organizacion_id=current_user.organizacion_id
            )
            db.session.add(nuevo_gasto)
            db.session.commit()
            flash('Gasto registrado exitosamente', 'success')
            return redirect(url_for('lista_gastos'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar el gasto: {e}', 'danger')

    return render_template('gasto_form.html', 
                           titulo="Registrar Nuevo Gasto", 
                           ordenes=ordenes,
                           now=datetime.now())

@app.route('/gastos/exportar_excel')
@login_required
@check_permission('perm_view_gastos')
def exportar_gastos_excel():
    """ Exporta Gastos a Excel (Multiusuario). """
    mes = request.args.get('mes', type=int)
    ano = request.args.get('ano', type=int)
    ahora = datetime.now()
    if not mes: mes = ahora.month
    if not ano: ano = ahora.year
    
    if current_user.rol == 'super_admin':
        query_gastos = Gasto.query
    else:
        query_gastos = Gasto.query.filter_by(organizacion_id=current_user.organizacion_id)

    gastos = query_gastos.filter(
        extract('month', Gasto.fecha) == mes,
        extract('year', Gasto.fecha) == ano
    ).order_by(Gasto.fecha.asc()).all()

    fuente_arial_12 = Font(name='Arial', size=12)
    fuente_arial_12_bold = Font(name='Arial', size=12, bold=True, color='FFFFFF') 
    header_fill = PatternFill(start_color='0000FF', end_color='0000FF', fill_type='solid') 
    header_align = Alignment(horizontal='center', vertical='center')
    currency_style = NamedStyle(name='currency_arial', 
                                number_format='$#,##0.00', 
                                font=fuente_arial_12)
    thin_border_side = Side(border_style="thin", color="000000")
    thin_border = Border(left=thin_border_side, 
                         right=thin_border_side, 
                         top=thin_border_side, 
                         bottom=thin_border_side)
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"{datetime(ano, mes, 1).strftime('%B').capitalize()} {ano}"
    
    if currency_style.name not in wb.named_styles:
        wb.add_named_style(currency_style)

    headers = ['ID Gasto', 'Fecha', 'Descripcion', 'Categoria', 'Monto', 'ID Orden Compra Asociada']
    ws.append(headers)
    
    for cell in ws[1]:
        cell.font = fuente_arial_12_bold 
        cell.fill = header_fill
        cell.alignment = header_align

    total_gastos = 0
    for gasto in gastos:
        fecha_excel = gasto.fecha.date()
        ws.append([
            gasto.id, fecha_excel, gasto.descripcion, 
            gasto.categoria, gasto.monto, 
            gasto.orden_compra_id if gasto.orden_compra_id else 'N/A'
        ])
        
        fila_actual = ws.max_row
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=fila_actual, column=col_idx)
            cell.font = fuente_arial_12
            
        monto_cell = ws.cell(row=fila_actual, column=5)
        monto_cell.style = currency_style.name
        total_gastos += gasto.monto

    rango_tabla = f"A1:F{ws.max_row}"
    tabla_excel = ExcelTable(displayName="GastosMes", ref=rango_tabla)
    estilo_tabla = TableStyleInfo(name="TableStyleMedium9", 
                                showFirstColumn=False, showLastColumn=False, 
                                showRowStripes=True, showColumnStripes=False)
    tabla_excel.tableStyleInfo = estilo_tabla
    ws.add_table(tabla_excel)

    fila_total = ws.max_row + 2 
    total_label_cell = ws.cell(row=fila_total, column=4)
    total_label_cell.value = "Gran Total"
    total_label_cell.font = fuente_arial_12_bold 
    total_label_cell.fill = header_fill 
    total_label_cell.alignment = Alignment(horizontal='right')
    total_label_cell.border = thin_border

    total_value_cell = ws.cell(row=fila_total, column=5)
    total_value_cell.value = total_gastos
    total_value_cell.style = currency_style.name
    total_value_cell.font = fuente_arial_12
    total_value_cell.border = thin_border

    for col_idx, col in enumerate(ws.columns, 1):
        column_letter = get_column_letter(col_idx)
        max_length = 0
        for cell in col:
            try: 
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = (max_length + 5) 
        ws.column_dimensions[column_letter].width = adjusted_width

    nombre_mes = datetime(ano, mes, 1).strftime('%B').capitalize()
    filename = f"Acuse_Gastos_{nombre_mes}_{ano}.xlsx"
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    response = make_response(buffer.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return response

# --- RUTAS DE AUTENTICACIÓN ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    """ Página de Registro de nuevos usuarios. """
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            new_user = User(
                username=form.username.data,
                email=form.email.data
                # La 'organizacion_id' y 'rol' se asignarán
                # por el Super Admin (Fase 3)
            )
            new_user.set_password(form.password.data)
            
            db.session.add(new_user)
            db.session.commit()
            
            flash(f'¡Cuenta creada para {form.username.data}! Ahora puedes iniciar sesión.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear la cuenta: {e}', 'danger')

    return render_template('register.html', titulo="Registro", form=form)

@app.route('/account/delete_picture', methods=['POST'])
@login_required
def delete_picture():
    """ Elimina la foto de perfil del usuario y la revierte a 'default.jpg'. """
    if current_user.image_file != 'default.jpg':
        try:
            picture_path = os.path.join(app.root_path, 'static/uploads/profile_pics', current_user.image_file)
            if os.path.exists(picture_path):
                os.remove(picture_path)
            current_user.image_file = 'default.jpg'
            db.session.commit()
            flash('Tu foto de perfil ha sido eliminada.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al eliminar la foto: {e}', 'danger')
    
    return redirect(url_for('account'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """ Página de Inicio de Sesión. """
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        
        if user and user.check_password(form.password.data):
            login_user(user)
            next_page = request.args.get('next') 
            flash('Inicio de sesión exitoso.', 'success')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Inicio de sesión fallido. Verifica tu usuario y contraseña.', 'danger')
            
    return render_template('login.html', titulo="Inicio de Sesión", form=form)

@app.route('/logout')
@login_required
def logout():
    """ Cierra la sesión del usuario. """
    logout_user()
    flash('Has cerrado la sesión.', 'info')
    return redirect(url_for('login'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """ Página para solicitar el reseteo de contraseña. """
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_reset_email(user)
        # Usamos la lógica segura (sin validación en el formulario)
        flash('Si existe una cuenta con ese e-mail, recibirás un correo con las instrucciones.', 'info')
        return redirect(url_for('login'))
        
    return render_template('forgot_password.html', titulo="Recuperar Contraseña", form=form)

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """ Página para ingresar la nueva contraseña (accedida desde el e-mail). """
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    try:
        email = s.loads(token, salt='password-reset-salt', max_age=1800)
    except:
        flash('El enlace de reseteo no es válido o ha expirado.', 'danger')
        return redirect(url_for('forgot_password'))
        
    user = User.query.filter_by(email=email).first()
    if user is None:
        flash('Usuario no encontrado.', 'danger')
        return redirect(url_for('login'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        try:
            user.set_password(form.password.data)
            db.session.commit()
            flash('¡Tu contraseña ha sido actualizada! Ya puedes iniciar sesión.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar la contraseña: {e}', 'danger')

    return render_template('reset_password.html', titulo="Restablecer Contraseña", form=form, token=token)

@app.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    """ Página de configuración de la cuenta del usuario. """
    form_account = UpdateAccountForm()
    form_password = ChangePasswordForm()

    if form_account.submit_account.data and form_account.validate_on_submit():
        try:
            if form_account.picture.data:
                if current_user.image_file != 'default.jpg':
                    old_pic_path = os.path.join(app.root_path, 'static/uploads/profile_pics', current_user.image_file)
                    if os.path.exists(old_pic_path):
                        os.remove(old_pic_path)
                picture_file = save_picture(form_account.picture.data)
                current_user.image_file = picture_file
            
            current_user.username = form_account.username.data
            current_user.email = form_account.email.data
            db.session.commit()
            flash('¡Tu cuenta ha sido actualizada!', 'success')
            return redirect(url_for('account'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar la cuenta: {e}', 'danger')

    if form_password.submit_password.data and form_password.validate_on_submit():
        try:
            if current_user.check_password(form_password.old_password.data):
                current_user.set_password(form_password.password.data)
                db.session.commit()
                flash('¡Tu contraseña ha sido cambiada!', 'success')
                return redirect(url_for('account'))
            else:
                flash('La contraseña actual es incorrecta.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al cambiar la contraseña: {e}', 'danger')

    if request.method == 'GET':
        form_account.username.data = current_user.username
        form_account.email.data = current_user.email
    
    image_url = url_for('static', filename='uploads/profile_pics/' + current_user.image_file)
    
    return render_template('account.html', 
                           titulo="Configuración de Cuenta",
                           image_url=image_url,
                           form_account=form_account,
                           form_password=form_password)

# --- RUTAS DEL SUPER ADMIN ---

def super_admin_required(f):
    """
    Decorador personalizado para verificar que el usuario
    sea 'super_admin'.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.rol != 'super_admin':
            flash('No tienes permiso para acceder a esta página.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/superadmin', methods=['GET'])
@login_required
@super_admin_required
def super_admin():
    """ 
    Panel principal del Super Admin para gestionar
    Organizaciones y Usuarios.
    """
    organizaciones = Organizacion.query.order_by(Organizacion.nombre).all()
    usuarios = User.query.order_by(User.username).all()
    
    return render_template('super_admin.html', 
                           titulo="Super Admin Panel",
                           organizaciones=organizaciones,
                           usuarios=usuarios)

@app.route('/superadmin/organizacion/nueva', methods=['POST'])
@login_required
@super_admin_required
def nueva_organizacion():
    """ Crea una nueva organización. """
    nombre = request.form.get('nombre')
    if not nombre:
        flash('El nombre de la organización no puede estar vacío.', 'danger')
        return redirect(url_for('super_admin'))
        
    existente = Organizacion.query.filter_by(nombre=nombre).first()
    if existente:
        flash(f'La organización "{nombre}" ya existe.', 'warning')
        return redirect(url_for('super_admin'))
        
    try:
        nueva_org = Organizacion(nombre=nombre)
        db.session.add(nueva_org)
        db.session.commit()
        flash(f'Organización "{nombre}" creada exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al crear la organización: {e}', 'danger')
        
    return redirect(url_for('super_admin'))

@app.route('/superadmin/usuario/asignar/<int:user_id>', methods=['POST'])
@login_required
@super_admin_required
def asignar_usuario(user_id):
    """ Asigna un rol y una organización a un usuario. """
    user = User.query.get_or_404(user_id)
    nuevo_rol = request.form.get('rol')
    nueva_org_id = request.form.get('organizacion_id')

    if not nuevo_rol:
        flash('Error: No se seleccionó un rol.', 'danger')
        return redirect(url_for('super_admin'))

    try:
        user.rol = nuevo_rol
        
        if nueva_org_id == '0':
            user.organizacion_id = None
        else:
            user.organizacion_id = int(nueva_org_id)
        
        if user.rol == 'super_admin':
            user.organizacion_id = None
            
        db.session.commit()
        flash(f'Usuario "{user.username}" actualizado.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar el usuario: {e}', 'danger')

    return redirect(url_for('super_admin'))
    
# ========================
# NUEVAS RUTAS DEL ADMIN
# ========================

@app.route('/admin_panel')
@login_required
@admin_required # Solo 'admin' o 'super_admin'
@check_org_permission # Debe pertenecer a una org (esto excluye al super_admin sin org)
def admin_panel():
    """ Panel para que un Admin gestione los usuarios de SU organización. """
    
    # Obtenemos solo los usuarios de la organización del admin actual
    usuarios = User.query.filter_by(
        organizacion_id=current_user.organizacion_id
    ).order_by(User.username).all()
    
    # Creamos un dict de formularios, uno para cada usuario
    forms = {}
    for user in usuarios:
        form = AdminPermissionForm()
        # Rellenamos el formulario con los permisos actuales del usuario
        form.perm_view_dashboard.data = user.perm_view_dashboard
        form.perm_view_management.data = user.perm_view_management
        form.perm_edit_management.data = user.perm_edit_management
        form.perm_create_oc_standard.data = user.perm_create_oc_standard
        form.perm_create_oc_proyecto.data = user.perm_create_oc_proyecto
        form.perm_do_salidas.data = user.perm_do_salidas
        form.perm_view_gastos.data = user.perm_view_gastos
        forms[user.id] = form
        
    return render_template('admin_panel.html', 
                           titulo="Panel de Administrador",
                           usuarios=usuarios,
                           forms=forms)

@app.route('/admin_panel/update/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def update_user_permissions(user_id):
    """ Actualiza los permisos de un usuario específico. """
    
    user_to_update = User.query.get_or_404(user_id)
    
    # --- CHEQUEO DE SEGURIDAD ---
    # Un admin solo puede editar usuarios de SU PROPIA organización
    if current_user.rol == 'admin' and user_to_update.organizacion_id != current_user.organizacion_id:
        flash('No tienes permiso para editar a este usuario.', 'danger')
        return redirect(url_for('admin_panel'))
        
    # No puedes editar tus propios permisos (solo el Super Admin puede)
    if user_to_update.id == current_user.id and current_user.rol != 'super_admin':
        flash('No puedes editar tus propios permisos. Pide a otro admin o al Super Admin que lo haga.', 'warning')
        return redirect(url_for('admin_panel'))
    # --- FIN CHEQUEO ---

    form = AdminPermissionForm()
    
    if form.validate_on_submit():
        try:
            # Actualizamos al usuario con los datos (checkboxes) del formulario
            user_to_update.perm_view_dashboard = form.perm_view_dashboard.data
            user_to_update.perm_view_management = form.perm_view_management.data
            user_to_update.perm_edit_management = form.perm_edit_management.data
            user_to_update.perm_create_oc_standard = form.perm_create_oc_standard.data
            user_to_update.perm_create_oc_proyecto = form.perm_create_oc_proyecto.data
            user_to_update.perm_do_salidas = form.perm_do_salidas.data
            user_to_update.perm_view_gastos = form.perm_view_gastos.data
            
            db.session.commit()
            flash(f'Permisos para {user_to_update.username} actualizados.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar permisos: {e}', 'danger')
    else:
        # Si la validación (CSRF) falla
        flash('Error de validación del formulario. Inténtalo de nuevo.', 'danger')
            
    return redirect(url_for('admin_panel'))


# --- Inicialización ---
if __name__ == '__main__':
    # Crea la base de datos y las tablas si no existen
    with app.app_context():
        db.create_all()

    app.run(debug=True, port=5000)
