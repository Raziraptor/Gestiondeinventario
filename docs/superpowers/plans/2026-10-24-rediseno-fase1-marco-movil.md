# Rediseño Fase 1 — Marco común, móvil tipo app y Dashboard · Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que toda la app adopte de una vez los tokens "Fusion refinada / Pergamino + terracota" y un marco móvil que nunca se mueve de lado (sin zoom, con bordes seguros, barra inferior), y que el Dashboard quede rediseñado con su tabla convertida en tarjetas en móvil.

**Architecture:** Los tokens viven solo en `static/css/fusion.css`; `compat.css` absorbe el `<style>` inline de `base.html` y lo útil de `design-system.css` (que se elimina). Todo lo de la sección 5 del spec va en un archivo nuevo `static/css/mobile.css`, cargado al final. El marco (`base.html`) gana una topbar compacta, una barra inferior en un parcial y un visor de imágenes en vanilla JS activado por `data-zoomable`. El Dashboard conserva sus filas `tr.fila-producto` y las reacomoda por CSS grid en < 640px.

**Tech Stack:** Flask + Jinja2, Bootstrap 5.3.3, Chart.js 4.4.3, Phosphor Icons, Inter + Archivo, vanilla JS, pytest (SQLite en memoria), Playwright (Python) para la verificación de anchos.

**Spec:** `docs/superpowers/specs/2026-10-24-rediseno-fusion-movil-design.md` — este plan cubre las fases 1 (marco común) y 2 (Dashboard) de la sección 7 del spec. Las fases 3 (otras 10 pantallas) y 4 (resto de plantillas) van en planes posteriores.

## Global Constraints

- CSP con nonces: **cero** handlers inline (`onclick=`, `onchange=`…); todo `<script>` inline lleva `nonce="{{ csp_nonce() }}"`; no se agregan CDNs nuevos (script-src permitido: `'self'`, nonce, `cdn.jsdelivr.net`).
- Keyframes que se apliquen a `<main>` o ancestros de modales: el `to` solo con `opacity` (nunca `transform`) — GOTCHA de stacking context, commit `37426b4`.
- Modales de páginas hijas en `{% block modals %}`, nunca dentro de `{% block content %}`.
- Punto de quiebre móvil: `max-width: 899.98px` (móvil) / `min-width: 900px` (escritorio). Tarjetas de tabla: `max-width: 639.98px`.
- Tokens exactos de la sección 4.1 del spec; `--glow: none` en ambos temas; sin gradientes decorativos.
- Archivo 600–700 (nunca 800) en títulos/kickers/cifras; Inter 400–500 en cuerpo, 600 solo botones/etiquetas cortas.
- Radios: tarjetas 14px, inputs 10px, botones/chips 999px, miniaturas 10px. Cifras con `font-variant-numeric: tabular-nums`.
- Sin `box-shadow` en tarjetas en reposo; sombra solo en flotantes (dropdown, modal, toast, FAB) y en hover dentro de `@media (hover:hover)`.
- Iconos nuevos o tocados: Phosphor (`ph ph-…`). El `<link>` de Bootstrap Icons se queda en esta fase (otras 58 plantillas aún lo usan).
- No cambia lógica de negocio, rutas, modelos ni permisos. IDs que usa JS existente se conservan: `#theme-toggle`, `#pushNavItem`, `#pushToggleBtn`, `#pushTestBtn`, `#pushBellIcon`, `#offlinePendingWrap`, `#offlinePendingBadge`, `#alertaBell`, `#alerta-badge`, `#alerta-lista`, `#alerta-count-label`, `#erpSidebar`, `#sidebarMobileToggle`, `#sbBackdrop`, `#cmdTrigger`, `#fabMain`, `#fabItems`, `#toastContainer`, `#offlineBanner*`, `#pwaInstallBanner`, `#tabla_inventario`, `#tabla_productos_cuerpo`, `.fila-producto`, `.td-acciones`, `.th-sortable`, `#contador_registros`.
- Tests: `SECRET_KEY=test python -m pytest -q`. Línea base: 56 pasan, 1 falla preexistente (`tests/test_auth.py::TestRegistration::test_register_duplicate_username_rejected`) que no se toca.
- Cada commit va seguido de `git push origin main` (regla del proyecto). Mensajes de commit terminan con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Antes de implementar UI: `/ui-ux-pro-max` + `/frontend-design` (CLAUDE.md del usuario). Antes de cerrar: `/ponytail-review` y code-review con Opus.

## Review Focus

1. **iOS Safari con teclado abierto** (input enfocado en la topbar o en un modal): la vista no debe hacer zoom ni quedar desplazada de lado al cerrar el teclado. → Task 3 verifica `font-size: 16px` computado en campos a 375px (paso Playwright en Task 8).
2. **Usuario con permisos parciales** (sin `perm_view_dashboard`, sin `perm_do_salidas`, sin `perm_create_oc_standard`): la barra inferior no debe mostrar destinos que le den 403. → test `test_bottom_nav_respects_permissions` en Task 5.
3. **Usuario no autenticado** (login, forgot/reset password, 403/404/500 con base.html): no debe renderizarse barra inferior, menú de avatar ni FAB, y nada debe romper por `current_user` anónimo. → test `test_login_page_has_no_app_chrome` en Task 5.
4. **Dashboard con 0 productos o sin almacén**: la fila vacía `colspan="9"` no debe heredar el grid de tarjetas y verse rota. → test `test_dashboard_empty_row_not_card` en Task 7 + regla CSS `tr.fila-producto` (no `tr`).
5. **Cambiar de tema con gráficas abiertas y en la PWA instalada**: las gráficas se redibujan con los colores nuevos y la barra de estado (`theme-color`) cambia sin recargar. → test `test_theme_color_meta_per_scheme` en Task 1 + verificación manual en Task 8.

---

### Task 1: Tokens nuevos y tema unificado

**Files:**
- Modify: `static/css/fusion.css` (bloque `:root` / `[data-theme="dark"]` y `[data-theme="light"]`, regla de `body` con `--bg-grad`)
- Modify: `static/js/fusion.js:158-171` (`setFusionTheme`, `toggleFusionTheme`)
- Modify: `templates/base.html:12` (meta theme-color), `:44-49` (script de tema previo al paint), `:954-956` (`#theme-toggle`), `:1177-1199` (script `applyTheme` — se elimina)
- Modify: `static/manifest.json` (`theme_color`, `background_color`)
- Test: `tests/test_frame.py` (nuevo)

**Interfaces:**
- Produces: `window.setFusionTheme(t: 'dark'|'light')` — única función de tema: escribe `data-theme` y `data-bs-theme` en `<html>`, guarda `erp_theme` **y** `app_theme` en localStorage (try/catch), pone `content` de `meta#themeColorMeta` = `getComputedStyle(html).getPropertyValue('--bg').trim()`, cambia la clase de todo `[data-theme-icon]` a `ph ph-sun` (oscuro) / `ph ph-moon` (claro), y despacha `themechange` en `window`.
- Produces: `window.toggleFusionTheme()`; cualquier elemento con `data-action="theme"` lo dispara (el binding ya existe en `fusion.js:179`).
- Produces: tokens CSS usados por todas las tareas siguientes: `--bg --card --card-2 --text --muted --faint --border --border-strong --accent --accent-deep --accent-tint --on-accent --sage --sage-tint --warn --warn-tint --danger --danger-tint --info --info-tint --glow`.

- [ ] **Step 1: Escribir los tests que fallan** en `tests/test_frame.py`

```python
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
```

(Ajustar la URL `/login` si el blueprint de auth monta otra ruta; verificar con `flask routes`.)

- [ ] **Step 2: Correr y ver que fallan**

Run: `SECRET_KEY=test python -m pytest tests/test_frame.py -v`
Expected: FAIL en los 5 tests (tokens viejos, `--bg-grad` presente, theme-color `#4f46e5`).

- [ ] **Step 3: Reescribir tokens en `fusion.css`**

Valores exactos de la tabla 4.1 del spec. Los tokens oscuros van en un bloque con selector exacto `:root { … }` (tema por defecto; `[data-theme="dark"]` no necesita bloque propio) y los claros en `[data-theme="light"] { … }` — los tests buscan esos dos selectores literales. Nombres de tints: `--sage-tint`, `--warn-tint`, `--danger-tint`, `--info-tint` (oscuro: el color a `.13` en `rgba`; claro: `#e8ecdc`, `#f3e7cf`, `#f4ddd8`, `rgba(74,127,165,.11)`). `body { background: var(--bg) }` sólido. Gradientes del logo (`.sb-logo`) y avatar → `background: var(--accent); color: var(--on-accent)`. Conservar cualquier otro token existente que usen componentes (`--sb-w`, `--r-card`…), ajustando `--r-card: 14px`.

- [ ] **Step 4: Unificar el tema**

- `base.html`: dos metas `<meta name="theme-color" content="#15161c" media="(prefers-color-scheme: dark)">` y `…#f6f2ea… light`, más `<meta name="theme-color" id="themeColorMeta" content="#15161c">` después de ellas (la sin `media` gana cuando JS la actualiza).
- El script previo al paint (línea 44) además pone `themeColorMeta.content` según el tema leído (`#15161c` / `#f6f2ea`), dentro del try/catch existente.
- `#theme-toggle` recibe `data-action="theme"`; su `<i>` recibe `data-theme-icon`. Borrar el script `applyTheme` de las líneas 1177-1199 (su lógica pasa a `setFusionTheme`).
- `fusion.js`: `setFusionTheme` según la interfaz de arriba; `toggleFusionTheme` lee `document.documentElement.dataset.theme` (no localStorage, que puede fallar). Al cargar, sincroniza los iconos con el tema actual.
- `manifest.json`: `theme_color` y `background_color` = `#15161c`.

- [ ] **Step 5: Correr los tests**

Run: `SECRET_KEY=test python -m pytest -q`
Expected: los 5 nuevos PASS; 56 previos PASS; 1 falla preexistente sin cambios.

- [ ] **Step 6: Commit**

```bash
git add static/css/fusion.css static/js/fusion.js static/manifest.json templates/base.html tests/test_frame.py
git commit -m "feat(ui): tokens Fusion refinada / Pergamino + terracota y tema unificado"
git push origin main
```

---

### Task 2: Consolidación CSS (una sola fuente de tokens)

**Files:**
- Modify: `static/css/compat.css` (recibe las reglas del `<style>` de `base.html` y lo vivo de `design-system.css`)
- Modify: `templates/base.html` (borrar `<style>…</style>` del `<head>`, borrar `<link>` a `design-system.css`, Bootstrap Icons → Phosphor en el marco)
- Delete: `static/css/design-system.css`
- Test: `tests/test_frame.py`

**Interfaces:**
- Consumes: tokens de Task 1.
- Produces: orden de hojas en `<head>`: Bootstrap → `fusion.css` → `compat.css` → (`mobile.css`, Task 3). Ningún `<style>` en `base.html`; los `{% block extra_css %}` de páginas hijas siguen funcionando.

- [ ] **Step 1: Tests que fallan**

```python
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

def test_no_legacy_indigo_in_shared_css():
    for f in ('compat.css', 'fusion.css'):
        css = (ROOT / 'static/css' / f).read_text(encoding='utf-8').lower()
        for hexv in ('#4f46e5', '#6366f1', '#10b981', '#ef4444', '#f59e0b'):
            assert hexv not in css, (f, hexv)
```

- [ ] **Step 2: Correr y ver que fallan** — Run: `SECRET_KEY=test python -m pytest tests/test_frame.py -v` · Expected: FAIL los 3.

- [ ] **Step 3: Migrar `<style>` de `base.html` a `compat.css`**

Mover el bloque entero al final de `compat.css` bajo el comentario `/* ── Componentes del marco (antes inline en base.html) ── */`. Al moverlo: todo hex de estado → tokens (`#10b981`→`var(--sage)`, `#ef4444`→`var(--danger)`, `#f59e0b`→`var(--warn)`, `var(--primary)` se queda porque compat ya lo mapea a `--accent`, `#fff` sobre acento → `var(--on-accent)`); fondos `rgba(...,.12)` de badges → `var(--*-tint)`. Aplicar las reglas 4.2 del spec en lo movido: quitar `translateY/scale` en hover de `.content-card`/`.dashboard-card` (dejar solo `border-color` y sombra dentro de `@media (hover:hover)`), quitar `rotate` de `.card-icon` y `.theme-btn`, `.dropdown-header` y `.total-panel-value` a peso 700, toasts con `animation` sin rebote (`cubic-bezier(.2,.8,.2,1)`). El `@media (max-width:576px)` de dropdowns se borra (lo reemplaza Task 3). En `fusion.css` y `compat.css` quitar además (regla 4.2): el punto pulsante de la campana (keyframe/animación del badge), el rebote de dropdowns (`cubic-bezier(.34,1.2,…)` / `(.34,1.56,…)`) y el `translateX` en hover de `.sb-item`; Archivo 800 → 700 donde aparezca.

- [ ] **Step 4: Vaciar y borrar `design-system.css`**

Para cada selector del archivo, `grep -rn "<clase>" templates static/js`; los que tengan uso (p.ej. `.status-pill`, `.status-pill--ok/--danger/--info/--warn` del dashboard) se reescriben en `compat.css` con tokens (`--sage`/`--sage-tint`, etc., pill 999px, peso 600, 0.75rem). Tokens propios (`--sidebar-*`, `--status-*`, indigo/slate) se descartan. Borrar el archivo y su `<link>`.

- [ ] **Step 5: Bootstrap Icons → Phosphor en `base.html`**

Incluye strings dentro de scripts del marco (modal de confirmación, toasts, FAB, paleta de comandos). Equivalencias: `bi-search`→`ph-magnifying-glass`, `bi-exclamation-triangle-fill`→`ph-fill ph-warning`, `bi-check-circle-fill`→`ph-fill ph-check-circle`, `bi-x-circle-fill`→`ph-fill ph-x-circle`, `bi-info-circle-fill`→`ph-fill ph-info`, `bi-plus-lg`→`ph-plus`, `bi-x-lg`→`ph-x`; el resto por nombre equivalente en phosphoricons.com.

- [ ] **Step 6: Tests + revisión visual rápida** — Run: `SECRET_KEY=test python -m pytest -q` · Expected: PASS (salvo la preexistente). Abrir `/` y `/dashboard` en escritorio con `flask run` y comparar contra la maqueta B/C: sin indigo visible, toasts y modal de confirmación con íconos.

- [ ] **Step 7: Commit**

```bash
git add -A static/css templates/base.html tests/test_frame.py
git commit -m "refactor(css): una sola fuente de tokens; base.html sin <style>; adiós design-system.css"
git push origin main
```

---

### Task 3: Capa móvil del marco (`mobile.css`)

**Files:**
- Create: `static/css/mobile.css`
- Modify: `templates/base.html:5` (viewport), `<head>` (link a `mobile.css` tras `compat.css`), modales del marco con `style="max-width:370px/420px"`, `#offlineBanner` y `#pwaInstallBanner` (estilos inline → clases)
- Modify: `static/css/fusion.css` (`.searchbar` con `min-width:0`; `.sb` `height:100dvh`)
- Test: `tests/test_frame.py`

**Interfaces:**
- Produces (clases para tareas siguientes): `.only-desktop` (oculto < 900px), `.only-mobile` (oculto ≥ 900px), `.app-banner` (banner flotante inferior con safe-area), `.modal-dialog.modal-sm-fluid` (ancho `min(var(--modal-w, 420px), calc(100vw - 2rem))`).
- Produces: variable `--bnav-h: 64px` (alto de la barra inferior, usado por Task 5) y `--safe-b: env(safe-area-inset-bottom, 0px)`.

- [ ] **Step 1: Tests que fallan**

```python
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
```

- [ ] **Step 2: Correr y ver que fallan** — Expected: FAIL los 4.

- [ ] **Step 3: Escribir `mobile.css`** con estas reglas (secciones 5.1, 5.3, 5.4, 5.7 del spec):

- Global: `html, body { overflow-x: clip; }`, `html { overscroll-behavior: none; touch-action: pan-x pan-y; -webkit-text-size-adjust: 100%; }`, `body { min-height: 100dvh; }`, `.shell, .main-wrap, .main, .topbar > * { min-width: 0; }`, `.table-responsive { overscroll-behavior-x: contain; -webkit-overflow-scrolling: touch; }`, `img, video, canvas { max-width: 100%; }`.
- `@media (max-width: 899.98px)`: `input, select, textarea, .form-control, .form-select, .input { font-size: 16px; }`; `.topbar { padding-top: calc(8px + env(safe-area-inset-top, 0px)); padding-left: max(12px, env(safe-area-inset-left)); padding-right: max(12px, env(safe-area-inset-right)); }`; `.sb { height: 100dvh; padding-bottom: env(safe-area-inset-bottom); padding-top: env(safe-area-inset-top); }`; `.dropdown-menu { max-width: calc(100vw - 2rem); }`; `.modal-dialog { margin: .75rem auto; max-width: calc(100vw - 2rem); }`.
- `.only-desktop/.only-mobile`, `.modal-sm-fluid`, `.app-banner` (fixed, `left: 50%`, `transform: translateX(-50%)`, `bottom: calc(1rem + var(--safe-b))`, ancho `min(360px, calc(100vw - 2rem))`, fondo `var(--card)`, borde `var(--border)`, texto `var(--text)`, sombra flotante, radio 14px; en móvil `bottom: calc(var(--bnav-h) + 12px + var(--safe-b))`).

- [ ] **Step 4: Ajustar `base.html` y `fusion.css`**

Viewport exacto del test. `.searchbar { min-width: 0; }` y su `<kbd>` oculto < 900px. Modales del marco: quitar `style="max-width:…"` y usar `class="modal-dialog modal-dialog-centered modal-sm-fluid"` con `style="--modal-w:370px"` / `420px`. Dropdown de la campana: quitar `min-width:310px;max-width:340px` → `style="width:min(340px, calc(100vw - 2rem))"`. Banners: estilos inline → `class="app-banner"` (+ `display:none` inicial, que el JS existente ya cambia); los colores fijos `#1e293b/#f1f5f9` desaparecen.

(Nota: `maximum-scale=1` bloquea el pellizco del navegador en Android; el visor de imágenes de Task 6 hace su propio zoom con transform, así que no le afecta.)

- [ ] **Step 5: Tests** — Run: `SECRET_KEY=test python -m pytest -q` · Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add static/css/mobile.css static/css/fusion.css templates/base.html tests/test_frame.py
git commit -m "feat(movil): marco fijo sin desplazamiento lateral, sin zoom de UI y con safe-area"
git push origin main
```

---

### Task 4: Topbar compacta y menú de avatar

**Files:**
- Modify: `templates/base.html:883-1006` (topbar), script de push (`:1456-…`, donde se hace `pushNavItem.style.display = ''`)
- Modify: `static/js/offline-queue.js:69-80` (función que actualiza `#offlinePendingBadge`)
- Modify: `static/css/mobile.css`, `static/css/fusion.css` (`.avatar-btn`)
- Test: `tests/test_frame.py`

**Interfaces:**
- Consumes: `.only-desktop` / `.only-mobile` (Task 3); `data-action="theme"` + `data-theme-icon` (Task 1).
- Produces: `#userMenuBtn` (botón avatar, siempre visible cuando hay sesión) con su `ul.dropdown-menu#userMenu`. Atributo `data-pending` en `#userMenuBtn` cuando hay operaciones offline pendientes (punto `--warn` vía `::after`).
- Produces: elementos proxy `[data-push-proxy="toggle"]` y `[data-push-proxy="test"]` (dentro de `li[data-push-menu]`, inicialmente `hidden`) que hacen `.click()` sobre `#pushToggleBtn` / `#pushTestBtn`.

- [ ] **Step 1: Tests que fallan**

```python
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
```

- [ ] **Step 2: Correr y ver que fallan** — Expected: FAIL los 2.

- [ ] **Step 3: Reestructurar la topbar**

Orden: hamburguesa (`.only-mobile`… mantener la clase `menu-btn` existente) · buscador · [`#offlinePendingWrap`, `#pushNavItem`, `#theme-toggle`, form de logout → `class="only-desktop"`] · campana · `#userMenuBtn`. El botón de tres puntos actual se reemplaza por `#userMenuBtn` (`.avatar-btn`: 36px, círculo `--accent`/`--on-accent`, inicial de `current_user.username`, `aria-label="Menú de {{ current_user.username }}"`). `#userMenu` contiene, en orden: cabecera (nombre + rol), ítems admin existentes, Cuenta, divider, `li.only-mobile` con botón `data-action="theme"` ("Cambiar tema", icono `data-theme-icon`), `li.only-mobile[data-push-menu][hidden]` con proxies push ("Notificaciones push", "Enviar prueba"), divider `only-mobile`, `li.only-mobile` con `<form method="POST" action="{{ url_for('auth.logout') }}">` + `csrf_token` + botón "Cerrar sesión" en `--danger`. Iconos de menú en `--muted` (regla 4.2: nada de colores variados).

- [ ] **Step 4: Cablear proxies y punto offline**

- Script de push: donde hace `pushNavItem.style.display = ''`, también `document.querySelectorAll('[data-push-menu]').forEach(li => li.hidden = false)`; el ítem "Enviar prueba" se muestra/oculta igual que `#pushTestBtn`. Un listener delegado en `#userMenu` para `[data-push-proxy]` llama `.click()` en el botón real.
- `offline-queue.js`: en la función que escribe `#offlinePendingBadge`, `userMenuBtn.toggleAttribute('data-pending', count > 0)` (con guard si no existe).
- CSS: `.avatar-btn[data-pending]::after` — punto 9px `--warn`, borde 2px `--bg`, arriba a la derecha.

- [ ] **Step 5: Tests** — Run: `SECRET_KEY=test python -m pytest -q` · Expected: PASS.

- [ ] **Step 6: Verificación manual a 320px** (DevTools, iPhone SE): la topbar cabe completa, el buscador se encoge, el menú del avatar abre dentro de la pantalla, cambiar tema desde el menú actualiza icono y `theme-color`.

- [ ] **Step 7: Commit**

```bash
git add templates/base.html static/js/offline-queue.js static/css tests/test_frame.py
git commit -m "feat(movil): topbar compacta; tema, push y logout pasan al menú del avatar"
git push origin main
```

---

### Task 5: Navegación inferior, FAB, toasts y banners

**Files:**
- Create: `templates/partials/bottom_nav.html`
- Modify: `templates/base.html` (incluir el parcial justo después de `</div>{# end shell #}`; script del sidebar `:1201-1222` para escuchar `[data-action="open-sidebar"]`; FAB `:1079-1112`)
- Modify: `static/css/mobile.css`
- Test: `tests/test_frame.py`

**Interfaces:**
- Consumes: `--bnav-h`, `--safe-b`, `.only-mobile` (Task 3).
- Produces: `nav.bnav#bottomNav` con hijos `a.bnav-item` / `button.bnav-item[data-action="open-sidebar"]`; activo = `.bnav-item.active` + `aria-current="page"`.

Regla de permisos (decisión del builder, mismos checks que el sidebar):

| Destino | Se muestra si | Si no |
|---|---|---|
| Panel → `main.dashboard` | `rol in ['super_admin','admin'] or perm_view_dashboard` | se muestra "Inicio" → `main.index` |
| Almacenes → `inventory.lista_almacenes` | `rol in [...] or perm_view_management` | se omite |
| Nueva salida → `inventory.registrar_salida` | `rol in [...] or perm_do_salidas` | se omite |
| Órdenes → `purchasing.lista_ordenes` | `rol in [...] or perm_create_oc_standard` | se omite |
| Más (abre sidebar) | siempre | — |

Activo: Panel con `main.dashboard`/`main.index`; Almacenes con `request.endpoint.startswith('inventory.') and 'almacen' in request.endpoint`; Nueva salida con `inventory.registrar_salida`; Órdenes con endpoints `purchasing.*orden*`.

- [ ] **Step 1: Tests que fallan**

```python
def test_bottom_nav_full_for_admin(client, admin_user):
    html = _home(client)
    nav = html.split('id="bottomNav"')[1].split('</nav>')[0]
    for ep in ('/dashboard', 'almacenes', 'salida', 'ordenes'):
        assert ep in nav, ep
    assert 'data-action="open-sidebar"' in nav

def test_bottom_nav_respects_permissions(client, regular_user):
    from tests.conftest import do_login
    do_login(client, 'user_alfa')          # solo perm_view_dashboard
    html = client.get('/').get_data(as_text=True)
    nav = html.split('id="bottomNav"')[1].split('</nav>')[0]
    assert '/dashboard' in nav
    assert 'ordenes' not in nav and 'registrar' not in nav
    assert nav.count('class="bnav-item') == 2   # Panel + Más

def test_login_page_has_no_app_chrome(client):
    html = client.get('/login').get_data(as_text=True)
    assert 'id="bottomNav"' not in html
    assert 'id="userMenuBtn"' not in html
    assert 'id="fabMain"' not in html
```

(Ajustar fragmentos de URL a lo que generen los `url_for` reales; ver `flask routes`.)

- [ ] **Step 2: Correr y ver que fallan** — Expected: FAIL los 3 (el tercero puede fallar por el FAB si hoy se renderiza sin sesión; si ya pasa, dejarlo como guardia).

- [ ] **Step 3: Parcial `bottom_nav.html` + CSS**

Solo si `current_user.is_authenticated`. Cada ítem: icono Phosphor (`ph-squares-four`, `ph-buildings`, `ph-arrow-square-out`, `ph-shopping-cart`, `ph-dots-three-outline`) + etiqueta 0.68rem peso 600. CSS: `.bnav` fija abajo, `height: calc(var(--bnav-h) + var(--safe-b))`, `padding-bottom: var(--safe-b)`, fondo `var(--card)`, borde superior `var(--border)`, grid de columnas iguales; `.bnav-item.active` con pastilla `--accent-tint` y color `--accent`; táctil ≥ 44px; oculta en ≥ 900px. En móvil `.main { padding-bottom: calc(var(--bnav-h) + var(--safe-b) + 24px); }`.

- [ ] **Step 4: Cablear "Más", FAB, toasts**

- Script del sidebar: además de `#sidebarMobileToggle`, cualquier `[data-action="open-sidebar"]` llama `openMobile()`; al abrir, foco al primer `.sb-item`; Escape cierra (ya existe).
- FAB (decisión del builder: se queda, elevado sobre la barra): envolver en `{% if current_user.is_authenticated %}`; en móvil `.fab-container { bottom: calc(var(--bnav-h) + var(--safe-b) + 16px); right: max(16px, env(safe-area-inset-right)); }`; colores fijos de `.fab-item-btn` (`#6366f1/#ef4444/#10b981`) → `var(--accent)`/`var(--card)` con borde, `.fab-main` sin glow (sombra flotante neutra), sin rebote.
- Toasts en móvil: `left: 16px; right: 16px; bottom: calc(var(--bnav-h) + var(--safe-b) + 12px); max-width: none;` y `min-width: 0` en `.toast-app`.

- [ ] **Step 5: Tests** — Run: `SECRET_KEY=test python -m pytest -q` · Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add templates/partials/bottom_nav.html templates/base.html static/css/mobile.css tests/test_frame.py
git commit -m "feat(movil): barra de navegación inferior con permisos; FAB y toasts sobre la barra"
git push origin main
```

---

### Task 6: Visor de imágenes con zoom (`data-zoomable`)

**Files:**
- Create: `static/js/image-viewer.js`
- Modify: `templates/base.html` (`<script src=".../image-viewer.js" defer>` junto a `fusion.js`)
- Modify: `static/css/mobile.css` (estilos `.iv-*`)
- Modify: plantillas con fotos — cada `<img>` cuyo `src` sale de `producto.imagen_url` o de fotos de incidencias/avances (`grep -rn "imagen_url\|foto" templates`), incluido `templates/dashboard.html:612`
- Test: `tests/test_frame.py`

**Interfaces:**
- Produces: cualquier `img[data-zoomable]` abre el visor al hacer clic/tap; `data-zoom-src="<url>"` opcional para usar otra resolución. API global `window.ImageViewer.open(src: string, alt: string)` y `.close()`.

Comportamiento (todo con Pointer Events, sin librerías):
- Overlay `div.iv-overlay[role="dialog"][aria-modal="true"]` creado una vez, fondo `rgba(0,0,0,.92)`, `touch-action: none`, `overscroll-behavior: contain`; bloquea scroll del body mientras está abierto.
- Escala 1–5. Pellizco con 2 punteros (escala relativa a la distancia inicial, centrada en el punto medio); arrastre con 1 puntero solo si escala > 1, limitado a los bordes de la imagen; doble tap (< 300 ms) alterna 1 ↔ 2.5 en el punto tocado; rueda en escritorio ±10%.
- Cierra con botón (44px, `top: calc(12px + env(safe-area-inset-top))`, `right: calc(12px + env(safe-area-inset-right))`, `aria-label="Cerrar imagen"`), Escape, o tap en el fondo con escala 1. Devuelve el foco al `<img>` de origen.
- `stopPropagation` en el clic del `img` para que filas clicables (Dashboard) no naveguen.

- [ ] **Step 1: Test que falla**

```python
def test_image_viewer_loaded_and_dashboard_thumbs_zoomable():
    base = (ROOT / 'templates/base.html').read_text(encoding='utf-8')
    dash = (ROOT / 'templates/dashboard.html').read_text(encoding='utf-8')
    assert 'js/image-viewer.js' in base
    assert 'data-zoomable' in dash
    js = (ROOT / 'static/js/image-viewer.js').read_text(encoding='utf-8')
    assert 'onclick' not in js and 'innerHTML' not in js     # CSP + XSS: construir con createElement
```

- [ ] **Step 2: Correr y ver que falla** — Expected: FAIL.

- [ ] **Step 3: Implementar `image-viewer.js`** — IIFE, delegación `document.addEventListener('click', …)` sobre `img[data-zoomable]`; transform con `translate3d(x,y,0) scale(s)` y `will-change: transform` solo mientras hay gesto; `prefers-reduced-motion` sin transición de apertura.

- [ ] **Step 4: Marcar imágenes** — agregar `data-zoomable` a las `<img>` encontradas en el grep (no a logos ni avatares).

- [ ] **Step 5: Tests + prueba manual** — Run: `SECRET_KEY=test python -m pytest -q` (PASS). En DevTools con emulación táctil (iPhone 12): abrir una foto del Dashboard, pellizcar (Shift+arrastre en Chrome), doble tap, cerrar con botón y Escape; la página de fondo no se movió ni hizo zoom; la consola no muestra violaciones de CSP.

- [ ] **Step 6: Commit**

```bash
git add static/js/image-viewer.js static/css/mobile.css templates tests/test_frame.py
git commit -m "feat(movil): visor de imágenes a pantalla completa con pellizco y doble tap"
git push origin main
```

---

### Task 7: Dashboard rediseñado y tabla → tarjetas en móvil

**Files:**
- Modify: `templates/dashboard.html` (todo el archivo: `<style>` de `:5-69` y `:800-818`, encabezado `:79-110`, salud `:111-153`, KPIs `:230-480`, filtros `:504-566`, tabla `:568-737`, gráficas JS `:1088-…`)
- Reference: `design_handoff_rediseno_inventario/README.md` (pantalla 2 "Rediseño - Dashboard"), `design_handoff_rediseno_inventario/disenos/` (archivo del Dashboard), maquetas B/C en `.superpowers/brainstorm/1603-1792863638/content/direccion-visual.html`
- Test: `tests/test_dashboard_ui.py` (nuevo)

**Interfaces:**
- Consumes: tokens (Task 1), `.only-mobile` (Task 3), `data-zoomable` (Task 6), `animateCounters(root)` y `FusionChart.tokens()` de `static/js/fusion.js`, evento `themechange` (Task 1).
- Produces: celdas de fila con clases `td-img`, `td-sku`, `td-nombre`, `td-cat`, `td-prov`, `td-stock`, `td-dias`, `td-estado`, `td-acc` (las celdas que ya tienen `td-acciones` la conservan). Select `#ordenMovil` (`.only-mobile`) cuyas opciones llevan `value="<col>|<tipo>"` y llaman a la función existente `ordenarTabla(col, tipo)`.

Diseño (sección 4 del spec + pantalla 2 del paquete, sin brillos ni gradientes):
- Encabezado: kicker uppercase `{{ almacen_seleccionado.nombre }} · {{ mes año }}` (0.65rem, tracking .14em, `--muted`), título Archivo 700, acciones pill a la derecha, **regla de 2px `--border-strong`** debajo.
- KPIs: tarjetas planas (`--card`, borde 1px, radio 14px, sin sombra en reposo), cifra Archivo 700 con `data-count` para `animateCounters`, `tabular-nums`, icono en `--muted` (no colores variados). Mantener la restricción existente de KPIs a `super_admin`/`admin`.
- Salud del almacén: meter tricolor `--danger`/`--sage`/`--info` con `transition: width`.
- Gráficas: colores desde `FusionChart.tokens()`; en `themechange` destruir y recrear `cMov`, `cEst`, `cTop`. Dona con `cutout: '70%'`.
- Filtros pill: activo = `--accent` / `--on-accent`; resto con borde `--border`; contadores como texto `--muted`, no badges de colores.
- Todos los `bi bi-*` del archivo → Phosphor.

Tarjetas (< 640px), reflujo de las mismas filas — **selector `tr.fila-producto`, nunca `tr` a secas** (la fila vacía `colspan` no debe volverse tarjeta):
- `#tabla_inventario thead { display: none }`; `tr.fila-producto { display: grid; grid-template-columns: 44px 1fr auto; grid-template-areas: "img nombre estado" "img sku stock" "acc acc acc"; gap: 2px 12px; padding: 12px 14px; border-bottom: 1px solid var(--border); }`; cada `td-*` a su `grid-area`, `td { padding: 0; border: 0 }`; `td-cat`, `td-prov`, `td-dias` ocultos (ya lo están < md); `td-acc` alineado a la derecha con botones de 44px (`pointer: coarse`).
- Miniatura 40px, radio 10px (`.td-img img`).
- `.table-responsive` del Dashboard sin scroll horizontal en < 640px (`overflow-x: visible`).
- Con `#ordenMovil` el usuario conserva el orden por SKU, Producto, Categoría y Stock en móvil.

- [ ] **Step 1: Tests que fallan** en `tests/test_dashboard_ui.py`

```python
import pytest
from tests.conftest import do_login
from app.extensions import db
from app.models.inventory import Almacen, Producto, Stock

@pytest.fixture
def almacen_con_producto(org):
    a = Almacen(nombre='Bodega Central', organizacion_id=org.id)
    p = Producto(nombre='Tornillo', codigo='T-001', organizacion_id=org.id, imagen_url='t.jpg')
    db.session.add_all([a, p]); db.session.flush()
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
    db.session.add(a); db.session.commit()
    html = _dash(client)
    assert 'El almacén está vacío' in html or 'sin almacén' in html.lower()
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / 'templates/dashboard.html').read_text(encoding='utf-8')
    assert 'tr.fila-producto {' in src or 'tr.fila-producto{' in src
```

(Si el import de `db` o los modelos vive en otra ruta, ajustar según `tests/conftest.py`.)

- [ ] **Step 2: Correr y ver que fallan** — Run: `SECRET_KEY=test python -m pytest tests/test_dashboard_ui.py -v` · Expected: FAIL en los 3 (si el fixture falla por otro motivo, arreglar el fixture antes de seguir).

- [ ] **Step 3: Invocar `/ui-ux-pro-max` y `/frontend-design`** con el README del paquete (pantalla 2) y las maquetas B/C como entrada; decidir espaciados y jerarquía final antes de tocar markup.

- [ ] **Step 4: Rediseñar `dashboard.html`** según la sección "Diseño" de arriba. Conservar todos los `id`, `data-*` y clases que usa el JS del archivo (`fila-producto`, `td-acciones`, `th-sortable`, `data-col`, `data-tipo`, `data-filtro-estado`, `active-filter`, `#contador_registros`, `#tabla_productos_cuerpo`, canvases `#chartMovimientos`, `#chartTopProductos`, `#chartEstado`). Mover los dos `<style>` del archivo a uno solo dentro de `{% block extra_css %}`.

- [ ] **Step 5: Tests** — Run: `SECRET_KEY=test python -m pytest -q` · Expected: PASS (salvo la preexistente).

- [ ] **Step 6: Regresión manual del Dashboard** (escritorio 1280px y móvil 375px, ambos temas): búsqueda, filtros de categoría/proveedor/estado, pills de filtro rápido, contador, orden por encabezado (escritorio) y por `#ordenMovil` (móvil), clic en fila → historial, botones Editar/Historial/Etiqueta, clic en miniatura → visor (sin navegar), cambio de tema redibuja gráficas, alertas de la campana.

- [ ] **Step 7: Commit**

```bash
git add templates/dashboard.html tests/test_dashboard_ui.py
git commit -m "feat(dashboard): rediseño Fusion refinada y tabla en tarjetas para móvil"
git push origin main
```

---

### Task 8: Verificación de anchos a 320–430px y cierre de fase

**Files:**
- Create: `scripts/check_mobile_overflow.py`
- Modify: plantillas que el script marque (esperables por spec 5.8: `actividad.html`, `almacenes.html`, `excel_config.html`, `etiqueta_personalizar.html`, `orden_form.html`, `plantilla_config.html`, `login.html`, `403/404/500.html`, `offline.html`) — solo anchos fijos (`width:`/`min-width:` ≥ 300px sin `max-width` → `max-width:100%` o `min(Npx, 100%)`) y tablas sin `.table-responsive`; el rediseño de esas pantallas es de las fases 3–4.

**Interfaces:**
- Produces: `python scripts/check_mobile_overflow.py --base-url URL --user U --password P [--paths-file F]` → imprime una tabla `ruta | ancho | scrollWidth | elementos que sobresalen` para anchos 320, 375, 390, 430 en tema oscuro y claro; código de salida 1 si alguna ruta tiene `document.documentElement.scrollWidth > window.innerWidth`. También reporta el `font-size` computado del primer `input` visible a 375px (debe ser `16px`).
- Lista de rutas por defecto dentro del script: `/`, `/dashboard`, y los endpoints GET sin parámetros de los listados de la sección 5.6 del spec (obtenerlos con `flask routes`).

- [ ] **Step 1: Preparar Playwright** — Run: `python -m playwright install chromium` · Expected: descarga completa (hoy el lanzamiento falla porque falta el navegador).

- [ ] **Step 2: Escribir el script** — `sync_playwright`, un `browser.new_context(viewport={'width': w, 'height': 800}, device_scale_factor=3, is_mobile=True, has_touch=True)` por ancho; login llenando el formulario de `templates/login.html` (leer ahí los selectores de usuario/contraseña); tema forzado con `page.add_init_script("localStorage.setItem('erp_theme', '<t>')")`. Para "elementos que sobresalen": los 5 primeros elementos cuyo `getBoundingClientRect().right > innerWidth + 1` y que no estén dentro de un ancestro con `overflow-x` `auto|scroll|hidden|clip` distinto de `html/body`.

- [ ] **Step 3: Correr contra el servidor local** — Run: `flask run` (usa `inventario.db` local) en otra terminal y `python scripts/check_mobile_overflow.py --base-url http://127.0.0.1:5000 --user <admin local> --password <…>` · Expected en esta primera corrida: puede listar fallos de las plantillas de 5.8.

- [ ] **Step 4: Corregir anchos fijos** marcados por el script y volver a correrlo · Expected: salida 0, todas las filas OK, `font-size 16px` reportado.

- [ ] **Step 5: Suite completa** — Run: `SECRET_KEY=test python -m pytest -q` · Expected: todo PASS salvo la falla preexistente.

- [ ] **Step 6: Commit**

```bash
git add scripts/check_mobile_overflow.py templates
git commit -m "test(movil): verificador de desbordamiento a 320-430px y anchos fijos corregidos"
git push origin main
```

- [ ] **Step 7: Revisión de cierre** — `/ponytail-review` sobre los commits de la fase, luego code-review con Opus (`/code-review`); aplicar hallazgos confirmados en un commit `fix(ui): hallazgos de revisión fase 1` + push. Avisar al usuario para la prueba en teléfonos reales (iPhone Safari + PWA, Android Chrome + PWA) con la lista de la sección 8 del spec y los comandos de servidor: ninguno nuevo en esta fase (no hay migraciones), solo `sudo systemctl restart inventario` tras el pull.
