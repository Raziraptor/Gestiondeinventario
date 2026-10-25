from pathlib import Path

import pytest

from app.extensions import db
from app.models.inventory import Almacen, Producto, Stock
from tests.conftest import do_login

DASHBOARD_SRC = Path(__file__).resolve().parent.parent / 'templates' / 'dashboard.html'


@pytest.fixture
def almacen_con_producto(org):
    a = Almacen(nombre='Bodega Central', organizacion_id=org.id)
    p = Producto(nombre='Tornillo', codigo='T-001', organizacion_id=org.id, imagen_url='t.jpg')
    db.session.add_all([a, p])
    db.session.flush()
    db.session.add(Stock(producto_id=p.id, almacen_id=a.id, cantidad=3, stock_minimo=5))
    db.session.commit()
    return a


def _dash(client):
    do_login(client, 'admin_alfa')
    r = client.get('/dashboard')
    assert r.status_code == 200
    return r.get_data(as_text=True)


def test_dashboard_rows_keep_js_hooks_and_card_cells(client, admin_user, almacen_con_producto):
    html = _dash(client)
    assert 'class="fila-producto"' in html and 'data-href=' in html
    for c in ('td-img', 'td-sku', 'td-nombre', 'td-stock', 'td-estado', 'td-acc', 'td-acciones'):
        assert c in html, c
    assert 'data-zoomable' in html
    assert 'id="ordenMovil"' in html


def test_dashboard_has_no_bootstrap_icons(client, admin_user, almacen_con_producto):
    html = _dash(client)
    assert 'bi bi-' not in html


def test_dashboard_empty_row_not_card(client, admin_user):
    a = Almacen(nombre='Vacío', organizacion_id=admin_user.organizacion_id)
    db.session.add(a)
    db.session.commit()
    html = _dash(client)
    assert 'El almacén está vacío' in html
    src = DASHBOARD_SRC.read_text(encoding='utf-8')
    assert 'tr.fila-producto {' in src or 'tr.fila-producto{' in src
