"""Modelos de sistema: audit log, push notifications, flujos de aprobación."""

from app.extensions import db
from app.helpers import now_mx


class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    id              = db.Column(db.Integer,    primary_key=True)
    fecha           = db.Column(db.DateTime,   nullable=False, default=now_mx, index=True)
    usuario_id      = db.Column(db.Integer,    db.ForeignKey('user.id'),         nullable=True)
    usuario         = db.relationship('User',  foreign_keys='AuditLog.usuario_id')
    organizacion_id = db.Column(db.Integer,    db.ForeignKey('organizacion.id'), nullable=False, index=True)
    accion          = db.Column(db.String(30), nullable=False)
    entidad         = db.Column(db.String(50), nullable=False)
    entidad_id      = db.Column(db.Integer,    nullable=True)
    descripcion     = db.Column(db.String(500), nullable=False)

    def __repr__(self):
        return f'<AuditLog {self.accion} {self.entidad} #{self.entidad_id}>'


class PushSubscription(db.Model):
    __tablename__ = 'push_subscription'
    id                = db.Column(db.Integer, primary_key=True)
    user_id           = db.Column(db.Integer, db.ForeignKey('user.id'),         nullable=False)
    organizacion_id   = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)
    endpoint          = db.Column(db.Text,    nullable=False, unique=True)
    subscription_json = db.Column(db.Text,    nullable=False)
    creada_en         = db.Column(db.DateTime, default=now_mx)
    user              = db.relationship('User', backref='push_subscriptions')


class SolicitudAprobacion(db.Model):
    __tablename__ = 'solicitud_aprobacion'
    id              = db.Column(db.Integer,    primary_key=True)
    entidad_tipo    = db.Column(db.String(30), nullable=False)
    entidad_id      = db.Column(db.Integer,    nullable=False)
    solicitante_id  = db.Column(db.Integer,    db.ForeignKey('user.id'), nullable=False)
    aprobador_id    = db.Column(db.Integer,    db.ForeignKey('user.id'), nullable=True)
    estado          = db.Column(db.String(20), nullable=False, default='pendiente')
    comentario      = db.Column(db.Text,       nullable=True)
    creado_en       = db.Column(db.DateTime,   default=now_mx)
    resuelto_en     = db.Column(db.DateTime,   nullable=True)
    organizacion_id = db.Column(db.Integer,    db.ForeignKey('organizacion.id'), nullable=False)

    solicitante = db.relationship('User', foreign_keys='SolicitudAprobacion.solicitante_id')
    aprobador   = db.relationship('User', foreign_keys='SolicitudAprobacion.aprobador_id')
