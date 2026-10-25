import re
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
        assert re.search(r'class="[^"]*(?<![\w-])%s(?![\w-])[^"]*"' % re.escape(c), html), c
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
    row = re.search(r'<tr[^>]*>(?:(?!</tr>).)*El almacén está vacío', html, re.S)
    assert row, 'fila vacía no encontrada'
    open_tr = re.findall(r'<tr[^>]*>', row.group(0))[-1]
    assert 'fila-producto' not in open_tr


def _card_block():
    src = DASHBOARD_SRC.read_text(encoding='utf-8')
    start = src.index('@media (max-width: 639.98px)')
    depth, i = 0, src.index('{', start)
    begin = i
    while True:
        depth += 1 if src[i] == '{' else -1 if src[i] == '}' else 0
        if depth == 0:
            return src[begin:i + 1]
        i += 1


def test_card_grid_scoped_to_fila_producto_only():
    block = _card_block()
    m = re.search(r'tr\.fila-producto\s*\{([^}]*)\}', block)
    assert m and 'display: grid' in m.group(1)
    assert not re.search(r'(^|[\s,}])tr\s*\{', block)


def test_card_name_clamps_two_lines_and_font_floor():
    block = _card_block()
    assert '-webkit-line-clamp: 2' in block and 'nowrap' not in block.split('.td-nombre .nombre')[1].split('}')[0]
    src = DASHBOARD_SRC.read_text(encoding='utf-8')
    for size in re.findall(r'font-size:\s*(\d*\.?\d+)rem', src.split('</style>')[0]):
        assert float(size) >= .75, size
