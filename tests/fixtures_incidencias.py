"""Fixtures y helpers compartidos por tests/test_incidencias_*.py.

Emitido por blueprints/incidencias-pendientes-departamentos (blueprint seccion 19.6).
No es un conftest: cada archivo de test los importa explicitamente, por ejemplo
    from tests.fixtures_incidencias import mundo, uploads_tmp, entrar, crear_incidencia  # noqa: F401
pytest encuentra un fixture importado en el namespace del modulo de test.

Solo usa modelos (paso 1 del blueprint); nada de servicios, para que sirva desde el paso 1.
"""

import io
from types import SimpleNamespace

import pytest
from PIL import Image

from app.extensions import db
from app.helpers import now_mx
from app.models.auth import Organizacion, User
from app.models.incidencias import (
    Departamento, DepartamentoMiembro, Incidencia, Pendiente, PendienteFoto,
)
from tests.conftest import do_login

PASSWORD = 'Pass1234!'


def crear_usuario(username, org, rol='user', nombre='Persona de Prueba', **campos):
    """Usuario activo con nombre_completo (por omision) y password PASSWORD."""
    u = User(
        username=username,
        email=f'{username}@prueba.test',
        rol=rol,
        organizacion_id=org.id if org else None,
        nombre_completo=nombre,
        **campos,
    )
    u.set_password(PASSWORD)
    db.session.add(u)
    db.session.commit()
    return u


def crear_departamento(org, nombre, encargado=None, auxiliares=()):
    d = Departamento(organizacion_id=org.id, nombre=nombre)
    db.session.add(d)
    db.session.flush()
    if encargado is not None:
        db.session.add(DepartamentoMiembro(departamento_id=d.id, user_id=encargado.id, rol='encargado'))
    for aux in auxiliares:
        db.session.add(DepartamentoMiembro(departamento_id=d.id, user_id=aux.id, rol='auxiliar'))
    db.session.commit()
    return d


def crear_incidencia(org, creador, pendientes=(('Pendiente 1', None),), estado='Abierto', titulo='Fuga en bano'):
    """Incidencia con N pendientes. pendientes = iterable de (descripcion, Departamento|None)."""
    n = Incidencia.query.filter_by(organizacion_id=org.id).count() + 1
    inc = Incidencia(
        folio=f'INC-T-{n:04d}',
        titulo=titulo,
        fecha=now_mx().date(),
        hora='10:00',
        ubicacion='Planta baja',
        reportado_por=creador.username,
        tipo='Infraestructura',
        prioridad='Media',
        severidad='Menor',
        descripcion='Descripcion de prueba',
        organizacion_id=org.id,
        creador_id=creador.id,
        estado=estado,
    )
    db.session.add(inc)
    db.session.flush()
    for orden, (descripcion, depto) in enumerate(pendientes):
        db.session.add(Pendiente(
            incidencia_id=inc.id,
            orden=orden,
            descripcion=descripcion,
            departamento_id=depto.id if depto is not None else None,
        ))
    db.session.commit()
    return inc


def agregar_foto(pendiente, path, descripcion=None):
    f = PendienteFoto(pendiente_id=pendiente.id, path=path, descripcion=descripcion)
    db.session.add(f)
    db.session.commit()
    return f


def png_bytes(color=(200, 30, 30)):
    """PNG RGB real de 8x8 (pasa verify_image_bytes). Colores distintos = imagenes distintas en el PDF."""
    buf = io.BytesIO()
    Image.new('RGB', (8, 8), color).save(buf, format='PNG')
    buf.seek(0)
    return buf


def entrar(client, user):
    """Inicia sesion con el password comun de estos fixtures."""
    return do_login(client, user.username, PASSWORD)


@pytest.fixture
def uploads_tmp(app, tmp_path):
    """Redirige UPLOAD_FOLDER a un directorio temporal: los tests nunca escriben en static/ del repo."""
    carpeta = tmp_path / 'static' / 'uploads'
    carpeta.mkdir(parents=True)
    app.config['UPLOAD_FOLDER'] = str(carpeta)
    return carpeta


@pytest.fixture
def mundo(app):
    """Dos organizaciones, roles tipicos y dos departamentos en la org principal.

    org:       admin, creador (perm_crear_incidencias), enc_a + aux_a (depto_a),
               enc_b (depto_b), ajeno (sin departamento), sin_nombre (nombre_completo vacio)
    org_beta:  admin_beta, user_beta
    """
    org = Organizacion(nombre='Org Incidencias', codigo_invitacion='INCI01')
    org_beta = Organizacion(nombre='Org Ajena', codigo_invitacion='AJEN01')
    db.session.add_all([org, org_beta])
    db.session.commit()

    admin = crear_usuario('inc_admin', org, rol='admin', nombre='Ana Administradora')
    creador = crear_usuario('inc_creador', org, nombre='Carlos Creador', perm_crear_incidencias=True)
    enc_a = crear_usuario('inc_enc_a', org, nombre='Elena Encargada')
    aux_a = crear_usuario('inc_aux_a', org, nombre='Arturo Auxiliar')
    enc_b = crear_usuario('inc_enc_b', org, nombre='Beatriz Encargada')
    ajeno = crear_usuario('inc_ajeno', org, nombre='Pedro Ajeno')
    sin_nombre = crear_usuario('inc_sin_nombre', org, nombre=None)
    admin_beta = crear_usuario('beta_admin_inc', org_beta, rol='admin', nombre='Bruno Beta')
    user_beta = crear_usuario('beta_user_inc', org_beta, nombre='Berta Beta')

    depto_a = crear_departamento(org, 'Mantenimiento', encargado=enc_a, auxiliares=[aux_a])
    depto_b = crear_departamento(org, 'Sistemas', encargado=enc_b)
    depto_beta = crear_departamento(org_beta, 'Mantenimiento', encargado=user_beta)

    return SimpleNamespace(
        org=org, org_beta=org_beta,
        admin=admin, creador=creador, enc_a=enc_a, aux_a=aux_a, enc_b=enc_b,
        ajeno=ajeno, sin_nombre=sin_nombre, admin_beta=admin_beta, user_beta=user_beta,
        depto_a=depto_a, depto_b=depto_b, depto_beta=depto_beta,
    )
