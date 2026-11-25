"""Quién ve y quién toca qué en incidencias. Toda ruta de incidencias decide con estas funciones.

Regla (decisión confirmada): admin/super_admin ven todo lo de su org; el creador ve lo suyo;
cualquier otro usuario ve solo incidencias con >= 1 pendiente de un departamento al que
pertenece, y dentro de ellas solo esos pendientes. Siempre filtrado por organizacion_id.
"""

from app.extensions import db
from app.models.incidencias import Departamento, DepartamentoMiembro, Incidencia, Pendiente
from app.services.incidencias import promedio


def es_admin(user) -> bool:
    return user.rol in ('admin', 'super_admin')


def puede_crear(user) -> bool:
    return es_admin(user) or bool(getattr(user, 'perm_crear_incidencias', False))


def departamentos_de(user) -> set:
    """Ids de departamentos de la org del usuario a los que pertenece (encargado o auxiliar)."""
    filas = (
        db.session.query(DepartamentoMiembro.departamento_id)
        .join(Departamento, Departamento.id == DepartamentoMiembro.departamento_id)
        .filter(DepartamentoMiembro.user_id == user.id,
                Departamento.organizacion_id == user.organizacion_id)
        .all()
    )
    return {f[0] for f in filas}


def query_visibles(user):
    base = Incidencia.query.filter_by(organizacion_id=user.organizacion_id)
    if es_admin(user):
        return base
    condicion = Incidencia.creador_id == user.id
    deptos = departamentos_de(user)
    if deptos:
        sub = db.session.query(Pendiente.incidencia_id).filter(Pendiente.departamento_id.in_(deptos))
        condicion = db.or_(condicion, Incidencia.id.in_(sub))
    return base.filter(condicion)


def puede_editar(inc, user) -> bool:
    """Creador o admin de la misma org: editar, reasignar, reabrir, campos de cierre."""
    if inc.organizacion_id != user.organizacion_id:
        return False
    return es_admin(user) or inc.creador_id == user.id


def pendientes_visibles(inc, user) -> list:
    if puede_editar(inc, user):
        return list(inc.pendientes)
    deptos = departamentos_de(user)
    return [p for p in inc.pendientes if p.departamento_id in deptos]


def puede_ver(inc, user) -> bool:
    return puede_editar(inc, user) or bool(pendientes_visibles(inc, user))


def puede_avanzar(pendiente, user) -> bool:
    return puede_editar(pendiente.incidencia, user) or pendiente.departamento_id in departamentos_de(user)


def progreso_para(inc, user) -> int:
    """Global para creador/admin; 'avance de tu parte' (media de sus pendientes) para los demás."""
    if puede_editar(inc, user):
        return inc.progreso
    return promedio(p.progreso for p in pendientes_visibles(inc, user))
