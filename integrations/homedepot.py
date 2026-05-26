"""
Automatización Playwright para Home Depot Pro.
Llena el carrito de una cuenta HD Pro con los ítems de una OC.

Requiere en el servidor:
  /root/venv/bin/pip install playwright playwright-stealth
  /root/venv/bin/playwright install chromium --with-deps
"""

import time
import random


HD_BASE = "https://www.homedepot.com"
HD_LOGIN = f"{HD_BASE}/auth/view/signin"
HD_SEARCH = f"{HD_BASE}/s/"
HD_CART   = f"{HD_BASE}/mycart/home"


def _random_delay(lo=0.8, hi=2.0):
    """Pausa aleatoria para reducir detección de bot."""
    time.sleep(random.uniform(lo, hi))


def fill_cart(credenciales: dict, items: list[dict]) -> dict:
    """
    Hace login en HD Pro y añade cada ítem al carrito.

    Args:
        credenciales: {'usuario': str, 'password': str}
        items: [{'sku': str, 'nombre': str, 'cantidad': int}, ...]

    Returns:
        {'cart_url': str, 'agregados': int, 'omitidos': [{'nombre', 'razon'}]}
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    try:
        from playwright_stealth import stealth_sync
        _stealth_available = True
    except ImportError:
        _stealth_available = False

    agregados = 0
    omitidos = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage'],
        )
        ctx = browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
            viewport={'width': 1280, 'height': 800},
        )
        page = ctx.new_page()

        if _stealth_available:
            stealth_sync(page)

        # --- LOGIN ---
        try:
            page.goto(HD_LOGIN, timeout=30_000)
            _random_delay()
            page.fill('#username', credenciales['usuario'])
            _random_delay(0.3, 0.8)
            page.fill('#password', credenciales['password'])
            _random_delay(0.3, 0.8)
            page.click('button[type="submit"]')
            page.wait_for_url(f'{HD_BASE}/**', timeout=20_000)
            _random_delay()
        except PWTimeout:
            browser.close()
            raise RuntimeError('Login en Home Depot Pro falló (timeout). Verifica credenciales o CAPTCHA.')

        # --- AGREGAR ÍTEMS ---
        for item in items:
            sku    = (item.get('sku') or '').strip()
            nombre = item.get('nombre', 'desconocido')
            cantidad = max(1, int(item.get('cantidad') or 1))

            search_term = sku if sku else nombre

            try:
                page.goto(f'{HD_SEARCH}{search_term}', timeout=20_000)
                _random_delay()

                # Primer resultado — botón "Add to Cart"
                add_btn = page.locator('button:has-text("Add to Cart"), button:has-text("Agregar al carrito")').first
                if not add_btn.is_visible(timeout=5_000):
                    omitidos.append({'nombre': nombre, 'sku': sku, 'razon': 'Producto no encontrado en HD'})
                    continue

                add_btn.click()
                _random_delay()

                # Ajustar cantidad si > 1
                if cantidad > 1:
                    try:
                        qty_input = page.locator('input[aria-label*="Quantity"], input[data-testid*="quantity"]').first
                        if qty_input.is_visible(timeout=3_000):
                            qty_input.triple_click()
                            qty_input.type(str(cantidad))
                            _random_delay(0.3, 0.6)
                    except Exception:
                        pass

                agregados += 1

            except PWTimeout:
                omitidos.append({'nombre': nombre, 'sku': sku, 'razon': 'Timeout al buscar producto'})
            except Exception as exc:
                omitidos.append({'nombre': nombre, 'sku': sku, 'razon': str(exc)})

        cart_url = HD_CART
        browser.close()

    return {
        'cart_url': cart_url,
        'agregados': agregados,
        'omitidos': omitidos,
    }
