"""Modelos para el chatbot de soporte y tickets de reporte de fallos."""

from app.extensions import db
from app.helpers import now_mx


class ChatConversacion(db.Model):
    __tablename__ = 'chat_conversacion'

    id              = db.Column(db.Integer, primary_key=True)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)
    usuario_id      = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    creado_en       = db.Column(db.DateTime, default=now_mx, nullable=False)

    mensajes = db.relationship('ChatMensaje', backref='conversacion',
                               lazy='dynamic', cascade='all, delete-orphan',
                               order_by='ChatMensaje.creado_en')


class ChatMensaje(db.Model):
    __tablename__ = 'chat_mensaje'

    id               = db.Column(db.Integer, primary_key=True)
    conversacion_id  = db.Column(db.Integer, db.ForeignKey('chat_conversacion.id',
                                                            ondelete='CASCADE'), nullable=False)
    rol              = db.Column(db.String(10), nullable=False)   # 'user' | 'assistant'
    contenido        = db.Column(db.Text, nullable=False)
    creado_en        = db.Column(db.DateTime, default=now_mx, nullable=False)


class SoporteReporte(db.Model):
    __tablename__ = 'soporte_reporte'

    id              = db.Column(db.Integer, primary_key=True)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizacion.id'), nullable=False)
    usuario_id      = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    titulo          = db.Column(db.String(300), nullable=False)
    descripcion     = db.Column(db.Text, nullable=False)
    conversacion_id = db.Column(db.Integer, db.ForeignKey('chat_conversacion.id',
                                                           ondelete='SET NULL'), nullable=True)
    estado          = db.Column(db.String(20), default='abierto', nullable=False)
    nota_admin      = db.Column(db.Text, nullable=True)
    creado_en       = db.Column(db.DateTime, default=now_mx, nullable=False)
    actualizado_en  = db.Column(db.DateTime, default=now_mx, onupdate=now_mx, nullable=False)

    usuario = db.relationship('User', foreign_keys=[usuario_id], lazy=True)
