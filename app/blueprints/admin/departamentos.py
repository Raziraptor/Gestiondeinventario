"""Administración de departamentos (admin/super_admin con organización)."""

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import admin_bp
from app.extensions import db
from app.helpers import _flash_err, check_org_permission, log_actividad
from app.models import User
from app.models.incidencias import Departamento, Pendiente
from app.services.departamentos import guardar_departamento


def _exigir_admin_org():
    if current_user.rol not in ('admin', 'super_admin') or not current_user.organizacion_id:
        abort(403)


def _depto_or_404(id):
    return Departamento.query.filter_by(id=id, organizacion_id=current_user.organizacion_id).first_or_404()


@admin_bp.route('/admin/departamentos')
@login_required
@check_org_permission
def lista_departamentos():
    _exigir_admin_org()
    org_id = current_user.organizacion_id
    departamentos = Departamento.query.filter_by(organizacion_id=org_id).order_by(Departamento.nombre).all()
    return render_template('admin_departamentos.html', titulo='Departamentos', departamentos=departamentos)


@admin_bp.route('/admin/departamentos/buscar-usuarios')
@login_required
@check_org_permission
def buscar_usuarios_departamento():
    """Búsqueda para el selector de encargado/auxiliares: por nombre o usuario, solo de la org, máx. 15."""
    _exigir_admin_org()
    q = request.args.get('q', '').strip().lower()[:60]
    if not q:
        return jsonify([])
    usuarios = (User.query
                .filter(User.organizacion_id == current_user.organizacion_id, User.is_active.is_(True),
                        db.or_(db.func.lower(db.func.coalesce(User.nombre_completo, '')).contains(q, autoescape=True),
                               db.func.lower(User.username).contains(q, autoescape=True)))
                .order_by(User.nombre_completo, User.username).limit(15).all())
    return jsonify([{'id': u.id, 'texto': u.nombre_mostrado} for u in usuarios])


def _guardar(depto=None):
    try:
        d = guardar_departamento(current_user.organizacion_id, request.form.get('nombre'),
                                 request.form.get('encargado_id') or None,
                                 request.form.getlist('auxiliar_ids'), depto=depto)
        log_actividad('editar' if depto else 'crear', 'departamento', f'Departamento {d.nombre}', entidad_id=d.id)
        db.session.commit()
        flash(f'Departamento {d.nombre} guardado.', 'success')
    except ValueError as e:
        db.session.rollback()
        flash(str(e), 'danger')
    except Exception as exc:
        db.session.rollback()
        _flash_err('Error al guardar el departamento.', exc)
    return redirect(url_for('admin.lista_departamentos'))


@admin_bp.route('/admin/departamentos/nuevo', methods=['POST'])
@login_required
@check_org_permission
def crear_departamento():
    _exigir_admin_org()
    return _guardar()


@admin_bp.route('/admin/departamentos/<int:id>/editar', methods=['POST'])
@login_required
@check_org_permission
def editar_departamento(id):
    _exigir_admin_org()
    return _guardar(_depto_or_404(id))


@admin_bp.route('/admin/departamentos/<int:id>/estado', methods=['POST'])
@login_required
@check_org_permission
def cambiar_estado_departamento(id):
    _exigir_admin_org()
    d = _depto_or_404(id)
    try:
        d.activo = not d.activo
        log_actividad('editar', 'departamento', f'Departamento {d.nombre} {"activado" if d.activo else "desactivado"}', entidad_id=d.id)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        _flash_err('Error al cambiar el estado del departamento.', exc)
    return redirect(url_for('admin.lista_departamentos'))


@admin_bp.route('/admin/departamentos/<int:id>/eliminar', methods=['POST'])
@login_required
@check_org_permission
def eliminar_departamento(id):
    _exigir_admin_org()
    d = _depto_or_404(id)
    if Pendiente.query.filter_by(departamento_id=d.id).first():
        flash('No se puede eliminar: tiene pendientes. Desactívalo.', 'warning')
        return redirect(url_for('admin.lista_departamentos'))
    try:
        log_actividad('eliminar', 'departamento', f'Departamento {d.nombre} eliminado', entidad_id=d.id)
        db.session.delete(d)
        db.session.commit()
        flash('Departamento eliminado.', 'success')
    except Exception as exc:
        db.session.rollback()
        _flash_err('Error al eliminar el departamento.', exc)
    return redirect(url_for('admin.lista_departamentos'))
