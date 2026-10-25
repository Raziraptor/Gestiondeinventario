"""Verificador de desbordamiento horizontal a 320-430px (tema oscuro y claro).

Uso:
    python scripts/check_mobile_overflow.py --base-url URL --user U --password P [--paths-file F] [--self-test]

Imprime `ruta | tema | ancho | scrollWidth/clientWidth | estado | detalle`
(solo las filas con fallo o con elementos sospechosos).

Compuerta (sale con 1) si ocurre cualquiera de:
  - hay elementos que sobresalen del viewport (fuera de contenedores con scroll);
  - con `html,body{overflow-x:visible}` (solo para medir: mobile.css lo fija en
    `clip` y oculta el desbordamiento), scrollWidth > clientWidth;
  - la navegacion falla, devuelve estado >= 400 (404 solo en la ruta de prueba
    404) o una ruta autenticada termina en /login;
  - el primer input visible de CUALQUIER pagina visitada a 375px no es 16px.
Errores de consola y violaciones de CSP se listan pero no afectan el exit code.
`--self-test` inyecta un div de 600px en cada pagina: debe terminar con exit 1.
"""
import argparse
import sys

from playwright.sync_api import sync_playwright

WIDTHS = (320, 375, 390, 430)
THEMES = ('dark', 'light')

# Rutas GET sin parametros que renderizan HTML para un admin.
DEFAULT_PATHS = [
    '/', '/dashboard', '/account', '/actividad', '/admin/manual', '/admin_panel',
    '/ajuste/nuevo', '/almacen/nuevo', '/almacenes', '/aprobaciones',
    '/categoria/nueva', '/categorias', '/centro-costo/nuevo', '/centros-costo',
    '/configuracion/etiquetas', '/configuracion/excel', '/configuracion/plantilla',
    '/cuentas-por-pagar', '/factura/nueva', '/finanzas', '/gasto/nuevo', '/gastos',
    '/incidencias/', '/incidencias/nueva', '/orden/nueva/manual', '/ordenes',
    '/presupuesto/nuevo', '/presupuestos', '/producto/nuevo', '/productos/importar',
    '/productos/sin-almacen', '/proveedor/nuevo', '/proveedores', '/proyecto-oc/nueva',
    '/proyectos-oc', '/reportes', '/salida', '/salidas', '/servicios', '/servicios/nuevo',
    '/soporte', '/soporte/admin', '/transferencia/nueva', '/usuarios',
]
# Rutas publicas (sin sesion): login, recuperacion, offline y 404.
PUBLIC_PATHS = ['/login', '/forgot-password', '/register', '/offline', '/ruta-inexistente-404']
EXPECT_STATUS = {'/ruta-inexistente-404': 404}

SELF_TEST_JS = (
    "document.addEventListener('DOMContentLoaded', () => {"
    "const d = document.createElement('div'); d.id = 'selftest-ancho';"
    "d.style.cssText = 'width:600px;height:20px;background:red';"
    "document.body.appendChild(d); });"
)

JS_OVERFLOW = r"""() => {
  const iw = window.innerWidth;
  const out = [], fx = [];
  const clipped = el => {
    // position:fixed: su bloque contenedor es el viewport; los ancestros con overflow no lo recortan.
    if (getComputedStyle(el).position === 'fixed') return false;
    for (let a = el.parentElement; a && a !== document.body && a !== document.documentElement; a = a.parentElement) {
      if (/(auto|scroll|hidden|clip)/.test(getComputedStyle(a).overflowX)) return true;
    }
    return false;
  };
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    if (el.closest('.sb:not(.open), .sb-backdrop, svg')) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0 || r.right <= iw + 1) continue;
    if (clipped(el)) continue;
    // Un fixed fuera del viewport no agranda el scroll (p. ej. brillos decorativos del login): solo aviso.
    const fixed = cs.position === 'fixed';
    const id = el.id ? '#' + el.id : '';
    const cl = typeof el.className === 'string' && el.className.trim()
      ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '';
    const d = el.tagName.toLowerCase() + id + cl + ' (' + Math.round(r.right) + ')';
    (fixed ? fx : out).push(fixed ? 'fixed ' + d : d);
    if (out.length >= 5) break;
  }
  return {iw, els: out, fx};
}"""

# Solo para medir: mobile.css pone overflow-x:clip en html/body y ahi scrollWidth no refleja el desbordamiento.
JS_MEASURE = r"""() => {
  const st = document.createElement('style');
  st.textContent = 'html,body{overflow-x:visible!important}';
  document.head.appendChild(st);
  const de = document.documentElement;
  const out = {sw: de.scrollWidth, cw: de.clientWidth};
  st.remove();
  return out;
}"""

JS_INPUT = r"""() => {
  const sel = 'input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=file])'
    + ':not([type=range]):not([type=color]):not([type=submit]):not([type=button]), select, textarea';
  for (const i of document.querySelectorAll(sel)) {
    const r = i.getBoundingClientRect(), cs = getComputedStyle(i);
    if (r.width > 0 && r.height > 0 && cs.visibility !== 'hidden')
      return {fs: cs.fontSize, el: i.tagName.toLowerCase() + (i.id ? '#' + i.id : '')};
  }
  return null;
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base-url', required=True)
    ap.add_argument('--user', required=True)
    ap.add_argument('--password', required=True)
    ap.add_argument('--paths-file')
    ap.add_argument('--self-test', action='store_true', help='inyecta un div de 600px; debe salir con 1')
    args = ap.parse_args()
    base = args.base_url.rstrip('/')
    paths = DEFAULT_PATHS
    if args.paths_file:
        with open(args.paths_file, encoding='utf-8') as f:
            paths = [l.strip() for l in f if l.strip() and not l.strip().startswith('#')]

    failures, console, rows, font_sizes, warns = 0, [], [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # Un solo login (el login tiene rate limit); el estado se reutiliza.
        ctx = browser.new_context(viewport={'width': 375, 'height': 800})
        pg = ctx.new_page()
        pg.goto(base + '/login')
        pg.fill('#username', args.user)
        pg.fill('#password', args.password)
        with pg.expect_navigation():
            pg.click('#loginSubmitBtn')
        pg.wait_for_load_state('networkidle')
        if '/login' in pg.url:
            print('Login fallido', file=sys.stderr)
            return 2
        state = ctx.storage_state()
        ctx.close()

        for theme in THEMES:
            for w in WIDTHS:
                for authed in (True, False):
                    kw = dict(viewport={'width': w, 'height': 800}, device_scale_factor=3,
                              is_mobile=True, has_touch=True)
                    if authed:
                        kw['storage_state'] = state
                    ctx = browser.new_context(**kw)
                    ctx.add_init_script(f"localStorage.setItem('erp_theme', '{theme}')")
                    if args.self_test:
                        ctx.add_init_script(SELF_TEST_JS)
                    page = ctx.new_page()
                    current = {'tag': ''}
                    page.on('console', lambda m: console.append((current['tag'], m.text[:160]))
                            if m.type == 'error' or 'Refused to' in m.text else None)
                    page.on('pageerror', lambda e: console.append((current['tag'], 'pageerror: ' + str(e)[:160])))
                    for path in (paths if authed else PUBLIC_PATHS):
                        current['tag'] = f'{path} {theme} {w}'
                        try:
                            resp = page.goto(base + path, wait_until='networkidle')
                        except Exception as exc:  # redireccion en bucle, timeout...
                            failures += 1
                            rows.append((path, theme, w, '-', 'FAIL', 'navegacion: ' + str(exc).splitlines()[0][:90]))
                            continue
                        page.wait_for_timeout(250)
                        final = page.url[len(base):].split('?')[0] or '/'
                        problems = []
                        want = EXPECT_STATUS.get(path)
                        if resp is None:
                            problems.append('sin respuesta HTTP')
                        elif want is not None and resp.status != want:
                            problems.append(f'HTTP {resp.status} (esperado {want})')
                        elif want is None and resp.status >= 400:
                            problems.append(f'HTTP {resp.status}')
                        if authed and final.startswith('/login'):
                            problems.append('termino en /login')
                        elif final.rstrip('/') != path.rstrip('/') and (path, final) not in warns:
                            warns.append((path, final))
                        res = page.evaluate(JS_OVERFLOW)
                        meas = page.evaluate(JS_MEASURE)
                        if w == 375 and theme == 'dark':
                            fi = page.evaluate(JS_INPUT)
                            if fi:
                                font_sizes.append((path, fi['el'], fi['fs']))
                        if want is not None:  # pagina de error por defecto de Werkzeug (sin meta viewport): solo estado
                            meas = {'sw': 0, 'cw': 0}
                        if res['els']:
                            problems.append('elementos fuera del viewport')
                        if meas['sw'] > meas['cw']:
                            problems.append(f"scrollWidth {meas['sw']} > clientWidth {meas['cw']}")
                        failures += bool(problems)
                        rows.append((path, theme, w, f"{meas['sw']}/{meas['cw']}",
                                     'FAIL' if problems else 'ok', '; '.join(problems + res['els'] + res['fx'][:2])))
                    ctx.close()
        browser.close()

    print('ruta | tema | ancho | scrollWidth/clientWidth | estado | detalle')
    for r in rows:
        if r[4] == 'FAIL' or r[5]:
            print(' | '.join(str(x) for x in r))
    print(f'-- {len(rows)} combinaciones, {failures} con fallo')
    for path, final in warns:
        print(f'AVISO: {path} termino en {final}')

    bad_fonts = [f for f in font_sizes if f[2] != '16px']
    print(f'font-size primer input a 375px: {len(font_sizes)} paginas con input, {len(bad_fonts)} != 16px')
    for f in bad_fonts:
        print('  input != 16px:', f)
    if console:
        uniq = sorted(set(console))
        print(f'-- {len(uniq)} errores de consola / CSP distintos (no afectan el codigo de salida)')
        for tag, msg in uniq[:40]:
            print('  ', tag, '|', msg)
    ok = failures == 0 and bool(font_sizes) and not bad_fonts
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
