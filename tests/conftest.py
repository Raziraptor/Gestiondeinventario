"""
Fixtures compartidos para toda la suite de tests.
Usa SQLite en memoria (TestingConfig) con CSRF desactivado.
"""

import pytest
from app import create_app
from app.extensions import db as _db
from app.models.auth import Organizacion, User


# ── App + DB (scope=function: DB limpia para cada test) ───────────────────────

@pytest.fixture
def app():
    """Crea app Flask con DB SQLite en memoria. Scope function = aislamiento total."""
    _app = create_app('testing')
    with _app.app_context():
        _db.create_all()
        yield _app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


# ── Factories de datos ─────────────────────────────────────────────────────────

@pytest.fixture
def org():
    o = Organizacion(nombre='Org Alfa', codigo_invitacion='ALFA01')
    _db.session.add(o)
    _db.session.commit()
    return o


@pytest.fixture
def org_beta():
    o = Organizacion(nombre='Org Beta', codigo_invitacion='BETA01')
    _db.session.add(o)
    _db.session.commit()
    return o


@pytest.fixture
def admin_user(org):
    u = User(username='admin_alfa', email='admin@alfa.com',
             rol='admin', organizacion_id=org.id)
    u.set_password('Pass1234!')
    _db.session.add(u)
    _db.session.commit()
    return u


@pytest.fixture
def regular_user(org):
    u = User(username='user_alfa', email='user@alfa.com',
             rol='user', organizacion_id=org.id,
             perm_view_dashboard=True)
    u.set_password('Pass1234!')
    _db.session.add(u)
    _db.session.commit()
    return u


@pytest.fixture
def beta_admin(org_beta):
    u = User(username='admin_beta', email='admin@beta.com',
             rol='admin', organizacion_id=org_beta.id)
    u.set_password('Pass1234!')
    _db.session.add(u)
    _db.session.commit()
    return u


@pytest.fixture
def orphan_user():
    u = User(username='orphan', email='orphan@test.com',
             rol='user', organizacion_id=None)
    u.set_password('Pass1234!')
    _db.session.add(u)
    _db.session.commit()
    return u


@pytest.fixture
def super_admin():
    u = User(username='superadmin', email='super@test.com',
             rol='super_admin', organizacion_id=None)
    u.set_password('Pass1234!')
    _db.session.add(u)
    _db.session.commit()
    return u


# ── Helpers de sesión ──────────────────────────────────────────────────────────

def do_login(client, username, password='Pass1234!'):
    return client.post(
        '/login',
        data={'username': username, 'password': password},
        follow_redirects=True,
    )


def do_logout(client):
    return client.get('/logout', follow_redirects=True)
