"""Departamentos de una organización y sus miembros (a lo más un encargado + N auxiliares).

Valida todo ANTES de mutar: si algo falla, lanza ValueError y no toca la sesión.
Ninguna función hace commit (el llamador registra log_actividad y confirma).
"""

from app.extensions import db
from app.models import User
from app.models.incidencias import Departamento, DepartamentoMiembro


def departamento_valido(departamento_id, org_id, solo_activos=True):
    """Departamento de la org, o None. Nunca se usa un id de formulario sin pasar por aquí."""
    try:
        did = int(departamento_id)
    except (TypeError, ValueError):
        return None
    q = Departamento.query.filter_by(id=did, organizacion_id=org_id)
    if solo_activos:
        q = q.filter_by(activo=True)
    return q.first()


def _ids_de_org(valores, org_id) -> set:
    try:
        ids = {int(v) for v in valores if str(v).strip()}
    except (TypeError, ValueError):
        raise ValueError('Usuario no válido.')
    if not ids:
        return set()
    encontrados = {u.id for u in User.query.filter(User.id.in_(ids), User.organizacion_id == org_id)}
    if encontrados != ids:
        raise ValueError('Algún usuario elegido no pertenece a tu organización.')
    return ids


def guardar_departamento(org_id, nombre, encargado_id=None, auxiliar_ids=(), depto=None):
    """Crea (depto=None) o actualiza un departamento y reemplaza sus miembros."""
    nombre = ' '.join((nombre or '').split())
    if not 2 <= len(nombre) <= 120:
        raise ValueError('El nombre debe tener entre 2 y 120 caracteres.')
    repetido = Departamento.query.filter(
        Departamento.organizacion_id == org_id,
        db.func.lower(Departamento.nombre) == nombre.lower(),
    )
    if depto is not None:
        repetido = repetido.filter(Departamento.id != depto.id)
    if repetido.first():
        raise ValueError('Ya existe un departamento con ese nombre.')
    encargado = _ids_de_org([encargado_id] if encargado_id else [], org_id)
    auxiliares = _ids_de_org(auxiliar_ids, org_id) - encargado

    if depto is None:
        depto = Departamento(organizacion_id=org_id, nombre=nombre)
        db.session.add(depto)
        db.session.flush()
    else:
        depto.nombre = nombre
        depto.miembros.delete()
    for uid in encargado:
        db.session.add(DepartamentoMiembro(departamento_id=depto.id, user_id=uid, rol='encargado'))
    for uid in sorted(auxiliares):
        db.session.add(DepartamentoMiembro(departamento_id=depto.id, user_id=uid, rol='auxiliar'))
    return depto
