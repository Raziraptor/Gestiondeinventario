"""Verificador de desbordamiento horizontal a 320-430px (tema oscuro y claro).

Uso:
    python scripts/check_mobile_overflow.py --base-url URL --user U --password P [--paths-file F]

Imprime `ruta | tema | ancho | scrollWidth | estado | elementos que sobresalen`
(solo las filas con fallo o con elementos sospechosos).
Sale con 1 si alguna ruta tiene scrollWidth > innerWidth, o si el font-size
computado del primer input visible a 375px no es 16px. Errores de consola y
violaciones de CSP se listan pero no afectan el codigo de salida.
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
    '/soporte', '/transferencia/nueva', '/usuarios',
]
# Rutas publicas (sin sesion): login, recuperacion, offline y 404.
PUBLIC_PATHS = ['/login', '/forgot-password', '/register', '/offline', '/ruta-inexistente-404']

JS_OVERFLOW = r"""() => {
  const iw = window.innerWidth;
  const out = [];
  const clipped = el => {
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
    const id = el.id ? '#' + el.id : '';
    const cl = typeof el.className === 'string' && el.className.trim()
      ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '';
    out.push(el.tagName.toLowerCase() + id + cl + ' (' + Math.round(r.right) + ')');
    if (out.length >= 5) break;
  }
  return {sw: document.documentElement.scrollWidth, iw, els: out};
}"""

JS_INPUT = r"""() => {
  const sel = 'input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea';
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
    args = ap.parse_args()
    base = args.base_url.rstrip('/')
    paths = DEFAULT_PATHS
    if args.paths_file:
        with open(args.paths_file, encoding='utf-8') as f:
            paths = [l.strip() for l in f if l.strip() and not l.startswith('#')]

    failures, console, rows, font_sizes = 0, [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # Un solo login (el login tiene rate limit); el estado se reutiliza.
        ctx = browser.new_context(viewport={'width': 375, 'height': 800})
        pg = ctx.new_page()
        pg.goto(base + '/login')
        pg.fill('#username', args.user)
        pg.fill('#password', args.password)
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
                    page = ctx.new_page()
                    current = {'tag': ''}
                    page.on('console', lambda m: console.append((current['tag'], m.text[:160]))
                            if m.type == 'error' or 'Refused to' in m.text else None)
                    page.on('pageerror', lambda e: console.append((current['tag'], 'pageerror: ' + str(e)[:160])))
                    for path in (paths if authed else PUBLIC_PATHS):
                        current['tag'] = f'{path} {theme} {w}'
                        try:
                            page.goto(base + path, wait_until='networkidle')
                        except Exception as exc:  # redireccion en bucle, timeout...
                            failures += 1
                            rows.append((path, theme, w, 0, 'FAIL', 'navegacion: ' + str(exc).splitlines()[0][:90]))
                            continue
                        page.wait_for_timeout(250)
                        res = page.evaluate(JS_OVERFLOW)
                        if w == 375 and theme == 'dark':
                            fi = page.evaluate(JS_INPUT)
                            if fi:
                                font_sizes.append((path, fi['el'], fi['fs']))
                        bad = res['sw'] > res['iw']
                        failures += bad
                        rows.append((path, theme, w, res['sw'], 'FAIL' if bad else 'ok', '; '.join(res['els'])))
                    ctx.close()
        browser.close()

    print('ruta | tema | ancho | scrollWidth | estado | elementos que sobresalen')
    for r in rows:
        if r[4] == 'FAIL' or r[5]:
            print(' | '.join(str(x) for x in r))
    print(f'-- {len(rows)} combinaciones, {failures} con scroll horizontal')

    first = font_sizes[0] if font_sizes else None
    print(f'font-size primer input a 375px: {first}')
    for f in font_sizes:
        if f[2] != '16px':
            print('  input != 16px:', f)
    if console:
        uniq = sorted(set(console))
        print(f'-- {len(uniq)} errores de consola / CSP distintos (no afectan el codigo de salida)')
        for tag, msg in uniq[:40]:
            print('  ', tag, '|', msg)
    ok = failures == 0 and first is not None and first[2] == '16px'
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
