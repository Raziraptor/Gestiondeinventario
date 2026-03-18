# ==============================================================================
# 1. IMPORTACIONES
# ==============================================================================

# --- Núcleo de Python ---
import os
import io
import csv
import secrets
from dotenv import load_dotenv
load_dotenv()
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
from flask_wtf.csrf import CSRFProtect
from threading import Thread
from flask import current_app
from itsdangerous.url_safe import URLSafeTimedSerializer
from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user
from flask_mail import Message

# --- Formularios (WTForms) ---
from wtforms import StringField, PasswordField, SubmitField, BooleanField # <-- AÑADIDO BooleanField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, Email

# --- Utilidades y Herramientas ---
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import extract, Date # <-- AÑADIDO Date
from sqlalchemy.exc import IntegrityError
from itsdangerous.url_safe import URLSafeTimedSerializer
from PIL import Image, ImageDraw, ImageFont
from PIL import Image
import qrcode
import secrets
from functools import wraps
from reportlab.lib.units import inch, mm
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing

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
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as ReportLabImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as ReportLabImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
from werkzeug.security import generate_password_hash
from sqlalchemy import text

# ==============================================================================
# 2. CONFIGURACIÓN DE LA APLICACIÓN
# ==============================================================================

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
csrf = CSRFProtect(app)
app.jinja_env.add_extension('jinja2.ext.do') # Para la lógica de 'set' en bucles

# --- Configuración de Variables de Entorno ---
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

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

# --- Configuración de Flask-Mail ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'dinventarioc@gmail.com'
app.config['MAIL_DEFAULT_SENDER'] = 'dinventarioc@gmail.com'
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')

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
    codigo_invitacion = db.Column(db.String(10), unique=True, nullable=True)
    
    # --- CAMPOS DE PERSONALIZACIÓN (NUEVO) ---
    logo_url = db.Column(db.String(255), nullable=True) # Logo de la empresa
    header_titulo = db.Column(db.String(150), nullable=True)     # Texto Grande
    header_subtitulo = db.Column(db.String(200), nullable=True)  # Texto Pequeño
    color_primario = db.Column(db.String(7), default='#333333') # Color hex para encabezados
    tipo_letra = db.Column(db.String(50), default='Helvetica') # Fuente del PDF
    direccion = db.Column(db.Text, nullable=True) # Dirección fiscal/física
    telefono = db.Column(db.String(20), nullable=True) # Teléfono de contacto
    usuarios = db.relationship('User', backref='organizacion', lazy=True)
    productos = db.relationship('Producto', backref='organizacion', lazy=True)
    categorias = db.relationship('Categoria', backref='organizacion', lazy=True)
    proveedores = db.relationship('Proveedor', backref='organizacion', lazy=True)
    ordenes_compra = db.relationship('OrdenCompra', backref='organizacion', lazy=True)
    salidas = db.relationship('Salida', backref='organizacion', lazy=True)
    gastos = db.relationship('Gasto', backref='organizacion', lazy=True)
    movimientos = db.relationship('Movimiento', backref='organizacion', lazy=True)
    proyectos_oc = db.relationship('ProyectoOC', backref='organizacion', lazy=True)

    # --- AÑADIDO ---
    almacenes = db.relationship('Almacen', backref='organizacion', lazy=True)

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
    
    # --- PERMISOS GRANULARES ---
    perm_view_dashboard = db.Column(db.Boolean, nullable=False, default=False)
    perm_view_management = db.Column(db.Boolean, nullable=False, default=False)
    perm_edit_management = db.Column(db.Boolean, nullable=False, default=False)
    perm_create_oc_standard = db.Column(db.Boolean, nullable=False, default=False)
    perm_create_oc_proyecto = db.Column(db.Boolean, nullable=False, default=False)
    perm_do_salidas = db.Column(db.Boolean, nullable=False, default=False)
    perm_view_gastos = db.Column(db.Boolean, nullable=False, default=False)
    
    # Relaciones de Auditoría
    ordenes_creadas = db.relationship('OrdenCompra', foreign_keys='OrdenCompra.creador_id', backref='creador', lazy=True)
    ordenes_canceladas = db.relationship('OrdenCompra', foreign_keys='OrdenCompra.cancelado_por_id', backref='cancelado_por', lazy=True)
    salidas_creadas = db.relationship('Salida', foreign_keys='Salida.creador_id', backref='creador', lazy=True)
    salidas_canceladas = db.relationship('Salida', foreign_keys='Salida.cancelado_por_id', backref='cancelado_por', lazy=True)
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
    contacto_telefono = db.Column(db.String(50), nullable=True)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)

class Categoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    descripcion = db.Column(db.String(255), nullable=True)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)

# --- MODELO 'Producto' MODIFICADO ---
class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(255), nullable=False)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    # --- CAMPOS DE STOCK ELIMINADOS ---
    precio_unitario = db.Column(db.Float, default=0.0)
    imagen_url = db.Column(db.String(255), nullable=True)
    
    # --- NUEVO CAMPO ---
    enlace_proveedor = db.Column(db.String(500), nullable=True)
    
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=True)
    categoria = db.relationship('Categoria', backref='productos', lazy=True)
    
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'), nullable=True)
    proveedor = db.relationship('Proveedor', backref='productos', lazy=True)
    
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)
    unidades_por_caja = db.Column(db.Integer, default=1)
    
    # --- NUEVA RELACIÓN ---
    stocks = db.relationship('Stock', backref='producto', lazy='dynamic', cascade="all, delete-orphan")
    
    def get_stock_total(self):
        """ Suma el stock de este producto en TODOS los almacenes. """
        return db.session.query(db.func.sum(Stock.cantidad)).filter_by(producto_id=self.id).scalar() or 0


# --- NUEVO MODELO 'Almacen' ---
class Almacen(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    ubicacion = db.Column(db.String(255), nullable=True) # ej. "Pasillo 5, Estante A"
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)
    
    stocks = db.relationship('Stock', backref='almacen', lazy='dynamic', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Almacen {self.nombre}>'

# --- NUEVO MODELO 'Stock' ---
class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    almacen_id = db.Column(db.Integer, db.ForeignKey('almacen.id'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False, default=0)
    
    stock_minimo = db.Column(db.Integer, nullable=False, default=5)
    stock_maximo = db.Column(db.Integer, nullable=False, default=100)
    
    # --- NUEVO CAMPO ---
    ubicacion = db.Column(db.String(100), nullable=True) 
    
    __table_args__ = (db.UniqueConstraint('producto_id', 'almacen_id', name='_producto_almacen_uc'),)
    
    @property
    def estado_stock(self):
        if self.cantidad < self.stock_minimo:
            return 'bajo'
        elif self.cantidad > self.stock_maximo:
            return 'exceso'
        return 'ok'
    def __repr__(self):
        return f'<Stock ProdID: {self.producto_id} AlmID: {self.almacen_id} Qty: {self.cantidad}>'

# --- MODELO 'OrdenCompra' MODIFICADO ---
class OrdenCompra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.now)
    fecha_recepcion = db.Column(db.DateTime, nullable=True)
    estado = db.Column(db.String(20), nullable=False, default='borrador')
    
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'), nullable=False)
    # --- LÍNEA RESTAURADA ---
    proveedor = db.relationship('Proveedor', backref='ordenes_compra', lazy=True)
    # ------------------------

    almacen_id = db.Column(db.Integer, db.ForeignKey('almacen.id'), nullable=False)
    almacen = db.relationship('Almacen')
    
    detalles = db.relationship('OrdenCompraDetalle', backref='orden', lazy=True, cascade="all, delete-orphan")
    
    creador_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cancelado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)
    
    @property
    def costo_total(self):
        return sum(detalle.subtotal for detalle in self.detalles)
    
    @property
    def costo_total(self):
        return sum(detalle.subtotal for detalle in self.detalles)

class OrdenCompraDetalle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    orden_id = db.Column(db.Integer, db.ForeignKey('orden_compra.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    producto = db.relationship('Producto')
    cantidad_solicitada = db.Column(db.Integer, nullable=False, default=1)
    cajas = db.Column(db.Float, nullable=True, default=0.0)
    costo_unitario_estimado = db.Column(db.Float, nullable=True, default=0.0)
    enlace_proveedor = db.Column(db.String(500), nullable=True)

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
    fecha = db.Column(db.Date, nullable=False, default=datetime.now().date)
    estado = db.Column(db.String(20), nullable=False, default='abierta')
    
    creador_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cancelado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # (Para auditoría futura) 
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)

    # --- LÍNEA AÑADIDA ---
    almacen_id = db.Column(db.Integer, db.ForeignKey('almacen.id'), nullable=False)
    almacen = db.relationship('Almacen') # Para fácil acceso
    
    movimientos = db.relationship('Movimiento', backref='salida', lazy='dynamic', cascade="all, delete-orphan")

class Movimiento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    producto = db.relationship('Producto', backref='movimientos', lazy=True)
    
    cantidad = db.Column(db.Integer, nullable=False) 
    tipo = db.Column(db.String(20), nullable=False) 
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.now)
    
    motivo = db.Column(db.String(255), nullable=False) 
    
    orden_compra_id = db.Column(db.Integer, db.ForeignKey('orden_compra.id'), nullable=True)
    salida_id = db.Column(db.Integer, db.ForeignKey('salida.id'), nullable=True)
    
    # --- LÍNEA AÑADIDA ---
    almacen_id = db.Column(db.Integer, db.ForeignKey('almacen.id'), nullable=False)

    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)

    def __repr__(self):
        return f'<Movimiento {self.producto_id} ({self.cantidad})>'
    
# --- MODELO 'ProyectoOC' MODIFICADO ---

Conversación con Gemini
Tú dijiste
aqui esta el codigo del orden_form, revisa por favor el dato que me comentaste: {% extends 'base.html' %}



{% block title %}{{ titulo }}{% endblock %}



{% block content %}

<style>

    /* ==========================================

       ESTILOS COMPLEMENTARIOS Y BOTÓN DE TEMA

       ========================================== */

       

    /* Ajustes específicos para inputs/selects en modo oscuro */

    [data-bs-theme="dark"] .form-control,

    [data-bs-theme="dark"] .form-select,

    [data-bs-theme="dark"] .input-group-text {

        background-color: var(--card-bg) !important;

        border-color: var(--glass-border) !important;

        color: var(--bs-body-color) !important;

    }

    [data-bs-theme="dark"] .form-control:focus,

    [data-bs-theme="dark"] .form-select:focus {

        background-color: #1f2937 !important;

        border-color: var(--bs-primary) !important;

        color: #ffffff !important;

    }

    [data-bs-theme="dark"] .form-control:disabled,

    [data-bs-theme="dark"] .form-select:disabled {

        background-color: #111827 !important;

        opacity: 0.7;

    }

    [data-bs-theme="dark"] .list-group-item {

        background-color: var(--card-bg) !important;

        border-color: var(--glass-border) !important;

        color: var(--bs-body-color);

    }

    [data-bs-theme="dark"] .list-group-item:hover {

        background-color: var(--hover-bg) !important;

    }



    /* Tarjetas de Producto (Líneas del carrito) */

    .producto-linea {

        transition: transform 0.2s ease, box-shadow 0.2s ease;

        background-color: var(--card-bg);

    }

    .producto-linea:hover {

        border-color: var(--bs-primary) !important;

        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05) !important;

    }

    [data-bs-theme="dark"] .producto-linea:hover {

        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3) !important;

    }



    /* --- ANIMACIÓN DEL BOTÓN DE TEMA (SOL / LUNA) --- */

    .theme-switch-wrapper {

        position: relative;

        width: 44px;

        height: 44px;

        border-radius: 50%;

        cursor: pointer;

        display: flex;

        align-items: center;

        justify-content: center;

        background-color: var(--card-bg);

        border: 1px solid var(--glass-border);

        transition: background-color 0.3s ease, border-color 0.3s ease, transform 0.2s ease;

        overflow: hidden;

        box-shadow: var(--card-shadow);

    }

    .theme-switch-wrapper:hover {

        transform: scale(1.08);

    }

    .theme-switch-icon {

        position: absolute;

        font-size: 1.3rem;

        transition: transform 0.6s cubic-bezier(0.68, -0.55, 0.265, 1.55), opacity 0.4s ease;

    }

    /* Estado inicial: MODO CLARO */

    .theme-switch-sun {

        color: #f59e0b; /* Amber */

        transform: translateY(0) rotate(0deg);

        opacity: 1;

    }

    .theme-switch-moon {

        color: #e2e8f0;

        transform: translateY(30px) rotate(90deg);

        opacity: 0;

    }

    

    /* Estado: MODO OSCURO */

    [data-bs-theme="dark"] .theme-switch-sun {

        transform: translateY(-30px) rotate(-90deg);

        opacity: 0;

    }

    [data-bs-theme="dark"] .theme-switch-moon {

        transform: translateY(0) rotate(0deg);

        opacity: 1;

    }

</style>



<!-- Cargar librería para leer QR/Barras -->

<script src="https://cdn.jsdelivr.net/npm/html5-qrcode/html5-qrcode.min.js" type="text/javascript"></script>



<div class="container-fluid mt-3 mb-5">



    <!-- BOTÓN DE TEMA ANIMADO (SOL/LUNA) -->

    <div class="d-flex justify-content-end mb-2">

        <div id="theme-toggle" class="theme-switch-wrapper" title="Alternar Tema Claro/Oscuro">

            <i class="bi bi-sun-fill theme-switch-icon theme-switch-sun"></i>

            <i class="bi bi-moon-stars-fill theme-switch-icon theme-switch-moon"></i>

        </div>

    </div>



    <!-- ENCABEZADO -->

    <div class="text-center mb-5">

        <h2 class="fw-bold fs-1"><i class="bi bi-file-earmark-text text-primary me-2"></i>{{ titulo }}</h2>

        <p class="text-muted fs-5">

            Genera una nueva solicitud de abastecimiento para tus almacenes

        </p>

    </div>



    <form method="POST" action="{{ url_for('editar_orden', id=orden.id) if orden else url_for('nueva_orden_manual') }}" id="form_orden">

        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

        

        <!-- ==========================================

             SECCIÓN 1: DATOS GENERALES

             ========================================== -->

        <div class="card shadow-sm mb-4 border-0 rounded-4">

            <div class="card-header bg-transparent pt-4 pb-3 border-bottom border-secondary border-opacity-25 d-flex align-items-center">

                <h5 class="mb-0 fw-bold text-body"><i class="bi bi-info-circle text-primary me-2"></i>Datos de la Orden</h5>

            </div>

            <div class="card-body p-4 p-md-5">

                <div class="row g-4">

                    <!-- Proveedor -->

                    <div class="col-md-6">

                        <label for="proveedor_id" class="form-label fw-bold small text-muted text-uppercase mb-2">Proveedor</label>

                        <div class="input-group input-group-lg shadow-sm">

                            <span class="input-group-text bg-light border-secondary border-opacity-25"><i class="bi bi-building text-secondary"></i></span>

                            <select class="form-select bg-light border-secondary border-opacity-25 fs-6" id="proveedor_id" name="proveedor_id" 

                                    {% if orden %}disabled{% endif %} required>

                                <option value="">-- Selecciona un proveedor --</option>

                                {% for prov in proveedores %}

                                    <option value="{{ prov.id }}" 

                                            {% if orden and orden.proveedor_id == prov.id %}selected{% endif %}>

                                        {{ prov.nombre }}

                                    </option>

                                {% endfor %}

                            </select>

                        </div>

                        {% if orden %}

                            <!-- Input oculto para que el servidor reciba el dato aunque el select esté disabled -->

                            <input type="hidden" id="hidden_proveedor_id" name="proveedor_id" value="{{ orden.proveedor_id }}">

                            <div class="form-text text-muted mt-2"><i class="bi bi-lock-fill me-1"></i>No se puede cambiar el proveedor de una orden existente.</div>

                        {% endif %}

                    </div>

                    

                    <!-- Almacén -->

                    <div class="col-md-6">

                        <label for="almacen_id" class="form-label fw-bold small text-muted text-uppercase mb-2">Almacén de Destino</label>

                        <div class="input-group input-group-lg shadow-sm">

                            <span class="input-group-text bg-light border-secondary border-opacity-25"><i class="bi bi-shop text-secondary"></i></span>

                            <select class="form-select bg-light border-secondary border-opacity-25 fs-6" id="almacen_id" name="almacen_id" 

                                    {% if orden %}disabled{% endif %} required>

                                <option value="">-- Selecciona un almacén --</option>

                                {% for alm in almacenes %}

                                    <option value="{{ alm.id }}" 

                                            {% if orden and orden.almacen_id == alm.id %}selected{% endif %}>

                                        {{ alm.nombre }}

                                    </option>

                                {% endfor %}

                            </select>

                        </div>

                        {% if orden %}

                            <input type="hidden" name="almacen_id" value="{{ orden.almacen_id }}">

                            <div class="form-text text-muted mt-2"><i class="bi bi-lock-fill me-1"></i>No se puede cambiar el almacén de una orden existente.</div>

                        {% endif %}

                    </div>

                </div>

            </div>

        </div>



        <!-- ==========================================

             SECCIÓN 2: BÚSQUEDA Y ESCANEO

             ========================================== -->

        <div class="card shadow-sm mb-5 border-0 rounded-4">

            <div class="card-header bg-transparent pt-4 pb-3 border-bottom border-info border-opacity-50 d-flex justify-content-between align-items-center">

                <h5 class="mb-0 fw-bold text-body"><i class="bi bi-search text-info me-2"></i>Buscar o Escanear Producto</h5>

            </div>

            <div class="card-body p-4 p-md-5">

                

                <div id="mensaje_bloqueo_buscador" class="alert alert-warning border-warning border-opacity-25 shadow-sm rounded-3 py-3 mb-4 d-flex align-items-center" style="display: none;">

                    <i class="bi bi-exclamation-triangle-fill fs-4 me-3 text-warning"></i>

                    <div>Primero selecciona un <strong>Proveedor</strong> y un <strong>Almacén</strong> en la parte superior para habilitar el buscador.</div>

                </div>



                <!-- ÁREA DE CÁMARA (Oculta por defecto) -->

                <div id="reader-container" class="mb-4 shadow-sm border border-secondary border-opacity-25 rounded-4 bg-light p-3" style="display: none;">

                    <div id="reader" style="width: 100%; max-width: 600px; margin: 0 auto; border-radius: 8px; overflow: hidden;"></div>

                    <div class="text-center mt-3">

                        <button type="button" class="btn btn-danger btn-sm fw-bold rounded-pill px-3 shadow-sm" onclick="detenerEscaner()">

                            <i class="bi bi-stop-circle me-1"></i> Detener Cámara

                        </button>

                    </div>

                </div>



                <div class="position-relative">

                    <div class="input-group input-group-lg shadow-sm">

                        <span class="input-group-text bg-light border-secondary border-opacity-25 text-primary"><i class="bi bi-upc-scan"></i></span>

                        <input type="text" id="buscador" class="form-control bg-light border-secondary border-opacity-25 fs-6" 

                               placeholder="Escribe Nombre, SKU o escanea un código..." autocomplete="off" disabled>

                        

                        <button class="btn btn-primary fw-bold px-4" type="button" id="btn_escanear" onclick="iniciarEscaner()" disabled>

                            <i class="bi bi-qr-code-scan me-1"></i> <span class="d-none d-sm-inline">Escanear</span>

                        </button>

                    </div>



                    <!-- Lista flotante de sugerencias -->

                    <div id="lista_sugerencias" class="list-group position-absolute w-100 shadow-lg border-secondary border-opacity-25 rounded-3" 

                         style="z-index: 1050; top: 100%; display: none; max-height: 300px; overflow-y: auto; margin-top: 5px;">

                    </div>

                </div>

            </div>

        </div>



        <!-- ==========================================

             SECCIÓN 3: LISTA DE PRODUCTOS (CARRITO)

             ========================================== -->

        <div class="d-flex justify-content-between align-items-end mb-3 mt-5 px-2">

            <h4 class="fw-bold mb-0 text-body"><i class="bi bi-box-seam text-primary me-2"></i>Artículos Solicitados</h4>

            <div class="bg-success bg-opacity-10 border border-success border-opacity-25 rounded-3 px-4 py-2 shadow-sm text-center">

                <small class="text-uppercase text-success fw-bold" style="font-size: 0.7rem; letter-spacing: 1px;">Total Estimado</small>

                <h3 class="text-success fw-bold mb-0">$<span id="gran_total">0.00</span></h3>

            </div>

        </div>



        <div id="lineas_productos_container" class="mb-5">

            

            {% if orden %}

                <!-- CARGA DE PRODUCTOS EXISTENTES (EDICIÓN) -->

                {% for detalle in orden.detalles %}

                    {% set p_match = productos | selectattr("id", "equalto", detalle.producto_id) | first %}

                    {% set factor = p_match.unidades_por_caja if p_match and 'unidades_por_caja' in p_match else 1 %}

                    

                    <!-- Verificamos si hay un enlace en el detalle o si no, heredamos el del producto original -->

                    {% set enlace_actual = detalle.enlace if detalle.enlace else (p_match.get('enlace', '') if p_match else '') %}

                    

                    <div class="producto-linea border border-secondary border-opacity-25 p-4 rounded-4 shadow-sm mb-3">

                        <div class="row g-3 align-items-center">

                            <!-- Producto Info -->

                            <div class="col-md-3">

                                <label class="form-label small fw-bold text-primary text-uppercase mb-1" style="font-size: 0.7rem; letter-spacing: 0.5px;">Producto</label>

                                <div class="fw-bold fs-6 text-body">{{ p_match.nombre if p_match else 'Producto ' ~ detalle.producto_id }}</div>

                                <div class="d-flex align-items-center gap-2 mt-1">

                                    <span class="badge bg-secondary bg-opacity-10 text-dark border border-secondary border-opacity-25 font-monospace"><i class="bi bi-upc opacity-50 me-1"></i>{{ p_match.codigo if p_match else 'N/A' }}</span>

                                    <span class="badge bg-info text-dark shadow-sm" style="font-size: 0.65rem;"><i class="bi bi-box-seam me-1"></i>Caja: {{ factor }} ud(s)</span>

                                </div>

                                <input type="hidden" name="producto_id[]" value="{{ detalle.producto_id }}">

                                <input type="hidden" class="factor-empaque" value="{{ factor }}">

                            </div>

                            

                            <!-- Cajas -->

                            <div class="col-md-2">

                                <label class="form-label small fw-bold text-muted text-uppercase mb-1" style="font-size: 0.7rem; letter-spacing: 0.5px;">Cajas</label>

                                <div class="input-group input-group-sm shadow-sm">

                                    <span class="input-group-text bg-light border-secondary border-opacity-25"><i class="bi bi-box text-secondary"></i></span>

                                    <input type="number" name="cajas[]" class="form-control bg-light border-secondary border-opacity-25 cajas-input text-center fw-bold" 

                                           value="{{ (detalle.cantidad_solicitada / factor) | round(2, 'floor') }}" min="0" step="0.01">

                                </div>

                            </div>



                            <!-- Unidades -->

                            <div class="col-md-2">

                                <label class="form-label small fw-bold text-muted text-uppercase mb-1" style="font-size: 0.7rem; letter-spacing: 0.5px;">Total Unid.</label>

                                <input type="number" name="cantidad[]" class="form-control form-control-sm bg-light border-secondary border-opacity-25 unidades-input text-center fw-bold shadow-sm" 

                                       value="{{ detalle.cantidad_solicitada }}" min="1" required>

                            </div>



                            <!-- Costo Unitario -->

                            <div class="col-md-3">

                                <label class="form-label small fw-bold text-muted text-uppercase mb-1" style="font-size: 0.7rem; letter-spacing: 0.5px;">Costo Unit.</label>

                                <div class="input-group input-group-sm shadow-sm">

                                    <span class="input-group-text bg-light border-secondary border-opacity-25 text-success fw-bold">$</span>

                                    <input type="number" name="costo[]" class="form-control bg-light border-secondary border-opacity-25 costo-input fw-bold text-dark" 

                                           value="{{ '%.2f'|format(detalle.costo_unitario_estimado) }}" step="0.01" min="0" required>

                                </div>

                                <small class="text-success subtotal-linea fw-bold d-block mt-1">Sub: $0.00</small>

                            </div>



                            <!-- Botón Quitar -->

                            <div class="col-md-2 text-end">

                                <button type="button" class="btn btn-outline-danger btn-sm rounded-pill px-3 shadow-sm fw-bold w-100" onclick="eliminarLinea(this)">

                                    <i class="bi bi-trash"></i> Quitar

                                </button>

                            </div>

                            

                            <!-- Campo de Enlace Opcional -->

                            <div class="col-12 mt-3 pt-2 border-top border-secondary border-opacity-10">

                                <div class="input-group input-group-sm">

                                    <span class="input-group-text bg-light border-secondary border-opacity-25 {% if enlace_actual %}text-primary fw-bold{% else %}text-secondary{% endif %}" style="font-size: 0.75rem;">

                                        <i class="bi bi-link-45deg me-1"></i> Enlace

                                    </span>

                                    <input type="url" name="enlace[]" class="form-control bg-light border-secondary border-opacity-25" 

                                           placeholder="https://ejemplo.com/producto (Opcional)" value="{{ enlace_actual }}">

                                </div>

                                {% if enlace_actual %}

                                    <div class="form-text text-primary small mt-1"><i class="bi bi-check2-circle"></i> Enlace recuperado.</div>

                                {% endif %}

                            </div>

                        </div>

                    </div>

                {% endfor %}

            {% else %}

                <!-- Mensaje vacío inicial -->

                <div id="mensaje_vacio" class="text-center text-muted py-5 border border-secondary border-opacity-25 rounded-4 border-dashed" style="background-color: var(--card-bg);">

                    <i class="bi bi-cart shadow-sm p-4 rounded-circle fs-1 opacity-25 d-inline-block mb-3 bg-light"></i>

                    <h5 class="fw-bold text-body">El carrito está vacío</h5>

                    <p class="mb-0">Usa el buscador o escáner de arriba para agregar productos a esta orden.</p>

                </div>

            {% endif %}

        </div>

        

        <!-- ==========================================

             SECCIÓN 4: BOTONES FINALES

             ========================================== -->

        <hr class="border-secondary border-opacity-25 mb-4">

        <div class="d-grid gap-3 d-md-flex justify-content-md-end mb-5">

            <a href="{{ url_for('lista_ordenes') }}" class="btn btn-outline-secondary rounded-pill fw-bold shadow-sm px-4 py-3">

                Cancelar

            </a>

            <button type="submit" class="btn btn-primary rounded-pill fw-bold shadow-sm px-5 py-3">

                <i class="bi bi-save me-2"></i> Guardar Orden de Compra

            </button>

        </div>

    </form>

</div>



<!-- SONIDO DE BEEP -->

<audio id="audio_beep" src="https://www.soundjay.com/button/beep-07.wav" preload="auto"></audio>



<!-- JAVASCRIPT -->

<script>

    // ==========================================

    // 0. SISTEMA DE TEMA (MODO CLARO / OSCURO)

    // ==========================================

    const themeToggleBtn = document.getElementById('theme-toggle');

    const htmlElement = document.documentElement;



    function applyTheme(theme) {

        htmlElement.setAttribute('data-bs-theme', theme);

        localStorage.setItem('app_theme', theme);

    }



    const savedTheme = localStorage.getItem('app_theme') || 'dark';

    applyTheme(savedTheme);



    if(themeToggleBtn) {

        themeToggleBtn.addEventListener('click', () => {

            const currentTheme = htmlElement.getAttribute('data-bs-theme');

            applyTheme(currentTheme === 'dark' ? 'light' : 'dark');

        });

    }



    // ==========================================

    // 1. INICIALIZACIÓN DE VARIABLES Y LÓGICA OC

    // ==========================================

    const todosLosProductos = {{ productos | tojson | safe }};

    

    const selectProveedor = document.getElementById('proveedor_id');

    const hiddenProveedor = document.getElementById('hidden_proveedor_id');

    const selectAlmacen = document.getElementById('almacen_id');

    const buscador = document.getElementById('buscador');

    const btnEscanear = document.getElementById('btn_escanear');

    const sugerencias = document.getElementById('lista_sugerencias');

    const container = document.getElementById('lineas_productos_container');

    const mensajeVacio = document.getElementById('mensaje_vacio');

    const mensajeBloqueo = document.getElementById('mensaje_bloqueo_buscador');

    const granTotalSpan = document.getElementById('gran_total');

    const audioBeep = document.getElementById('audio_beep');



    // Función auxiliar para obtener el ID del proveedor

    function getProveedorId() {

        return selectProveedor.value || (hiddenProveedor ? hiddenProveedor.value : "");

    }



    // --- ACTIVAR/DESACTIVAR BUSCADOR ---

    function verificarEstadoBuscador() {

        const provId = getProveedorId();

        const almId = selectAlmacen.value;



        if (provId && almId) {

            buscador.disabled = false;

            btnEscanear.disabled = false;

            mensajeBloqueo.style.display = 'none';

        } else {

            buscador.disabled = true;

            btnEscanear.disabled = true;

            mensajeBloqueo.style.display = 'block';

        }

    }



    if(selectProveedor) {

        selectProveedor.addEventListener('change', function() {

            const lineas = container.querySelectorAll('.producto-linea');

            if(lineas.length > 0) {

                if(confirm("Si cambias de proveedor, se borrarán los productos actuales de la orden. ¿Continuar?")) {

                    container.innerHTML = '';

                    if(mensajeVacio) {

                        container.appendChild(mensajeVacio);

                        mensajeVacio.style.display = 'block';

                    }

                    recalcularTotales();

                } else {

                    // Revertir no es trivial, se asume que el usuario acepta

                }

            }

            verificarEstadoBuscador();

        });

    }

    

    if(selectAlmacen) selectAlmacen.addEventListener('change', verificarEstadoBuscador);

    

    document.addEventListener('DOMContentLoaded', () => {

        verificarEstadoBuscador();

        recalcularTotales();

    });





    // ==========================================

    // 2. LÓGICA DE BÚSQUEDA Y ESCÁNER

    // ==========================================

    let html5QrcodeScanner = null;

    let isScanning = false;

    let ultimoCodigo = null;



    function iniciarEscaner() {

        if (isScanning || !getProveedorId()) return;

        document.getElementById('reader-container').style.display = 'block';

        html5QrcodeScanner = new Html5Qrcode("reader");

        html5QrcodeScanner.start({ facingMode: "environment" }, { fps: 10, qrbox: 250 }, onScanSuccess, () => {})

        .then(() => { isScanning = true; btnEscanear.classList.add('disabled'); })

        .catch(err => { alert("No se pudo acceder a la cámara."); document.getElementById('reader-container').style.display = 'none'; });

    }



    function detenerEscaner() {

        if (html5QrcodeScanner && isScanning) {

            html5QrcodeScanner.stop().then(() => {

                document.getElementById('reader-container').style.display = 'none';

                btnEscanear.classList.remove('disabled');

                html5QrcodeScanner.clear();

                isScanning = false;

            });

        }

    }



    function onScanSuccess(decodedText) {

        if (decodedText === ultimoCodigo) return; 

        ultimoCodigo = decodedText;

        setTimeout(() => ultimoCodigo = null, 2000);



        try { audioBeep.play(); } catch(e) {}



        const provId = getProveedorId();

        const producto = todosLosProductos.find(p => p.codigo.toLowerCase() === decodedText.toLowerCase() && p.proveedor_id == provId);

        

        if (producto) {

            agregarProducto(producto);

        } else {

            alert(`El código ${decodedText} no existe o no pertenece a este proveedor.`);

        }

    }



    // Buscador manual (Typeahead)

    buscador.addEventListener('input', function() {

        const query = this.value.toLowerCase().trim();

        const provId = getProveedorId();

        sugerencias.innerHTML = ''; 



        if (query.length === 0 || !provId) {

            sugerencias.style.display = 'none';

            return;

        }



        const resultados = todosLosProductos.filter(p => 

            p.proveedor_id == provId && 

            (p.nombre.toLowerCase().includes(query) || p.codigo.toLowerCase().includes(query))

        );



        if (resultados.length > 0) {

            sugerencias.style.display = 'block';

            resultados.forEach(p => {

                const item = document.createElement('a');

                item.href = '#';

                item.classList.add('list-group-item', 'list-group-item-action', 'py-3');

                

                const factorTexto = p.unidades_por_caja ? ` (Caja: ${p.unidades_por_caja} uds)` : '';

                // Asumimos que si existe un enlace base en el producto, lo mostramos como hint

                const linkIcon = p.enlace ? '<i class="bi bi-link-45deg text-primary ms-2" title="Tiene enlace automático"></i>' : '';

                

                item.innerHTML = `

                    <div class="d-flex justify-content-between align-items-center">

                        <div>

                            <strong class="text-body">${p.nombre}</strong> ${linkIcon}<br>

                            <small class="text-muted"><i class="bi bi-upc"></i> ${p.codigo}${factorTexto}</small>

                        </div>

                        <span class="badge bg-success shadow-sm px-2 py-1">$${p.precio_unitario || p.costo || '0.00'}</span>

                    </div>

                `;



                item.onclick = (e) => {

                    e.preventDefault();

                    agregarProducto(p);

                    buscador.value = '';

                    sugerencias.style.display = 'none';

                    buscador.focus();

                };

                sugerencias.appendChild(item);

            });

        } else {

            sugerencias.style.display = 'none';

        }

    });



    document.addEventListener('click', (e) => {

        if (e.target !== buscador) sugerencias.style.display = 'none';

    });





    // ==========================================

    // 3. LÓGICA DE CARRITO Y CÁLCULOS

    // ==========================================

    function agregarProducto(producto) {

        if (mensajeVacio) mensajeVacio.style.display = 'none';



        // Evitar duplicados: Sumar caja

        const existingInput = document.querySelector(`input[name="producto_id[]"][value="${producto.id}"]`);

        if (existingInput) {

            const row = existingInput.closest('.producto-linea');

            const cajasInput = row.querySelector('.cajas-input');

            cajasInput.value = parseFloat(cajasInput.value) + 1;

            cajasInput.dispatchEvent(new Event('input', { bubbles: true }));

            

            row.style.borderColor = "var(--bs-primary)";

            row.style.boxShadow = "0 0 15px rgba(79, 70, 229, 0.3)";

            setTimeout(() => { 

                row.style.borderColor = ""; 

                row.style.boxShadow = ""; 

            }, 800);

            return;

        }



        const factor = producto.unidades_por_caja || 1;

        const costo = parseFloat(producto.precio_unitario || producto.costo || 0).toFixed(2);

        

        // Pre-cargar el enlace del producto si existe en el catálogo

        const enlace = producto.enlace || '';

        const linkEstilos = enlace ? 'text-primary fw-bold' : 'text-secondary';

        const linkMensaje = enlace ? `<div class="form-text text-primary small mt-1"><i class="bi bi-check2-circle"></i> Enlace auto-detectado.</div>` : '';



        const div = document.createElement('div');

        div.classList.add('producto-linea', 'border', 'border-secondary', 'border-opacity-25', 'p-4', 'rounded-4', 'shadow-sm', 'mb-3');

        

        div.innerHTML = `

            <div class="row g-3 align-items-center">

                <!-- Info Producto -->

                <div class="col-md-3">

                    <label class="form-label small fw-bold text-primary text-uppercase mb-1" style="font-size: 0.7rem; letter-spacing: 0.5px;">Producto</label>

                    <div class="fw-bold fs-6 text-body">${producto.nombre}</div>

                    <div class="d-flex align-items-center gap-2 mt-1">

                        <span class="badge bg-secondary bg-opacity-10 text-dark border border-secondary border-opacity-25 font-monospace"><i class="bi bi-upc opacity-50 me-1"></i>${producto.codigo}</span>

                        <span class="badge bg-info text-dark shadow-sm" style="font-size: 0.65rem;"><i class="bi bi-box-seam me-1"></i>Caja: ${factor} ud(s)</span>

                    </div>

                    <input type="hidden" name="producto_id[]" value="${producto.id}">

                    <input type="hidden" class="factor-empaque" value="${factor}">

                </div>

                

                <!-- Cajas -->

                <div class="col-md-2">

                    <label class="form-label small fw-bold text-muted text-uppercase mb-1" style="font-size: 0.7rem; letter-spacing: 0.5px;">Cajas</label>

                    <div class="input-group input-group-sm shadow-sm">

                        <span class="input-group-text bg-light border-secondary border-opacity-25"><i class="bi bi-box text-secondary"></i></span>

                        <input type="number" name="cajas[]" class="form-control bg-light border-secondary border-opacity-25 cajas-input text-center fw-bold" value="1" min="0" step="0.01">

                    </div>

                </div>



                <!-- Unidades -->

                <div class="col-md-2">

                    <label class="form-label small fw-bold text-muted text-uppercase mb-1" style="font-size: 0.7rem; letter-spacing: 0.5px;">Total Unid.</label>

                    <input type="number" name="cantidad[]" class="form-control form-control-sm bg-light border-secondary border-opacity-25 unidades-input text-center fw-bold shadow-sm" value="${factor}" min="1" required>

                </div>



                <!-- Costo Unitario -->

                <div class="col-md-3">

                    <label class="form-label small fw-bold text-muted text-uppercase mb-1" style="font-size: 0.7rem; letter-spacing: 0.5px;">Costo Unit.</label>

                    <div class="input-group input-group-sm shadow-sm">

                        <span class="input-group-text bg-light border-secondary border-opacity-25 text-success fw-bold">$</span>

                        <input type="number" name="costo[]" class="form-control bg-light border-secondary border-opacity-25 costo-input fw-bold text-dark" value="${costo}" step="0.01" min="0" required>

                    </div>

                    <small class="text-success subtotal-linea fw-bold d-block mt-1">Sub: $0.00</small>

                </div>



                <!-- Botón Quitar -->

                <div class="col-md-2 text-end">

                    <button type="button" class="btn btn-outline-danger btn-sm rounded-pill px-3 shadow-sm fw-bold w-100" onclick="eliminarLinea(this)">

                        <i class="bi bi-trash"></i> Quitar

                    </button>

                </div>



                <!-- Campo de Enlace (Auto-Completado si existe) -->

                <div class="col-12 mt-3 pt-2 border-top border-secondary border-opacity-10">

                    <div class="input-group input-group-sm">

                        <span class="input-group-text bg-light border-secondary border-opacity-25 ${linkEstilos}" style="font-size: 0.75rem;">

                            <i class="bi bi-link-45deg me-1"></i> Enlace

                        </span>

                        <input type="url" name="enlace[]" class="form-control bg-light border-secondary border-opacity-25" 

                               placeholder="https://ejemplo.com/producto (Opcional)" value="${enlace}">

                    </div>

                    ${linkMensaje}

                </div>

            </div>

        `;



        container.appendChild(div);

        recalcularTotales();

    }



    container.addEventListener('input', function(e) {

        const row = e.target.closest('.producto-linea');

        if (!row) return;



        const factor = parseFloat(row.querySelector('.factor-empaque').value) || 1;

        const inputCajas = row.querySelector('.cajas-input');

        const inputUnidades = row.querySelector('.unidades-input');



        if (e.target.classList.contains('cajas-input')) {

            const cajas = parseFloat(inputCajas.value) || 0;

            inputUnidades.value = Math.ceil(cajas * factor); 

        }

        else if (e.target.classList.contains('unidades-input')) {

            const unidades = parseInt(inputUnidades.value) || 0;

            inputCajas.value = (unidades / factor).toFixed(2);

        }



        recalcularTotales();

    });



    window.eliminarLinea = function(boton) {

        boton.closest('.producto-linea').remove();

        const items = document.getElementsByName('producto_id[]');

        if (items.length === 0 && mensajeVacio) {

            mensajeVacio.style.display = 'block';

        }

        recalcularTotales();

    }



    function recalcularTotales() {

        let granTotal = 0;

        const lineas = document.querySelectorAll('.producto-linea');

        

        lineas.forEach(linea => {

            const unidades = parseInt(linea.querySelector('.unidades-input').value) || 0;

            const costoUnitario = parseFloat(linea.querySelector('.costo-input').value) || 0;

            

            const subtotal = unidades * costoUnitario;

            granTotal += subtotal;

            

            const labelSubtotal = linea.querySelector('.subtotal-linea');

            if(labelSubtotal) {

                // Formateamos con comas para la vista en pantalla

                labelSubtotal.innerText = `Sub: $${subtotal.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

            }

        });



        granTotalSpan.innerText = granTotal.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});

    }

</script>

{% endblock %}

Gemini dijo
He revisado el código que me has compartido y, efectivamente, el problema de por qué no se mostraban los enlaces al editar una orden existente estaba en el nombre del atributo dentro de la plantilla HTML.

Como me comentaste que el campo en la base de datos se llama enlace_proveedor, en el archivo app.py ya lo estamos mapeando correctamente, pero en la plantilla orden_form.html estábamos intentando leer detalle.enlace en lugar de detalle.enlace_proveedor.

He actualizado el Canvas con la versión final de las funciones en app.py y a continuación te genero el archivo orden_form.html con la corrección aplicada en la línea de detección de enlaces.

He actualizado las funciones de app.py en el Canvas para asegurar que el guardado (POST) y la lectura (GET) utilicen consistentemente el nombre de campo enlace_proveedor. También he generado el archivo templates/orden_form.html con la corrección necesaria para que el enlace se detecte correctamente en el modo de edición.

Recuerda que para que estos cambios tengan efecto, la columna enlace_proveedor debe existir tanto en tu tabla Producto como en OrdenCompraDetalle.

¿Deseas que revisemos alguna otra vista o módulo?

Tú dijiste
pudes darme el orden_form.html

Gemini dijo
Aquí tienes el archivo orden_form.html completo y actualizado. He asegurado que la lógica de detección de enlaces use el nombre de columna correcto (enlace_proveedor) y que el diseño sea totalmente responsivo y compatible con el modo oscuro.

He actualizado el archivo con las siguientes mejoras críticas:

Detección de Enlaces: En el modo de edición (Jinja), ahora busca detalle.enlace_proveedor. En el modo de búsqueda (JS), busca producto.enlace (ya que tu app.py lo mapea así).

Visualización Inteligente: El distintivo "Enlace auto-detectado" aparece solo cuando el catálogo tiene un link guardado, ayudando al usuario a saber qué productos ya están configurados.

Cálculo de Cajas: Mantiene la lógica bidireccional (Cajas ↔ Unidades) basada en el empaque configurado.

UI Adaptable: Bordes más suaves, sombras profundas y compatibilidad total con el modo oscuro de tu sistema.

Tú dijiste
acabo de tener este error: AssertionError: View function mapping is overwriting an exi>

Mar 18 00:34:35 Gestordeinventario gunicorn[860521]: [2026-03-18 00:34:35 +0000] [860521] [INFO] Worker exiting >

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]: [2026-03-18 00:34:35 +0000] [860522] [ERROR] Exception in w>

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]: Traceback (most recent call last):

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:   File "/root/venv/lib/python3.10/site-packages/gunicorn/ar>

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:     worker.init_process()

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:   File "/root/venv/lib/python3.10/site-packages/gunicorn/wo>

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:     self.load_wsgi()

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:   File "/root/venv/lib/python3.10/site-packages/gunicorn/wo>

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:     self.wsgi = self.app.wsgi()

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:   File "/root/venv/lib/python3.10/site-packages/gunicorn/ap>

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:     self.callable = self.load()

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:   File "/root/venv/lib/python3.10/site-packages/gunicorn/ap>

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:     return self.load_wsgiapp()

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:   File "/root/venv/lib/python3.10/site-packages/gunicorn/ap>

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:     return util.import_app(self.app_uri)

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:   File "/root/venv/lib/python3.10/site-packages/gunicorn/ut>

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:     mod = importlib.import_module(module)

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:   File "/usr/lib/python3.10/importlib/__init__.py", line 12>

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:     return _bootstrap._gcd_import(name[level:], package, le>

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:   File "<frozen importlib._bootstrap>", line 1050, in _gcd_>

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:   File "<frozen importlib._bootstrap>", line 1027, in _find>

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:   File "<frozen importlib._bootstrap>", line 1006, in _find>

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:   File "<frozen importlib._bootstrap>", line 688, in _load_>

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:   File "<frozen importlib._bootstrap_external>", line 883, >

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:   File "<frozen importlib._bootstrap>", line 241, in _call_>

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:   File "/root/Gestiondeinventario/app.py", line 2587, in <m>

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:     def nueva_orden_manual():

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:   File "/root/venv/lib/python3.10/site-packages/flask/sansi>

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:     self.add_url_rule(rule, endpoint, f, **options)

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:   File "/root/venv/lib/python3.10/site-packages/flask/sansi>

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:     return f(self, *args, **kwargs)

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:   File "/root/venv/lib/python3.10/site-packages/flask/sansi>

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]:     raise AssertionError(

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]: AssertionError: View function mapping is overwriting an exi>

Mar 18 00:34:35 Gestordeinventario gunicorn[860522]: [2026-03-18 00:34:35 +0000] [860522] [INFO] Worker exiting >

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]: [2026-03-18 00:34:35 +0000] [860523] [ERROR] Exception in w>

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]: Traceback (most recent call last):

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:   File "/root/venv/lib/python3.10/site-packages/gunicorn/ar>

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:     worker.init_process()

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:   File "/root/venv/lib/python3.10/site-packages/gunicorn/wo>

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:     self.load_wsgi()

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:   File "/root/venv/lib/python3.10/site-packages/gunicorn/wo>

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:     self.wsgi = self.app.wsgi()

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:   File "/root/venv/lib/python3.10/site-packages/gunicorn/ap>

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:     self.callable = self.load()

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:   File "/root/venv/lib/python3.10/site-packages/gunicorn/ap>

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:     return self.load_wsgiapp()

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:   File "/root/venv/lib/python3.10/site-packages/gunicorn/ap>

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:     return util.import_app(self.app_uri)

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:   File "/root/venv/lib/python3.10/site-packages/gunicorn/ut>

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:     mod = importlib.import_module(module)

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:   File "/usr/lib/python3.10/importlib/__init__.py", line 12>

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:     return _bootstrap._gcd_import(name[level:], package, le>

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:   File "<frozen importlib._bootstrap>", line 1050, in _gcd_>

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:   File "<frozen importlib._bootstrap>", line 1027, in _find>

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:   File "<frozen importlib._bootstrap>", line 1006, in _find>

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:   File "<frozen importlib._bootstrap>", line 688, in _load_>

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:   File "<frozen importlib._bootstrap_external>", line 883, >

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:   File "<frozen importlib._bootstrap>", line 241, in _call_>

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:   File "/root/Gestiondeinventario/app.py", line 2587, in <m>

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:     def nueva_orden_manual():

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:   File "/root/venv/lib/python3.10/site-packages/flask/sansi>

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:     self.add_url_rule(rule, endpoint, f, **options)

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:   File "/root/venv/lib/python3.10/site-packages/flask/sansi>

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:     return f(self, *args, **kwargs)

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:   File "/root/venv/lib/python3.10/site-packages/flask/sansi>

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]:     raise AssertionError(

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]: AssertionError: View function mapping is overwriting an exi>

Mar 18 00:34:35 Gestordeinventario gunicorn[860523]: [2026-03-18 00:34:35 +0000] [860523] [INFO] Worker exiting >

lines 54-100/100 (END)

Gemini dijo
Este error (AssertionError: View function mapping is overwriting an existing endpoint function) ocurre porque tienes la función nueva_orden_manual definida dos veces en tu archivo app.py.

Cuando Flask arranca, intenta registrar cada ruta, pero al encontrar dos funciones con el mismo nombre (nueva_orden_manual), se bloquea para evitar ambigüedades. Probablemente al pegar el código que te pasé anteriormente, dejaste la versión vieja en el archivo.

Para solucionarlo:

Abre tu archivo app.py.

Busca la línea 2587 (según tu log de error).

Verás que hay dos bloques que empiezan con @app.route('/orden/nueva/manual'...).

Borra ambas versiones y pega únicamente esta versión corregida que incluye el soporte para enlace_proveedor que revisamos hace un momento.

He actualizado el archivo Rutas de Órdenes en el Canvas con el código limpio y consolidado para que lo copies sin duplicados.

He actualizado el código en el Canvas para que tengas las dos funciones necesarias sin repeticiones. Una vez que borres la función duplicada de tu archivo app.py, el error desaparecerá al reiniciar Gunicorn.

Tú dijiste
ya vi el error, elimine la ruta editar_orden y agregue esa de nuevo por accidente, pudieras darme la ruta que falta

Gemini dijo
Entiendo perfectamente, es un error muy común al copiar y pegar bloques grandes de código. El error de AssertionError persistía porque seguías teniendo dos funciones con el mismo nombre, y al intentar borrar una, terminaste eliminando la que sí necesitabas.

He preparado el bloque de código para Canvas con las dos rutas (nueva_orden_manual y editar_orden) correctamente identificadas para que puedas reemplazar ese sector de tu archivo app.py y todo vuelva a la normalidad.

Con este código en Canvas tienes ambas funciones listas. Solo asegúrate de borrar las duplicadas en tu app.py antes de pegar estas para evitar que Gunicorn vuelva a lanzar el error de mapeo de funciones.

Tú dijiste
tuve este error, donde nos falta agregar?

Gemini dijo
El error invalid keyword argument indica que el modelo OrdenCompraDetalle en tu archivo app.py todavía no tiene definida la columna enlace_proveedor. Al intentar crear un objeto con ese parámetro, Python no lo reconoce y lanza el error.

Para solucionarlo, debemos realizar dos pasos:

En el código: Agregar la columna enlace_proveedor a la clase OrdenCompraDetalle.

En la base de datos: Ejecutar un comando para crear físicamente esa columna (similar a lo que hicimos con la tabla de productos).

He actualizado el Canvas para incluir la definición correcta del modelo y las rutas ajustadas.

Pasos finales para corregir el error:
Actualiza el código: Copia el contenido del Canvas a tu archivo app.py. Asegúrate de que la clase OrdenCompraDetalle ahora incluya la línea enlace_proveedor.

Actualiza la base de datos: Reinicia tu servidor y entra en tu navegador a la dirección: http://tu-dominio.com/fix_db_detalle (estando logueado como administrador).

Limpia: Una vez que veas el mensaje de éxito en el navegador, puedes borrar la ruta temporal /fix_db_detalle de tu código.

Con esto, el error de "invalid keyword argument" desaparecerá porque Python ya sabrá que ese campo existe en el modelo.

Tú dijiste
genial, ya funciono, ahora modernicemos el ordenes.html, aprovechando la actualizacion, podemos agregar una funcion en los filtros para poder ocultar las ordenes canceladas, te paso el codigo actual:{% extends 'base.html' %}



{% block title %}Órdenes de Compra{% endblock %}



{% block content %}

    <!-- ENCABEZADO -->

    <div class="d-flex justify-content-between align-items-center mb-4">

        <div>

            <h2><i class="bi bi-cart-check-fill"></i> Historial de Compras</h2>

            <p class="text-muted mb-0">Gestión de aprovisionamiento y recepción de mercancía.</p>

        </div>

        <a href="{{ url_for('nueva_orden_manual') }}" class="btn btn-primary shadow-sm">

            <i class="bi bi-plus-lg"></i> Crear OC Manual

        </a>

    </div>



    <!-- SECCIÓN DE FILTROS -->

    <div class="card bg-light mb-4 shadow-sm border-0">

        <div class="card-body py-3">

            <form method="GET" action="{{ url_for('lista_ordenes') }}" class="row g-2 align-items-end">

                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

                

                <div class="col-md-3">

                    <label for="mes" class="form-label fw-bold small text-muted">Mes</label>

                    <select id="mes" name="mes" class="form-select form-select-sm">

                        {% for num, nombre in meses_lista %}

                            <option value="{{ num }}" {% if num == mes_seleccionado %}selected{% endif %}>

                                {{ nombre }}

                            </option>

                        {% endfor %}

                    </select>

                </div>

                

                <div class="col-md-2">

                    <label for="ano" class="form-label fw-bold small text-muted">Año</label>

                    <input type="number" id="ano" name="ano" class="form-control form-control-sm" 

                           value="{{ ano_seleccionado }}" min="2020" max="2050">

                </div>

                

                <div class="col-md-4">

                    <label for="proveedor_id" class="form-label fw-bold small text-muted">Proveedor</label>

                    <select id="proveedor_id" name="proveedor_id" class="form-select form-select-sm">

                        <option value="0">-- Todos --</option>

                        {% for prov in proveedores %}

                            <option value="{{ prov.id }}" {% if prov.id == prov_seleccionado %}selected{% endif %}>

                                {{ prov.nombre }}

                            </option>

                        {% endfor %}

                    </select>

                </div>

                

                <div class="col-md-3 d-grid">

                    <button type="submit" class="btn btn-secondary btn-sm">

                        <i class="bi bi-filter"></i> Filtrar

                    </button>

                </div>

            </form>

        </div>

    </div>



    <!-- GRID DE TARJETAS (VARIABLES VERIFICADAS) -->

    <div class="row row-cols-1 row-cols-md-2 row-cols-xl-3 g-4">

        {% for orden in ordenes %}

            

            <!-- Lógica de estilos idéntica a tu código original pero adaptada a tarjetas -->

            {% set border_class = 'border-warning' %}

            {% set header_class = 'bg-warning text-dark' %}

            {% set badge_class = 'bg-white text-warning' %}

            {% set icon_state = 'bi-pencil-square' %}



            {% if orden.estado == 'recibida' %}

                {% set border_class = 'border-success' %}

                {% set header_class = 'bg-success text-white' %}

                {% set badge_class = 'bg-light text-success' %}

                {% set icon_state = 'bi-check-circle-fill' %}

            {% elif orden.estado == 'enviada' %}

                {% set border_class = 'border-info' %}

                {% set header_class = 'bg-info text-dark' %}

                {% set badge_class = 'bg-light text-info' %}

                {% set icon_state = 'bi-truck' %}

            {% elif orden.estado == 'cancelada' %}

                {% set border_class = 'border-secondary' %}

                {% set header_class = 'bg-secondary text-white' %}

                {% set badge_class = 'bg-light text-dark' %}

                {% set icon_state = 'bi-x-circle-fill' %}

            {% endif %}



            <div class="col">

                <div class="card h-100 shadow-sm {{ border_class }}">

                    

                    <!-- ENCABEZADO -->

                    <div class="card-header {{ header_class }} d-flex justify-content-between align-items-center">

                        <div>

                            <h5 class="card-title mb-0 fw-bold fs-6">OC #{{ orden.id }}</h5>

                            <small class="opacity-75">{{ orden.fecha_creacion.strftime('%d/%m/%Y') }}</small>

                        </div>

                        <span class="badge {{ badge_class }} border opacity-90">

                            <i class="{{ icon_state }}"></i> {{ orden.estado.capitalize() }}

                        </span>

                    </div>



                    <!-- CUERPO -->

                    <div class="card-body">

                        <!-- Proveedor y Creador -->

                        <div class="mb-3">

                            <h6 class="text-dark fw-bold mb-1">

                                <i class="bi bi-building"></i> {{ orden.proveedor.nombre }}

                            </h6>

                            <small class="text-muted d-block">

                                <i class="bi bi-person"></i> Creado por: {{ orden.creador.username }}

                            </small>

                            

                            <!-- Verificación de variable cancelado_por -->

                            {% if orden.estado == 'cancelada' and orden.cancelado_por %}

                                <small class="text-danger d-block">

                                    <i class="bi bi-person-x"></i> Cancelado por: {{ orden.cancelado_por.username }}

                                </small>

                            {% endif %}

                        </div>



                        <!-- Resumen de Items (Iterando sobre orden.detalles) -->

                        <div class="bg-light border rounded p-2 small mb-3">

                            <div class="d-flex justify-content-between border-bottom pb-1 mb-1">

                                <strong class="text-muted">Items</strong>

                                <span class="badge bg-white text-dark border">{{ orden.detalles|length }}</span>

                            </div>

                            <ul class="list-unstyled mb-0 text-muted">

                                {% for detalle in orden.detalles %}

                                    {% if loop.index <= 3 %}

                                    <li class="d-flex justify-content-between py-1 border-bottom border-light">

                                        <span class="text-truncate" style="max-width: 140px;">

                                            <!-- Variable correcta: detalle.producto.nombre -->

                                            {{ detalle.producto.nombre }}

                                        </span>

                                        <!-- Variable correcta: detalle.cantidad_solicitada -->

                                        <span class="fw-bold text-dark">x{{ detalle.cantidad_solicitada }}</span>

                                    </li>

                                    {% endif %}

                                {% endfor %}

                                

                                {% if (orden.detalles|length) > 3 %}

                                    <li class="text-center fst-italic pt-1 text-muted" style="font-size: 0.7rem;">

                                        + {{ (orden.detalles|length) - 3 }} items más...

                                    </li>

                                {% endif %}

                            </ul>

                        </div>



                        <!-- Total -->

                        <div class="text-center">

                            <small class="text-uppercase text-muted" style="font-size: 0.7rem;">Total Estimado</small>

                            <!-- Variable correcta: orden.costo_total -->

                            <div class="fs-4 fw-bold text-dark">${{ "{:,.2f}".format(orden.costo_total) }}</div>

                        </div>

                    </div>



                    <!-- PIE: ACCIONES -->

                    <div class="card-footer bg-white py-2">

                        <div class="d-grid gap-2">

                            

                            <!-- Acciones según Estado (Lógica idéntica al original) -->

                            {% if orden.estado != 'recibida' and orden.estado != 'enviada' and orden.estado != 'cancelada' %}

                                <!-- ESTADO: BORRADOR (El 'else' del original) -->

                                <div class="btn-group w-100">

                                    <a href="{{ url_for('editar_orden', id=orden.id) }}" class="btn btn-outline-warning btn-sm fw-bold text-dark">

                                        <i class="bi bi-pencil"></i> Editar

                                    </a>

                                    <form action="{{ url_for('enviar_orden', id=orden.id) }}" method="POST" class="btn-group">

                                        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

                                        <button type="submit" class="btn btn-info btn-sm fw-bold text-dark">

                                            <i class="bi bi-send"></i> Enviar

                                        </button>

                                    </form>

                                    <form action="{{ url_for('cancelar_orden', id=orden.id) }}" method="POST" class="btn-group" 

                                          onsubmit="return confirm('¿Estás seguro de que deseas cancelar esta orden?');">

                                        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

                                        <button type="submit" class="btn btn-secondary btn-sm" title="Cancelar">

                                            <i class="bi bi-x-lg"></i>

                                        </button>

                                    </form>

                                </div>



                            {% elif orden.estado == 'enviada' %}

                                <!-- ESTADO: ENVIADA (Aquí estaba el problema backend antes) -->

                                <!-- El action debe ser exactamente este: -->

                                <form action="{{ url_for('recibir_orden', id=orden.id) }}" method="POST" class="d-grid"

                                      onsubmit="return confirm('¿Confirmas que la mercancía ha llegado físicamente al almacén?');">

                                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

                                    <button type="submit" class="btn btn-success btn-sm fw-bold shadow-sm">

                                        <i class="bi bi-box-seam"></i> Marcar como "Recibida"

                                    </button>

                                </form>



                            {% elif orden.estado == 'recibida' %}

                                <!-- ESTADO: RECIBIDA -->

                                <div class="text-center text-success small py-1 border border-success rounded bg-light">

                                    <i class="bi bi-calendar-check"></i> Recibida el {{ orden.fecha_recepcion.strftime('%d/%m/%Y') }}

                                </div>

                            {% endif %}



                            <!-- Botones Comunes -->

                            <div class="d-flex justify-content-between mt-2 pt-2 border-top">

                                <a href="{{ url_for('ver_orden', id=orden.id) }}" class="btn btn-link btn-sm text-secondary ps-0 text-decoration-none">

                                    <i class="bi bi-eye"></i> Ver Detalle

                                </a>

                                <a href="{{ url_for('generar_oc_pdf', id=orden.id) }}" class="btn btn-link btn-sm text-danger pe-0 text-decoration-none" target="_blank">

                                    <i class="bi bi-file-earmark-pdf"></i> PDF

                                </a>

                            </div>



                        </div>

                    </div>

                </div>

            </div>



        {% else %}

            <!-- MENSAJE VACÍO -->

            <div class="col-12 text-center py-5">

                <i class="bi bi-cart-x text-muted opacity-25" style="font-size: 5rem;"></i>

                <h5 class="mt-3 text-muted">No se encontraron Órdenes de Compra.</h5>

                <p class="text-muted small">Intenta cambiando los filtros o crea una nueva.</p>

                <a href="{{ url_for('nueva_orden_manual') }}" class="btn btn-primary mt-2">

                    Crear Primera OC

                </a>

            </div>

        {% endfor %}

    </div>

{% endblock %}

Gemini dijo
¡Excelente idea! Modernizar el historial de órdenes le dará mucha más claridad al flujo de trabajo. He rediseñado el archivo ordenes.html para que coincida con la estética de "Tarjeta Moderna" que estamos usando, con soporte total para modo oscuro y, lo más importante, he añadido el interruptor inteligente para ocultar las órdenes canceladas al instante sin recargar la página.

Aquí tienes el código completo para actualizar tu archivo:
Listado de Órdenes de Compra
17 mar, 7:00 p.m.

Mejoras implementadas:
Interruptor Inteligente: Añadí un switch en la barra de filtros. Lo mejor es que usa JavaScript y LocalStorage, por lo que si el usuario decide ocultar las canceladas, la página recordará esa preferencia incluso después de recargar o navegar a otra sección.

Diseño de Tarjetas Moderno:

Borde Superior Temático: Cada tarjeta tiene una línea de color en la parte superior que identifica visualmente el estado (Borrador, Enviada, Recibida, Cancelada).

Efecto Elevación: Las tarjetas se elevan ligeramente (hover) para dar profundidad.

Resumen Compacto: Se muestran los primeros 3 productos de forma elegante dentro de la tarjeta.

Soporte Modo Oscuro: He incluido las clases necesarias para que en el modo oscuro las tarjetas se vean en negro profundo con bordes sutiles, eliminando el gris claro de Bootstrap que suele verse mal en oscuridad.

Botones de Acción Consolidados: Los botones principales (Editar/Enviar/Recibir) están agrupados en bloques visuales más limpios.

Tú dijiste
ayudame con algo, ahora al ver el orden_detalle, pues tambien deberia aparecer junto con el nombre del producto, tal vez algun boton para que te lleve al enlace si es que el producto tiene un enlace asociado, aqui esta el codigo actual: {% extends 'base.html' %}



{% block title %}{{ titulo }}{% endblock %}



{% block content %}

<style>

    /* ==========================================

       ESTILOS COMPLEMENTARIOS Y BOTÓN DE TEMA

       ========================================== */

       

    /* Tablas en Modo Oscuro */

    [data-bs-theme="dark"] .table {

        color: var(--bs-body-color);

        border-color: var(--glass-border);

    }

    [data-bs-theme="dark"] .table-light th,

    [data-bs-theme="dark"] .table-light td {

        background-color: var(--card-bg) !important;

        color: #ffffff !important;

        border-bottom: 2px solid var(--glass-border) !important;

    }

    [data-bs-theme="dark"] .table-hover tbody tr:hover td {

        background-color: var(--hover-bg) !important;

        color: #ffffff;

    }

    [data-bs-theme="dark"] .table td {

        border-color: var(--glass-border) !important;

    }

    

    /* Cajas de Info (Proveedor/Almacén) */

    .info-box {

        background-color: var(--bs-body-bg);

        transition: background-color 0.3s ease, border-color 0.3s ease;

    }

    [data-bs-theme="dark"] .info-box {

        background-color: #1a1a1a !important;

        border-color: #333 !important;

    }



    /* --- ANIMACIÓN DEL BOTÓN DE TEMA (SOL / LUNA) --- */

    .theme-switch-wrapper {

        position: relative;

        width: 44px;

        height: 44px;

        border-radius: 50%;

        cursor: pointer;

        display: flex;

        align-items: center;

        justify-content: center;

        background-color: var(--card-bg);

        border: 1px solid var(--glass-border);

        transition: background-color 0.3s ease, border-color 0.3s ease, transform 0.2s ease;

        overflow: hidden;

        box-shadow: var(--card-shadow);

    }

    .theme-switch-wrapper:hover {

        transform: scale(1.08);

    }

    .theme-switch-icon {

        position: absolute;

        font-size: 1.3rem;

        transition: transform 0.6s cubic-bezier(0.68, -0.55, 0.265, 1.55), opacity 0.4s ease;

    }

    /* Estado inicial: MODO CLARO */

    .theme-switch-sun {

        color: #f59e0b; /* Amber */

        transform: translateY(0) rotate(0deg);

        opacity: 1;

    }

    .theme-switch-moon {

        color: #e2e8f0;

        transform: translateY(30px) rotate(90deg);

        opacity: 0;

    }

    

    /* Estado: MODO OSCURO */

    [data-bs-theme="dark"] .theme-switch-sun {

        transform: translateY(-30px) rotate(-90deg);

        opacity: 0;

    }

    [data-bs-theme="dark"] .theme-switch-moon {

        transform: translateY(0) rotate(0deg);

        opacity: 1;

    }

</style>



<div class="container-fluid mt-3 mb-5">



    <!-- BOTÓN DE TEMA ANIMADO (SOL/LUNA) -->

    <div class="d-flex justify-content-end mb-2">

        <div id="theme-toggle" class="theme-switch-wrapper" title="Alternar Tema Claro/Oscuro">

            <i class="bi bi-sun-fill theme-switch-icon theme-switch-sun"></i>

            <i class="bi bi-moon-stars-fill theme-switch-icon theme-switch-moon"></i>

        </div>

    </div>



    <!-- ENCABEZADO Y BOTONES DE ACCIÓN -->

    <div class="d-flex flex-column flex-xl-row justify-content-between align-items-xl-center mb-4 gap-3">

        <div>

            <h2 class="mb-1 fw-bold"><i class="bi bi-file-earmark-text-fill text-primary me-2"></i>{{ titulo }}</h2>

            <p class="text-muted mb-0">Resumen detallado y estado actual de la solicitud.</p>

        </div>

        

        <div class="d-flex flex-wrap gap-2">

            <!-- Botón PDF -->

            <a href="{{ url_for('generar_oc_pdf', id=orden.id) }}" class="btn btn-danger shadow-sm rounded-pill px-4 fw-bold" target="_blank">

                <i class="bi bi-file-earmark-pdf me-1"></i> Imprimir PDF

            </a>

            

            {% if orden.estado == 'borrador' %}

            <!-- Botón Editar -->

            <a href="{{ url_for('editar_orden', id=orden.id) }}" class="btn btn-warning shadow-sm rounded-pill px-4 fw-bold text-dark">

                <i class="bi bi-pencil me-1"></i> Editar OC

            </a>

            <!-- Botón Cancelar -->

            <form action="{{ url_for('cancelar_orden', id=orden.id) }}" method="POST" style="display: inline;" 

                  onsubmit="return confirm('¿Estás seguro de que deseas cancelar esta orden de compra?');">

                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

                <button type="submit" class="btn btn-outline-danger shadow-sm rounded-pill px-4 fw-bold">

                    <i class="bi bi-x-circle me-1"></i> Cancelar

                </button>

            </form>

            {% endif %}

            

            <!-- Botón Volver -->

            <a href="{{ url_for('lista_ordenes') }}" class="btn btn-outline-secondary shadow-sm rounded-pill px-4 fw-bold">

                <i class="bi bi-arrow-left me-1"></i> Volver

            </a>

        </div>

    </div>



    <!-- TARJETA PRINCIPAL DEL DETALLE -->

    <div class="card shadow-sm border-0 rounded-4">

        

        <!-- CABECERA: Estado y Creador -->

        {% set status_class = 'bg-warning text-dark' %}

        {% set status_icon = 'bi-clock-history' %}

        {% if orden.estado == 'cancelada' %}

            {% set status_class = 'bg-secondary text-white' %}

            {% set status_icon = 'bi-x-circle' %}

        {% elif orden.estado == 'recibida' %}

            {% set status_class = 'bg-success text-white' %}

            {% set status_icon = 'bi-check-circle' %}

        {% endif %}



        <div class="card-header bg-transparent pt-4 pb-3 border-bottom border-secondary border-opacity-25 d-flex flex-column flex-sm-row justify-content-between align-items-sm-center gap-2">

            <div class="d-flex align-items-center gap-3">

                <h5 class="mb-0 fw-bold text-body">Estado Actual:</h5>

                <span class="badge {{ status_class }} rounded-pill px-3 py-2 shadow-sm fs-6">

                    <i class="bi {{ status_icon }} me-1"></i> {{ orden.estado|capitalize }}

                </span>

            </div>

            <div class="text-muted fw-semibold d-flex align-items-center">

                <div class="bg-secondary bg-opacity-10 rounded-circle p-2 me-2 d-flex align-items-center justify-content-center" style="width:30px; height:30px;">

                    <i class="bi bi-person text-secondary"></i>

                </div>

                Creada por: {{ orden.creador.username }}

            </div>

        </div>

        

        <div class="card-body p-4 p-md-5">

            

            <!-- CAJAS DE INFORMACIÓN (Proveedor y Almacén) -->

            <div class="row g-4 mb-5">

                <div class="col-md-6">

                    <div class="p-4 rounded-4 border border-secondary border-opacity-25 h-100 info-box shadow-sm">

                        <h6 class="text-uppercase text-muted fw-bold small mb-2" style="letter-spacing: 1px;">

                            <i class="bi bi-building me-1 text-primary"></i> Proveedor

                        </h6>

                        <div class="fs-4 fw-bold text-body">{{ orden.proveedor.nombre }}</div>

                        {% if orden.proveedor.contacto or orden.proveedor.email %}

                            <hr class="border-secondary border-opacity-25 my-2">

                            <div class="small text-muted">

                                {% if orden.proveedor.contacto %}<i class="bi bi-person-badge me-1"></i> {{ orden.proveedor.contacto }}<br>{% endif %}

                                {% if orden.proveedor.email %}<i class="bi bi-envelope me-1"></i> {{ orden.proveedor.email }}{% endif %}

                            </div>

                        {% endif %}

                    </div>

                </div>

                

                <div class="col-md-6">

                    <div class="p-4 rounded-4 border border-secondary border-opacity-25 h-100 info-box shadow-sm">

                        <h6 class="text-uppercase text-muted fw-bold small mb-2" style="letter-spacing: 1px;">

                            <i class="bi bi-shop me-1 text-primary"></i> Almacén de Destino

                        </h6>

                        <div class="fs-4 fw-bold text-body">{{ orden.almacen.nombre }}</div>

                        {% if orden.almacen.ubicacion %}

                            <hr class="border-secondary border-opacity-25 my-2">

                            <div class="small text-muted">

                                <i class="bi bi-geo-alt me-1"></i> {{ orden.almacen.ubicacion }}

                            </div>

                        {% endif %}

                    </div>

                </div>

            </div>

            

            <!-- TABLA DE DETALLES -->

            <h5 class="fw-bold mb-3 text-body"><i class="bi bi-list-check text-primary me-2"></i>Artículos Solicitados</h5>

            

            <div class="table-responsive border border-secondary border-opacity-25 rounded-4 shadow-sm">

                <table class="table table-hover align-middle mb-0">

                    <thead class="table-light text-secondary text-uppercase small" style="letter-spacing: 0.5px;">

                        <tr>

                            <th class="ps-4 border-0">Producto</th>

                            <th class="text-center border-0">SKU</th>

                            <th class="text-center border-0">Cant. / Cajas</th>

                            <th class="text-end border-0">Costo Unit.</th>

                            <th class="text-end pe-4 border-0">Subtotal</th>

                        </tr>

                    </thead>

                    <tbody>

                        {% for detalle in orden.detalles %}

                        <tr>

                            <!-- Producto -->

                            <td class="ps-4 py-3 fw-bold text-body">{{ detalle.producto.nombre }}</td>

                            

                            <!-- SKU -->

                            <td class="text-center font-monospace text-muted small">

                                <span class="bg-secondary bg-opacity-10 px-2 py-1 rounded"><i class="bi bi-upc opacity-50 me-1"></i>{{ detalle.producto.codigo }}</span>

                            </td>

                            

                            <!-- Cantidad y Cajas -->

                            <td class="text-center">

                                <span class="fw-bold fs-6">{{ detalle.cantidad_solicitada }}</span>

                                {% if detalle.cajas and detalle.cajas > 0 %}

                                    <span class="badge bg-info text-dark ms-2 shadow-sm" style="font-size: 0.7rem;" title="Cajas Aproximadas">

                                        <i class="bi bi-box-seam me-1"></i> {{ detalle.cajas|round(2, 'floor') }}

                                    </span>

                                {% endif %}

                            </td>

                            

                            <!-- Costo Unitario -->

                            <td class="text-end text-muted">

                                ${{ "{:,.2f}".format(detalle.costo_unitario_estimado) }}

                            </td>

                            

                            <!-- Subtotal -->

                            <td class="text-end pe-4 fw-bold text-body">

                                ${{ "{:,.2f}".format(detalle.subtotal) }}

                            </td>

                        </tr>

                        {% endfor %}

                    </tbody>

                    

                    <!-- PIE DE TABLA CON TOTAL -->

                    <tfoot class="table-light border-top border-secondary border-opacity-25">

                        <tr>

                            <td colspan="4" class="text-end py-3 fw-bold text-uppercase text-muted small" style="letter-spacing: 1px;">

                                Total Estimado:

                            </td>

                            <td class="text-end pe-4 py-3 fs-4 fw-bold text-success">

                                ${{ "{:,.2f}".format(orden.costo_total) }}

                            </td>

                        </tr>

                    </tfoot>

                </table>

            </div>



        </div>

    </div>

</div>



<!-- SCRIPT DEL TEMA OSCURO/CLARO -->

<script>

    const themeToggleBtn = document.getElementById('theme-toggle');

    const htmlElement = document.documentElement;



    function applyTheme(theme) {

        htmlElement.setAttribute('data-bs-theme', theme);

        localStorage.setItem('app_theme', theme);

    }



    // Inicializar Tema (Cargar desde memoria o establecer Dark por defecto)

    const savedTheme = localStorage.getItem('app_theme') || 'dark';

    applyTheme(savedTheme);



    // Evento del Botón

    if(themeToggleBtn) {

        themeToggleBtn.addEventListener('click', () => {

            const currentTheme = htmlElement.getAttribute('data-bs-theme');

            applyTheme(currentTheme === 'dark' ? 'light' : 'dark');

        });

    }

</script>

{% endblock %}

Gemini dijo
¡Excelente iniciativa! Es muy útil tener el enlace directo al producto mientras se revisa el detalle de la orden, especialmente para confirmar especificaciones o precios en tiempo real.

He actualizado el archivo Canvas (que corresponde a tu vista de detalle de orden) para que la columna de producto ahora incluya un botón elegante y discreto que solo aparece si el registro tiene un enlace guardado.

He modificado la columna de Producto para que ahora contenga tanto el nombre como el botón de enlace (si existe). El botón tiene una animación sutil al pasar el mouse para que sea intuitivo pero no distraiga del resto de la información.

Tú dijiste
veo que el ordenes.html no esta respondiendo bien al sistema de claro y oscuro, te adjunto una imagen para que lo veas

Gemini dijo
Entiendo perfectamente el problema. En la imagen se observa que algunos contenedores (como el de "Artículos") mantienen un fondo blanco brillante (#ffffff) que rompe totalmente la estética del modo oscuro, dificultando la lectura de los textos claros.

Voy a corregir el archivo Canvas de templates/ordenes.html ajustando las clases de utilidad de Bootstrap y añadiendo reglas específicas para que los fondos se adapten dinámicamente al tema seleccionado, asegurando que el contraste sea perfecto en ambos modos.

He realizado los siguientes ajustes para solucionar lo que se ve en la imagen:

Fondos Dinámicos: He forzado que las clases .bg-light y .bg-white se conviertan en tonos oscuros semitransparentes cuando el tema dark esté activo. Esto eliminará esos "parches blancos" en las tarjetas de las órdenes.

Contraste de Texto: Se han revisado las clases text-body y text-dark para asegurar que el texto sea blanco o gris claro en el modo oscuro.

Barra de Filtros: Ahora los campos de selección y el interruptor de "Ocultar Canceladas" tienen un fondo oscuro coherente con el resto de la aplicación.

Resumen de Artículos: El cuadro de la lista de productos dentro de la tarjeta ahora tiene un fondo translúcido muy elegante que permite leer el SKU y el nombre sin problemas de contraste.

Con estos cambios, la visualización debería ser idéntica a la del Dashboard o el Detalle de Orden, respetando la estética "Pure Black".

Tú dijiste
antes de continuar con lo demas, me gustaria que modifiquemos la funcion de generar_oc_pdf, para que ahora tambien dentro del mismo cuadro abajo se pueda acceder al enlace del producto, tal vez debajo del nombre, en pequeño o algo asi, aqui esta el codigo actual de la ruta: @app.route('/orden/<int:id>/pdf')

@login_required

@check_permission('perm_create_oc_standard')

def generar_oc_pdf(id):

    orden = OrdenCompra.query.filter_by(

        id=id, 

        organizacion_id=current_user.organizacion_id

    ).first_or_404()

    org = orden.organizacion

    proveedor = orden.proveedor

    

    # --- CONFIGURACIÓN DE PÁGINA ---

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(buffer, pagesize=A4, 

                            rightMargin=inch, leftMargin=inch,

                            topMargin=0.5*inch, bottomMargin=inch)

    story = []

    styles = getSampleStyleSheet()

    

    # --- ESTILOS ---

    fuente_base = org.tipo_letra if org.tipo_letra in ['Helvetica', 'Times-Roman', 'Courier'] else 'Helvetica'

    color_primario = colors.HexColor(org.color_primario) if org.color_primario else colors.darkblue

    

    # Estilos de Texto

    style_brand_title = ParagraphStyle(name='BrandTitle', parent=styles['Heading1'], fontName=f'{fuente_base}-Bold', fontSize=20, leading=22, textColor=colors.black, spaceAfter=2)

    style_brand_sub = ParagraphStyle(name='BrandSub', parent=styles['Normal'], fontName=fuente_base, fontSize=10, leading=12, textColor=colors.gray)

    style_normal = ParagraphStyle(name='MiNormal', parent=styles['Normal'], fontName=fuente_base, fontSize=10, leading=12)

    style_bold = ParagraphStyle(name='MiBold', parent=styles['Normal'], fontName=f'{fuente_base}-Bold', fontSize=10, leading=12)

    style_th = ParagraphStyle(name='MiTH', parent=styles['Normal'], fontName=f'{fuente_base}-Bold', fontSize=10, textColor=colors.white, alignment=TA_CENTER)

    

    # Estilos para Total

    style_total_label = ParagraphStyle(name='TotalLabel', parent=styles['Normal'], fontName=f'{fuente_base}-Bold', fontSize=11, alignment=TA_RIGHT)

    style_total_value = ParagraphStyle(name='TotalValue', parent=styles['Normal'], fontName=f'{fuente_base}-Bold', fontSize=11, alignment=TA_RIGHT)



    # ==========================================

    # 1. ENCABEZADO PERSONALIZADO (Logo + Texto)

    # ==========================================

    logo_element = []

    if org.logo_url:

        logo_path = os.path.join(app.config['UPLOAD_FOLDER'], org.logo_url)

        if os.path.exists(logo_path):

            img = ReportLabImage(logo_path)

            max_h = 1.0 * inch

            aspect = img.imageWidth / float(img.imageHeight)

            img.drawHeight = max_h

            img.drawWidth = max_h * aspect

            logo_element.append(img)

    

    text_elements = []

    texto_p = org.header_titulo if org.header_titulo else org.nombre

    text_elements.append(Paragraph(texto_p, style_brand_title))

    if org.header_subtitulo:

        text_elements.append(Paragraph(org.header_subtitulo, style_brand_sub))



    if logo_element:

        data_header = [[logo_element, text_elements]]

        col_widths = [1.5*inch, 4.5*inch]

    else:

        data_header = [[text_elements]]

        col_widths = [6*inch]



    t_header = Table(data_header, colWidths=col_widths)

    t_header.setStyle(TableStyle([

        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),

        ('LEFTPADDING', (0,0), (-1,-1), 0),

        ('BOTTOMPADDING', (0,0), (-1,-1), 10),

    ]))

    story.append(t_header)

    

    # Barra separadora de color

    story.append(Table([['']], colWidths=[6.2*inch], rowHeights=[2], style=TableStyle([

        ('BACKGROUND', (0,0), (-1,-1), color_primario)

    ])))

    story.append(Spacer(1, 0.2*inch))



    # ==========================================

    # 2. INFORMACIÓN (PROVEEDOR Y ORDEN)

    # ==========================================

    

    # Intento seguro de obtener datos de contacto

    p_email = getattr(proveedor, 'email', getattr(proveedor, 'correo', getattr(proveedor, 'contacto_email', '-')))

    p_tel = getattr(proveedor, 'telefono', getattr(proveedor, 'celular', '-'))

    p_contacto = getattr(proveedor, 'contacto', getattr(proveedor, 'nombre_contacto', '-'))



    info_proveedor = [

        Paragraph("<b>PROVEEDOR:</b>", style_normal),

        Paragraph(f"{proveedor.nombre}", style_bold),

        Paragraph(f"Contacto: {p_contacto}", style_normal),

        Paragraph(f"Email: {p_email}", style_normal),

        Paragraph(f"Tel: {p_tel}", style_normal),

    ]



    info_orden = [

        Paragraph(f"<b>ORDEN DE COMPRA #{orden.id}</b>", style_brand_title),

        Paragraph(f"<b>Fecha:</b> {orden.fecha_creacion.strftime('%d/%m/%Y')}", style_normal),

        Paragraph(f"<b>Estado:</b> {orden.estado}", style_normal),

        Paragraph(f"<b>Almacén:</b> {orden.almacen.nombre if orden.almacen else 'General'}", style_normal),

    ]



    t_info = Table([[info_proveedor, info_orden]], colWidths=[3.5*inch, 2.7*inch])

    t_info.setStyle(TableStyle([

        ('VALIGN', (0,0), (-1,-1), 'TOP'),

        ('LEFTPADDING', (0,0), (-1,-1), 0),

    ]))

    story.append(t_info)

    story.append(Spacer(1, 0.2*inch))



    # ==========================================

    # 3. TABLA DE PRODUCTOS (ACTUALIZADA CON CAJAS)

    # ==========================================

    

    headers = [

        Paragraph("Producto / SKU", style_th),

        Paragraph("Cajas", style_th),

        Paragraph("Unidades", style_th),

        Paragraph("Costo U.", style_th),

        Paragraph("Subtotal", style_th)

    ]

    

    data_table = [headers]

    total_general = 0

    

    for detalle in orden.detalles:

        subtotal = detalle.cantidad_solicitada * detalle.costo_unitario_estimado

        total_general += subtotal

        

        # Extraemos las cajas y factor de empaque de forma segura

        factor_empaque = getattr(detalle.producto, 'unidades_por_caja', 1) or 1

        cajas = getattr(detalle, 'cajas', 0)

        cajas_str = f"{cajas:g}" if cajas else "0"

        

        # Descripción con salto de línea para SKU y Factor

        desc = f"<b>{detalle.producto.nombre}</b><br/>SKU: {detalle.producto.codigo}<br/><font color='gray'>Empaque: {factor_empaque} ud(s)</font>"

        

        row = [

            Paragraph(desc, style_normal),

            Paragraph(cajas_str, style_normal),

            Paragraph(str(detalle.cantidad_solicitada), style_normal),

            Paragraph(f"${detalle.costo_unitario_estimado:,.2f}", style_normal),

            Paragraph(f"${subtotal:,.2f}", style_normal)

        ]

        data_table.append(row)



    # --- FILA DE TOTAL (INTEGRADA Y ADAPTADA) ---

    row_total = [

        '', # 0

        '', # 1

        '', # 2

        Paragraph("TOTAL:", style_total_label), # 3

        Paragraph(f"${total_general:,.2f}", style_total_value) # 4

    ]

    data_table.append(row_total)



    # Configuración de Anchos (Ajustado para 5 columnas, Total = 6.2 inches)

    col_widths_prod = [2.4*inch, 0.8*inch, 0.8*inch, 1.0*inch, 1.2*inch]

    

    t_productos = Table(data_table, colWidths=col_widths_prod, repeatRows=1)

    

    # ESTILOS COMPLETOS (Bordes, Colores y Fusión)

    estilos = [

        # Encabezado

        ('BACKGROUND', (0,0), (-1,0), color_primario),

        ('TEXTCOLOR', (0,0), (-1,0), colors.white),

        ('ALIGN', (0,0), (-1,0), 'CENTER'),

        ('VALIGN', (0,0), (-1,0), 'MIDDLE'),

        

        # Cuerpo (Rejilla completa)

        ('GRID', (0,0), (-1,-2), 0.5, colors.black), 

        ('ALIGN', (1,1), (2,-2), 'CENTER'), # Centrar Cajas y Unidades

        ('ALIGN', (3,1), (-1,-1), 'RIGHT'),  # Precios a la derecha

        ('VALIGN', (0,1), (-1,-1), 'MIDDLE'),

        ('TOPPADDING', (0,0), (-1,-1), 6),

        ('BOTTOMPADDING', (0,0), (-1,-1), 6),

        

        # Fila de Total (Última fila adaptada a las nuevas columnas)

        ('SPAN', (0,-1), (2,-1)),            # Fusionar columnas 0, 1 y 2

        ('LINEABOVE', (0,-1), (-1,-1), 1, colors.black), # Línea superior gruesa

        ('BACKGROUND', (3,-1), (-1,-1), colors.whitesmoke), # Fondo gris tenue en total

        ('BOX', (3,-1), (4,-1), 0.5, colors.black), # Caja alrededor del total y etiqueta

    ]

    

    t_productos.setStyle(TableStyle(estilos))

    story.append(t_productos)



    # --- GENERAR ---

    doc.build(story)

    buffer.seek(0)

    filename = f"OC_{orden.id}_{secure_filename(org.nombre)}.pdf"

    return send_file(buffer, as_attachment=False, download_name=filename, mimetype='application/pdf')

Gemini dijo
Claro, entiendo perfectamente. Vamos a actualizar la lógica de generación de PDF en el Canvas para que incluya el enlace del proveedor directamente en la tabla de productos. Esto permitirá que, al imprimir o compartir el documento, se tenga una referencia rápida al origen del artículo.

He preparado la función actualizada para tu archivo app.py, integrando el enlace con un tamaño de fuente reducido y un color azul para que sea fácilmente identificable pero no sobrecargue visualmente la tabla.

He actualizado la función para que busque el enlace tanto en el detalle de la orden (que es donde lo guardamos al crearla) como en el catálogo de productos (como respaldo). Ahora el PDF mostrará la URL en un tamaño pequeño (size='7') y color azul debajo del SKU de cada producto.

¿Te gustaría que hagamos algún otro ajuste en el formato del PDF o continuamos con los demás módulos?

Tú dijiste
acabo de ver que en el ordenes.html no esta el boton para cambiar entre oscuro y claro

Gemini dijo
Claro, tienes razón. He actualizado el archivo Canvas agregando el botón animado de Sol/Luna en la parte superior derecha de la vista de órdenes, manteniendo la misma estética y funcionalidad que en el resto de la aplicación.

He añadido el bloque de Botón de Tema Animado y su correspondiente lógica de JavaScript al final del archivo. También incluí los estilos necesarios para que el icono de Sol/Luna funcione con las animaciones de transición que ya utilizas en otras partes del sistema.

Tú dijiste
ahora vayamos al proyecto_oc_form, aqui ademas de modernizar la imagen quisiera que mejoraramos el sistema de busqueda, que aparezca el buscador para los productos como en las OC normales, usa ese estilo de sistema de busqueda, pero agrega abajo para agregar manualmente si es necesario, ademas de agregar 2 campos, enlace y ademas un cuadro de texto donde se pueda poner comentarios o detalles de porque se solicita cada articulo, claro eso es opcional

Gemini dijo
Entendido, vamos a transformar el formulario de Órdenes de Compra para Proyectos (proyecto_oc_form.html). Aplicaremos el diseño moderno de tarjetas que hemos estado usando, integraremos el buscador "tipo buscador de almacén" con sugerencias inteligentes y añadiremos los campos de enlace y comentarios por artículo.

También incluiré la lógica para permitir la entrada manual de artículos que no estén en el catálogo, lo cual es muy común en compras de proyectos específicos.
Formulario de OC Proyecto
17 mar, 7:28 p.m.

Mejoras principales en el Canvas:
Buscador Inteligente: He implementado un sistema idéntico al que usamos en el inventario del almacén. Puedes buscar por nombre o SKU y, al seleccionar, la fila se bloquea para evitar errores (a menos que sea manual).

Agregar Manual: Hay un botón prominente para añadir artículos que no existen en el sistema. Estos se marcan con un borde gris para diferenciarlos de los artículos de inventario (que van en azul).

Sistema de "Detalles" Desplegable: Para mantener el formulario limpio, los campos de Enlace y Comentarios están ocultos bajo el botón "Detalles" en cada fila. Al hacer clic, se expande la tarjeta del artículo revelando esos campos.

Soporte Modo Oscuro Completo: He corregido las clases de fondo y texto para que se vea perfecto en el estilo "Pure Black".

Calculadora en Tiempo Real: El total de la orden se actualiza instantáneamente mientras cambias cantidades o costos.

Efectos Visuales: Las filas nuevas aparecen con una pequeña animación de deslizamiento para que el usuario sepa dónde se agregó el artículo.

Tú dijiste
veo algunos detalles, como esto es de proyecto, no va a un almacen y ademas al querer buscar algun producto aunque escriba el nombre no aparece nada y al presionar el boton de agregar manualmente no hace nada

Gemini dijo
Entiendo perfectamente los puntos que mencionas. He realizado los ajustes en el Canvas para eliminar la dependencia de almacenes (ya que es para proyectos), corregir la lógica del buscador para que filtre correctamente y asegurar que el botón de carga manual funcione al instante.

He reorganizado el script para que las funciones estén disponibles desde el primer momento y he simplificado el acceso a los datos del catálogo.

Cambios realizados en el Canvas:
Eliminación de Almacenes: He quitado la sección de selección de almacén, ya que indicas que las OC de proyectos no van destinadas a stock de almacén físico. He añadido una nota informativa en su lugar.

Lógica del Buscador Corregida: He reescrito la función de búsqueda para asegurar que filtre correctamente el array productosBase. También corregí el mapeo de campos (usando p.precio_unitario o p.costo según disponibilidad).

Botón de Agregar Manual: He corregido la referencia al botón y la función de clonación del template. Ahora, al presionar el botón, se genera una fila vacía con el foco puesto directamente en el nombre para que empieces a escribir.

Estructura de Scripts: He movido las funciones críticas fuera de bloques condicionales para asegurar que siempre estén disponibles en el DOM.

UI de Detalles: Los botones de "Eliminar" y "Detalles" ahora tienen sus eventos vinculados correctamente dentro de la función de creación de filas.

¿Necesitas que ajuste algún campo adicional para la lógica de los proyectos?

Tú dijiste
creo que si faltan esos campos, solo el del almacen no deberia ser obligatorio, ya que no es necesario

Gemini dijo
Entiendo perfectamente los errores. El problema principal es que el sistema está intentando guardar los campos de enlace y comentarios en el modelo de la base de datos, pero esas columnas aún no existen en la tabla de detalles de la orden. Además, falta el campo obligatorio para el Nombre del Proyecto y, como bien mencionas, el almacén no debe ser requerido en este flujo.

Voy a actualizar el Canvas para incluir el campo del proyecto y eliminar la obligatoriedad del almacén. También te proporcionaré el código necesario para actualizar tu base de datos y el modelo en app.py.

1. Actualización del Formulario en el Canvas
He añadido el campo Nombre del Proyecto en la columna izquierda y eliminado la selección de almacén para que el formulario sea más ágil y específico para proyectos externos.

2. Cómo solucionar el error en el Backend (app.py)
El error invalid keyword argument indica que el modelo no conoce los campos. Debes hacer lo siguiente:

A. Actualiza el modelo OrdenCompraDetalle en app.py:
Busca la clase OrdenCompraDetalle y añade estas dos líneas:

Python
class OrdenCompraDetalle(db.Model):
    # ... tus otros campos (id, orden_id, producto_id, etc.) ...
    
    # AÑADE ESTAS DOS LÍNEAS:
    enlace_proveedor = db.Column(db.String(500), nullable=True)
    comentarios = db.Column(db.Text, nullable=True)

**B. Añade las columnas a la base de datos de forma rápida:**
Puedes pegar esta ruta temporal en tu `app.py`, ejecutarla una vez en el navegador y luego borrarla:
```python
@app.route('/fix_oc_columns')
def fix_oc_columns():
    from sqlalchemy import text
    try:
        db.session.execute(text("ALTER TABLE orden_compra_detalle ADD COLUMN enlace_proveedor VARCHAR(500);"))
        db.session.execute(text("ALTER TABLE orden_compra_detalle ADD COLUMN comentarios TEXT;"))
        db.session.commit()
        return "Columnas añadidas con éxito."
    except Exception as e:
        db.session.rollback()
        return f"Error o aviso: {str(e)}"

**C. Actualiza la lógica de guardado en la ruta de Proyectos:**
Asegúrate de que en la función donde procesas el `POST` de la orden de proyecto, los nombres coincidan:
```python
# Dentro de tu ruta de guardado (POST):
enlaces = request.form.getlist('enlace[]')
comentarios_lista = request.form.getlist('comentarios[]')

# Al crear el detalle en el loop:
detalle = OrdenCompraDetalle(
    orden_id=nueva_orden.id,
    producto_id=productos_ids[i],
    cantidad_solicitada=float(cantidades[i]),
    costo_unitario_estimado=float(costos[i]),
    enlace_proveedor=enlaces[i] if i < len(enlaces) else None, # <- Ahora sí funcionará
    comentarios=comentarios_lista[i] if i < len(comentarios_lista) else None
)

Con estos cambios, el formulario dejará de dar error y podrás guardar el **Nombre del Proyecto** sin necesidad de seleccionar un almacén. ¿Te gustaría que revisáramos algo más?
Tú dijiste
sigo teniendo el mismo problema

Gemini dijo
Entiendo perfectamente. Los errores que me muestras en las imágenes confirman dos cosas críticas:

Error de Base de Datos: El mensaje 'enlace_proveedor' is an invalid keyword argument significa que tu modelo OrdenCompraDetalle en el archivo app.py no tiene definida esa columna, o el nombre no coincide exactamente.

Error de Validación: El mensaje El nombre del proyecto y el almacén son obligatorios es una validación manual en tu ruta de Flask que está bloqueando el guardado porque no enviamos un almacen_id.

Para solucionar esto, he actualizado el Canvas ajustando los nombres de los campos para que sean más descriptivos y he añadido una sección para el Almacén (marcada como opcional visualmente) para que no rompa tu lógica actual de validación, mientras ajustas el código de Python.

Aquí tienes el código completo y corregido para el formulario:

Pasos Críticos para que funcione (Python):
Para resolver el error de la imagen, debes aplicar estos cambios en tu archivo app.py, de lo contrario, el formulario seguirá fallando al intentar guardar:

Arreglar el error invalid keyword argument:
En la clase OrdenCompraDetalle de tu app.py, debes asegurarte de que el nombre de la columna sea exactamente igual al que usas en el constructor. Si el error dice que enlace_proveedor no existe, es porque no lo has añadido al modelo. Añade esto a la clase:

Python
enlace_proveedor = db.Column(db.String(500), nullable=True)
comentarios_detalle = db.Column(db.Text, nullable=True)

Arreglar el error de "Almacén Obligatorio":
Busca la ruta de guardado (el @app.route del POST de proyectos) y modifica la validación. Cambia esto:

Python
if not nombre_proyecto or not almacen_id:
    flash("El nombre del proyecto y el almacén son obligatorios.", "danger")
    Por esto (para que el almacén sea opcional en el código):
```python
if not nombre_proyecto:
    flash("El nombre del proyecto es obligatorio.", "danger")

Actualizar la Base de Datos:
Si estás usando SQLite o PostgreSQL, la base de datos no sabe que añadiste esos campos. Ejecuta la ruta /actualizar_bd_enlace que te proporcioné anteriormente o usa el comando ALTER TABLE orden_compra_detalle ADD COLUMN enlace_proveedor VARCHAR(500); directamente en tu gestión de base de datos.

He modificado el Canvas para que incluya de nuevo el selector de Almacén (por si decides dejarlo obligatorio en el backend por ahora) y he ajustado los nombres de los campos de detalles para que coincidan con la lógica que tu servidor está esperando.

Tú dijiste
que debemos modificar en estas clases para que funcionen: class ProyectoOC(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    nombre_proyecto = db.Column(db.String(255), nullable=False)

    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.now)

    estado = db.Column(db.String(20), nullable=False, default='borrador')

    

    creador_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)

    

    # --- LÍNEA AÑADIDA ---

    almacen_id = db.Column(db.Integer, db.ForeignKey('almacen.id'), nullable=False)

    almacen = db.relationship('Almacen') # Para fácil acceso

    

    detalles = db.relationship('ProyectoOCDetalle', backref='proyecto_oc', lazy=True, cascade="all, delete-orphan")



    @property

    def costo_total(self):

        return sum(detalle.subtotal for detalle in self.detalles)



class ProyectoOCDetalle(db.Model):

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

        if self.producto:

            return self.producto.nombre

        else:

            return self.descripcion_nuevo
            
class ProyectoOC(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre_proyecto = db.Column(db.String(255), nullable=False)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.now)
    estado = db.Column(db.String(20), nullable=False, default='borrador')
    
    creador_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)
    
    # MODIFICADO: nullable=True para que el almacén sea opcional
    almacen_id = db.Column(db.Integer, db.ForeignKey('almacen.id'), nullable=True) 
    almacen = db.relationship('Almacen')
    
    detalles = db.relationship('ProyectoOCDetalle', backref='proyecto_oc', lazy=True, cascade="all, delete-orphan")

    @property
    def costo_total(self):
        return sum(detalle.subtotal for detalle in self.detalles)

class ProyectoOCDetalle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    proyecto_oc_id = db.Column(db.Integer, db.ForeignKey('proyecto_oc.id'), nullable=False)
    
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=True)
    producto = db.relationship('Producto')
    
    descripcion_nuevo = db.Column(db.String(255), nullable=True)
    proveedor_sugerido = db.Column(db.String(100), nullable=True)
    
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    costo_unitario = db.Column(db.Float, nullable=False, default=0.0)

    # --- NUEVOS CAMPOS AÑADIDOS ---
    enlace_proveedor = db.Column(db.String(500), nullable=True)
    comentarios_detalle = db.Column(db.Text, nullable=True)

    @property
    def subtotal(self):
        return self.cantidad * self.costo_unitario

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
    
    # --- LÍNEA AÑADIDA ---
    codigo_invitacion = StringField('Código de Invitación (Opcional)')
    
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
    old_password = PasswordField('Contraseña Actual', validators=[DataRequired()])
    password = PasswordField('Nueva Contraseña', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Nueva Contraseña', 
                                     validators=[DataRequired(), EqualTo('password', message='Las contraseñas deben coincidir.')])
    submit_password = SubmitField('Cambiar Contraseña')

class RequestResetForm(FlaskForm):
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    submit = SubmitField('Solicitar Reseteo de Contraseña')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('Nueva Contraseña', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Nueva Contraseña', 
                                     validators=[DataRequired(), EqualTo('password', message='Las contraseñas deben coincidir.')])
    submit = SubmitField('Restablecer Contraseña')

class AdminPermissionForm(FlaskForm):
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

def super_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol != 'super_admin':
            flash('Acceso denegado. Se requieren privilegios de Super Administrador.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

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

def send_async_email(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            print(f"Error enviando correo de recuperación: {str(e)}")

def send_reset_email(user):
    app_actual = current_app._get_current_object()
    
    # Usamos URLSafeTimedSerializer para generar un token directamente desde el email
    s = URLSafeTimedSerializer(app_actual.config['SECRET_KEY'])
    token = s.dumps(user.email, salt='password-reset-salt')
    
    msg = Message('Petición de Restablecimiento de Contraseña',
                  recipients=[user.email])
    
    msg.body = (
        f"Para restablecer tu contraseña, visita el siguiente enlace:\n"
        f"{url_for('reset_password', token=token, _external=True)}\n\n"
        f"Si no hiciste esta petición, simplemente ignora este correo y no habrá cambios."
    )
    
    # Lanzar el hilo (Thread)
    Thread(target=send_async_email, args=(app_actual, msg)).start()

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
        query = model.query
    else:
        query = model.query.filter_by(organizacion_id=current_user.organizacion_id)
    
    item = query.filter_by(id=item_id).first_or_404()
    return item

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
            if current_user.rol in ['super_admin', 'admin']:
                return f(*args, **kwargs)
            
            if not getattr(current_user, permission_name, False):
                flash('No tienes permiso para acceder a esta función.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator
  
# ==============================================================================
# 🛡️ CABECERAS DE SEGURIDAD (SECURITY HEADERS)
# ==============================================================================
@app.after_request
def add_security_headers(response):
    # 1. Prevenir Clickjacking
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    
    # 2. Prevenir MIME-sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    
    # 3. Forzar conexiones seguras HTTPS (HSTS)
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
    # 4. Política de Referencia
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    # 5. Desactivar hardware innecesario en el navegador
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=()'
    
    # 6. Content Security Policy (CSP)
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net fonts.googleapis.com; "
        "font-src 'self' data: cdn.jsdelivr.net fonts.gstatic.com; "
        "img-src 'self' data: blob: https:; "
        "connect-src 'self';"
    )
    response.headers['Content-Security-Policy'] = csp
    
    return response
# ==============================================================================
# 8. RUTAS DE LA APLICACIÓN
# ==============================================================================

# -----------------------------------------------------------------
# GESTIÓN DE USUARIOS Y CONTRASEÑAS (ADMIN)
# -----------------------------------------------------------------

@app.route('/usuarios')
@login_required
def lista_usuarios():
    """Muestra la lista de todos los usuarios registrados (Solo Admins)."""
    if current_user.rol not in ['super_admin', 'admin']:
        flash('Acceso restringido a administradores.', 'danger')
        return redirect(url_for('dashboard'))
    
    usuarios = User.query.order_by(User.username).all()
    return render_template('usuarios.html', usuarios=usuarios)

@app.route('/admin/usuario/<int:id>/reset_password', methods=['POST'])
@login_required
def admin_reset_password(id):
    """
    Acción para que un Admin fuerce el cambio de contraseña de otro usuario.
    """
    # 1. Seguridad: Solo Admins
    if current_user.rol not in ['super_admin', 'admin']:
        flash('No tienes permisos para realizar esta acción.', 'danger')
        return redirect(url_for('dashboard'))

    # 2. Buscar usuario
    usuario_objetivo = User.query.get_or_404(id)
    
    # 3. Obtener nueva contraseña del form
    nueva_password = request.form.get('new_password')
    
    if not nueva_password or len(nueva_password) < 4:
        flash('La contraseña es muy corta (mínimo 4 caracteres).', 'warning')
        return redirect(url_for('lista_usuarios'))

    try:
        # 4. Sobrescribir contraseña
        usuario_objetivo.password_hash = generate_password_hash(nueva_password)
        db.session.commit()
        
        flash(f'✅ Contraseña actualizada correctamente para: {usuario_objetivo.username}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar: {e}', 'danger')

    return redirect(url_for('lista_usuarios'))
      
# =============================================
# NUEVAS RUTAS PARA ETIQUETAS
# =============================================

@app.route('/producto/<int:id>/etiqueta/configurar')
@login_required
@check_permission('perm_view_dashboard')
def configurar_etiqueta(id):
    """ Muestra el formulario para elegir tamaño de etiqueta. """
    producto = get_item_or_404(Producto, id)
    
    # Atrapamos de qué almacén viene el usuario (por la URL)
    almacen_seleccionado = request.args.get('almacen_id', type=int)
    
    # La ubicación específica ahora se maneja dinámicamente en la plantilla HTML
    # iterando sobre producto.stocks, así que ya no necesitamos buscarla aquí.
    
    return render_template('etiqueta_config.html', 
                           producto=producto, 
                           almacen_seleccionado=almacen_seleccionado)

@app.route('/producto/<int:id>/etiqueta/generar', methods=['POST'])
@login_required
@check_permission('perm_view_dashboard')
def generar_etiqueta_personalizada(id):
    """ Genera etiqueta JPG. QR abajo-derecha para dar espacio al Nombre arriba (Full Width). """
    producto = get_item_or_404(Producto, id)
    
    # --- NUEVO: Obtener datos de ubicación específicos del almacén seleccionado ---
    almacen_id = request.form.get('almacen_id')
    ubicacion = "N/A"
    
    if almacen_id:
        stock_especifico = Stock.query.filter_by(producto_id=id, almacen_id=almacen_id).first()
        if stock_especifico and stock_especifico.ubicacion:
            ubicacion = stock_especifico.ubicacion

    tamano = request.form.get('tamano') # '1x3' o '1.75x4'
    DPI = 300 
    
    # --- CONFIGURACIÓN DE TAMAÑOS ---
    if tamano == '1.75x4':
        width_px = int(4 * DPI)
        height_px = int(1.75 * DPI)
        
        font_size_nombre = 75
        font_size_codigo = 95
        font_size_ubic = 45
        
        qr_box_size = 13
        margin = 30
        gap_text_qr = 30
        
    else: # Default 1x3
        width_px = int(3 * DPI)
        height_px = int(1 * DPI)
        
        font_size_nombre = 50
        font_size_codigo = 65
        font_size_ubic = 35
        
        # Reducimos un pelín el QR para asegurar que deje espacio arriba
        qr_box_size = 8 
        margin = 20
        gap_text_qr = 20

    # Crear lienzo
    img = Image.new('RGB', (width_px, height_px), color='white')
    d = ImageDraw.Draw(img)

    # --- CARGA DE FUENTES ---
    try:
        font_path_regular = os.path.join(app.root_path, 'static', 'fonts', 'CenturyGothic.ttf')
        font_path_bold = os.path.join(app.root_path, 'static', 'fonts', 'CenturyGothic-Bold.ttf')
        if not os.path.exists(font_path_bold): font_path_bold = "arialbd.ttf" 
        if not os.path.exists(font_path_regular): font_path_regular = "arial.ttf"
        fnt_nombre = ImageFont.truetype(font_path_regular, font_size_nombre)
        fnt_codigo = ImageFont.truetype(font_path_bold, font_size_codigo)
        fnt_ubic = ImageFont.truetype(font_path_regular, font_size_ubic)
    except IOError:
        fnt_nombre = ImageFont.load_default()
        fnt_codigo = ImageFont.load_default()
        fnt_ubic = ImageFont.load_default()

    # ==========================================
    # 1. POSICIONAR CÓDIGO QR (Abajo - Derecha)
    # ==========================================
    qr_wrapper = qrcode.make(producto.codigo, box_size=qr_box_size, border=0)
    qr_img = getattr(qr_wrapper, '_img', qr_wrapper)
    qr_w, qr_h = qr_img.size
    
    # X: Pegado a la derecha
    x_qr = int(width_px - qr_w - margin)
    
    # Y: Pegado al fondo (ABAJO) en lugar de centrado
    # Esto libera el espacio de arriba para el nombre largo
    y_qr = int(height_px - qr_h - margin)
    
    img.paste(qr_img, (x_qr, y_qr))

    # ==========================================
    # 2. POSICIONAR TEXTO
    # ==========================================
    margin_left = margin
    current_y = margin # Empezamos arriba
    
    # Lógica inteligente para el ancho del Nombre:
    # Si el nombre está "arriba" del QR (verticalmente), puede usar todo el ancho.
    # Si el nombre choca con el QR, se limita.
    
    # Calculamos dónde empieza el QR verticalmente
    qr_top_y = y_qr 
    
    # Espacio seguro para texto ancho (Nombre)
    # Si la linea de texto termina ANTES de que empiece el QR, usa ancho total
    if (current_y + font_size_nombre) < qr_top_y:
        max_name_width = int(width_px - (margin * 2)) # Ancho completo
    else:
        max_name_width = int(x_qr - margin_left - gap_text_qr) # Limitado por QR

    # --- A. Nombre del Producto ---
    nombre_texto = producto.nombre
    while d.textlength(nombre_texto + "...", font=fnt_nombre) > max_name_width and len(nombre_texto) > 0:
        nombre_texto = nombre_texto[:-1]
    if len(nombre_texto) < len(producto.nombre):
        nombre_texto += "..."
        
    d.text((margin_left, current_y), nombre_texto, font=fnt_nombre, fill="black")
    
    # --- B. Código (SKU) ---
    current_y += int(font_size_nombre + 5)
    
    # Para las siguientes líneas, probablemente ya estemos a la altura del QR, así que limitamos el ancho
    if (current_y + font_size_codigo) < qr_top_y:
        max_std_width = int(width_px - (margin * 2))
    else:
        max_std_width = int(x_qr - margin_left - gap_text_qr)
        
    codigo_texto = producto.codigo
    while d.textlength(codigo_texto, font=fnt_codigo) > max_std_width and len(codigo_texto) > 0:
         codigo_texto = codigo_texto[:-1]
         
    d.text((margin_left, current_y), codigo_texto, font=fnt_codigo, fill="#1f4e79") # Azul
    
    # --- C. Ubicación / ID ---
    current_y += int(font_size_codigo + 5)
    
    texto_inferior = f"UBIC: {ubicacion}" if ubicacion and ubicacion != "N/A" else f"ID: {producto.id}"
    while d.textlength(texto_inferior, font=fnt_ubic) > max_std_width and len(texto_inferior) > 0:
         texto_inferior = texto_inferior[:-1]
         
    d.text((margin_left, current_y), texto_inferior, font=fnt_ubic, fill="black")

    # ==========================================
    # 3. POSICIONAR IMAGEN (Izquierda - Debajo del Texto)
    # ==========================================
    y_img_start = int(current_y + font_size_ubic + 10)
    
    # El espacio disponible ahora es más limitado porque el QR está abajo a la derecha,
    # pero la esquina inferior izquierda suele estar libre.
    available_height = int(height_px - y_img_start - margin)
    
    # El ancho disponible para la imagen es hasta donde empieza el QR
    available_width = int(x_qr - margin_left - 10)

    if available_height > 20 and producto.imagen_url:
        path_img_prod = os.path.join(app.config['UPLOAD_FOLDER'], producto.imagen_url)
        if os.path.exists(path_img_prod):
            try:
                prod_img = Image.open(path_img_prod)
                
                # Definimos caja máxima
                box_w = available_width
                box_h = available_height
                
                prod_img.thumbnail((box_w, box_h))
                img.paste(prod_img, (margin_left, y_img_start))
            except Exception:
                pass

    # --- GUARDAR ---
    buffer = io.BytesIO()
    img.save(buffer, 'JPEG', quality=100)
    buffer.seek(0)
    
    nombre_clean = secure_filename(producto.nombre)
    filename = f"Etiqueta_{nombre_clean}_{tamano}.jpg"

    return send_file(buffer, mimetype='image/jpeg', as_attachment=True, download_name=filename)

# --- Rutas Principales (Dashboard) ---

@app.route('/')
@login_required
def index():
    """ Dashboard Principal (Multiusuario) con Alertas por Almacén. """
    
    alertas_agrupadas = {}
    pending_map = {}
    
    if current_user.rol == 'super_admin':
        # (El Super Admin ve todo, agrupado por organización)
        pass
    elif current_user.organizacion_id:
        org_id = current_user.organizacion_id
        
        # 1. Encontrar todos los items de stock BAJO de esta organización
        alertas_crudas = db.session.query(Stock).join(Almacen).join(Producto).filter(
            Almacen.organizacion_id == org_id,
            Stock.cantidad < Stock.stock_minimo
        ).all()

        # 2. Encontrar OCs pendientes (borrador o enviada) de esta organización
        ordenes_pendientes = db.session.query(
            OrdenCompraDetalle.producto_id, 
            OrdenCompra.id, 
            User.username,
            OrdenCompra.estado,
            OrdenCompra.almacen_id
        ).join(
            OrdenCompra, OrdenCompraDetalle.orden_id == OrdenCompra.id
        ).join(
            User, OrdenCompra.creador_id == User.id
        ).filter(
            OrdenCompra.estado.in_(['borrador', 'enviada']),
            OrdenCompra.organizacion_id == org_id
        ).all()

        # 3. Convertir OCs pendientes en un mapa de búsqueda rápida
        for prod_id, orden_id, username, estado, alm_id in ordenes_pendientes:
            pending_map[(prod_id, alm_id)] = {
                'orden_id': orden_id, 
                'username': username,
                'estado': estado
            }
            
        # 4. Agrupar las alertas por (Almacén, Proveedor)
        alertas_agrupadas = defaultdict(list)
        for item_stock in alertas_crudas:
            if (item_stock.producto_id, item_stock.almacen_id) in pending_map:
                continue
                
            if item_stock.producto.proveedor:
                key = (item_stock.almacen_id, item_stock.almacen.nombre, 
                       item_stock.producto.proveedor_id, item_stock.producto.proveedor.nombre)
                alertas_agrupadas[key].append(item_stock)
            else:
                key = (item_stock.almacen_id, item_stock.almacen.nombre, 0, "Proveedor no asignado")
                alertas_agrupadas[key].append(item_stock)

    return render_template('index.html', 
                           alertas_agrupadas=alertas_agrupadas,
                           pending_map=pending_map)

@app.route('/dashboard')
@login_required
@check_org_permission
@check_permission('perm_view_dashboard')
def dashboard():
    """ 
    Página del Dashboard de Inventario (Filtros y Tabla).
    MODIFICADO para Multi-Almacén.
    """
    
    if current_user.rol == 'super_admin':
        almacenes = Almacen.query.all()
    else:
        almacenes = Almacen.query.filter_by(organizacion_id=current_user.organizacion_id).order_by(Almacen.nombre).all()

    almacen_id_solicitado = request.args.get('almacen_id', type=int)
    almacen_seleccionado = None

    if almacen_id_solicitado:
        if current_user.rol == 'super_admin':
            almacen_seleccionado = Almacen.query.get(almacen_id_solicitado)
        else:
            almacen_seleccionado = Almacen.query.filter_by(id=almacen_id_solicitado, organizacion_id=current_user.organizacion_id).first()
    
    if not almacen_seleccionado and almacenes:
        almacen_seleccionado = almacenes[0]
    
    if almacen_seleccionado:
        items_stock = db.session.query(Stock).filter_by(almacen_id=almacen_seleccionado.id).join(Producto).order_by(Producto.nombre).all()
    else:
        items_stock = []

    if current_user.rol == 'super_admin':
        categorias = Categoria.query.all()
        proveedores = Proveedor.query.all()
    else:
        org_id = current_user.organizacion_id
        categorias = Categoria.query.filter_by(organizacion_id=org_id).all()
        proveedores = Proveedor.query.filter_by(organizacion_id=org_id).all()
            
    return render_template('dashboard.html', 
                           items_stock=items_stock,
                           almacenes=almacenes,
                           almacen_seleccionado=almacen_seleccionado,
                           categorias=categorias,
                           proveedores=proveedores)

# --- Rutas de Productos ---

@app.route('/api/productos/buscar')
@login_required
def api_buscar_productos():
    """
    API para buscar productos por Nombre o SKU dinámicamente.
    Retorna JSON para ser consumido por JavaScript.
    """
    query = request.args.get('q', '').strip()
    
    if not query:
        return jsonify([])

    # Buscamos coincidencias en Nombre O Código (SKU)
    # Usamos ilike para que no importen mayúsculas/minúsculas
    productos = Producto.query.filter(
        (Producto.nombre.ilike(f'%{query}%')) | 
        (Producto.codigo.ilike(f'%{query}%'))
    ).filter_by(organizacion_id=current_user.organizacion_id).limit(10).all()

    resultados = []
    for p in productos:
        resultados.append({
            'id': p.id,
            'texto_mostrar': f"{p.nombre} (SKU: {p.codigo})", # Lo que se ve en la lista
            'nombre': p.nombre,
            'codigo': p.codigo,
            'precio': p.precio_unitario
        })
    
    return jsonify(resultados)

@app.route('/producto/nuevo', methods=['GET', 'POST'])
@login_required
@check_org_permission #(Si usas este decorador, mantenlo)
@check_permission('perm_edit_management') #(Si usas este decorador, mantenlo)
def nuevo_producto():
    """ 
    Crea un nuevo producto. 
    CORREGIDO: Manejo de strings vacíos en la conversión a float.
    """
    org_id = current_user.organizacion_id
    proveedores = Proveedor.query.filter_by(organizacion_id=org_id).all()
    categorias = Categoria.query.filter_by(organizacion_id=org_id).all()
    almacenes = Almacen.query.filter_by(organizacion_id=org_id).all() 
    
    if request.method == 'POST':
        imagen_filename = None
            
        def repoblar_formulario_con_error():
            # El uso de 'or 0.0' previene el error si el campo llega vacío
            costo_val = request.form.get('costo_estandar')
            precio_unitario_float = float(costo_val) if costo_val and costo_val.strip() else 0.0

            producto_temporal = Producto(
                nombre=request.form.get('nombre'),
                codigo=request.form.get('codigo'),
                categoria_id=int(request.form.get('categoria_id') or 0) or None,
                precio_unitario=precio_unitario_float, 
                proveedor_id=int(request.form.get('proveedor_id') or 0) or None,
                unidades_por_caja=int(request.form.get('unidades_por_caja') or 1),
                organizacion_id=org_id
            )
            producto_temporal.costo_estandar = producto_temporal.precio_unitario
            
            return render_template('producto_form.html', 
                                   titulo="Nuevo Producto", 
                                   proveedores=proveedores,
                                   categorias=categorias,
                                   almacenes=almacenes, 
                                   producto=producto_temporal)
            
        if 'imagen' in request.files:
            file = request.files['imagen']
            if file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                imagen_filename = filename
            elif file.filename != '' and not allowed_file(file.filename):
                flash('Tipo de archivo de imagen no permitido.', 'danger')
                return repoblar_formulario_con_error()
        
        try:
            # CORRECCIÓN VITAL: Validar string vacío antes de float()
            costo_raw = request.form.get('costo_estandar')
            precio_final = float(costo_raw) if costo_raw and costo_raw.strip() else 0.0

            nuevo_prod = Producto(
                nombre=request.form['nombre'],
                codigo=request.form['codigo'],
                categoria_id=request.form.get('categoria_id') or None,
                precio_unitario=precio_final,
                imagen_url=imagen_filename,
                proveedor_id=request.form.get('proveedor_id') or None,
                unidades_por_caja=int(request.form.get('unidades_por_caja', 1)), 
                organizacion_id=current_user.organizacion_id,
                enlace_proveedor=request.form.get('enlace_proveedor')
            )
            db.session.add(nuevo_prod)
            db.session.flush()

            cantidad_inicial = int(request.form.get('cantidad_inicial') or 0)
            almacen_inicial_id = int(request.form.get('almacen_inicial_id') or 0)
            ubicacion_inicial = request.form.get('ubicacion_inicial')

            almacen_seleccionado = None
            if almacen_inicial_id > 0:
                almacen_seleccionado = Almacen.query.filter_by(id=almacen_inicial_id, organizacion_id=org_id).first()

            if almacen_seleccionado:
                nuevo_stock = Stock(
                    producto_id=nuevo_prod.id,
                    almacen_id=almacen_seleccionado.id,
                    cantidad=cantidad_inicial, 
                    stock_minimo=int(request.form.get('stock_minimo') or 5),
                    stock_maximo=int(request.form.get('stock_maximo') or 100),
                    ubicacion=ubicacion_inicial
                )
                db.session.add(nuevo_stock)

                if cantidad_inicial > 0:
                    movimiento_inicial = Movimiento(
                        producto_id=nuevo_prod.id,
                        cantidad=cantidad_inicial,
                        tipo='entrada-inicial',
                        fecha=datetime.now(),
                        motivo='Stock Inicial (Creación)',
                        almacen_id=almacen_inicial_id,
                        organizacion_id=org_id
                    )
                    db.session.add(movimiento_inicial)
                
            db.session.commit()
            flash('Producto creado exitosamente.', 'success')
            
            if almacen_seleccionado:
                 return redirect(url_for('gestionar_inventario_almacen', id=almacen_seleccionado.id))
            return redirect(url_for('dashboard'))
        
        except IntegrityError as e:
            db.session.rollback()
            if "producto_codigo_key" in str(e) or "UNIQUE constraint failed" in str(e):
                flash('Error: El Código (SKU) ya existe.', 'danger')
            else:
                flash(f'Error de base de datos: {e}', 'danger')
            return repoblar_formulario_con_error()
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error inesperado: {e}', 'danger')
            return repoblar_formulario_con_error()
            
    return render_template('producto_form.html', 
                           titulo="Nuevo Producto", 
                           proveedores=proveedores,
                           categorias=categorias,
                           almacenes=almacenes,
                           producto=None)
 
@app.route('/producto/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@check_permission('perm_edit_management')
def editar_producto(id):
    """ 
    Edita un producto.
    CORREGIDO: Previene error 'could not convert string to float' en campos vacíos.
    """
    producto = Producto.query.get_or_404(id)
    org_id = producto.organizacion_id
    proveedores = Proveedor.query.filter_by(organizacion_id=org_id).all()
    categorias = Categoria.query.filter_by(organizacion_id=org_id).all()

    almacen_id = request.args.get('almacen_id', type=int)
    stock_item = None
    if almacen_id:
        stock_item = Stock.query.filter_by(producto_id=producto.id, almacen_id=almacen_id).first()

    if request.method == 'POST':
        try:
            if 'imagen' in request.files:
                file = request.files['imagen']
                if file.filename != '' and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    producto.imagen_url = filename

            producto.nombre = request.form['nombre']
            producto.codigo = request.form['codigo']
            producto.categoria_id = request.form.get('categoria_id') or None
            producto.proveedor_id = request.form.get('proveedor_id') or None
            producto.unidades_por_caja = int(request.form.get('unidades_por_caja') or 1)
            producto.enlace_proveedor = request.form.get('enlace_proveedor')
            
            # CORRECCIÓN AQUÍ: Manejar el valor vacío de costo_estandar
            costo_raw = request.form.get('costo_estandar')
            producto.precio_unitario = float(costo_raw) if costo_raw and costo_raw.strip() else 0.0

            if stock_item:
                stock_item.stock_minimo = int(request.form.get('stock_minimo') or 0)
                stock_item.stock_maximo = int(request.form.get('stock_maximo') or 0)
                stock_item.cantidad = int(request.form.get('cantidad') or 0)
                stock_item.ubicacion = request.form.get('ubicacion')

            db.session.commit()
            flash('Producto actualizado exitosamente', 'success')
            return redirect(url_for('gestionar_inventario_almacen', id=almacen_id) if almacen_id else url_for('dashboard'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar producto: {e}', 'danger')

    # Preparar visualización del costo para el template
    producto.costo_estandar = producto.precio_unitario
    return render_template('producto_form.html', 
                           titulo="Editar Producto", 
                           producto=producto, 
                           proveedores=proveedores, 
                           categorias=categorias, 
                           stock_item=stock_item)
  
@app.route('/producto/<int:id>/etiqueta')
@login_required
@check_permission('perm_view_dashboard')
def generar_etiqueta(id):
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
    """ Muestra el Kardex (Movimientos) Y el Stock Actual por Almacén. """
    producto = get_item_or_404(Producto, id)
    
    # --- 1. OBTENER STOCK ACTUAL ---
    # Buscamos dónde está este producto (en qué almacenes y qué cantidad)
    stocks_actuales = Stock.query.filter_by(producto_id=id).join(Almacen).order_by(Almacen.nombre).all()
    
    # Calcular el total global para mostrarlo en grande
    total_global = sum(s.cantidad for s in stocks_actuales)
    
    # --- 2. OBTENER MOVIMIENTOS ---
    movimientos_query = Movimiento.query.filter_by(producto_id=id).order_by(Movimiento.fecha.desc())
    
    if current_user.rol != 'super_admin':
        movimientos_query = movimientos_query.filter(Movimiento.organizacion_id == current_user.organizacion_id)
        
    movimientos = movimientos_query.all()
    
    # Agrupar movimientos por almacén para la vista
    historial_por_almacen = defaultdict(list)
    for m in movimientos:
        # Usamos una consulta segura por si el almacén fue borrado (aunque no debería pasar con cascade)
        alm_nombre = Almacen.query.get(m.almacen_id).nombre if m.almacen_id else "Sin Almacén"
        historial_por_almacen[alm_nombre].append(m)
    
    return render_template('historial_producto.html', 
                           producto=producto, 
                           historial_por_almacen=historial_por_almacen,
                           stocks_actuales=stocks_actuales, # <-- DATO NUEVO
                           total_global=total_global)       # <-- DATO NUEVO

# --- Rutas de Categorías ---

@app.route('/categorias')
@login_required
@check_org_permission
@check_permission('perm_view_management')
def lista_categorias():
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
    if request.method == 'POST':
        try:
            nuevo_prov = Proveedor(
                nombre=request.form['nombre'],
                contacto_email=request.form.get('contacto_email'),
                contacto_telefono=request.form.get('contacto_telefono'),
                organizacion_id=current_user.organizacion_id
            )
            db.session.add(nuevo_prov)
            db.session.commit()
            flash('Proveedor creado exitosamente', 'success')
            return redirect(url_for('lista_proveedores'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear proveedor: {e}', 'danger')
            
    return render_template('proveedor_form.html', titulo="Nuevo Proveedor", proveedor=None)

@app.route('/proveedor/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@check_permission('perm_edit_management')
def editar_proveedor(id):
    proveedor = get_item_or_404(Proveedor, id)
    
    if request.method == 'POST':
        try:
            proveedor.nombre = request.form['nombre']
            proveedor.contacto_email = request.form.get('contacto_email')
            proveedor.contacto_telefono = request.form.get('contacto_telefono')
            
            db.session.commit()
            flash('Proveedor actualizado exitosamente', 'success')
            return redirect(url_for('lista_proveedores'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar el proveedor: {e}', 'danger')

    return render_template('proveedor_form.html', 
                           titulo="Editar Proveedor", 
                           proveedor=proveedor)

# --- Rutas de Almacenes ---

@app.route('/almacenes')
@login_required
@admin_required # Solo Admins y Super Admins pueden gestionar almacenes
def lista_almacenes():
    """ Muestra la lista de almacenes de la organización. """
    if current_user.rol == 'super_admin':
        almacenes = Almacen.query.all()
    else:
        almacenes = Almacen.query.filter_by(organizacion_id=current_user.organizacion_id).all()
        
    return render_template('almacenes.html', 
                           almacenes=almacenes,
                           titulo="Gestionar Almacenes")

@app.route('/almacen/nuevo', methods=['GET', 'POST'])
@login_required
@admin_required
def nuevo_almacen():
    """ Formulario para crear un nuevo almacén. """
    if request.method == 'POST':
        try:
            nuevo_alm = Almacen(
                nombre=request.form['nombre'],
                ubicacion=request.form.get('ubicacion'),
                organizacion_id=current_user.organizacion_id
            )
            db.session.add(nuevo_alm)
            db.session.commit()
            flash('Almacén creado exitosamente', 'success')
            return redirect(url_for('lista_almacenes'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear el almacén: {e}', 'danger')
            
    return render_template('almacen_form.html', 
                           titulo="Nuevo Almacén", 
                           almacen=None)

@app.route('/almacen/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def editar_almacen(id):
    """ Edita un almacén existente. """
    almacen = get_item_or_404(Almacen, id)
    
    if request.method == 'POST':
        try:
            almacen.nombre = request.form['nombre']
            almacen.ubicacion = request.form.get('ubicacion')
            db.session.commit()
            flash('Almacén actualizado exitosamente', 'success')
            return redirect(url_for('lista_almacenes'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar el almacén: {e}', 'danger')

    return render_template('almacen_form.html', 
                           titulo="Editar Almacén", 
                           almacen=almacen)

@app.route('/almacen/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_almacen(id):
    # Solo administradores
    if current_user.rol not in ['super_admin', 'admin']:
        flash('No tienes permiso para eliminar almacenes.', 'danger')
        return redirect(url_for('lista_almacenes'))

    almacen = Almacen.query.get_or_404(id)

    # Opcional: Validar que esté vacío antes de borrar
    # stocks_activos = Stock.query.filter_by(almacen_id=id).filter(Stock.cantidad > 0).count()
    # if stocks_activos > 0:
    #     flash(f'No puedes eliminar "{almacen.nombre}" porque aún tiene productos con stock.', 'warning')
    #     return redirect(url_for('lista_almacenes'))

    try:
        db.session.delete(almacen)
        db.session.commit()
        flash('Almacén eliminado correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar el almacén (puede tener datos relacionados): {e}', 'danger')

    return redirect(url_for('lista_almacenes'))

@app.route('/almacen/<int:id>/inventario', methods=['GET', 'POST'])
@login_required
# @admin_required # (O usa @check_permission si es lo que usas en tu sistema)
def gestionar_inventario_almacen(id):
    almacen = get_item_or_404(Almacen, id)
    org_id = almacen.organizacion_id

    if request.method == 'POST':
        try:
            producto_id = int(request.form.get('producto_id'))
            ubicacion = request.form.get('ubicacion')
            # 1. CAPTURAR CANTIDAD (Calculada por el frontend: Cajas * Factor)
            cantidad = float(request.form.get('cantidad', 0))

            if not producto_id:
                raise Exception("No se seleccionó un producto.")

            stock_existente = Stock.query.filter_by(
                almacen_id=id, 
                producto_id=producto_id
            ).first()
            
            if stock_existente:
                flash('Ese producto ya está registrado en este almacén.', 'warning')
            else:
                # 2. CREAR STOCK CON CANTIDAD INICIAL Y ORG_ID
                nuevo_stock = Stock(
                    producto_id=producto_id,
                    almacen_id=id,
                    cantidad=cantidad, # <-- Usamos la cantidad del form
                    stock_minimo=5,
                    stock_maximo=100,
                    ubicacion=ubicacion
                )
                db.session.add(nuevo_stock)

                # 3. REGISTRAR MOVIMIENTO INICIAL (Si aplica)
                if cantidad > 0:
                    movimiento = Movimiento(
                        producto_id=producto_id,
                        cantidad=cantidad,
                        tipo='entrada-inicial',
                        fecha=datetime.now(),
                        motivo='Stock Inicial (Alta Manual en Almacén)',
                        almacen_id=id,
                        organizacion_id=org_id
                    )
                    db.session.add(movimiento)

                db.session.commit()
                flash(f'Producto añadido al almacén con stock {cantidad}.', 'success')
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error al añadir producto: {e}', 'danger')
        
        return redirect(url_for('gestionar_inventario_almacen', id=id))

    # LÓGICA GET
    productos_en_stock_ids = [s.producto_id for s in almacen.stocks]
    productos_catalogo = Producto.query.filter_by(organizacion_id=org_id).all()
    
    # Filtrar solo productos que NO están en este almacén
    productos_para_anadir = [
        p for p in productos_catalogo if p.id not in productos_en_stock_ids
    ]
    
    productos_para_anadir_json = []
    for p in productos_para_anadir:
        productos_para_anadir_json.append({
            "id": p.id,
            "nombre": p.nombre,
            "codigo": p.codigo,
            # 4. ENVIAR FACTOR DE EMPAQUE (Para la calculadora JS)
            "unidades_por_caja": int(p.unidades_por_caja) if p.unidades_por_caja and p.unidades_por_caja > 0 else 1
        })
    
    return render_template('almacen_inventario.html',
                           titulo=f"Inventario de {almacen.nombre}",
                           almacen=almacen,
                           productos_para_anadir_json=productos_para_anadir_json)

# --- FUNCIÓN NUEVA: eliminar_producto_de_almacen ---
@app.route('/almacen/stock/eliminar/<int:id>', methods=['POST'])
@login_required
@admin_required
def eliminar_producto_de_almacen(id):
    """ 
    Elimina un producto de un almacén específico (borra el registro de Stock).
    El producto sigue existiendo en el catálogo global.
    """
    stock_item = Stock.query.get_or_404(id)
    almacen_id = stock_item.almacen_id
    
    if stock_item.almacen.organizacion_id != current_user.organizacion_id:
        flash('No tienes permiso para realizar esta acción.', 'danger')
        return redirect(url_for('lista_almacenes'))

    try:
        nombre_prod = stock_item.producto.nombre
        nombre_alm = stock_item.almacen.nombre
        
        db.session.delete(stock_item)
        db.session.commit()
        
        flash(f'Producto "{nombre_prod}" eliminado de "{nombre_alm}".', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar del almacén: {e}', 'danger')

    return redirect(url_for('gestionar_inventario_almacen', id=almacen_id))

# ========================
# NUEVAS RUTAS: GESTIÓN DE HUÉRFANOS
# ========================

@app.route('/productos/sin-almacen')
@login_required
@check_org_permission
@check_permission('perm_view_management')
def lista_productos_sin_almacen():
    """ Muestra productos que existen en catálogo pero NO en ningún almacén (Stock). """
    org_id = current_user.organizacion_id
    
    # 1. Subconsulta: IDs de productos que SÍ tienen al menos un registro de Stock
    # (Un producto tiene stock si existe una fila en la tabla 'stock' vinculada a él)
    ids_con_stock = db.session.query(Stock.producto_id).join(Almacen).filter(
        Almacen.organizacion_id == org_id
    ).distinct()
    
    # 2. Consulta Principal: Productos de la org que NO están en la lista anterior
    productos_huerfanos = Producto.query.filter(
        Producto.organizacion_id == org_id,
        ~Producto.id.in_(ids_con_stock) # El símbolo ~ niega la condición (NOT IN)
    ).all()
    
    # Necesitamos los almacenes para el dropdown de asignación
    almacenes = Almacen.query.filter_by(organizacion_id=org_id).all()
    
    return render_template('productos_sin_almacen.html',
                           titulo="Productos Sin Asignar",
                           productos=productos_huerfanos,
                           almacenes=almacenes)

@app.route('/producto/asignar-rapido', methods=['POST'])
@login_required
@check_permission('perm_edit_management')
def asignar_producto_rapido():
    """ Asigna un producto a un almacén rápidamente desde la lista de huérfanos. """
    try:
        producto_id = int(request.form.get('producto_id'))
        almacen_id = int(request.form.get('almacen_id'))
        
        if not producto_id or not almacen_id:
            raise Exception("Datos incompletos.")

        producto = Producto.query.get_or_404(producto_id)
        
        # Verificar si ya existe (doble check de seguridad)
        existe = Stock.query.filter_by(producto_id=producto_id, almacen_id=almacen_id).first()
        if existe:
            flash(f'El producto ya estaba en ese almacén.', 'warning')
        else:
            # Crear Stock inicial en 0
            nuevo_stock = Stock(
                producto_id=producto_id,
                almacen_id=almacen_id,
                cantidad=0,
                stock_minimo=5,
                stock_maximo=100
            )
            db.session.add(nuevo_stock)
            db.session.commit()
            flash(f'Producto "{producto.nombre}" asignado correctamente.', 'success')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Error al asignar producto: {e}', 'danger')
        
    return redirect(url_for('lista_productos_sin_almacen'))

#<---------SALIDA DE PRODUCTOS (REESCRITO PARA MULTI-ALMACÉN)----------->

@app.route('/salidas')
@login_required
@check_org_permission
@check_permission('perm_do_salidas')
def historial_salidas():
    """ Muestra el historial de Hojas de Salida Diarias (Multiusuario). """
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
    """ Muestra el detalle de una Hoja de Salida Diaria (Multiusuario). """
    salida = get_item_or_404(Salida, id)
    # Ordenamos los movimientos por hora para verlos cronológicamente
    movimientos = salida.movimientos.order_by(Movimiento.fecha.asc()).all()
    
    return render_template('salida_detalle.html', 
                           salida=salida, 
                           movimientos=movimientos,
                           titulo=f"Salida del {salida.fecha.strftime('%Y-%m-%d')}")

@app.route('/salida', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_do_salidas')
def registrar_salida():
    """ 
    AÑADE items a la Hoja de Salida del día de hoy.
    (MODIFICADO para Multi-Almacén)
    """
    org_id = current_user.organizacion_id
    
    # --- LÓGICA DE ALMACÉN ---
    almacen_id_solicitado = request.args.get('almacen_id', type=int)
    almacenes_org = Almacen.query.filter_by(organizacion_id=org_id).all()
    
    almacen_seleccionado = None
    if almacen_id_solicitado:
        almacen_seleccionado = Almacen.query.get(almacen_id_solicitado)
        # Chequeo de seguridad
        if not almacen_seleccionado or almacen_seleccionado.organizacion_id != org_id:
            flash('Permiso denegado para ese almacén.', 'danger')
            return redirect(url_for('historial_salidas'))
    
    if not almacenes_org:
        flash('No se pueden registrar salidas porque no hay almacenes creados.', 'warning')
        return redirect(url_for('index'))
    
    if not almacen_seleccionado:
        return render_template('seleccionar_almacen.html',
                               titulo="Seleccionar Almacén de Origen",
                               almacenes=almacenes_org,
                               destino_ruta='registrar_salida') # Ruta a la que volver

    # --- LÓGICA DE BUSCAR-O-CREAR LA HOJA DIARIA ---
    today = datetime.now().date()
    salida_del_dia = Salida.query.filter_by(
        fecha=today, 
        organizacion_id=org_id,
        almacen_id=almacen_seleccionado.id # <-- Filtro por almacén
    ).first()

    if not salida_del_dia:
        salida_del_dia = Salida(
            fecha=today,
            creador_id=current_user.id,
            organizacion_id=org_id,
            almacen_id=almacen_seleccionado.id # <-- Asignar almacén
        )
        db.session.add(salida_del_dia)
        db.session.flush()

    # --- LÓGICA DE PRODUCTOS ---
    # Filtramos solo productos que tienen stock EN ESE ALMACÉN
    productos_en_almacen = db.session.query(Producto).join(Stock).filter(
        Stock.almacen_id == almacen_seleccionado.id,
        Producto.organizacion_id == org_id,
        Stock.cantidad > 0 # Solo mostrar productos que TENGAN stock
    ).all()
    
    productos_lista = []
    for p in productos_en_almacen:
        # Obtenemos el stock específico de ESE almacén
        stock_item = Stock.query.filter_by(producto_id=p.id, almacen_id=almacen_seleccionado.id).first()
        productos_lista.append({
            'id': p.id,
            'nombre': p.nombre,
            'codigo': p.codigo,
            'stock_actual': stock_item.cantidad if stock_item else 0
        })

    if request.method == 'POST':
        try:
            productos_ids = request.form.getlist('producto_id[]')
            cantidades = request.form.getlist('cantidad[]')
            motivos = request.form.getlist('motivo[]') # <-- AHORA ES UNA LISTA

            if not productos_ids:
                flash('Debes añadir al menos un producto a la salida.', 'danger')
                return redirect(url_for('registrar_salida', almacen_id=almacen_seleccionado.id))

            # --- 1. FASE DE VALIDACIÓN ---
            productos_para_actualizar = [] 
            for i in range(len(productos_ids)):
                prod_id = productos_ids[i]
                cant_str = cantidades[i]
                
                if not prod_id or not cant_str: continue
                cantidad_salida = int(cant_str)
                
                # Buscamos el item de stock específico
                stock_item = Stock.query.filter_by(producto_id=prod_id, almacen_id=almacen_seleccionado.id).first()
                
                if not stock_item:
                    flash(f'Error: Producto no válido.', 'danger')
                    db.session.rollback()
                    return render_template('salida_form.html', titulo=f"Registrar Salida de: {almacen_seleccionado.nombre}", productos=productos_lista, salida_id=salida_del_dia.id, almacen=almacen_seleccionado)
                if cantidad_salida <= 0:
                    flash('Todas las cantidades deben ser positivas.', 'danger')
                    db.session.rollback() 
                    return render_template('salida_form.html', titulo=f"Registrar Salida de: {almacen_seleccionado.nombre}", productos=productos_lista, salida_id=salida_del_dia.id, almacen=almacen_seleccionado)
                
                # --- VALIDACIÓN CRÍTICA DE STOCK (Ahora en la tabla Stock) ---
                if stock_item.cantidad < cantidad_salida:
                    flash(f'Error: Stock insuficiente para "{stock_item.producto.nombre}". Stock actual: {stock_item.cantidad}', 'danger')
                    db.session.rollback()
                    return render_template('salida_form.html', titulo=f"Registrar Salida de: {almacen_seleccionado.nombre}", productos=productos_lista, salida_id=salida_del_dia.id, almacen=almacen_seleccionado)
                
                productos_para_actualizar.append((stock_item, cantidad_salida, motivos[i]))

            # --- 2. FASE DE EJECUCIÓN ---
            for stock_item, cantidad_salida, motivo_item in productos_para_actualizar:
                
                # 1. Actualizar el stock del item
                stock_item.cantidad -= cantidad_salida
                db.session.add(stock_item)
                
                # 2. Registrar el movimiento VINCULADO
                movimiento = Movimiento(
                    producto_id=stock_item.producto_id,
                    cantidad= -cantidad_salida, # Negativo
                    tipo='salida',
                    fecha=datetime.now(), # <-- Hora exacta
                    motivo=motivo_item, # <-- Motivo por item
                    salida=salida_del_dia, # <-- Vinculamos a la hoja diaria
                    almacen_id=almacen_seleccionado.id, # <-- ESTAMPAR ID
                    organizacion_id=org_id
                )
                db.session.add(movimiento)
            
            db.session.commit()
            flash(f'Se añadieron {len(productos_para_actualizar)} items a la salida del día.', 'success')
            # Redirigimos al detalle de la hoja de hoy
            return redirect(url_for('ver_salida', id=salida_del_dia.id)) 

        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar la salida: {e}', 'danger')
    
    return render_template('salida_form.html', 
                           titulo=f"Registrar Salida de: {almacen_seleccionado.nombre}", 
                           productos=productos_lista,
                           salida_id=salida_del_dia.id, # Pasamos el ID para el botón "Ver Hoja de Hoy"
                           almacen=almacen_seleccionado)

@app.route('/movimiento/<int:id>/eliminar', methods=['POST'])
@login_required
@check_permission('perm_do_salidas')
def eliminar_movimiento_salida(id):
    """ 
    Elimina un SOLO item (Movimiento) de una hoja de salida 
    y REVIERTE el stock.
    """
    movimiento = get_item_or_404(Movimiento, id)
    
    if movimiento.tipo != 'salida':
        flash('Error: Solo se pueden eliminar items de salida.', 'danger')
        return redirect(url_for('historial_salidas'))
        
    salida_id_redirect = movimiento.salida_id

    try:
        # --- LÓGICA MODIFICADA ---
        # Buscamos el item de stock específico
        stock_item = Stock.query.filter_by(
            producto_id=movimiento.producto_id, 
            almacen_id=movimiento.almacen_id
        ).first()
        cantidad_a_devolver = abs(movimiento.cantidad)
        
        # 1. Revertir el stock
        if stock_item:
            stock_item.cantidad += cantidad_a_devolver
            db.session.add(stock_item)
        else:
            # Si el stock no existe, lo creamos (caso raro)
            stock_item = Stock(
                producto_id=movimiento.producto_id,
                almacen_id=movimiento.almacen_id,
                cantidad=cantidad_a_devolver,
                organizacion_id=movimiento.organizacion_id # Aseguramos la org
            )
            db.session.add(stock_item)
        
        # 2. Registrar el ajuste (para auditoría)
        mov_ajuste = Movimiento(
            producto_id=movimiento.producto_id,
            cantidad=cantidad_a_devolver,
            tipo='ajuste-entrada',
            fecha=datetime.now(),
            motivo=f'Corrección/Eliminación de item (Salida #{salida_id_redirect})',
            almacen_id=movimiento.almacen_id,
            organizacion_id=movimiento.organizacion_id
        )
        db.session.add(mov_ajuste)
        
        # 3. Eliminar el movimiento de salida original
        db.session.delete(movimiento)
        
        db.session.commit()
        flash(f'Item "{movimiento.producto.nombre}" eliminado. Stock revertido.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar el item: {e}', 'danger')

    # Si la hoja de salida todavía existe, redirige a ella
    if salida_id_redirect and Salida.query.get(salida_id_redirect):
        return redirect(url_for('ver_salida', id=salida_id_redirect))
    # Si era el último item, la hoja se borró (por la cascada), 
    # así que redirigimos al historial
    return redirect(url_for('historial_salidas'))


@app.route('/salida/<int:id>/pdf')
@login_required
@check_permission('perm_do_salidas')
def generar_salida_pdf(id):
    """ Genera un PDF de Salida (Multiusuario, Multi-Almacén). """
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
    # --- AÑADIDO ALMACÉN ---
    story.append(Paragraph(f"<b>Almacén:</b> {salida.almacen.nombre}", styles['h3']))
    story.append(Spacer(1, 0.25 * inch))
    info_salida = f"""
        <b>Fecha:</b> {salida.fecha.strftime('%Y-%m-%d')}<br/>
        <b>Estado:</b> <font color="{'red' if salida.estado == 'cancelada' else 'green'}">
            {salida.estado.capitalize()}
        </font><br/>
        <b>Creada por:</b> {salida.creador.username}
    """
    story.append(Paragraph(info_salida, styles['BodyText']))
    story.append(Spacer(1, 0.5 * inch))

    # --- TABLA PDF MODIFICADA ---
    data = [[
        Paragraph('Producto', style_header), 
        Paragraph('SKU', style_header), 
        Paragraph('Motivo', style_header),
        Paragraph('Cantidad Retirada', style_header)
    ]]
    # Usamos .all() porque la relación ahora es 'dynamic'
    for mov in salida.movimientos.order_by(Movimiento.fecha.asc()).all():
        producto = Paragraph(mov.producto.nombre, style_left)
        sku = Paragraph(mov.producto.codigo, style_left)
        motivo = Paragraph(mov.motivo, style_left)
        cantidad = Paragraph(str(abs(mov.cantidad)), style_right)
        data.append([producto, sku, motivo, cantidad])

    style = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E9ECEF")),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 8),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8F9FA")]), 
        ('GRID', (0,0), (-1,-1), 1, colors.HexColor("#DEE2E6")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#DEE2E6")),
    ])

    tabla_salida = Table(data, colWidths=[2.5*inch, 1.5*inch, 1.25*inch, 1.25*inch])
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
    
# --- RUTAS DE ÓRDENES DE COMPRA (OC) ---

@app.route('/ordenes')
@login_required
@check_org_permission
@check_permission('perm_create_oc_standard')
def lista_ordenes():
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
    try:
        ids_productos_a_ordenar = request.form.getlist('producto_id')
        almacen_id = request.form.get('almacen_id', type=int)
        
        if not ids_productos_a_ordenar or not almacen_id:
            flash('Error en la solicitud de alerta.', 'danger')
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
            organizacion_id=current_user.organizacion_id,
            almacen_id=almacen_id
        )
        db.session.add(nueva_oc)
        
        for prod in productos:
            stock_item = Stock.query.filter_by(producto_id=prod.id, almacen_id=almacen_id).first()
            if stock_item:
                cantidad_sugerida = stock_item.stock_maximo - stock_item.cantidad
            else:
                cantidad_sugerida = 5
            
            cantidad_final = max(1, cantidad_sugerida)
            
            # NUEVO: Calculamos las cajas basadas en el empaque
            factor_empaque = getattr(prod, 'unidades_por_caja', 1) or 1
            cajas_calculadas = cantidad_final / factor_empaque
            
            # Usamos costo en lugar de precio_unitario por si tu base de datos usa costo
            costo_unitario = getattr(prod, 'precio_unitario', getattr(prod, 'costo', 0))
            
            detalle = OrdenCompraDetalle(
                orden=nueva_oc,
                producto_id=prod.id,
                cantidad_solicitada=cantidad_final,
                costo_unitario_estimado=costo_unitario,
                cajas=cajas_calculadas # <- Aquí guardamos las cajas
            )
            db.session.add(detalle)
        
        db.session.commit()
        flash('Nueva Orden de Compra generada en "Borrador".', 'success')
        return redirect(url_for('lista_ordenes'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error al generar la orden: {e}', 'danger')
        return redirect(url_for('index'))
        
@app.route('/ordenes/recibir/<int:id>', methods=['POST'])
@login_required
def recibir_orden(id):
    """
    Recibe una OC y actualiza el Stock del Almacén correspondiente.
    Genera movimientos de entrada (Kardex).
    """
    # Usamos la consulta estándar compatible con tu versión de Flask
    orden = OrdenCompra.query.get_or_404(id)
    
    if orden.estado == 'recibida':
        flash('Esta orden ya fue recibida anteriormente.', 'warning')
        return redirect(url_for('lista_ordenes'))

    # Validación CRÍTICA: La orden debe tener un almacén destino
    if not orden.almacen_id:
        flash('Error: La orden no tiene un almacén asignado. No se puede ingresar el stock.', 'danger')
        return redirect(url_for('lista_ordenes'))

    try:
        org_id = orden.organizacion_id
        
        # Iteramos sobre los detalles (Variables originales del código que me diste)
        for detalle in orden.detalles:
            producto = detalle.producto
            cantidad = detalle.cantidad_solicitada
            
            # 1. ACTUALIZAR STOCK DEL ALMACÉN
            # Buscamos si el producto ya existe en ESTE almacén específico
            stock_item = Stock.query.filter_by(
                producto_id=producto.id,
                almacen_id=orden.almacen_id
            ).first()

            if stock_item:
                # Si existe, sumamos
                stock_item.cantidad += cantidad
                db.session.add(stock_item) # Aseguramos persistencia
            else:
                # Si no existe, lo creamos en este almacén
                nuevo_stock = Stock(
                    producto_id=producto.id,
                    almacen_id=orden.almacen_id,
                    cantidad=cantidad,
                    stock_minimo=5,  # Valores por defecto
                    stock_maximo=100
                )
                db.session.add(nuevo_stock)

            # 2. REGISTRAR MOVIMIENTO
            # CORRECCIÓN: Se agrega 'almacen_id' obligatorio para evitar NotNullViolation
            movimiento = Movimiento(
                producto_id=producto.id,
                cantidad=cantidad,
                tipo='entrada',
                fecha=datetime.now(),
                motivo=f'Recepción de OC #{orden.id}',
                orden_compra_id=orden.id,
                organizacion_id=org_id,
                almacen_id=orden.almacen_id  # <--- ¡ESTA LÍNEA ES LA SOLUCIÓN!
            )
            db.session.add(movimiento)
            
            # Opcional: Si aún usas el contador global en Producto, lo actualizamos también
            if hasattr(producto, 'cantidad_stock'):
                producto.cantidad_stock = (producto.cantidad_stock or 0) + cantidad
                db.session.add(producto)
        
        # 3. Finalizar Orden
        orden.estado = 'recibida'
        orden.fecha_recepcion = datetime.now()
        db.session.add(orden)
        
        db.session.commit()
        flash(f'¡Orden recibida! Stock ingresado correctamente al almacén: {orden.almacen.nombre}', 'success')
        
    except Exception as e:
        db.session.rollback()
        # Mejoramos el mensaje de error para que sea más legible si vuelve a pasar
        flash(f'Error al recibir la orden: {str(e)}', 'danger')
        print(f"DEBUG ERROR RECIBIR: {e}") 
    
    return redirect(url_for('lista_ordenes'))

@app.route('/orden/<int:id>/enviar', methods=['POST'])
@login_required
@check_permission('perm_create_oc_standard')
def enviar_orden(id):
    orden = OrdenCompra.query.filter_by(
        id=id, 
        organizacion_id=current_user.organizacion_id
    ).first_or_404()

    if orden.estado in ['borrador', 'Pendiente']:
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
    """ Genera un PDF profesional de la Orden de Compra incluyendo enlaces de proveedor. """
    orden = OrdenCompra.query.filter_by(
        id=id, 
        organizacion_id=current_user.organizacion_id
    ).first_or_404()
    org = orden.organizacion
    proveedor = orden.proveedor
    
    # --- CONFIGURACIÓN DE PÁGINA ---
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                            rightMargin=inch, leftMargin=inch,
                            topMargin=0.5*inch, bottomMargin=inch)
    story = []
    styles = getSampleStyleSheet()
    
    # --- ESTILOS ---
    fuente_base = org.tipo_letra if org.tipo_letra in ['Helvetica', 'Times-Roman', 'Courier'] else 'Helvetica'
    color_primario = colors.HexColor(org.color_primario) if org.color_primario else colors.darkblue
    
    # Estilos de Texto
    style_brand_title = ParagraphStyle(name='BrandTitle', parent=styles['Heading1'], fontName=f'{fuente_base}-Bold', fontSize=20, leading=22, textColor=colors.black, spaceAfter=2)
    style_brand_sub = ParagraphStyle(name='BrandSub', parent=styles['Normal'], fontName=fuente_base, fontSize=10, leading=12, textColor=colors.gray)
    style_normal = ParagraphStyle(name='MiNormal', parent=styles['Normal'], fontName=fuente_base, fontSize=10, leading=12)
    style_bold = ParagraphStyle(name='MiBold', parent=styles['Normal'], fontName=f'{fuente_base}-Bold', fontSize=10, leading=12)
    style_th = ParagraphStyle(name='MiTH', parent=styles['Normal'], fontName=f'{fuente_base}-Bold', fontSize=10, textColor=colors.white, alignment=TA_CENTER)
    
    # Estilos para Total
    style_total_label = ParagraphStyle(name='TotalLabel', parent=styles['Normal'], fontName=f'{fuente_base}-Bold', fontSize=11, alignment=TA_RIGHT)
    style_total_value = ParagraphStyle(name='TotalValue', parent=styles['Normal'], fontName=f'{fuente_base}-Bold', fontSize=11, alignment=TA_RIGHT)

    # ==========================================
    # 1. ENCABEZADO PERSONALIZADO (Logo + Texto)
    # ==========================================
    logo_element = []
    if org.logo_url:
        logo_path = os.path.join(app.config['UPLOAD_FOLDER'], org.logo_url)
        if os.path.exists(logo_path):
            img = ReportLabImage(logo_path)
            max_h = 1.0 * inch
            aspect = img.imageWidth / float(img.imageHeight)
            img.drawHeight = max_h
            img.drawWidth = max_h * aspect
            logo_element.append(img)
    
    text_elements = []
    texto_p = org.header_titulo if org.header_titulo else org.nombre
    text_elements.append(Paragraph(texto_p, style_brand_title))
    if org.header_subtitulo:
        text_elements.append(Paragraph(org.header_subtitulo, style_brand_sub))

    if logo_element:
        data_header = [[logo_element, text_elements]]
        col_widths = [1.5*inch, 4.5*inch]
    else:
        data_header = [[text_elements]]
        col_widths = [6*inch]

    t_header = Table(data_header, colWidths=col_widths)
    t_header.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(t_header)
    
    # Barra separadora de color
    story.append(Table([['']], colWidths=[6.2*inch], rowHeights=[2], style=TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), color_primario)
    ])))
    story.append(Spacer(1, 0.2*inch))

    # ==========================================
    # 2. INFORMACIÓN (PROVEEDOR Y ORDEN)
    # ==========================================
    p_email = getattr(proveedor, 'email', getattr(proveedor, 'correo', getattr(proveedor, 'contacto_email', '-')))
    p_tel = getattr(proveedor, 'telefono', getattr(proveedor, 'celular', '-'))
    p_contacto = getattr(proveedor, 'contacto', getattr(proveedor, 'nombre_contacto', '-'))

    info_proveedor = [
        Paragraph("<b>PROVEEDOR:</b>", style_normal),
        Paragraph(f"{proveedor.nombre}", style_bold),
        Paragraph(f"Contacto: {p_contacto}", style_normal),
        Paragraph(f"Email: {p_email}", style_normal),
        Paragraph(f"Tel: {p_tel}", style_normal),
    ]

    info_orden = [
        Paragraph(f"<b>ORDEN DE COMPRA #{orden.id}</b>", style_brand_title),
        Paragraph(f"<b>Fecha:</b> {orden.fecha_creacion.strftime('%d/%m/%Y')}", style_normal),
        Paragraph(f"<b>Estado:</b> {orden.estado}", style_normal),
        Paragraph(f"<b>Almacén:</b> {orden.almacen.nombre if orden.almacen else 'General'}", style_normal),
    ]

    t_info = Table([[info_proveedor, info_orden]], colWidths=[3.5*inch, 2.7*inch])
    t_info.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(t_info)
    story.append(Spacer(1, 0.2*inch))

    # ==========================================
    # 3. TABLA DE PRODUCTOS (CON ENLACES)
    # ==========================================
    headers = [
        Paragraph("Producto / SKU", style_th),
        Paragraph("Cajas", style_th),
        Paragraph("Unidades", style_th),
        Paragraph("Costo U.", style_th),
        Paragraph("Subtotal", style_th)
    ]
    
    data_table = [headers]
    total_general = 0
    
    for detalle in orden.detalles:
        subtotal = detalle.cantidad_solicitada * detalle.costo_unitario_estimado
        total_general += subtotal
        
        factor_empaque = getattr(detalle.producto, 'unidades_por_caja', 1) or 1
        cajas = getattr(detalle, 'cajas', 0)
        cajas_str = f"{cajas:g}" if cajas else "0"
        
        # --- LÓGICA DE ENLACE ---
        # Priorizamos el enlace guardado en el detalle de la orden, si no existe, usamos el del catálogo
        enlace_url = getattr(detalle, 'enlace_proveedor', None)
        if not enlace_url:
            enlace_url = getattr(detalle.producto, 'enlace_proveedor', None)

        # Construimos la descripción
        desc = f"<b>{detalle.producto.nombre}</b><br/>SKU: {detalle.producto.codigo}<br/><font color='gray' size='8'>Empaque: {factor_empaque} ud(s)</font>"
        
        # Si existe enlace, lo añadimos en pequeño y azul
        if enlace_url:
            # ReportLab interpreta etiquetas font básicas. Acortamos la URL visual si es muy larga.
            display_url = (enlace_url[:50] + '...') if len(enlace_url) > 53 else enlace_url
            desc += f"<br/><font color='blue' size='7'>{display_url}</font>"
        
        row = [
            Paragraph(desc, style_normal),
            Paragraph(cajas_str, style_normal),
            Paragraph(str(int(detalle.cantidad_solicitada)), style_normal),
            Paragraph(f"${detalle.costo_unitario_estimado:,.2f}", style_normal),
            Paragraph(f"${subtotal:,.2f}", style_normal)
        ]
        data_table.append(row)

    # FILA DE TOTAL
    row_total = [
        '', '', '', 
        Paragraph("TOTAL:", style_total_label), 
        Paragraph(f"${total_general:,.2f}", style_total_value)
    ]
    data_table.append(row_total)

    col_widths_prod = [2.4*inch, 0.8*inch, 0.8*inch, 1.0*inch, 1.2*inch]
    t_productos = Table(data_table, colWidths=col_widths_prod, repeatRows=1)
    
    estilos = [
        ('BACKGROUND', (0,0), (-1,0), color_primario),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-2), 0.5, colors.black), 
        ('ALIGN', (1,1), (2,-2), 'CENTER'),
        ('ALIGN', (3,1), (-1,-1), 'RIGHT'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('SPAN', (0,-1), (2,-1)),
        ('LINEABOVE', (0,-1), (-1,-1), 1, colors.black),
        ('BACKGROUND', (3,-1), (-1,-1), colors.whitesmoke),
        ('BOX', (3,-1), (4,-1), 0.5, colors.black),
    ]
    
    t_productos.setStyle(TableStyle(estilos))
    story.append(t_productos)

    # --- GENERAR Y ENVIAR ---
    doc.build(story)
    buffer.seek(0)
    filename = f"OC_{orden.id}_{secure_filename(org.nombre)}.pdf"
    return send_file(buffer, as_attachment=False, download_name=filename, mimetype='application/pdf')

@app.route('/orden/nueva/manual', methods=['GET', 'POST'])
@login_required
@check_permission('perm_create_oc_standard')
def nueva_orden_manual():
    """ Crea una nueva Orden de Compra manualmente. """
    
    if request.method == 'POST':
        try:
            proveedor_id = request.form.get('proveedor_id')
            almacen_id = request.form.get('almacen_id') # Nuevo campo Multi-Almacén
            
            if not proveedor_id:
                flash("Debes seleccionar un proveedor.", "warning")
                return redirect(request.url)

            # 1. Crear la Cabecera de la Orden
            nueva_orden = OrdenCompra(
                proveedor_id=proveedor_id,
                organizacion_id=current_user.organizacion_id,
                creador_id=current_user.id,
                estado='borrador', # <-- CORRECCIÓN: Debe nacer como borrador
                almacen_id=almacen_id if almacen_id else None # Guardamos el almacén destino
            )
            db.session.add(nueva_orden)
            db.session.flush() # Para obtener el ID de la orden antes de seguir

            # 2. Procesar las líneas de productos
            productos_ids = request.form.getlist('producto_id[]')
            cantidades = request.form.getlist('cantidad[]')
            costos = request.form.getlist('costo[]')
            cajas_lista = request.form.getlist('cajas[]') # <-- Capturamos las cajas
            enlaces_lista = request.form.getlist('enlace[]') # <-- NUEVO: Capturamos los enlaces

            for i in range(len(productos_ids)):
                if productos_ids[i] and float(cantidades[i]) > 0:
                    
                    # Extraer el valor de las cajas de forma segura
                    try:
                        cajas_val = float(cajas_lista[i])
                    except (IndexError, ValueError, TypeError):
                        cajas_val = 0.0
                        
                    # NUEVO: Extraer el enlace de forma segura
                    try:
                        enlace_val = enlaces_lista[i]
                    except IndexError:
                        enlace_val = ''
                    
                    detalle = OrdenCompraDetalle( 
                        orden_id=nueva_orden.id,
                        producto_id=productos_ids[i],
                        cantidad_solicitada=float(cantidades[i]),
                        costo_unitario_estimado=float(costos[i]),
                        cajas=cajas_val, # <-- Guardamos las cajas
                        enlace_proveedor=enlace_val # <-- CORRECCIÓN: Guardamos en enlace_proveedor
                    )
                    db.session.add(detalle)

            db.session.commit()
            flash(f"Orden #{nueva_orden.id} creada exitosamente en estado borrador.", "success")
            return redirect(url_for('lista_ordenes'))

        except Exception as e:
            db.session.rollback()
            flash(f"Error al crear orden: {e}", "danger")
            return redirect(request.url)

    # --- MÉTODO GET: Renderizar el formulario ---
    org_id = current_user.organizacion_id
    proveedores = Proveedor.query.filter_by(organizacion_id=org_id).all()
    almacenes = Almacen.query.filter_by(organizacion_id=org_id).all()

    # Convertir productos a diccionario para que tojson funcione
    productos_query = Producto.query.filter_by(organizacion_id=org_id).all()
    productos_lista = []
    for p in productos_query:
        productos_lista.append({
            'id': p.id,
            'nombre': p.nombre,
            'codigo': p.codigo,
            'precio_unitario': getattr(p, 'precio_unitario', getattr(p, 'costo', 0)),
            'proveedor_id': p.proveedor_id,
            'unidades_por_caja': getattr(p, 'unidades_por_caja', 1),
            'enlace': getattr(p, 'enlace_proveedor', '') # <-- CORRECCIÓN: Leemos enlace_proveedor
        })
    
    return render_template('orden_form.html', 
                           titulo="Nueva Orden de Compra",
                           orden=None,
                           proveedores=proveedores,
                           productos=productos_lista,
                           almacenes=almacenes)

@app.route('/orden/<int:id>')
@login_required
@check_permission('perm_view_dashboard')
def ver_orden(id):
    """ Muestra el detalle de una Orden de Compra (Solo lectura). """
    orden = OrdenCompra.query.filter_by(
        id=id, 
        organizacion_id=current_user.organizacion_id
    ).first_or_404()
    return render_template('orden_detalle.html', 
                           orden=orden, 
                           titulo=f"Detalle de Orden #{orden.id}")

@app.route('/orden/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@check_permission('perm_create_oc_standard')
def editar_orden(id):
    orden = OrdenCompra.query.filter_by(
        id=id, 
        organizacion_id=current_user.organizacion_id
    ).first_or_404()

    if orden.estado != 'borrador': # <-- CORRECCIÓN: Ajustado a 'borrador'
        flash('Solo se pueden editar órdenes en estado "Borrador".', 'warning')
        return redirect(url_for('ver_orden', id=id))

    org_id = orden.organizacion_id
    proveedores = Proveedor.query.filter_by(organizacion_id=org_id).all()
    almacenes = Almacen.query.filter_by(organizacion_id=org_id).all()
    
    # NUEVO: Lista de productos construida como diccionarios (igual que en crear manual)
    productos_query = Producto.query.filter_by(organizacion_id=org_id).all()
    productos_lista = []
    for p in productos_query:
        productos_lista.append({
            'id': p.id,
            'nombre': p.nombre,
            'codigo': p.codigo,
            'precio_unitario': getattr(p, 'precio_unitario', getattr(p, 'costo', 0)),
            'proveedor_id': p.proveedor_id,
            'unidades_por_caja': getattr(p, 'unidades_por_caja', 1), # <-- Aseguramos que el frontend sepa cuantas cajas
            'enlace': getattr(p, 'enlace_proveedor', '') # <-- CORRECCIÓN: Leemos enlace_proveedor
        })
    
    if request.method == 'POST':
        try:
            orden.proveedor_id = request.form.get('proveedor_id')
            
            # Borramos detalles anteriores
            OrdenCompraDetalle.query.filter_by(orden_id=orden.id).delete()
            
            # Capturamos del formulario
            productos_ids = request.form.getlist('producto_id[]')
            cantidades = request.form.getlist('cantidad[]')
            costos = request.form.getlist('costo[]')
            cajas_lista = request.form.getlist('cajas[]')
            enlaces_lista = request.form.getlist('enlace[]') # <-- ¡NUEVO! Capturamos enlaces editados

            if not productos_ids:
                 flash('La orden debe tener al menos un producto.', 'danger')
                 db.session.rollback()
                 return render_template('orden_form.html',
                                        titulo=f"Editar Orden de Compra #{orden.id}",
                                        proveedores=proveedores,
                                        productos=productos_lista,
                                        almacenes=almacenes,
                                        orden=orden)
            
            # Llenamos los nuevos detalles usando el loop seguro por índices
            for i in range(len(productos_ids)):
                prod_id = productos_ids[i]
                cant = cantidades[i]
                cost = costos[i]

                if not prod_id or not cant or not cost:
                    continue 
                
                # Extraer el valor de cajas protegiendo contra listas vacías
                try:
                    cajas_val = float(cajas_lista[i])
                except (IndexError, ValueError, TypeError):
                    cajas_val = 0.0

                # NUEVO: Extraer el enlace de forma segura
                try:
                    enlace_val = enlaces_lista[i]
                except IndexError:
                    enlace_val = ''

                detalle = OrdenCompraDetalle(
                    orden_id=orden.id,
                    producto_id=int(prod_id),
                    cantidad_solicitada=int(cant),
                    costo_unitario_estimado=float(cost),
                    cajas=cajas_val,
                    enlace_proveedor=enlace_val # <-- Lo guardamos en BD
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
                                   almacenes=almacenes,
                                   orden=orden)

    return render_template('orden_form.html', 
                           titulo=f"Editar Orden de Compra #{orden.id}",
                           proveedores=proveedores,
                           productos=productos_lista, # <-- Mandamos lista de diccionarios
                           almacenes=almacenes,
                           orden=orden)

@app.route('/orden/<int:id>/cancelar', methods=['POST'])
@login_required
@check_permission('perm_create_oc_standard')
def cancelar_orden(id):
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

@app.route('/orden/<int:id>/eliminar', methods=['POST'])
@login_required
@check_permission('perm_create_oc_standard') # Usamos el mismo permiso de crear/editar
def eliminar_orden(id):
    """
    Maneja la eliminación de órdenes:
    - Si estaba Pendiente: Funciona como 'Cancelar y Eliminar' (Automático).
    - Si estaba Recibida: Funciona como 'Limpiar Historial'.
    """
    orden = OrdenCompra.query.filter_by(
        id=id, 
        organizacion_id=current_user.organizacion_id
    ).first_or_404()
    
    # Validaciones de seguridad opcionales
    # (Por ejemplo, impedir borrar si ya tiene movimientos de stock complejos asociados, 
    # aunque en este sistema simple asumimos que al borrar la OC no revertimos el stock histórico, solo borramos el papel).
    
    estado_anterior = orden.estado
    
    try:
        # Primero eliminamos los detalles para evitar errores de integridad (si no hay cascada configurada)
        OrdenDetalle.query.filter_by(orden_id=orden.id).delete()
        
        # Ahora eliminamos la cabecera
        db.session.delete(orden)
        db.session.commit()
        
        if estado_anterior == 'Pendiente':
            flash(f'Orden #{id} cancelada y eliminada correctamente.', 'success')
        else:
            flash(f'Orden #{id} eliminada del historial.', 'info')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar la orden: {e}', 'danger')
        
    return redirect(url_for('lista_ordenes'))

# =============================================
# RUTAS PARA OC DE PROYECTO
# =============================================

@app.route('/proyectos-oc')
@login_required
@check_org_permission
@check_permission('perm_create_oc_proyecto')
def lista_proyectos_oc():
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
    proyecto_oc = get_item_or_404(ProyectoOC, id)
    return render_template('proyecto_oc_detalle.html', 
                           proyecto_oc=proyecto_oc, 
                           titulo=f"Detalle OC Proyecto #{proyecto_oc.id}")

@app.route('/proyecto-oc/nueva', methods=['GET', 'POST'])
@login_required
@check_org_permission
@check_permission('perm_create_oc_proyecto')
def nuevo_proyecto_oc():
    org_id = current_user.organizacion_id
    
    # 1. Preparar Productos para JS
    productos_query = Producto.query.filter_by(organizacion_id=org_id).all()
    productos_lista = []
    for p in productos_query:
        productos_lista.append({
            'id': p.id,
            'nombre': p.nombre,
            'codigo': p.codigo,
            'precio_unitario': p.precio_unitario,
        })
        
    # 2. Preparar Proveedores para JS (CORRECCIÓN AQUÍ)
    proveedores_query = Proveedor.query.filter_by(organizacion_id=org_id).order_by(Proveedor.nombre).all()
    proveedores_lista = [{'id': p.id, 'nombre': p.nombre} for p in proveedores_query]

    # 3. Obtener Almacenes (siguen siendo objetos, se usan en un bucle Jinja normal)
    almacenes = Almacen.query.filter_by(organizacion_id=org_id).all()

    if request.method == 'POST':
        try:
            nombre_proyecto = request.form.get('nombre_proyecto')
            almacen_id = request.form.get('almacen_id')
            
            if not nombre_proyecto:
            flash("El nombre del proyecto es obligatorio.", "danger")
                # Usamos return para no lanzar excepción y perder datos del form
                return render_template('proyecto_oc_form.html', 
                           titulo="Crear OC de Proyecto",
                           productos=productos_lista,
                           proveedores=proveedores_lista,
                           almacenes=almacenes,
                           proyecto_oc=None,
                           detalles_json=None)

            nueva_proyecto_oc = ProyectoOC(
                nombre_proyecto=nombre_proyecto,
                creador_id=current_user.id,
                organizacion_id=org_id,
                almacen_id=almacen_id
            )
            db.session.add(nueva_proyecto_oc)

            tipos = request.form.getlist('tipo_item[]')
            productos_existentes_ids = request.form.getlist('producto_id_existente[]') 
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
                    # Asegurar que es un entero válido
                    prod_id_val = int(productos_existentes_ids[i]) if productos_existentes_ids[i].isdigit() else 0
                    if prod_id_val > 0:
                        detalle.producto_id = prod_id_val
                    else:
                         detalle.producto_id = None # Evitar error de FK
                else: 
                    detalle.descripcion_nuevo = productos_nuevos[i]
                
                db.session.add(detalle)

            db.session.commit()
            flash(f'OC de Proyecto #{nueva_proyecto_oc.id} creada en "Borrador".', 'success')
            return redirect(url_for('lista_proyectos_oc'))

        except Exception as e:
            db.session.rollback()
            print(f"ERROR OC PROYECTO: {e}") # Para ver en logs de Render
            flash(f'Error al crear la OC de Proyecto: {e}', 'danger')
    
    return render_template('proyecto_oc_form.html', 
                           titulo="Crear OC de Proyecto",
                           productos=productos_lista,
                           proveedores=proveedores_lista, # <-- Pasamos la lista corregida
                           almacenes=almacenes,
                           proyecto_oc=None,
                           detalles_json=None)

@app.route('/proyecto-oc/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@check_permission('perm_create_oc_proyecto')
def editar_proyecto_oc(id):
    proyecto_oc = get_item_or_404(ProyectoOC, id)
    org_id = proyecto_oc.organizacion_id

    if proyecto_oc.estado != 'borrador':
        flash('Solo se pueden editar Órdenes de Proyecto en estado "Borrador".', 'warning')
        return redirect(url_for('ver_proyecto_oc', id=id))

    if request.method == 'POST':
        try:
            proyecto_oc.nombre_proyecto = request.form.get('nombre_proyecto')
            ProyectoOCDetalle.query.filter_by(proyecto_oc_id=id).delete()
            
            tipos = request.form.getlist('tipo_item[]')
            productos_existentes_ids = request.form.getlist('producto_id_existente[]') 
            productos_nuevos = request.form.getlist('producto_nuevo_descripcion[]')
            cantidades = request.form.getlist('cantidad[]')
            costos = request.form.getlist('costo[]')
            proveedores_sugeridos = request.form.getlist('proveedor_sugerido[]')

            for i in range(len(tipos)):
                if not cantidades[i] or not costos[i]: continue 
                detalle = ProyectoOCDetalle(
                    proyecto_oc_id=id,
                    cantidad=int(cantidades[i]),
                    costo_unitario=float(costos[i]),
                    proveedor_sugerido=proveedores_sugeridos[i]
                )
                if tipos[i] == 'existente':
                    prod_id_val = int(productos_existentes_ids[i]) if productos_existentes_ids[i].isdigit() else 0
                    if prod_id_val > 0: detalle.producto_id = prod_id_val
                    else: detalle.producto_id = None
                else: 
                    detalle.descripcion_nuevo = productos_nuevos[i]
                db.session.add(detalle)

            db.session.commit()
            flash(f'OC de Proyecto #{proyecto_oc.id} actualizada.', 'success')
            return redirect(url_for('ver_proyecto_oc', id=id))

        except Exception as e:
            db.session.rollback()
            print(f"ERROR EDITAR OC PROYECTO: {e}")
            flash(f'Error al actualizar la OC de Proyecto: {e}', 'danger')
            return redirect(url_for('editar_proyecto_oc', id=id))
    
    # --- GET: Preparar datos ---
    productos_query = Producto.query.filter_by(organizacion_id=org_id).all()
    productos_lista = []
    for p in productos_query:
        productos_lista.append({
            'id': p.id, 'nombre': p.nombre, 'codigo': p.codigo, 'precio_unitario': p.precio_unitario
        })
        
    # CORRECCIÓN AQUÍ TAMBIÉN:
    proveedores_query = Proveedor.query.filter_by(organizacion_id=org_id).order_by(Proveedor.nombre).all()
    proveedores_lista = [{'id': p.id, 'nombre': p.nombre} for p in proveedores_query]

    almacenes = Almacen.query.filter_by(organizacion_id=org_id).all()
    
    detalles_json = []
    for d in proyecto_oc.detalles:
        detalles_json.append({
            'tipo': 'existente' if d.producto_id else 'nuevo',
            'producto_id': d.producto_id,
            'descripcion_nuevo': d.descripcion_nuevo,
            'cantidad': d.cantidad,
            'costo_unitario': d.costo_unitario,
            'proveedor_sugerido': d.proveedor_sugerido
        })
    
    return render_template('proyecto_oc_form.html', 
                           titulo=f"Editar OC de Proyecto #{proyecto_oc.id}",
                           productos=productos_lista,
                           proveedores=proveedores_lista, # <-- Pasamos la lista corregida
                           almacenes=almacenes,
                           proyecto_oc=proyecto_oc,
                           detalles_json=detalles_json)

@app.route('/proyecto-oc/<int:id>/pdf')
@login_required
@check_permission('perm_create_oc_proyecto')
def generar_proyecto_oc_pdf(id):
    proyecto_oc = get_item_or_404(ProyectoOC, id)
    
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

    story.append(Paragraph(f"OC DE PROYECTO #{proyecto_oc.id}", styles['h1']))
    story.append(Paragraph(f"<b>Proyecto:</b> {proyecto_oc.nombre_proyecto}", styles['h3']))
    story.append(Spacer(1, 0.25 * inch))

    info_header = f"""
        <b>Creada por:</b> {proyecto_oc.creador.username}<br/>
        <b>Fecha Creación:</b> {proyecto_oc.fecha_creacion.strftime('%Y-%m-%d')}<br/>
        <b>Estado:</b> {proyecto_oc.estado.capitalize()}
    """
    story.append(Paragraph(info_header, styles['BodyText']))
    story.append(Spacer(1, 0.5 * inch))

    data = [[
        Paragraph('Tipo', style_header), 
        Paragraph('Descripción', style_header), 
        Paragraph('Proveedor Sug.', style_header),
        Paragraph('Cant.', style_header),
        Paragraph('Costo Unit.', style_header),
        Paragraph('Subtotal', style_header)
    ]]
    
    for detalle in proyecto_oc.detalles:
        tipo = Paragraph("Inventario" if detalle.producto_id else "Nuevo", style_left)
        descripcion = Paragraph(detalle.descripcion, style_left)
        proveedor = Paragraph(detalle.proveedor_sugerido or 'N/A', style_left)
        cantidad = Paragraph(str(detalle.cantidad), style_right)
        costo_unit = Paragraph(f"${detalle.costo_unitario:.2f}", style_right)
        subtotal = Paragraph(f"${detalle.subtotal:.2f}", style_right)
        data.append([tipo, descripcion, proveedor, cantidad, costo_unit, subtotal])

    data.append([
        '', '', '', '', 
        Paragraph('TOTAL (Est.):', style_total_label), 
        Paragraph(f"${proyecto_oc.costo_total:.2f}", style_total_value)
    ])

    style = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E9ECEF")),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 8),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, colors.HexColor("#F8F9FA")]), 
        ('GRID', (0,0), (-1,-2), 1, colors.HexColor("#DEE2E6")),
        ('BOX', (0,0), (-1,-2), 1, colors.HexColor("#DEE2E6")),
        ('BACKGROUND', (0,-1), (5,-1), colors.white),
        ('GRID', (4,-1), (5,-1), 1, colors.HexColor("#DEE2E6")),
        ('SPAN', (0,-1), (3,-1)),
    ])
    
    tabla_oc = Table(data, colWidths=[0.8*inch, 2.2*inch, 1.5*inch, 0.5*inch, 0.75*inch, 0.75*inch])
    tabla_oc.setStyle(style)
    story.append(tabla_oc)
    
    doc.build(story)
    
    fecha_str = proyecto_oc.fecha_creacion.strftime("%Y-%m-%d")
    filename = f"ProyectoOC_#{proyecto_oc.id}_{fecha_str}.pdf"

    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=False,
        download_name=filename,
        mimetype='application/pdf'
    )

@app.route('/proyecto-oc/<int:id>/cancelar', methods=['POST'])
@login_required
@check_permission('perm_create_oc_proyecto')
def cancelar_proyecto_oc(id):
    """ Cancela una OC de Proyecto (solo si está en 'borrador'). """
    proyecto_oc = get_item_or_404(ProyectoOC, id)
    
    if proyecto_oc.estado != 'borrador':
        flash('Error: Solo se pueden cancelar órdenes en estado "Borrador".', 'danger')
        return redirect(url_for('lista_proyectos_oc'))

    try:
        db.session.delete(proyecto_oc)
        db.session.commit()
        flash(f'OC de Proyecto #{proyecto_oc.id} cancelada exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al cancelar la orden: {e}', 'danger')
    
    return redirect(url_for('lista_proyectos_oc'))


# --- RUTAS DE CONTROL DE GASTOS ---
@app.route('/gastos')
@login_required
@check_org_permission
@check_permission('perm_view_gastos')
def lista_gastos():
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

@app.route('/gasto/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@check_permission('perm_view_gastos')
def editar_gasto(id):
    """ Edita un gasto existente. """
    gasto = get_item_or_404(Gasto, id)
    org_id = current_user.organizacion_id
    
    # Necesitamos las órdenes para el dropdown (si se quiere cambiar la asociación)
    ordenes = OrdenCompra.query.filter_by(organizacion_id=org_id).order_by(OrdenCompra.fecha_creacion.desc()).all()

    if request.method == 'POST':
        try:
            # Convertir la fecha del formulario
            fecha_gasto = datetime.strptime(request.form['fecha'], '%Y-%m-%d')
            
            # Manejo del ID de OC (puede ser cadena vacía si no se selecciona nada)
            oc_id = request.form.get('orden_compra_id')
            if oc_id == "" or oc_id == "None": 
                oc_id = None

            # Actualizar campos
            gasto.descripcion = request.form['descripcion']
            gasto.monto = float(request.form['monto'])
            gasto.categoria = request.form['categoria']
            gasto.fecha = fecha_gasto
            gasto.orden_compra_id = oc_id
            
            db.session.commit()
            flash('Gasto actualizado exitosamente', 'success')
            return redirect(url_for('lista_gastos'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar el gasto: {e}', 'danger')

    return render_template('gasto_form.html', 
                           titulo="Editar Gasto", 
                           ordenes=ordenes,
                           gasto=gasto) # <-- Pasamos el objeto gasto

@app.route('/gastos/exportar_excel')
@login_required
@check_permission('perm_view_gastos')
def exportar_gastos_excel():
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
    """ Página de Registro de nuevos usuarios (MODIFICADA para códigos). """
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        
        # --- LÓGICA DE CÓDIGO DE INVITACIÓN AÑADIDA ---
        org_id_asignada = None
        rol_asignado = 'user' # Por defecto es 'user'
        
        codigo = form.codigo_invitacion.data
        if codigo:
            # Si el usuario escribió un código, lo buscamos
            org = Organizacion.query.filter_by(codigo_invitacion=codigo.upper()).first()
            
            if not org:
                # El código es inválido, detenemos el registro y mostramos error
                flash('El código de invitación no es válido.', 'danger')
                return render_template('register.html', titulo="Registro", form=form)
            else:
                # ¡Código válido! Asignamos la organización y el rol
                org_id_asignada = org.id
                rol_asignado = 'user' # Los usuarios que se unen por código son 'user'
        # --- FIN DE LÓGICA AÑADIDA ---
        
        try:
            new_user = User(
                username=form.username.data,
                email=form.email.data,
                organizacion_id=org_id_asignada, # <-- MODIFICADO
                rol=rol_asignado                 # <-- MODIFICADO
            )
            new_user.set_password(form.password.data)
            
            db.session.add(new_user)
            db.session.commit()
            
            if org_id_asignada:
                flash(f'¡Cuenta creada! Has sido añadido a la organización {org.nombre}.', 'success')
            else:
                flash(f'¡Cuenta creada! Pide a un Super Admin que te asigne a una organización.', 'success')
            
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
        # Siempre mostramos el mismo mensaje para no revelar si un email está registrado (Buena práctica de seguridad)
        flash('Si existe una cuenta con ese e-mail, recibirás un correo con las instrucciones.', 'info')
        return redirect(url_for('login'))
        
    return render_template('forgot_password.html', titulo="Recuperar Contraseña", form=form)

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """ Página para ingresar la nueva contraseña (accedida desde el e-mail). """
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    
    try:
        # Intentamos decodificar el token con un máximo de 30 minutos (1800 segundos) de validez
        email = s.loads(token, salt='password-reset-salt', max_age=1800)
    except Exception:
        flash('El enlace de reseteo no es válido o ha expirado.', 'danger')
        return redirect(url_for('forgot_password'))
        
    user = User.query.filter_by(email=email).first()
    if user is None:
        flash('Usuario no encontrado.', 'danger')
        return redirect(url_for('login'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        try:
            # Usar set_password si lo tienes en el modelo, o generate_password_hash directo
            user.password_hash = generate_password_hash(form.password.data)
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

@app.route('/configuracion/plantilla', methods=['GET', 'POST'])
@login_required
@admin_required
def configurar_plantilla():
    organizacion = current_user.organizacion
    
    if request.method == 'POST':
        try:
            # 1. Guardar Logo (Código existente)
            if 'logo' in request.files:
                file = request.files['logo']
                if file.filename != '' and allowed_file(file.filename):
                    filename = secure_filename(f"logo_org_{organizacion.id}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    organizacion.logo_url = filename

            # 2. NUEVO: Guardar Textos Personalizados
            organizacion.header_titulo = request.form.get('header_titulo')
            organizacion.header_subtitulo = request.form.get('header_subtitulo')
            
            # 3. Guardar otros datos (Color, Fuente, etc.)
            organizacion.color_primario = request.form.get('color_primario', '#333333')
            organizacion.tipo_letra = request.form.get('tipo_letra', 'Helvetica')
            organizacion.direccion = request.form.get('direccion')
            organizacion.telefono = request.form.get('telefono')
            
            db.session.commit()
            flash('Diseño de marca actualizado correctamente.', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al guardar: {e}', 'danger')
            
        return redirect(url_for('configurar_plantilla'))
        
    return render_template('plantilla_config.html', org=organizacion)

    
# --- RUTAS DEL SUPER ADMIN ---

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
    """ Crea una nueva organización y le genera un código de invitación. """
    nombre = request.form.get('nombre')
    if not nombre:
        flash('El nombre de la organización no puede estar vacío.', 'danger')
        return redirect(url_for('super_admin'))
        
    existente = Organizacion.query.filter_by(nombre=nombre).first()
    if existente:
        flash(f'La organización "{nombre}" ya existe.', 'warning')
        return redirect(url_for('super_admin'))
        
    try:
        # --- LÓGICA DE CÓDIGO ÚNICO AÑADIDA ---
        codigo = None
        while codigo is None or Organizacion.query.filter_by(codigo_invitacion=codigo).first():
            # Genera un código de 8 caracteres (ej: "A1b-C2dE")
            codigo = secrets.token_urlsafe(6).upper() 
        # --- FIN DE LÓGICA AÑADIDA ---

        nueva_org = Organizacion(
            nombre=nombre,
            codigo_invitacion=codigo # <-- AÑADIDO
        )
        db.session.add(nueva_org)
        db.session.commit()
        flash(f'Organización "{nombre}" creada. Código de invitación: {codigo}', 'success')
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
def admin_panel():
    """ Panel para que un Admin gestione los usuarios de SU organización. """
    
    if current_user.rol == 'super_admin':
        return redirect(url_for('super_admin'))
        
    usuarios = User.query.filter_by(
        organizacion_id=current_user.organizacion_id
    ).order_by(User.username).all()
    
    forms = {}
    for user in usuarios:
        form = AdminPermissionForm()
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
    if current_user.rol == 'admin' and user_to_update.organizacion_id != current_user.organizacion_id:
        flash('No tienes permiso para editar a este usuario.', 'danger')
        return redirect(url_for('admin_panel'))
        
    if user_to_update.id == current_user.id and current_user.rol != 'super_admin':
        flash('No puedes editar tus propios permisos. Pide a otro admin o al Super Admin que lo haga.', 'warning')
        return redirect(url_for('admin_panel'))
    # --- FIN CHEQUEO ---

    form = AdminPermissionForm()
    
    if form.validate_on_submit():
        try:
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
        flash('Error de validación del formulario. Inténtalo de nuevo.', 'danger')
            
    return redirect(url_for('admin_panel'))

# --- Inicialización ---
if __name__ == '__main__':
    # Creación del superadmin solo se hace dentro del contexto si es necesario
    with app.app_context():
        crear_superadmin()
        
    # Lee el modo debug del archivo .env (Por defecto será False por seguridad)
    modo_debug = os.environ.get('FLASK_DEBUG', 'False') == 'True'
    app.run(host='0.0.0.0', port=5000, debug=modo_debug)
    app.run(debug=True, port=5000)
