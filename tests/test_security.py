"""
Tests de seguridad:
  - Cabeceras HTTP en todas las respuestas
  - Aislamiento multi-tenant (un usuario de Org B no ve datos de Org A)
  - Rutas protegidas requieren autenticación
"""

import pytest
from app.models.inventory import Categoria
from app.extensions import db
from tests.conftest import do_login


# ── Cabeceras de seguridad ─────────────────────────────────────────────────────

class TestSecurityHeaders:
    """_register_security_headers() debe añadir cabeceras en TODAS las respuestas."""

    def test_x_frame_options(self, client):
        r = client.get('/login')
        assert r.headers.get('X-Frame-Options') == 'SAMEORIGIN'

    def test_x_content_type_options(self, client):
        r = client.get('/login')
        assert r.headers.get('X-Content-Type-Options') == 'nosniff'

    def test_referrer_policy_present(self, client):
        r = client.get('/login')
        assert 'Referrer-Policy' in r.headers

    def test_content_security_policy_present(self, client):
        r = client.get('/login')
        assert 'Content-Security-Policy' in r.headers

    def test_hsts_present(self, client):
        r = client.get('/login')
        assert 'Strict-Transport-Security' in r.headers

    def test_headers_present_on_authenticated_route(self, client, admin_user):
        do_login(client, admin_user.username)
        r = client.get('/ordenes', follow_redirects=True)
        assert r.headers.get('X-Frame-Options') == 'SAMEORIGIN'
        assert 'Content-Security-Policy' in r.headers


# ── Aislamiento multi-tenant ───────────────────────────────────────────────────

class TestMultiTenantIsolation:
    """
    Verifica que get_item_or_404() filtre por org.
    Un usuario de Org B no debe poder leer ni editar recursos de Org A.
    """

    def test_cross_org_category_edit_denied(self, client, org, org_beta,
                                             admin_user, beta_admin):
        cat = Categoria(nombre='Cat Alfa Privada', organizacion_id=org.id)
        db.session.add(cat)
        db.session.commit()
        cat_id = cat.id

        do_login(client, beta_admin.username)
        r = client.get(f'/categoria/editar/{cat_id}', follow_redirects=True)
        # Debe ser 404 (get_item_or_404 no lo encuentra) o redirigir sin datos
        assert r.status_code == 404 or b'Cat Alfa Privada' not in r.data

    def test_own_org_category_edit_accessible(self, client, org, admin_user):
        cat = Categoria(nombre='Cat Alfa Propia', organizacion_id=org.id)
        db.session.add(cat)
        db.session.commit()

        do_login(client, admin_user.username)
        r = client.get(f'/categoria/editar/{cat.id}', follow_redirects=True)
        assert r.status_code == 200
        assert b'Cat Alfa Propia' in r.data

    def test_super_admin_can_access_any_org_resource(self, client, org,
                                                       super_admin):
        cat = Categoria(nombre='Cat Super', organizacion_id=org.id)
        db.session.add(cat)
        db.session.commit()

        do_login(client, super_admin.username)
        r = client.get(f'/categoria/editar/{cat.id}', follow_redirects=True)
        # super_admin siempre pasa el filtro de org
        assert r.status_code == 200
        assert b'Cat Super' in r.data


# ── Rutas protegidas requieren autenticación ───────────────────────────────────

class TestAuthenticationRequired:
    @pytest.mark.parametrize('path', [
        '/ordenes',
        '/categorias',
        '/proveedores',
        '/almacenes',
        '/usuarios',
    ])
    def test_unauthenticated_access_redirects_to_login(self, client, path):
        r = client.get(path, follow_redirects=False)
        assert r.status_code in (301, 302)
        assert 'login' in r.headers.get('Location', '').lower()

    def test_login_page_publicly_accessible(self, client):
        r = client.get('/login')
        assert r.status_code == 200

    def test_register_page_publicly_accessible(self, client):
        r = client.get('/register')
        assert r.status_code == 200
