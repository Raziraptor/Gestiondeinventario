import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from flask_mail import Mail, Message
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError
from werkzeug.security import generate_password_hash, check_password_hash
import io # Para manejar el PDF en memoria
import qrcode
from flask import send_file
import io
import csv
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, NamedStyle
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.styles import Font, PatternFill, Alignment, NamedStyle, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table as ExcelTable, TableStyleInfo
from flask import make_response # Para enviar el archivo CSV
from sqlalchemy import extract # Para filtrar por mes/año
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from datetime import datetime # Para la fecha actual
from datetime import datetime
from werkzeug.utils import secure_filename # Para limpiar nombres de archivo
from collections import defaultdict
from datetime import datetime
from collections import defaultdict
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, Email
from itsdangerous.url_safe import URLSafeTimedSerializer
import secrets # Para nombres de archivo aleatorios
from PIL import Image # Para procesar imágenes
from flask_wtf.file import FileField, FileAllowed # Para subir archivos

def save_picture(form_picture):
    """Guarda y redimensiona la foto de perfil subida."""
    # 1. Genera un nombre de archivo aleatorio
    random_hex = secrets.token_hex(8)
    # 2. Obtiene la extensión del archivo original (ej. 'jpg', 'png')
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    # 3. Define la ruta completa de guardado
    picture_path = os.path.join(app.root_path, 'static/uploads/profile_pics', picture_fn)

    # 4. Redimensiona la imagen a 125x125 (estilo Bootstrap)
    output_size = (125, 125)
    i = Image.open(form_picture)
    i.thumbnail(output_size)
    
    # 5. Guarda la imagen redimensionada
    i.save(picture_path)

    return picture_fn # Devuelve el nuevo nombre de archivo

# --- Configuración de la App ---

basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.jinja_env.add_extension('jinja2.ext.do')
# --- LÓGICA DE BASE DE DATOS MEJORADA ---
# Busca una 'DATABASE_URL' en las variables de entorno (para producción)
db_url = os.environ.get('DATABASE_URL')

if db_url:
    # Si estamos en producción (DigitalOcean), usa PostgreSQL
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
else:
    # Si estamos en local, usa el archivo sqlite
    print("ADVERTENCIA: No se encontró DATABASE_URL. Usando SQLite local.")
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'inventario.db')
# --- FIN DE LA LÓGICA ---
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limite de 16MB para las imágenes
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
db = SQLAlchemy(app)
# --- CONFIGURACIÓN DE LOGIN ---
login_manager = LoginManager()
login_manager.init_app(app)
# Si un usuario no logueado intenta ir a una pág. protegida,
# lo redirige a 'login'
login_manager.login_view = 'login'
# Mensaje de 'flash' que se mostrará
login_manager.login_message = 'Por favor, inicia sesión para acceder a esta página.'
login_manager.login_message_category = 'info'
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
# --- CONFIGURACIÓN DE FLASK-MAIL ---
# (Usa variables de entorno para seguridad)
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', 1]
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME') # Tu e-mail
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD') # Tu contraseña de aplicación
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME')

mail = Mail(app) # <-- Inicializa Mail
# --- FIN DE LA CONFIGURACIÓN DE MAIL ---
# Serializador para generar tokens seguros con tiempo de expiración
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# --- Modelos de la Base de Datos ---

class Proveedor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    contacto_email = db.Column(db.String(100))
    # Relación: Un proveedor puede tener muchos productos
    productos = db.relationship('Producto', backref='proveedor', lazy=True)

class Categoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    descripcion = db.Column(db.String(255), nullable=True)
    # Relación inversa: 'productos' nos dará la lista de productos en esta categoría

class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    # --- CAMBIO: Campo de texto reemplazado por Llave Foránea ---
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=True)
    categoria = db.relationship('Categoria', backref=db.backref('productos', lazy=True))
    # --- FIN DEL CAMBIO ---
    cantidad_stock = db.Column(db.Integer, nullable=False, default=0)
    stock_minimo = db.Column(db.Integer, nullable=False, default=5)
    stock_maximo = db.Column(db.Integer, nullable=False, default=100)
    precio_unitario = db.Column(db.Float, default=0.0)
    # Llave foránea para la relación con Proveedor
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'), nullable=True)
    # --- NUEVO CAMPO PARA LA IMAGEN ---
    imagen_url = db.Column(db.String(255), nullable=True) # Guarda el nombre del archivo
    
    # Propiedad para verificar alertas de stock (Funcionalidad 1)
    @property
    def estado_stock(self):
        if self.cantidad_stock < self.stock_minimo:
            return 'bajo' # Por debajo del mínimo
        elif self.cantidad_stock > self.stock_maximo:
            return 'exceso' # Por encima del máximo
        return 'ok'

class OrdenCompra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.now)
    fecha_recepcion = db.Column(db.DateTime, nullable=True)
    estado = db.Column(db.String(20), nullable=False, default='borrador')
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'), nullable=False)
    proveedor = db.relationship('Proveedor', backref=db.backref('ordenes_compra', lazy=True))
    detalles = db.relationship('OrdenCompraDetalle', backref='orden', lazy=True, cascade="all, delete-orphan")
    
    # --- NUEVAS LÍNEAS (AUDITORÍA) ---
    creador_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cancelado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    # --- FIN DE NUEVAS LÍNEAS ---
    
    @property
    def costo_total(self):
        # Calcula el costo total sumando los detalles
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
    categoria = db.Column(db.String(50), nullable=True) # Ej: 'Operativo', 'Materia Prima', 'Marketing'
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.now)
    
    # Opcional: Vincular un gasto a una orden de compra específica
    orden_compra_id = db.Column(db.Integer, db.ForeignKey('orden_compra.id'), nullable=True)
    orden_compra = db.relationship('OrdenCompra', backref=db.backref('gastos_asociados', lazy=True))

    def __repr__(self):
        return f'<Gasto {self.descripcion} - ${self.monto}>'
    
class Salida(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.now)
    motivo = db.Column(db.String(255), nullable=True)
    estado = db.Column(db.String(20), nullable=False, default='completada')
    
    # --- NUEVAS LÍNEAS (AUDITORÍA) ---
    creador_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cancelado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    # --- FIN DE NUEVAS LÍNEAS ---

class Movimiento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    producto = db.relationship('Producto', backref=db.backref('movimientos', lazy=True))
    
    cantidad = db.Column(db.Integer, nullable=False) 
    tipo = db.Column(db.String(20), nullable=False) 
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.now)
    motivo = db.Column(db.String(255), nullable=True) 
    
    orden_compra_id = db.Column(db.Integer, db.ForeignKey('orden_compra.id'), nullable=True)
    
    # --- NUEVAS LÍNEAS ---
    salida_id = db.Column(db.Integer, db.ForeignKey('salida.id'), nullable=True)
    salida = db.relationship('Salida', backref=db.backref('movimientos', lazy=True, cascade="all, delete-orphan"))
    # --- FIN DE NUEVAS LÍNEAS ---

    def __repr__(self):
        return f'<Movimiento {self.producto.nombre} ({self.cantidad})>'

# El modelo UserMixin incluye las propiedades estándar de Flask-Login
# (is_authenticated, is_active, is_anonymous, get_id())
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    image_file = db.Column(db.String(20), nullable=False, default='default.jpg')
    password_hash = db.Column(db.String(255), nullable=False) 

    # --- NUEVAS LÍNEAS (RELACIONES INVERSAS) ---
    ordenes_creadas = db.relationship('OrdenCompra', foreign_keys='OrdenCompra.creador_id', backref='creador', lazy=True)
    ordenes_canceladas = db.relationship('OrdenCompra', foreign_keys='OrdenCompra.cancelado_por_id', backref='cancelado_por', lazy=True)
    salidas_creadas = db.relationship('Salida', foreign_keys='Salida.creador_id', backref='creador', lazy=True)
    salidas_canceladas = db.relationship('Salida', foreign_keys='Salida.cancelado_por_id', backref='cancelado_por', lazy=True)
    # --- FIN DE NUEVAS LÍNEAS ---

    def set_password(self, password):
        """Crea un hash seguro para la contraseña."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verifica si la contraseña coincide con el hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'
    
@login_manager.user_loader
def load_user(user_id):
    """Callback para recargar el objeto User desde el ID de la sesión."""
    return User.query.get(int(user_id))

# --- FORMULARIOS DE AUTENTICACIÓN ---

class RegistrationForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired(), Length(min=4, max=80)])
    
    # --- NUEVO CAMPO ---
    email = StringField('E-mail', validators=[DataRequired(), Email(message='E-mail no válido.')])
    
    password = PasswordField('Contraseña', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Contraseña', 
                                     validators=[DataRequired(), EqualTo('password', message='Las contraseñas deben coincidir.')])
    submit = SubmitField('Registrarse')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Ese nombre de usuario ya existe. Por favor, elige otro.')
            
    # --- NUEVA FUNCIÓN DE VALIDACIÓN ---
    def validate_email(self, email):
        """Validador personalizado para asegurar que el e-mail no exista."""
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Ese e-mail ya está registrado. Por favor, usa otro.')

class LoginForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    submit = SubmitField('Iniciar Sesión')

# --- Rutas de la Aplicación ---

@app.route('/')
@login_required
def index():
    """ Dashboard Principal: Muestra todos los productos y alertas agrupadas """
    productos = Producto.query.all()
    
    # --- Lógica de Alertas (sin cambios) ---
    alertas_crudas = [p for p in productos if p.estado_stock == 'bajo']
    alertas_agrupadas = defaultdict(list)
    proveedor_desconocido = Proveedor(id=0, nombre="Proveedor no asignado")

    for alerta in alertas_crudas:
        if alerta.proveedor:
            alertas_agrupadas[alerta.proveedor.nombre].append(alerta)
        else:
            alertas_agrupadas[proveedor_desconocido.nombre].append(alerta)

    # --- Lógica de Filtros (sin cambios) ---
    categorias = Categoria.query.all()
    proveedores = Proveedor.query.all()

    # --- LÓGICA MODIFICADA PARA VERIFICAR ÓRDENES PENDIENTES ---
    # 1. Encontrar todas las OCs en 'borrador' O 'enviada'
    ordenes_pendientes = db.session.query(
        OrdenCompraDetalle.producto_id, 
        OrdenCompra.id, 
        User.username,
        OrdenCompra.estado  # <-- Añadimos el estado para la plantilla
    ).join(
        OrdenCompra, OrdenCompraDetalle.orden_id == OrdenCompra.id
    ).join(
        User, OrdenCompra.creador_id == User.id
    ).filter(
        # ¡CAMBIO CLAVE! Ahora busca ambos estados
        OrdenCompra.estado.in_(['borrador', 'enviada']) 
    ).all()

    # 2. Convertir en un mapa de búsqueda rápida {producto_id: info}
    pending_map = {} # <-- Renombrado de 'borrador_map'
    for prod_id, orden_id, username, estado in ordenes_pendientes:
        pending_map[prod_id] = {
            'orden_id': orden_id, 
            'username': username,
            'estado': estado # <-- Pasamos el estado a la plantilla
        }
    # --- FIN DE LA LÓGICA MODIFICADA ---

    return render_template('index.html', 
                           productos=productos, 
                           alertas_agrupadas=alertas_agrupadas,
                           categorias=categorias,
                           proveedores=proveedores,
                           pending_map=pending_map) # <-- Pasamos el mapa renombrado

@app.route('/producto/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_producto():
    # Estas listas se necesitan en GET y en caso de error en POST
    proveedores = Proveedor.query.all()
    categorias = Categoria.query.all()
    
    if request.method == 'POST':
        imagen_filename = None
        
        # --- 1. Función interna para repoblar el formulario en caso de error ---
        def repoblar_formulario_con_error():
            """
            Crea un objeto Producto temporal (sin guardar en BD) 
            con los datos del formulario para repoblar los campos.
            """
            producto_temporal = Producto(
                nombre=request.form.get('nombre'),
                codigo=request.form.get('codigo'),
                # Usamos 'int(val or 0) or None' para manejar campos vacíos
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
                                   producto=producto_temporal) # <-- Pasamos el objeto temporal
        # --- Fin de la función interna ---

        # 2. Lógica de la imagen
        if 'imagen' in request.files:
            file = request.files['imagen']
            if file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                imagen_filename = filename
            elif file.filename != '' and not allowed_file(file.filename):
                # --- CAMBIO AQUÍ ---
                flash('Tipo de archivo de imagen no permitido. Los demás datos se han conservado.', 'danger')
                return repoblar_formulario_con_error() # <-- USAMOS LA FUNCIÓN
        
        # 3. Lógica de guardado en BD
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
                proveedor_id=request.form.get('proveedor_id') or None
            )
            db.session.add(nuevo_prod)
            db.session.commit()
            flash('Producto creado exitosamente', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            # --- CAMBIO AQUÍ ---
            flash(f'Error al crear producto (quizás el SKU ya existe). Los datos se han conservado.', 'danger')
            return repoblar_formulario_con_error() # <-- USAMOS LA FUNCIÓN
            
    # --- Lógica GET (sin cambios) ---
    return render_template('producto_form.html', 
                           titulo="Nuevo Producto", 
                           proveedores=proveedores,
                           categorias=categorias,
                           producto=None)

@app.route('/producto/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_producto(id):
    producto = Producto.query.get_or_404(id)
    proveedores = Proveedor.query.all()
    categorias = Categoria.query.all()

    if request.method == 'POST':
        try:
            # --- 1. LÓGICA DE IMAGEN (LA PARTE QUE FALTABA) ---
            # Verificamos si se subió un archivo nuevo
            if 'imagen' in request.files:
                file = request.files['imagen']
                if file.filename != '' and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    
                    # --- ¡AQUÍ ESTÁ LA LÍNEA CLAVE! ---
                    # Actualizamos el campo 'imagen_url' en el objeto producto
                    producto.imagen_url = filename 
                    
                elif file.filename != '' and not allowed_file(file.filename):
                    flash('Tipo de archivo de imagen no permitido', 'danger')
                    return render_template('producto_form.html', 
                                           titulo="Editar Producto", 
                                           producto=producto,
                                           proveedores=proveedores,
                                           categorias=categorias)
            # --- FIN DE LA LÓGICA DE IMAGEN ---


            # --- 2. LÓGICA DE OTROS CAMPOS ---
            producto.nombre = request.form['nombre']
            producto.codigo = request.form['codigo']
            
            # (Aquí estaba la coma que ya corregimos)
            producto.categoria_id = request.form.get('categoria_id') or None
            
            producto.cantidad_stock = int(request.form['cantidad_stock'])
            producto.stock_minimo = int(request.form['stock_minimo'])
            producto.stock_maximo = int(request.form['stock_maximo'])
            producto.precio_unitario = float(request.form['precio_unitario'])
            producto.proveedor_id = request.form.get('proveedor_id') or None

            # --- 3. GUARDAR TODO ---
            db.session.commit()
            flash('Producto actualizado exitosamente', 'success')
            return redirect(url_for('index'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar producto: {e}', 'danger')

    # --- Lógica GET (sin cambios) ---
    return render_template('producto_form.html', 
                           titulo="Editar Producto", 
                           producto=producto,
                           proveedores=proveedores,
                           categorias=categorias)

@app.route('/producto/<int:id>/etiqueta')
@login_required
def generar_etiqueta(id):
    """ Genera una etiqueta en PDF con Código QR para un producto """
    producto = Producto.query.get_or_404(id)

    try:
        # --- 1. Preparar el PDF en memoria ---
        buffer = io.BytesIO()
        
        # Usamos un tamaño de etiqueta común (ej. 4x2 pulgadas)
        # Modificacion de etiqueta para uso de imagenes 01/11/2025
        # Convertimos pulgadas a puntos (1 pulgada = 72 puntos)
        label_width = 4 * inch
        label_height = 2.5 * inch
        
        c = canvas.Canvas(buffer, pagesize=(label_width, label_height))
        
        # --- 2. Generar el Código QR ---
        # El QR contendrá el código (SKU) del producto
        qr_img = qrcode.make(producto.codigo)
        qr_img_path = io.BytesIO()
        qr_img.save(qr_img_path, format='PNG')
        qr_img_path.seek(0)

        # --- FIX: Envolvemos el BytesIO con ImageReader ---
        qr_para_pdf = ImageReader(qr_img_path)

        # Dibujar el QR en el PDF (a la derecha)
        # Usamos 'inch' para posicionar fácilmente
        c.drawImage(
            qr_para_pdf,  # <--- ESTA ES LA LÍNEA CORREGIDA
            label_width - (1.6 * inch), # Posición X (derecha)
            0.6 * inch,                 # Posición Y (abajo)
            width=(1.4 * inch),         # Ancho del QR
            height=(1.4 * inch),        # Alto del QR
            preserveAspectRatio=True
        )

        # --- 3. Escribir texto en el PDF ---
        # Posicionamos el texto a la izquierda del QR
        text_x = 0.25 * inch
        text_y = label_height - (0.5 * inch)
        
        # Nombre del Producto (grande)
        c.setFont('Helvetica-Bold', 12)
        c.drawString(text_x, text_y, producto.nombre[:25]) # Limita a 25 caracteres
        
        # Código (SKU) (más pequeño)
        c.setFont('Helvetica', 10)
        c.drawString(text_x, text_y - (0.3 * inch), f"SKU: {producto.codigo}")
        
        # Precio (opcional)
        c.setFont('Helvetica', 10)
        c.drawString(text_x, text_y - (0.6 * inch), f"Precio: ${producto.precio_unitario:.2f}")

        # --- NUEVO: DIBUJAR LA IMAGEN DEL PRODUCTO (si existe) ---
        if producto.imagen_url:
            img_path = os.path.join(app.config['UPLOAD_FOLDER'], producto.imagen_url)
            if os.path.exists(img_path): # Verificar que la imagen realmente existe
                try:
                    # Cargar la imagen del disco
                    prod_img = ImageReader(img_path)
                    # Posicionarla a la izquierda del texto, debajo del nombre
                    c.drawImage(
                        prod_img,
                        0.1 * inch,             # Posición X
                        0.2 * inch,              # Posición Y
                        width=1.5 * inch,        # Ancho deseado
                        height=1.0 * inch,       # Alto deseado
                        preserveAspectRatio=True # Mantener proporciones
                    )
                except Exception as img_err:
                    print(f"Error al dibujar imagen en PDF: {img_err}")
                    # Puedes dibujar un mensaje de error o simplemente ignorar

        # --- 4. Finalizar y enviar el PDF ---
        c.showPage()
        c.save()
        
        buffer.seek(0) # Regresa al inicio del buffer

        # --- 1. Generar el nombre de archivo ---
        
        # Limpiamos el nombre del producto (ej. "Tornillos 1/2" -> "Tornillos_12")
        nombre_base = secure_filename(producto.nombre) 
        
        # Obtenemos la fecha de hoy (ej. "2025-11-01")
        fecha_str = datetime.now().strftime("%Y-%m-%d")
        
        # Creamos el nombre final
        nombre_archivo = f"{nombre_base}_{fecha_str}.pdf"

        # --- 2. Enviar el archivo ---
        return send_file(
            buffer,
            # Forzamos la descarga (en lugar de solo mostrarlo)
            as_attachment=False, 
            # Usamos nuestro nuevo nombre de archivo
            download_name=nombre_archivo,
            mimetype='application/pdf'
        )

    except Exception as e:
        flash(f'Error al generar etiqueta: {e}', 'danger')
        return redirect(url_for('index'))

@app.route('/producto/<int:id>/historial')
@login_required
def historial_producto(id):
    """ Muestra el Kardex (historial de movimientos) para un solo producto. """
    producto = Producto.query.get_or_404(id)
    
    # Gracias a la relación 'backref', podemos acceder a 'producto.movimientos'.
    # Los ordenamos por fecha, del más reciente al más antiguo.
    movimientos = sorted(producto.movimientos, key=lambda m: m.fecha, reverse=True)
    
    return render_template('historial_producto.html', 
                           producto=producto, 
                           movimientos=movimientos)

# --- RUTAS DE CATEGORÍAS ---

@app.route('/categorias')
@login_required
def lista_categorias():
    """ Muestra la lista de todas las categorías. """
    categorias = Categoria.query.all()
    return render_template('categorias.html', categorias=categorias)

@app.route('/categoria/nueva', methods=['GET', 'POST'])
@login_required
def nueva_categoria():
    """ Formulario para crear una nueva categoría. """
    if request.method == 'POST':
        try:
            nueva_cat = Categoria(
                nombre=request.form['nombre'],
                descripcion=request.form.get('descripcion') # .get() es seguro si está vacío
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
def editar_categoria(id):
    """ Formulario para editar una categoría existente. """
    categoria = Categoria.query.get_or_404(id)
    
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
def eliminar_categoria(id):
    """ 
    Elimina una categoría. 
    Primero, des-asigna todos los productos que la usan.
    """
    categoria_a_eliminar = Categoria.query.get_or_404(id)
    
    try:
        # 1. Encontrar todos los productos que usan esta categoría
        productos_afectados = Producto.query.filter_by(categoria_id=categoria_a_eliminar.id).all()
        
        # 2. Des-asignarlos (ponerlos en Nulo/N/A)
        for producto in productos_afectados:
            producto.categoria_id = None
            # (No es necesario db.session.add(producto), 
            # SQLAlchemy ya rastrea el cambio)
        
        # 3. Ahora sí, eliminar la categoría
        db.session.delete(categoria_a_eliminar)
        
        # 4. Guardar todos los cambios (la des-asignación Y la eliminación)
        db.session.commit()
        
        flash(f'Categoría "{categoria_a_eliminar.nombre}" eliminada. Los productos asociados fueron des-asignados.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar la categoría: {e}', 'danger')

    return redirect(url_for('lista_categorias'))

# --- RUTAS DE PROVEEDORES ---

@app.route('/proveedores')
@login_required
def lista_proveedores():
    proveedores = Proveedor.query.all()
    return render_template('proveedores.html', proveedores=proveedores)

@app.route('/proveedor/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_proveedor():
    if request.method == 'POST':
        try:
            nuevo_prov = Proveedor(
                nombre=request.form['nombre'],
                contacto_email=request.form['contacto_email']
            )
            db.session.add(nuevo_prov)
            db.session.commit()
            flash('Proveedor creado exitosamente', 'success')
            return redirect(url_for('lista_proveedores'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear proveedor: {e}', 'danger')
            
    return render_template('proveedor_form.html', titulo="Nuevo Proveedor")

@app.route('/salidas')
@login_required
def historial_salidas():
    """ 
    Muestra un historial de todos los lotes de Salida, 
    filtrado por mes y año.
    """
    
    # 1. Obtener los valores del filtro desde la URL
    mes = request.args.get('mes', type=int)
    ano = request.args.get('ano', type=int)
    
    # 2. Establecer valores por defecto (mes/año actual)
    ahora = datetime.now()
    if not mes:
        mes = ahora.month
    if not ano:
        ano = ahora.year

    # 3. Obtener listas para los dropdowns de filtros
    meses_lista = [
        (1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'), (4, 'Abril'), 
        (5, 'Mayo'), (6, 'Junio'), (7, 'Julio'), (8, 'Agosto'), 
        (9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre')
    ]

    # 4. Construir la consulta de base de datos dinámicamente
    query = Salida.query.filter(
        extract('month', Salida.fecha) == mes,
        extract('year', Salida.fecha) == ano
    )

    # 5. Ejecutar la consulta
    salidas = query.order_by(Salida.fecha.desc()).all()
    
    # 6. Renderizar la plantilla
    return render_template('salidas.html', 
                           salidas=salidas,
                           meses_lista=meses_lista,
                           mes_seleccionado=mes,
                           ano_seleccionado=ano)

@app.route('/salida/<int:id>')
@login_required
def ver_salida(id):
    """ Muestra el detalle de un solo lote de Salida. """
    salida = Salida.query.get_or_404(id)
    # Gracias al 'backref', salida.movimientos nos da la lista de productos
    return render_template('salida_detalle.html', salida=salida)

# --- RUTAS DE ÓRDENES DE COMPRA (OC) ---

@app.route('/ordenes')
@login_required
def lista_ordenes():
    """ 
    Muestra una lista de Órdenes de Compra, 
    filtrada por mes, año y proveedor.
    """
    
    # 1. Obtener los valores del filtro desde la URL
    mes = request.args.get('mes', type=int)
    ano = request.args.get('ano', type=int)
    prov_id = request.args.get('proveedor_id', type=int)
    
    # 2. Establecer valores por defecto (mes/año actual)
    ahora = datetime.now()
    if not mes:
        mes = ahora.month
    if not ano:
        ano = ahora.year

    # 3. Obtener listas para los dropdowns de filtros
    proveedores = Proveedor.query.order_by(Proveedor.nombre).all()
    meses_lista = [
        (1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'), (4, 'Abril'), 
        (5, 'Mayo'), (6, 'Junio'), (7, 'Julio'), (8, 'Agosto'), 
        (9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre')
    ]

    # 4. Construir la consulta de base de datos dinámicamente
    query = OrdenCompra.query
    
    # Filtrar por mes y año (siempre filtramos por un rango de fechas)
    query = query.filter(extract('month', OrdenCompra.fecha_creacion) == mes)
    query = query.filter(extract('year', OrdenCompra.fecha_creacion) == ano)

    # Filtrar por proveedor (solo si se seleccionó uno)
    if prov_id and prov_id != 0: # 0 significa "Todos"
        query = query.filter_by(proveedor_id=prov_id)

    # 5. Ejecutar la consulta
    ordenes = query.order_by(OrdenCompra.fecha_creacion.desc()).all()
    
    return render_template('ordenes.html', 
                           ordenes=ordenes,
                           proveedores=proveedores,
                           meses_lista=meses_lista,
                           mes_seleccionado=mes,
                           ano_seleccionado=ano,
                           prov_seleccionado=prov_id or 0) # Pasamos el ID seleccionado

@app.route('/orden/nueva', methods=['POST'])
@login_required
def nueva_orden():
    """ 
    Crea una nueva orden de compra (OC) en 'borrador' 
    basada en las sugerencias del dashboard.
    """
    try:
        # Obtenemos los IDs de los productos seleccionados desde el formulario del dashboard
        ids_productos_a_ordenar = request.form.getlist('producto_id')
        
        if not ids_productos_a_ordenar:
            flash('No se seleccionaron productos para la orden.', 'warning')
            return redirect(url_for('index'))

        # Buscamos los productos y agrupamos por proveedor
        productos = Producto.query.filter(Producto.id.in_(ids_productos_a_ordenar)).all()
        
        # Asumimos que todos los productos de esta tanda son del MISMO proveedor
        # (El formulario en index.html se asegurará de esto)
        proveedor_id_comun = productos[0].proveedor_id
        if not all(p.proveedor_id == proveedor_id_comun for p in productos):
            flash('Error: Los productos seleccionados deben ser del mismo proveedor.', 'danger')
            return redirect(url_for('index'))

        # Creamos la cabecera de la OC
        nueva_oc = OrdenCompra(
            proveedor_id=proveedor_id_comun,
            estado='borrador', # El usuario la revisará antes de 'enviarla'
            creador_id=current_user.id
        )
        db.session.add(nueva_oc)
        
        # Creamos los detalles (líneas de producto)
        for prod in productos:
            # Sugerimos ordenar la diferencia (max - actual)
            cantidad_sugerida = prod.stock_maximo - prod.cantidad_stock
            
            detalle = OrdenCompraDetalle(
                orden=nueva_oc, # Vincula al objeto OC
                producto_id=prod.id,
                cantidad_solicitada=max(1, cantidad_sugerida), # Ordenar al menos 1
                costo_unitario_estimado=prod.precio_unitario # Usamos el precio como estimado
            )
            db.session.add(detalle)
        
        db.session.commit()
        flash('Nueva Orden de Compra generada en "Borrador". Revísala y márcala como "Enviada".', 'success')
        return redirect(url_for('lista_ordenes'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error al generar la orden: {e}', 'danger')
        return redirect(url_for('index'))

@app.route('/orden/<int:id>/recibir', methods=['POST'])
@login_required
def recibir_orden(id):
    """ Marca una orden como 'recibida', actualiza el stock y REGISTRA EL MOVIMIENTO. """
    orden = OrdenCompra.query.get_or_404(id)
    
    if orden.estado == 'recibida':
        flash('Esta orden ya fue recibida anteriormente.', 'warning')
        return redirect(url_for('lista_ordenes'))

    try:
        # 1. Actualizar el stock de cada producto en la orden
        for detalle in orden.detalles:
            producto = detalle.producto
            producto.cantidad_stock += detalle.cantidad_solicitada
            db.session.add(producto)
            
            # --- NUEVA LÓGICA: REGISTRAR MOVIMIENTO DE ENTRADA ---
            movimiento = Movimiento(
                producto_id=producto.id,
                cantidad=detalle.cantidad_solicitada, # Positivo
                tipo='entrada',
                fecha=datetime.now(),
                motivo=f'Recepción de OC #{orden.id}',
                orden_compra_id=orden.id
            )
            db.session.add(movimiento)
            # --- FIN DE LA NUEVA LÓGICA ---
        
        # 2. Marcar la orden como recibida
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
def enviar_orden(id):
    """ Cambia el estado de la orden de 'borrador' a 'enviada'. """
    orden = OrdenCompra.query.get_or_404(id)
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
def generar_oc_pdf(id):
    """ 
    Genera un archivo PDF para una Orden de Compra específica
    (Versión 3.0 con estilo "Bootstrap").
    """
    orden = OrdenCompra.query.get_or_404(id)
    
    # 1. Preparar el PDF en memoria
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                            rightMargin=inch, leftMargin=inch,
                            topMargin=inch, bottomMargin=inch)
    
    story = []
    styles = getSampleStyleSheet()

    # --- 2. DEFINIR ESTILOS DE PÁRRAFO (Estilo Bootstrap) ---
    
    # Estilo base
    style_body = ParagraphStyle(name='Body', parent=styles['BodyText'], fontName='Helvetica', fontSize=10)
    
    # Estilo para celdas alineadas a la derecha
    style_right = ParagraphStyle(name='BodyRight', parent=style_body, alignment=TA_RIGHT)
    
    # Estilo para celdas alineadas a la izquierda (para nombres de producto)
    style_left = ParagraphStyle(name='BodyLeft', parent=style_body, alignment=TA_LEFT)
    
    # --- CAMBIO: Cabecera con texto negro (no blanco) ---
    style_header = ParagraphStyle(name='Header', parent=style_body, fontName='Helvetica-Bold', 
                                  alignment=TA_CENTER, textColor=colors.black)

    # Estilo para la etiqueta "TOTAL"
    style_total_label = ParagraphStyle(name='TotalLabel', parent=style_body, fontName='Helvetica-Bold', alignment=TA_RIGHT)
    
    # Estilo para el valor "TOTAL"
    style_total_value = ParagraphStyle(name='TotalValue', parent=style_body, fontName='Helvetica-Bold', alignment=TA_RIGHT)

    
    # 3. Título y Cabecera
    story.append(Paragraph(f"ORDEN DE COMPRA #{orden.id}", styles['h1']))
    story.append(Paragraph(f"<b>Estado:</b> {orden.estado.capitalize()}", styles['h3']))
    story.append(Spacer(1, 0.25 * inch))

    # 4. Información del Proveedor
    info_proveedor = f"""
        <b>Proveedor:</b> {orden.proveedor.nombre}<br/>
        <b>Email Contacto:</b> {orden.proveedor.contacto_email}<br/>
        <b>Fecha Creación:</b> {orden.fecha_creacion.strftime('%Y-%m-%d')}
    """
    story.append(Paragraph(info_proveedor, styles['BodyText']))
    story.append(Spacer(1, 0.5 * inch))

    # 5. Tabla de Productos (con Paragraphs, como antes)
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

    # 6. Fila de Total (con Paragraphs, como antes)
    data.append([
        '', 
        '', 
        Paragraph('TOTAL (Est.):', style_total_label), 
        Paragraph(f"${orden.costo_total:.2f}", style_total_value)
    ])

    # --- 7. DEFINIR EL ESTILO DE TABLA (Estilo Bootstrap) ---
    style = TableStyle([
        # --- Estilo de Cabecera (Bootstrap 'thead-light') ---
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E9ECEF")), # Fondo gris claro
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), # Alinear todo verticalmente al medio
        ('PADDING', (0,0), (-1,-1), 8), # Padding de 8 puntos en todas las celdas

        # --- Estilo de Cuerpo (Bootstrap 'table-striped') ---
        # Filas alternas (blanco, gris muy claro)
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, colors.HexColor("#F8F9FA")]), 
        
        # --- Estilo de Bordes (Bootstrap 'table-bordered') ---
        ('GRID', (0,0), (-1,-2), 1, colors.HexColor("#DEE2E6")), # Borde gris claro
        ('BOX', (0,0), (-1,-2), 1, colors.HexColor("#DEE2E6")),

        # --- Estilo Fila de Total ---
        ('BACKGROUND', (0,-1), (3,-1), colors.white), # Fondo blanco (sin franja)
        ('GRID', (2,-1), (3,-1), 1, colors.HexColor("#DEE2E6")), # Borde gris en celdas de total
        ('SPAN', (0,-1), (1,-1)), # Unir las dos primeras celdas
    ])

    # 8. Crear el objeto Tabla
    tabla_oc = Table(data, colWidths=[2.75*inch, 1.0*inch, 1.25*inch, 1.25*inch])
    tabla_oc.setStyle(style)
    story.append(tabla_oc)
    
    # 9. Construir el PDF
    doc.build(story)
    
    # 10. Preparar el nombre del archivo
    fecha_str = orden.fecha_creacion.strftime("%Y-%m-%d")
    filename = f"OC#{orden.id}_{fecha_str}.pdf"

    # 11. Enviar el archivo al navegador
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=False,
        download_name=filename,
        mimetype='application/pdf'
    )

#<---------SALIDA DE PRODUCTOS----------->

@app.route('/salida', methods=['GET', 'POST'])
@login_required
def registrar_salida():
    """ 
    Registra una nueva Salida (como un lote) y sus movimientos asociados.
    """
    
    # Preparamos la lista de productos (igual que antes)
    productos_query = Producto.query.all()
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

            # --- 1. FASE DE VALIDACIÓN (TODO O NADA) ---
            productos_para_actualizar = [] 
            for prod_id, cant_str in zip(productos_ids, cantidades):
                if not prod_id or not cant_str: continue
                cantidad_salida = int(cant_str)
                producto = Producto.query.get_or_404(prod_id)
                if cantidad_salida <= 0:
                    flash('Todas las cantidades deben ser positivas.', 'danger')
                    db.session.rollback() 
                    return render_template('salida_form.html', 
                                           titulo="Registrar Salida", 
                                           productos=productos_lista)
                if producto.cantidad_stock < cantidad_salida:
                    flash(f'Error: Stock insuficiente para "{producto.nombre}". Stock actual: {producto.cantidad_stock}, Solicitado: {cantidad_salida}', 'danger')
                    db.session.rollback()
                    return render_template('salida_form.html', 
                                           titulo="Registrar Salida", 
                                           productos=productos_lista)
                productos_para_actualizar.append((producto, cantidad_salida))

            # --- 2. FASE DE EJECUCIÓN (CON NUEVO LOTE DE SALIDA) ---
            
            # --- CAMBIO: Crear el "header" de Salida ---
            nueva_salida = Salida(
                fecha=datetime.now(),
                motivo=motivo_general,
                creador_id=current_user.id
            )
            db.session.add(nueva_salida)
            # (No necesitamos hacer commit aún, se hará todo al final)

            for producto, cantidad_salida in productos_para_actualizar:
                
                # 1. Actualizar el stock
                producto.cantidad_stock -= cantidad_salida
                db.session.add(producto)
                
                # 2. Registrar el movimiento VINCULADO
                movimiento = Movimiento(
                    producto_id=producto.id,
                    cantidad= -cantidad_salida,
                    tipo='salida',
                    fecha=datetime.now(),
                    motivo=motivo_general, # Mantenemos el motivo por consistencia
                    salida=nueva_salida # <-- VINCULAMOS AL LOTE
                )
                db.session.add(movimiento)
            
            db.session.commit()
            flash(f'Salida #{nueva_salida.id} registrada con {len(productos_para_actualizar)} productos.', 'success')
            return redirect(url_for('historial_salidas')) # Redirigimos al historial

        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar la salida: {e}', 'danger')
    
    # --- Lógica GET ---
    return render_template('salida_form.html', 
                           titulo="Registrar Salida", 
                           productos=productos_lista)

@app.route('/salida/<int:id>/cancelar', methods=['POST'])
@login_required
def cancelar_salida(id):
    """ 
    Cancela un lote de Salida y revierte el stock creando 
    movimientos de ajuste positivos.
    """
    salida = Salida.query.get_or_404(id)
    
    if salida.estado == 'cancelada':
        flash('Esta salida ya ha sido cancelada.', 'warning')
        return redirect(url_for('historial_salidas'))

    try:
        # 1. Marcar la salida como cancelada
        salida.estado = 'cancelada'
        salida.cancelado_por_id = current_user.id
        db.session.add(salida)
        
        # 2. Revertir el inventario para CADA movimiento en la salida
        for mov in salida.movimientos:
            producto = mov.producto
            cantidad_a_devolver = abs(mov.cantidad) # abs() convierte -10 a 10
            
            # 2a. Devolvemos el stock al producto
            producto.cantidad_stock += cantidad_a_devolver
            db.session.add(producto)
            
            # 2b. Creamos un nuevo movimiento de "Ajuste" (entrada)
            mov_ajuste = Movimiento(
                producto_id=producto.id,
                cantidad=cantidad_a_devolver, # Positivo
                tipo='ajuste-entrada',
                fecha=datetime.now(),
                motivo=f'Cancelación de Salida #{salida.id}'
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
def generar_salida_pdf(id):
    """ 
    Genera un PDF para un lote de Salida (Comprobante de Salida).
    """
    salida = Salida.query.get_or_404(id)
    
    # 1. Preparar el PDF en memoria
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                            rightMargin=inch, leftMargin=inch,
                            topMargin=inch, bottomMargin=inch)
    
    story = []
    styles = getSampleStyleSheet()

    # 2. Definir Estilos (Estilo Bootstrap)
    style_body = ParagraphStyle(name='Body', parent=styles['BodyText'], fontName='Helvetica', fontSize=10)
    style_right = ParagraphStyle(name='BodyRight', parent=style_body, alignment=TA_RIGHT)
    style_left = ParagraphStyle(name='BodyLeft', parent=style_body, alignment=TA_LEFT)
    style_header = ParagraphStyle(name='Header', parent=style_body, fontName='Helvetica-Bold', alignment=TA_CENTER, textColor=colors.black)

    # 3. Título y Cabecera
    story.append(Paragraph(f"COMPROBANTE DE SALIDA #{salida.id}", styles['h1']))
    story.append(Spacer(1, 0.25 * inch))

    # 4. Información de la Salida
    info_salida = f"""
        <b>Motivo:</b> {salida.motivo}<br/>
        <b>Fecha:</b> {salida.fecha.strftime('%Y-%m-%d %H:%M')}<br/>
        <b>Estado:</b> <font color="{'red' if salida.estado == 'cancelada' else 'green'}">
            {salida.estado.capitalize()}
        </font>
    """
    story.append(Paragraph(info_salida, styles['BodyText']))
    story.append(Spacer(1, 0.5 * inch))

    # 5. Tabla de Productos
    data = [[
        Paragraph('Producto', style_header), 
        Paragraph('SKU', style_header), 
        Paragraph('Cantidad Retirada', style_header)
    ]]
    
    for mov in salida.movimientos:
        producto = Paragraph(mov.producto.nombre, style_left)
        sku = Paragraph(mov.producto.codigo, style_left)
        # abs() para mostrar 10 en lugar de -10
        cantidad = Paragraph(str(abs(mov.cantidad)), style_right)
        data.append([producto, sku, cantidad])

    # 6. Definir el Estilo de Tabla (Bootstrap 'table-striped')
    style = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E9ECEF")), # Fondo gris claro
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 8),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8F9FA")]), 
        ('GRID', (0,0), (-1,-1), 1, colors.HexColor("#DEE2E6")), # Borde gris
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#DEE2E6")),
    ])

    # 7. Crear el objeto Tabla con anchos de columna
    tabla_salida = Table(data, colWidths=[3*inch, 2*inch, 1.25*inch])
    tabla_salida.setStyle(style)
    story.append(tabla_salida)
    
    # 8. Construir el PDF
    doc.build(story)
    
    # 9. Preparar el nombre del archivo
    fecha_str = salida.fecha.strftime("%Y-%m-%d")
    filename = f"Salida_#{salida.id}_{fecha_str}.pdf"

    # 10. Enviar el archivo al navegador
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=False,
        download_name=filename,
        mimetype='application/pdf'
    )

@app.route('/orden/<int:id>')
@login_required
def ver_orden(id):
    """ Muestra el detalle de una sola Orden de Compra. """
    orden = OrdenCompra.query.get_or_404(id)
    return render_template('orden_detalle.html', orden=orden, titulo=f"Detalle OC #{orden.id}")

@app.route('/orden/nueva_manual', methods=['GET', 'POST'])
@login_required
def nueva_orden_manual():
    """ Muestra el formulario para crear una OC manual y la guarda. """
    
    # Preparamos las variables que la plantilla necesita SIEMPRE
    proveedores = Proveedor.query.all()
    
    # --- SOLUCIÓN: Convertir objetos Producto a una lista de diccionarios ---
    productos_query = Producto.query.all()
    productos_lista = []
    for p in productos_query:
        productos_lista.append({
            'id': p.id,
            'nombre': p.nombre,
            'codigo': p.codigo,
            'precio_unitario': p.precio_unitario,
            'proveedor_id': p.proveedor_id
        })
    # --- FIN DE LA SOLUCIÓN ---
    
    if request.method == 'POST':
        try:
            proveedor_id = request.form.get('proveedor_id')
            if not proveedor_id:
                flash('Debes seleccionar un proveedor.', 'danger')
                return render_template('orden_form.html',
                                       titulo="Crear Orden de Compra Manual",
                                       proveedores=proveedores,
                                       productos=productos_lista, # <-- Usar lista
                                       orden=None) 

            # ... (Lógica para crear la nueva_oc) ...
            nueva_oc = OrdenCompra(
                proveedor_id=proveedor_id,
                estado='borrador',
                creador_id=current_user.id
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
                                       productos=productos_lista, # <-- Usar lista
                                       orden=None)

            # ... (Lógica para iterar y añadir detalles) ...
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
                                   productos=productos_lista, # <-- Usar lista
                                   orden=None)
    
    # --- Lógica GET (mostrar formulario por primera vez) ---
    return render_template('orden_form.html', 
                           titulo="Crear Orden de Compra Manual",
                           proveedores=proveedores,
                           productos=productos_lista, # <-- Usar lista
                           orden=None)

@app.route('/orden/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_orden(id):
    """ Muestra el formulario para editar una OC y guarda los cambios. """
    orden = OrdenCompra.query.get_or_404(id)
    proveedores = Proveedor.query.all()

    # --- SOLUCIÓN: Convertir objetos Producto a una lista de diccionarios ---
    productos_query = Producto.query.all()
    productos_lista = []
    for p in productos_query:
        productos_lista.append({
            'id': p.id,
            'nombre': p.nombre,
            'codigo': p.codigo,
            'precio_unitario': p.precio_unitario,
            'proveedor_id': p.proveedor_id
        })
    # --- FIN DE LA SOLUCIÓN ---

    if orden.estado != 'borrador':
        flash('Solo se pueden editar órdenes en estado "Borrador".', 'warning')
        return redirect(url_for('ver_orden', id=id))

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
                                       productos=productos_lista, # <-- Usar lista
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
                                   productos=productos_lista, # <-- Usar lista
                                   orden=orden)

    # --- Lógica GET (mostrar formulario de edición) ---
    return render_template('orden_form.html', 
                           titulo=f"Editar Orden de Compra #{orden.id}",
                           proveedores=proveedores,
                           productos=productos_lista, # <-- Usar lista
                           orden=orden)

@app.route('/orden/<int:id>/cancelar', methods=['POST'])
@login_required
def cancelar_orden(id):
    """ Marca una Orden de Compra como 'cancelada' y guarda quién lo hizo. """
    orden = OrdenCompra.query.get_or_404(id)
    
    if orden.estado != 'borrador':
        flash('Error: Solo se pueden cancelar órdenes en estado "Borrador".', 'danger')
        return redirect(url_for('lista_ordenes'))

    try:
        orden.estado = 'cancelada'
        orden.cancelado_por_id = current_user.id # <-- AÑADIR ESTO
        
        db.session.commit()
        flash('Orden de Compra cancelada exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al cancelar la orden: {e}', 'danger')
    
    return redirect(url_for('lista_ordenes'))

# --- RUTAS DE CONTROL DE GASTOS ---

@app.route('/gastos')
@login_required
def lista_gastos():
    """ 
    Muestra una lista de todos los gastos, filtrada por mes y año si se proveen. 
    """
    # Obtener el mes y año de los argumentos de la URL (ej. /gastos?mes=11&ano=2025)
    mes = request.args.get('mes', type=int)
    ano = request.args.get('ano', type=int)
    
    # Si no se proveen, usamos el mes y año actual
    ahora = datetime.now()
    if not mes:
        mes = ahora.month
    if not ano:
        ano = ahora.year

    # Filtramos la consulta a la base de datos
    query_gastos = Gasto.query.filter(
        extract('month', Gasto.fecha) == mes,
        extract('year', Gasto.fecha) == ano
    ).order_by(Gasto.fecha.desc())
    
    gastos = query_gastos.all()
    total_gastos = sum(g.monto for g in gastos)
    
    # Creamos una lista de meses para el dropdown
    meses_lista = [
        (1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'), (4, 'Abril'), 
        (5, 'Mayo'), (6, 'Junio'), (7, 'Julio'), (8, 'Agosto'), 
        (9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre')
    ]

    return render_template('gastos.html', 
                           gastos=gastos, 
                           total_gastos=total_gastos,
                           mes_seleccionado=mes,
                           ano_seleccionado=ano,
                           meses_lista=meses_lista)

@app.route('/gasto/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_gasto():
    """ Formulario para registrar un nuevo gasto. """
    # Pasamos las órdenes de compra para poder asociar un gasto (opcional)
    ordenes = OrdenCompra.query.order_by(OrdenCompra.fecha_creacion.desc()).all()

    if request.method == 'POST':
        try:
            # Convertir fecha de 'YYYY-MM-DD' a objeto datetime
            fecha_gasto = datetime.strptime(request.form['fecha'], '%Y-%m-%d')
            
            # Obtener el ID de la OC, si se proporcionó
            oc_id = request.form.get('orden_compra_id')
            if oc_id == "": # Si el usuario seleccionó "Ninguna"
                oc_id = None

            nuevo_gasto = Gasto(
                descripcion=request.form['descripcion'],
                monto=float(request.form['monto']),
                categoria=request.form['categoria'],
                fecha=fecha_gasto,
                orden_compra_id=oc_id
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
def exportar_gastos_excel():
    """ 
    Genera un archivo Excel (.xlsx) formateado de los gastos,
    con bordes en el total y columnas más anchas.
    """
    # 1. Obtener datos (igual que antes)
    mes = request.args.get('mes', type=int)
    ano = request.args.get('ano', type=int)

    ahora = datetime.now()
    if not mes: mes = ahora.month
    if not ano: ano = ahora.year

    gastos = Gasto.query.filter(
        extract('month', Gasto.fecha) == mes,
        extract('year', Gasto.fecha) == ano
    ).order_by(Gasto.fecha.asc()).all()

    # --- 2. Definición de Estilos ---
    
    fuente_arial_12 = Font(name='Arial', size=12)
    fuente_arial_12_bold = Font(name='Arial', size=12, bold=True, color='FFFFFF') 

    header_fill = PatternFill(start_color='0000FF', end_color='0000FF', fill_type='solid') 
    header_align = Alignment(horizontal='center', vertical='center')

    currency_style = NamedStyle(name='currency_arial', 
                                number_format='$#,##0.00', 
                                font=fuente_arial_12)

    # --- CAMBIO: Definimos un estilo de borde delgado ---
    thin_border_side = Side(border_style="thin", color="000000") # Borde negro delgado
    thin_border = Border(left=thin_border_side, 
                         right=thin_border_side, 
                         top=thin_border_side, 
                         bottom=thin_border_side)

    # --- 3. Creación del Excel en memoria ---
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"{datetime(ano, mes, 1).strftime('%B').capitalize()} {ano}"
    
    if currency_style.name not in wb.named_styles:
        wb.add_named_style(currency_style)

    # 4. Escribir la Cabecera (Títulos)
    headers = ['ID Gasto', 'Fecha', 'Descripcion', 'Categoria', 'Monto', 'ID Orden Compra Asociada']
    ws.append(headers)
    
    # Aplicar estilo a la cabecera (Fila 1)
    for cell in ws[1]:
        cell.font = fuente_arial_12_bold 
        cell.fill = header_fill
        cell.alignment = header_align
        # (Dejamos que el Estilo de Tabla maneje los bordes del header)

    # 5. Escribir los datos
    total_gastos = 0
    for gasto in gastos:
        fecha_excel = gasto.fecha.date()
        
        ws.append([
            gasto.id,
            fecha_excel,
            gasto.descripcion,
            gasto.categoria,
            gasto.monto,
            gasto.orden_compra_id if gasto.orden_compra_id else 'N/A'
        ])
        
        fila_actual = ws.max_row
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=fila_actual, column=col_idx)
            cell.font = fuente_arial_12
            
        monto_cell = ws.cell(row=fila_actual, column=5)
        monto_cell.style = currency_style.name
        
        total_gastos += gasto.monto

    # 6. Aplicar el formato de Tabla (como antes)
    rango_tabla = f"A1:F{ws.max_row}"
    tabla_excel = ExcelTable(displayName="GastosMes", ref=rango_tabla) # <-- LÍNEA CORREGIDA
    estilo_tabla = TableStyleInfo(name="TableStyleMedium9", 
                                showFirstColumn=False,
                                showLastColumn=False, 
                                showRowStripes=True,
                                showColumnStripes=False)
    tabla_excel.tableStyleInfo = estilo_tabla
    ws.add_table(tabla_excel)


    # 7. Escribir el "Gran Total" (dos filas después de la tabla)
    fila_total = ws.max_row + 2 
    
    total_label_cell = ws.cell(row=fila_total, column=4)
    total_label_cell.value = "Gran Total"
    total_label_cell.font = fuente_arial_12_bold 
    total_label_cell.fill = header_fill 
    total_label_cell.alignment = Alignment(horizontal='right')
    # --- CAMBIO: Añadimos el borde al total ---
    total_label_cell.border = thin_border

    total_value_cell = ws.cell(row=fila_total, column=5)
    total_value_cell.value = total_gastos
    total_value_cell.style = currency_style.name
    total_value_cell.font = fuente_arial_12
    # --- CAMBIO: Añadimos el borde al total ---
    total_value_cell.border = thin_border


    # 8. Auto-ajustar el ancho de las columnas
    for col_idx, col in enumerate(ws.columns, 1):
        column_letter = get_column_letter(col_idx)
        max_length = 0
        for cell in col:
            try: 
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        
        # --- CAMBIO: Aumentamos el padding de +2 a +5 para más espacio ---
        adjusted_width = (max_length + 5) 
        ws.column_dimensions[column_letter].width = adjusted_width

    # 9. Preparar y enviar la respuesta (como antes)
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
    # Si el usuario ya está logueado, lo mandamos al index
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            # --- CAMBIO AQUÍ: Añadir el e-mail ---
            new_user = User(
                username=form.username.data,
                email=form.email.data
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

class UpdateAccountForm(FlaskForm):
    """ Formulario para actualizar username, email y foto. """
    username = StringField('Usuario', validators=[DataRequired(), Length(min=4, max=80)])
    email = StringField('E-mail', validators=[DataRequired(), Email(message='E-mail no válido.')])
    picture = FileField('Actualizar Foto de Perfil', validators=[FileAllowed(['jpg', 'png', 'jpeg'])])
    submit_account = SubmitField('Actualizar Datos') # Le damos un nombre único

    def validate_username(self, username):
        """ Valida si el nuevo username ya existe. """
        if username.data != current_user.username: # Solo si cambió el nombre
            user = User.query.filter_by(username=username.data).first()
            if user:
                raise ValidationError('Ese nombre de usuario ya existe. Por favor, elige otro.')
            
    def validate_email(self, email):
        """ Valida si el nuevo e-mail ya existe. """
        if email.data != current_user.email: # Solo si cambió el e-mail
            user = User.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError('Ese e-mail ya está registrado. Por favor, usa otro.')

class ChangePasswordForm(FlaskForm):
    """ Formulario para cambiar la contraseña (estando logueado). """
    old_password = PasswordField('Contraseña Actual', validators=[DataRequired()])
    password = PasswordField('Nueva Contraseña', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Nueva Contraseña', 
                                     validators=[DataRequired(), EqualTo('password', message='Las contraseñas deben coincidir.')])
    submit_password = SubmitField('Cambiar Contraseña') # Nombre único

@app.route('/account/delete_picture', methods=['POST'])
@login_required
def delete_picture():
    """ Elimina la foto de perfil del usuario y la revierte a 'default.jpg'. """
    
    # Solo procedemos si el usuario tiene una foto que NO es la de por defecto
    if current_user.image_file != 'default.jpg':
        try:
            # 1. Construir la ruta al archivo de la foto
            picture_path = os.path.join(app.root_path, 'static/uploads/profile_pics', current_user.image_file)
            
            # 2. Eliminar el archivo físico del servidor (si existe)
            if os.path.exists(picture_path):
                os.remove(picture_path)
                
            # 3. Actualizar la base de datos para que apunte a 'default.jpg'
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
        
        # Verificamos si el usuario existe y la contraseña es correcta
        if user and user.check_password(form.password.data):
            login_user(user) # <-- ¡La magia de Flask-Login!
            
            # Requerido por Flask-Login para seguridad de la sesión
            next_page = request.args.get('next') 
            
            flash('Inicio de sesión exitoso.', 'success')
            # Si el usuario intentaba ir a una pág. protegida, lo llevamos allí
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Inicio de sesión fallido. Verifica tu usuario y contraseña.', 'danger')
            
    return render_template('login.html', titulo="Inicio de Sesión", form=form)

class RequestResetForm(FlaskForm):
    """ Formulario para pedir un reseteo de contraseña. """
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    submit = SubmitField('Solicitar Reseteo de Contraseña')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is None:
            raise ValidationError('No existe una cuenta con ese e-mail. Regístrate primero.')

class ResetPasswordForm(FlaskForm):
    """ Formulario para ingresar la nueva contraseña. """
    password = PasswordField('Nueva Contraseña', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Nueva Contraseña', 
                                     validators=[DataRequired(), EqualTo('password', message='Las contraseñas deben coincidir.')])
    submit = SubmitField('Restablecer Contraseña')

@app.route('/logout')
@login_required  # El usuario debe estar logueado para poder salir
def logout():
    """ Cierra la sesión del usuario. """
    logout_user()
    flash('Has cerrado la sesión.', 'info')
    return redirect(url_for('login'))

def send_reset_email(user):
    """ Función auxiliar para generar y enviar el e-mail. """
    # Genera un token que expira en 30 minutos (1800 segundos)
    token = s.dumps(user.email, salt='password-reset-salt')
    
    # Crea la URL que irá en el e-mail
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
        print(f"Error de Mail: {e}") # Para depuración en la terminal

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
        # ¡Importante! Mostramos el mismo mensaje aunque el e-mail no exista
        # para no revelar qué e-mails están registrados.
        flash('Si existe una cuenta con ese e-mail, recibirás un correo con las instrucciones.', 'info')
        return redirect(url_for('login'))
        
    return render_template('forgot_password.html', titulo="Recuperar Contraseña", form=form)

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """ Página para ingresar la nueva contraseña (accedida desde el e-mail). """
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    try:
        # Verificamos el token (expira en 1800s = 30 min)
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
            # Actualizamos la contraseña del usuario
            user.set_password(form.password.data)
            db.session.commit()
            flash('¡Tu contraseña ha sido actualizada! Ya puedes iniciar sesión.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar la contraseña: {e}', 'danger')

    return render_template('reset_password.html', titulo="Restablecer Contraseña", form=form, token=token)

@app.route('/account', methods=['GET', 'POST'])
@login_required # El usuario DEBE estar logueado
def account():
    """ Página de configuración de la cuenta del usuario. """
    
    # Creamos las instancias de los dos formularios
    form_account = UpdateAccountForm()
    form_password = ChangePasswordForm()

    # --- Lógica para el Formulario 1: Actualizar Datos ---
    if form_account.submit_account.data and form_account.validate_on_submit():
        try:
            # Si el usuario subió una foto nueva
            if form_account.picture.data:
                # (Opcional: borrar foto antigua si no es 'default.jpg')
                if current_user.image_file != 'default.jpg':
                    old_pic_path = os.path.join(app.root_path, 'static/uploads/profile_pics', current_user.image_file)
                    if os.path.exists(old_pic_path):
                        os.remove(old_pic_path)
                
                # Guardar la nueva foto
                picture_file = save_picture(form_account.picture.data)
                current_user.image_file = picture_file
            
            # Actualizar username y email
            current_user.username = form_account.username.data
            current_user.email = form_account.email.data
            
            db.session.commit()
            flash('¡Tu cuenta ha sido actualizada!', 'success')
            return redirect(url_for('account')) # Redirige a la misma página
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar la cuenta: {e}', 'danger')

    # --- Lógica para el Formulario 2: Cambiar Contraseña ---
    if form_password.submit_password.data and form_password.validate_on_submit():
        try:
            # 1. Verificar la contraseña antigua
            if current_user.check_password(form_password.old_password.data):
                # 2. Si es correcta, establecer la nueva
                current_user.set_password(form_password.password.data)
                db.session.commit()
                flash('¡Tu contraseña ha sido cambiada!', 'success')
                return redirect(url_for('account'))
            else:
                flash('La contraseña actual es incorrecta.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al cambiar la contraseña: {e}', 'danger')

    # --- Lógica GET (cuando solo se carga la página) ---
    # Rellenamos el formulario de "Actualizar Datos" con la info actual
    if request.method == 'GET':
        form_account.username.data = current_user.username
        form_account.email.data = current_user.email
    
    # Preparamos la URL de la foto de perfil para mostrarla
    image_url = url_for('static', filename='uploads/profile_pics/' + current_user.image_file)
    
    return render_template('account.html', 
                           titulo="Configuración de Cuenta",
                           image_url=image_url,
                           form_account=form_account,
                           form_password=form_password)

# --- Inicialización ---
if __name__ == '__main__':
    # Crea la base de datos y las tablas si no existen
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)