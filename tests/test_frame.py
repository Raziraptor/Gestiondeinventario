import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FUSION = (ROOT / 'static/css/fusion.css').read_text(encoding='utf-8')

def _block(selector):
    m = re.search(re.escape(selector) + r'\s*\{([^}]*)\}', FUSION)
    assert m, f'no existe bloque {selector}'
    return m.group(1)

def test_dark_tokens_match_spec():
    b = _block(':root')
    for tok, val in {'--bg': '#15161c', '--card': '#1c1e26', '--card-2': '#20232c',
                     '--text': '#ececef', '--accent': '#9184d9', '--accent-deep': '#b3a9e6',
                     '--on-accent': '#15161c', '--danger': '#e0716d', '--glow': 'none'}.items():
        assert re.search(rf'{tok}\s*:\s*{re.escape(val)}\s*;', b), tok

def test_light_tokens_match_spec():
    b = _block('[data-theme="light"]')
    for tok, val in {'--bg': '#f6f2ea', '--card': '#fdfaf4', '--text': '#201e1d',
                     '--border': '#e2dccf', '--border-strong': '#201e1d', '--accent': '#c67139',
                     '--on-accent': '#ffffff', '--danger': '#b0473b', '--glow': 'none'}.items():
        assert re.search(rf'{tok}\s*:\s*{re.escape(val)}\s*;', b), tok

def test_no_decorative_gradients_in_fusion():
    assert 'radial-gradient' not in FUSION
    assert '--bg-grad' not in FUSION

def test_theme_color_meta_per_scheme(client):
    html = client.get('/login').get_data(as_text=True)
    assert 'id="themeColorMeta"' in html
    assert 'name="theme-color" content="#15161c" media="(prefers-color-scheme: dark)"' in html
    assert 'name="theme-color" content="#f6f2ea" media="(prefers-color-scheme: light)"' in html
    assert '#4f46e5' not in html

def test_manifest_colors():
    import json
    m = json.loads((ROOT / 'static/manifest.json').read_text(encoding='utf-8'))
    assert m['theme_color'] == '#15161c' and m['background_color'] == '#15161c'


def test_base_has_no_inline_style_block(client):
    src = (ROOT / 'templates/base.html').read_text(encoding='utf-8')
    head = src.split('</head>')[0]
    assert '<style' not in head
    assert 'design-system.css' not in src
    assert not (ROOT / 'static/css/design-system.css').exists()


def test_shell_uses_only_phosphor(client, admin_user):
    from tests.conftest import do_login
    do_login(client, 'admin_alfa')
    assert client.get('/').status_code == 200
    src = (ROOT / 'templates/base.html').read_text(encoding='utf-8')
    assert 'bi bi-' not in src and "'bi " not in src and '"bi ' not in src
    assert "'bi-" not in src
    html = client.get('/').get_data(as_text=True)
    frame = re.sub(r'<main\b.*?</main>', '', html, flags=re.S)
    # solo el marco: el contenido de <main> (plantillas hijas) migra en fases posteriores
    assert re.search(r'class="[^"]*\bbi(-| )', frame) is None


def test_no_legacy_indigo_in_shared_css():
    for f in ('compat.css', 'fusion.css'):
        css = (ROOT / 'static/css' / f).read_text(encoding='utf-8').lower()
        for hexv in ('#4f46e5', '#6366f1', '#10b981', '#ef4444', '#f59e0b'):
            assert hexv not in css, (f, hexv)


def test_border_strong_reserved_for_title_rules():
    owners = {
        'compat.css': ('.form-control, .form-select', '.input-group-text'),
        'fusion.css': ('.btn-ghost', '.input, select.input'),
    }
    for f, sels in owners.items():
        css = (ROOT / 'static/css' / f).read_text(encoding='utf-8')
        for sel in sels:
            m = re.search(re.escape(sel) + r'[^{]*\{([^}]*)\}', css)
            assert m, (f, sel)
            assert '--border-strong' not in m.group(1), (f, sel)


VIEWPORT = ('<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, '
            'viewport-fit=cover, interactive-widget=resizes-content">')

def test_viewport_meta(client):
    assert VIEWPORT in client.get('/login').get_data(as_text=True)

def test_mobile_css_loaded_last(client):
    html = client.get('/login').get_data(as_text=True)
    assert html.index('css/compat.css') < html.index('css/mobile.css')

def test_mobile_css_frame_rules():
    css = (ROOT / 'static/css/mobile.css').read_text(encoding='utf-8')
    for needle in ('overflow-x: clip', 'overscroll-behavior: none', 'touch-action: pan-x pan-y',
                   '100dvh', 'font-size: 16px', 'env(safe-area-inset-top', 'env(safe-area-inset-bottom',
                   'overscroll-behavior-x: contain', 'calc(100vw - 2rem)'):
        assert needle in css, needle

def test_shell_has_no_fixed_px_dialogs():
    src = (ROOT / 'templates/base.html').read_text(encoding='utf-8')
    assert 'max-width:370px' not in src and 'max-width:420px' not in src
    assert 'min-width:310px' not in src and 'min-width:280px' not in src


def test_mobile_input_16px_scoped_to_mobile():
    css = (ROOT / 'static/css/mobile.css').read_text(encoding='utf-8')
    inside, outside, i = [], css, 0
    for m in re.finditer(r'@media \(max-width: 899\.98px\) \{', css):
        depth, j = 1, m.end()
        while depth:
            depth += {'{': 1, '}': -1}.get(css[j], 0)
            j += 1
        inside.append(css[m.end():j - 1])
        outside = outside.replace(css[m.start():j], '')
    block = '\n'.join(inside)
    assert 'font-size: 16px' in block and '.cmd-search-input' in block
    assert 'font-size: 16px' not in outside


def _home(client):
    from tests.conftest import do_login
    do_login(client, 'admin_alfa')
    return client.get('/').get_data(as_text=True)


def test_topbar_avatar_menu_contains_moved_actions(client, admin_user):
    html = _home(client)
    menu = html.split('id="userMenu"')[1].split('</ul>')[0]
    assert 'data-action="theme"' in menu
    assert 'data-push-menu' in menu
    assert 'Cerrar sesión' in menu and 'name="csrf_token"' in menu
    assert 'Personalizar Marca' in menu and 'Cuenta' in menu


def test_desktop_only_topbar_actions_marked(client, admin_user):
    html = _home(client)
    for anchor in ('id="theme-toggle"', 'id="offlinePendingWrap"'):
        tag = re.search(rf'<[^>]*{anchor}[^>]*>', html).group(0)
        assert 'only-desktop' in tag, anchor
    assert html.count('id="theme-toggle"') == 1


def test_menu_logout_is_post_form_danger_mobile_only(client, admin_user):
    html = _home(client)
    menu = html.split('id="userMenu"')[1].split('</ul>')[0]
    li = re.search(r'<li class="[^"]*only-mobile[^"]*">\s*<form[^>]*>.*?</li>', menu, re.S).group(0)
    assert re.search(r'<form[^>]*method="POST"', li)
    assert 'is-danger' in li and 'Cerrar sesión' in li


def test_topbar_logout_form_is_desktop_only(client, admin_user):
    html = _home(client)
    forms = [m for m in re.finditer(r'<form[^>]*action="[^"]*/logout[^"]*"[^>]*>', html)]
    assert len(forms) == 2
    desktop = [m for m in forms if 'only-desktop' in m.group(0)]
    assert len(desktop) == 1
    menu_start = html.index('id="userMenu"')
    menu_end = html.index('</ul>', menu_start)
    in_menu = [m for m in forms if menu_start < m.start() < menu_end]
    assert len(in_menu) == 1 and in_menu[0] not in desktop


def test_avatar_button_aria_label(client, admin_user):
    html = _home(client)
    tag = re.search(r'<button[^>]*id="userMenuBtn"[^>]*>', html).group(0)
    assert 'aria-label="Menú de admin_alfa"' in tag


def _bottom_nav(html):
    return html.split('id="bottomNav"')[1].split('</nav>')[0]


def test_bottom_nav_full_for_admin(client, admin_user, app):
    html = _home(client)
    nav = _bottom_nav(html)
    with app.test_request_context():
        from flask import url_for
        for ep in ('main.dashboard', 'inventory.lista_almacenes',
                   'inventory.registrar_salida', 'purchasing.lista_ordenes'):
            assert f'href="{url_for(ep)}"' in nav, ep
    assert 'data-action="open-sidebar"' in nav
    assert 'aria-label="Nueva salida"' in nav
    assert nav.count('class="bnav-item') == 5


def test_bottom_nav_respects_permissions(client, regular_user, app):
    from tests.conftest import do_login
    do_login(client, 'user_alfa')          # solo perm_view_dashboard
    html = client.get('/').get_data(as_text=True)
    nav = _bottom_nav(html)
    with app.test_request_context():
        from flask import url_for
        assert f'href="{url_for("main.dashboard")}"' in nav
        for ep in ('inventory.lista_almacenes', 'inventory.registrar_salida',
                   'purchasing.lista_ordenes'):
            assert url_for(ep) not in nav, ep
    assert nav.count('class="bnav-item') == 2   # Panel + Más


def test_bottom_nav_hides_almacenes_without_admin_role(client, regular_user, app):
    from tests.conftest import do_login
    from app.extensions import db
    regular_user.perm_view_management = True
    db.session.commit()
    do_login(client, 'user_alfa')
    nav = _bottom_nav(client.get('/').get_data(as_text=True))
    with app.test_request_context():
        from flask import url_for
        assert url_for('inventory.lista_almacenes') not in nav


def test_bottom_nav_active_item_has_aria_current(client, admin_user, app):
    html = _home(client)
    nav = _bottom_nav(html)
    assert nav.count('aria-current="page"') == 1
    with app.test_request_context():
        from flask import url_for
        dash = url_for('main.dashboard')
    tags = re.findall(r'<a [^>]*>', nav)
    current = [t for t in tags if 'aria-current="page"' in t]
    assert len(current) == 1 and f'href="{dash}"' in current[0]


def test_bottom_nav_on_404_has_no_active_item(client, admin_user, app):
    # La app no registra errorhandler: Flask sirve su 404 plano (sin base.html).
    # Se verifica por separado que 404.html, renderizado con request.endpoint=None, no rompe la barra.
    from tests.conftest import do_login
    do_login(client, 'admin_alfa')
    assert client.get('/no-existe').status_code == 404
    from flask import render_template
    from flask_login import login_user
    with app.test_request_context('/no-existe'):
        login_user(admin_user)
        html = render_template('404.html')
    assert 'id="bottomNav"' in html
    assert 'aria-current' not in _bottom_nav(html)


def test_bottom_nav_home_fallback_without_dashboard_perm(client, regular_user, app):
    from tests.conftest import do_login
    from app.extensions import db
    regular_user.perm_view_dashboard = False
    db.session.commit()
    do_login(client, 'user_alfa')
    nav = _bottom_nav(client.get('/').get_data(as_text=True))
    with app.test_request_context():
        from flask import url_for
        assert f'href="{url_for("main.index")}"' in nav
        assert url_for('main.dashboard') not in nav
    assert '<span>Inicio</span>' in nav and 'Panel' not in nav


def test_bottom_nav_almacenes_active_is_exact(client, admin_user, app):
    from tests.conftest import do_login
    do_login(client, 'admin_alfa')
    with app.test_request_context():
        from flask import url_for
        alm = url_for('inventory.lista_almacenes')
    nav = _bottom_nav(client.get(alm).get_data(as_text=True))
    cur = [t for t in re.findall(r'<a [^>]*>', nav) if 'aria-current' in t]
    assert len(cur) == 1 and f'href="{alm}"' in cur[0]
    tpl = (ROOT / 'templates/partials/bottom_nav.html').read_text(encoding='utf-8')
    assert "'almacen' in _ep" not in tpl
    assert 'inventory.lista_productos_sin_almacen' not in tpl


def test_sidebar_stacks_above_bottom_nav():
    css = (ROOT / 'static/css/mobile.css').read_text(encoding='utf-8')
    assert re.search(r'\.sb\s*\{[^}]*z-index:\s*1045', css)
    assert re.search(r'\.sb-backdrop\s*\{[^}]*z-index:\s*1040', css)
    assert re.search(r'\.bnav\s*\{[^}]*z-index:\s*1030', css)


def test_offline_banner_has_no_legacy_id_rules():
    css = (ROOT / 'static/css/compat.css').read_text(encoding='utf-8')
    assert '#offlineBanner' not in css


def test_sidebar_toggle_aria(client, admin_user):
    html = _home(client)
    tag = re.search(r'<button[^>]*id="sidebarMobileToggle"[^>]*>', html).group(0)
    assert 'aria-controls="erpSidebar"' in tag and 'aria-expanded="false"' in tag


def test_login_page_has_no_app_chrome(client):
    html = client.get('/login').get_data(as_text=True)
    assert 'id="bottomNav"' not in html
    assert 'id="userMenuBtn"' not in html
    assert 'id="fabMain"' not in html


def test_image_viewer_loaded_and_dashboard_thumbs_zoomable():
    base = (ROOT / 'templates/base.html').read_text(encoding='utf-8')
    dash = (ROOT / 'templates/dashboard.html').read_text(encoding='utf-8')
    assert 'js/image-viewer.js' in base
    assert 'data-zoomable' in dash
    js = (ROOT / 'static/js/image-viewer.js').read_text(encoding='utf-8')
    assert 'onclick' not in js and 'innerHTML' not in js     # CSP + XSS: construir con createElement
    css = (ROOT / 'static/css/mobile.css').read_text(encoding='utf-8')
    assert re.search(r'\.iv-overlay\s*\{[^}]*z-index:\s*10050', css)
    assert re.search(r'\.iv-overlay\s*\{[^}]*touch-action:\s*none', css)
    close = re.search(r'\.iv-close\s*\{([^}]*)\}', css).group(1)
    assert '#fff' not in close and 'rgba(' not in close and 'var(--iv-fg)' in close
    fus = (ROOT / 'static/css/fusion.css').read_text(encoding='utf-8')
    assert fus.count('--iv-fg:') == 2 and fus.count('--iv-btn-bg:') == 2
    for name in ('incidencias/detalle.html', 'incidencias/form.html',
                 'productos_sin_almacen.html', 'producto_form.html'):
        assert 'data-zoomable' in (ROOT / 'templates' / name).read_text(encoding='utf-8')


def test_every_photo_img_is_zoomable():
    photo = re.compile(r"imagen_url|foto_path|foto\d_path|filename=ruta")
    seen = 0
    for path in (ROOT / 'templates').rglob('*.html'):
        for tag in re.findall(r'<img\b[^>]*>', path.read_text(encoding='utf-8')):
            src = re.search(r'src="([^"]*)"', tag)
            if src and photo.search(src.group(1)):
                seen += 1
                assert 'data-zoomable' in tag, f'{path.name}: {tag}'
    assert seen >= 9


def test_incident_photos_have_no_wrapping_link():
    html = (ROOT / 'templates/incidencias/detalle.html').read_text(encoding='utf-8')
    assert 'target="_blank"' not in html
