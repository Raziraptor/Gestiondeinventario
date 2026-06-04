"""
Entry point para Gunicorn en producción.
Uso: gunicorn wsgi:app
Reemplaza el anterior: gunicorn app:app
"""

from app import create_app

app = create_app('production')
