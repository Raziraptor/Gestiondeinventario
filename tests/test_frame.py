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
