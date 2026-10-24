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
