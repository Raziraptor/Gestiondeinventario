import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Departamento, Pendiente, PendienteFoto, User
from tests.fixtures_incidencias import agregar_foto, crear_incidencia, mundo  # noqa: F401


def test_tablas_y_columnas_nuevas(app):
    insp = inspect(db.engine)
    tablas = set(insp.get_table_names())
    assert {'departamento', 'departamento_miembro', 'pendiente', 'pendiente_foto', 'notificacion'} <= tablas
    cols = lambda t: {c['name'] for c in insp.get_columns(t)}
    assert {'expira_en', 'aviso_expiracion_enviado'} <= cols('incidencia')
    assert 'pendiente_id' in cols('incidencia_avance')
    assert {'nombre_completo', 'perm_crear_incidencias'} <= cols('user')


def test_borrar_incidencia_borra_pendientes_y_fotos(mundo):
    inc = crear_incidencia(mundo.org, mundo.creador)
    agregar_foto(inc.pendientes[0], 'uploads/incidencias/1/x.png', 'foto')
    db.session.delete(inc)
    db.session.commit()
    assert Pendiente.query.count() == 0
    assert PendienteFoto.query.count() == 0


def test_departamento_nombre_unico_por_org(mundo):
    db.session.add(Departamento(organizacion_id=mundo.org_beta.id, nombre='Sistemas'))
    db.session.commit()
    db.session.add(Departamento(organizacion_id=mundo.org.id, nombre='Sistemas'))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_nombre_mostrado_y_permiso_por_omision(mundo):
    assert mundo.enc_a.nombre_mostrado == 'Elena Encargada (inc_enc_a)'
    assert mundo.sin_nombre.nombre_mostrado == 'inc_sin_nombre'
    assert db.session.get(User, mundo.ajeno.id).perm_crear_incidencias is False
