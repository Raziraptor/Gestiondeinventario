"""Modelos para el módulo de reporte y seguimiento de incidencias."""

from decimal import Decimal

from app.extensions import db
from app.helpers import now_mx


_TIPOS_INCIDENCIA = ['Infraestructura', 'Equipo/mobiliario', 'Instalaciones', 'Seguridad', 'Otro']
_PRIORIDADES     = ['Baja', 'Media', 'Alta', 'Urgente']
_SEVERIDADES     = ['Menor', 'Moderada', 'Grave', 'Crítica']
_ESTADOS         = ['Abierto', 'En proceso', 'Resuelto', 'Cerrado sin resolver', 'Escalado']
_ESTADOS_CIERRE  = ['Resuelto', 'Cerrado sin resolver', 'Escalado']


class Incidencia(db.Model):
    __tablename__ = 'incidencia'

    id           = db.Column(db.Integer, primary_key=True)
    folio        = db.Column(db.String(20),  nullable=False)
    titulo       = db.Column(db.String(300), nullable=False)

    # 01 Datos del reporte
    fecha            = db.Column(db.Date,        nullable=False)
    hora             = db.Column(db.String(10),  nullable=False)
    ubicacion        = db.Column(db.String(200), nullable=False)
    reportado_por    = db.Column(db.String(150), nullable=False)
    cargo_reporta    = db.Column(db.String(150), nullable=True)
    contacto_reporta = db.Column(db.String(100), nullable=True)

    # 02 Clasificación
    tipo       = db.Column(db.String(50), nullable=False)
    tipo_otro  = db.Column(db.String(150), nullable=True)
    prioridad  = db.Column(db.String(20), nullable=False)
    severidad  = db.Column(db.String(20), nullable=False)
    lesionados             = db.Column(db.Boolean, nullable=False, default=False)
    descripcion_lesionados = db.Column(db.Text, nullable=True)

    # 03 Descripción
    descripcion = db.Column(db.Text, nullable=False)

    # 04 Evidencia fotográfica inicial (hasta 3 fotos)
    foto1_path = db.Column(db.String(300), nullable=True)
    foto1_desc = db.Column(db.String(300), nullable=True)
    foto2_path = db.Column(db.String(300), nullable=True)
    foto2_desc = db.Column(db.String(300), nullable=True)
    foto3_path = db.Column(db.String(300), nullable=True)
    foto3_desc = db.Column(db.String(300), nullable=True)

    # 05 Asignación
    responsable_nombre   = db.Column(db.String(150), nullable=True)
    responsable_puesto   = db.Column(db.String(150), nullable=True)
    asignado_por         = db.Column(db.String(150), nullable=True)
    fecha_asignacion     = db.Column(db.Date,        nullable=True)
    fecha_compromiso     = db.Column(db.Date,        nullable=True)
    contacto_responsable = db.Column(db.String(100), nullable=True)
    asignado_user_id     = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    # Estado y progreso
    estado   = db.Column(db.String(30),  nullable=False, default='Abierto')
    progreso = db.Column(db.Integer,     nullable=False, default=0)

    # 07 Causa raíz e impacto
    causa_raiz = db.Column(db.Text, nullable=True)
    impacto    = db.Column(db.Text, nullable=True)

    # 08 Costos
    mostrar_costos = db.Column(db.Boolean, nullable=False, default=True)

    # 09 Cierre
    estado_final       = db.Column(db.String(50), nullable=True)
    fecha_cierre       = db.Column(db.Date,       nullable=True)
    comentarios_cierre = db.Column(db.Text,       nullable=True)
    firma_reporto      = db.Column(db.String(150), nullable=True)
    firma_responsable  = db.Column(db.String(150), nullable=True)
    firma_vobo         = db.Column(db.String(150), nullable=True)

    # Multi-tenancy y autoría
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)
    creador_id      = db.Column(db.Integer, db.ForeignKey('user.id'),         nullable=False)
    creado_en       = db.Column(db.DateTime, nullable=False, default=now_mx)
    actualizado_en  = db.Column(db.DateTime, nullable=False, default=now_mx, onupdate=now_mx)

    # Relaciones
    creador    = db.relationship('User', foreign_keys=[creador_id],        lazy=True)
    asignado_a = db.relationship('User', foreign_keys=[asignado_user_id],  lazy=True)
    avances = db.relationship(
        'IncidenciaAvance', backref='incidencia', lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='IncidenciaAvance.creado_en',
    )
    acciones = db.relationship(
        'IncidenciaAccion', backref='incidencia', lazy='dynamic',
        cascade='all, delete-orphan',
    )
    costos = db.relationship(
        'IncidenciaCosto', backref='incidencia', lazy='dynamic',
        cascade='all, delete-orphan',
    )

    __table_args__ = (
        db.UniqueConstraint('folio', 'organizacion_id', name='_uc_incidencia_folio_org'),
    )

    @property
    def total_costos(self):
        return sum((c.monto or Decimal(0)) for c in self.costos)

    def __repr__(self):
        return f'<Incidencia {self.folio} - {self.titulo[:40]}>'


class IncidenciaAvance(db.Model):
    __tablename__ = 'incidencia_avance'

    id            = db.Column(db.Integer, primary_key=True)
    incidencia_id = db.Column(db.Integer, db.ForeignKey('incidencia.id'), nullable=False)
    texto         = db.Column(db.Text,    nullable=False)
    porcentaje    = db.Column(db.Integer, nullable=False, default=0)
    concluido     = db.Column(db.Boolean, nullable=False, default=False)
    foto_path     = db.Column(db.String(300), nullable=True)
    autor_id      = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    creado_en     = db.Column(db.DateTime, nullable=False, default=now_mx)

    autor = db.relationship('User', foreign_keys=[autor_id], lazy=True)


class IncidenciaAccion(db.Model):
    __tablename__ = 'incidencia_accion'

    id            = db.Column(db.Integer, primary_key=True)
    incidencia_id = db.Column(db.Integer, db.ForeignKey('incidencia.id'), nullable=False)
    accion        = db.Column(db.String(500), nullable=False)
    responsable   = db.Column(db.String(150), nullable=True)
    fecha_limite  = db.Column(db.Date,        nullable=True)


class IncidenciaCosto(db.Model):
    __tablename__ = 'incidencia_costo'

    id            = db.Column(db.Integer, primary_key=True)
    incidencia_id = db.Column(db.Integer, db.ForeignKey('incidencia.id'), nullable=False)
    concepto      = db.Column(db.String(200),    nullable=False)
    descripcion   = db.Column(db.String(500),    nullable=True)
    monto         = db.Column(db.Numeric(10, 2), nullable=False, default=0)
