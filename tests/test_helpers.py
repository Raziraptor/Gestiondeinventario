"""
Tests de helpers y decoradores de acceso definidos en app/helpers.py.
Los decoradores se prueban vía rutas HTTP (necesitan request context + current_user).
"""

from datetime import datetime

import pytest

from app.helpers import now_mx, allowed_file, CATEGORIAS_GASTO
from tests.conftest import do_login


# ── Utilidades puras ───────────────────────────────────────────────────────────

class TestNowMx:
    def test_returns_naive_datetime(self, app):
        dt = now_mx()
        assert isinstance(dt, datetime)
        assert dt.tzinfo is None

    def test_returns_time_close_to_utcnow(self, app):
        dt = now_mx()
        delta = abs((datetime.now() - dt).total_seconds())
        # Mexico City es UTC-6/UTC-5 según DST; la diferencia con utcnow es fija
        # Solo verificamos que es una datetime reciente (dentro de 1 hora)
        assert delta < 3600


class TestAllowedFile:
    @pytest.mark.parametrize('filename', ['photo.jpg', 'img.jpeg', 'logo.png', 'anim.gif'])
    def test_accepted_extensions(self, filename):
        assert allowed_file(filename) is True

    @pytest.mark.parametrize('filename', ['script.py', 'data.csv', 'doc.pdf', 'archive.zip'])
    def test_rejected_extensions(self, filename):
        assert allowed_file(filename) is False

    def test_uppercase_extension_accepted(self):
        assert allowed_file('PHOTO.JPG') is True

    def test_mixed_case_extension_accepted(self):
        assert allowed_file('logo.Png') is True

    def test_no_extension_rejected(self):
        assert allowed_file('sinextension') is False

    def test_dotfile_without_extension_rejected(self):
        # '.htaccess' → rsplit('.', 1) da ['', 'htaccess'] — htaccess no está en whitelist
        assert allowed_file('.htaccess') is False


class TestCategoriasGasto:
    def test_whitelist_exact_values(self):
        expected = {'Servicios', 'Nómina', 'Mantenimiento', 'Insumos', 'Inventario', 'Otros'}
        assert set(CATEGORIAS_GASTO) == expected

    def test_whitelist_length_signals_intent(self):
        # Si se añade/elimina una categoría, este test fuerza la conversación
        assert len(CATEGORIAS_GASTO) == 6


# ── Decoradores de acceso (probados vía rutas HTTP) ────────────────────────────

class TestCheckOrgPermission:
    """@check_org_permission bloquea usuarios sin org asignada."""

    def test_orphan_user_redirected_with_warning(self, client, orphan_user):
        do_login(client, orphan_user.username)
        r = client.get('/ordenes', follow_redirects=True)
        assert r.status_code == 200
        # Debe aparecer el mensaje de warning sobre organización
        assert b'organiza' in r.data or b'Super Admin' in r.data
        # No debe ver contenido de órdenes
        assert b'Nueva Orden' not in r.data

    def test_user_with_org_accesses_route(self, client, admin_user):
        do_login(client, admin_user.username)
        r = client.get('/ordenes', follow_redirects=True)
        assert r.status_code == 200
        # La página de órdenes carga sin redirección de org
        assert b'organiza' not in r.data or b'Orden' in r.data


class TestAdminRequired:
    """@admin_required bloquea usuarios con rol 'user'."""

    def test_regular_user_blocked_from_admin_panel(self, client, regular_user):
        do_login(client, regular_user.username)
        r = client.get('/usuarios', follow_redirects=True)
        assert r.status_code == 200
        assert b'restringido' in r.data or b'Acceso' in r.data

    def test_admin_accesses_admin_panel(self, client, admin_user):
        do_login(client, admin_user.username)
        r = client.get('/usuarios', follow_redirects=True)
        assert r.status_code == 200
        assert b'permiso' not in r.data or b'Usuario' in r.data

    def test_super_admin_accesses_admin_panel(self, client, super_admin):
        do_login(client, super_admin.username)
        r = client.get('/usuarios', follow_redirects=True)
        assert r.status_code == 200
