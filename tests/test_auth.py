"""
Tests de autenticación: login, logout, registro, redirecciones.
CSRF desactivado en TestingConfig — no se envía token en ningún POST.
"""

import pytest
from app.models.auth import User
from tests.conftest import do_login, do_logout


class TestLogin:
    def test_valid_credentials_redirect_away_from_login(self, client, admin_user):
        r = do_login(client, admin_user.username)
        assert r.status_code == 200
        # Tras login exitoso Flask redirige al index, no queda en /login
        assert b'Iniciar Sesi' not in r.data

    def test_wrong_password_stays_on_login(self, client, admin_user):
        r = client.post(
            '/login',
            data={'username': admin_user.username, 'password': 'incorrecto'},
            follow_redirects=True,
        )
        assert r.status_code == 200
        assert b'Iniciar' in r.data

    def test_unknown_user_stays_on_login(self, client):
        r = client.post(
            '/login',
            data={'username': 'noexiste', 'password': 'cualquiera'},
            follow_redirects=True,
        )
        assert r.status_code == 200
        assert b'Iniciar' in r.data

    def test_logout_clears_session(self, client, admin_user):
        do_login(client, admin_user.username)
        do_logout(client)
        # Ruta protegida debe redirigir a login después del logout
        r = client.get('/account', follow_redirects=False)
        assert r.status_code in (301, 302)

    def test_unauthenticated_get_redirects_to_login(self, client):
        r = client.get('/account', follow_redirects=False)
        assert r.status_code in (301, 302)
        assert 'login' in r.headers['Location'].lower()


class TestRegistration:
    def test_register_creates_user_in_db(self, client):
        client.post('/register', data={
            'username': 'newuser01',
            'email': 'newuser01@test.com',
            'password': 'Pass1234!',
            'confirm_password': 'Pass1234!',
        }, follow_redirects=True)
        assert User.query.filter_by(username='newuser01').first() is not None

    def test_register_with_invite_links_org(self, client, org):
        client.post('/register', data={
            'username': 'invited01',
            'email': 'invited01@test.com',
            'password': 'Pass1234!',
            'confirm_password': 'Pass1234!',
            'codigo_invitacion': org.codigo_invitacion,
        }, follow_redirects=True)
        u = User.query.filter_by(username='invited01').first()
        assert u is not None
        assert u.organizacion_id == org.id

    def test_register_with_invalid_invite_rejects_registration(self, client):
        r = client.post('/register', data={
            'username': 'noinvite01',
            'email': 'noinvite01@test.com',
            'password': 'Pass1234!',
            'confirm_password': 'Pass1234!',
            'codigo_invitacion': 'INVALIDO',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert b'v\xc3\xa1lido' in r.data or b'invitaci' in r.data  # flash: "no es válido"
        # El usuario NO se crea si el invite es inválido
        assert User.query.filter_by(username='noinvite01').first() is None

    def test_register_duplicate_username_rejected(self, client, admin_user):
        r = client.post('/register', data={
            'username': admin_user.username,
            'email': 'otro@test.com',
            'password': 'Pass1234!',
            'confirm_password': 'Pass1234!',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert b'ya existe' in r.data
        # Solo debe existir un usuario con ese username
        assert User.query.filter_by(username=admin_user.username).count() == 1

    def test_register_duplicate_email_rejected(self, client, admin_user):
        r = client.post('/register', data={
            'username': 'otrousr',
            'email': admin_user.email,
            'password': 'Pass1234!',
            'confirm_password': 'Pass1234!',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert b'ya est' in r.data  # "ya está registrado"

    def test_register_password_mismatch_leaves_user_uncreated(self, client):
        client.post('/register', data={
            'username': 'mismatch01',
            'email': 'mismatch01@test.com',
            'password': 'Pass1234!',
            'confirm_password': 'Different!',
        }, follow_redirects=True)
        assert User.query.filter_by(username='mismatch01').first() is None
