"""
HD Pro Quick Order — generación de CSV y upload automático.

HD Pro acepta una lista SKU+cantidad vía Quick Order que llena el carrito.
Columnas CSV requeridas: Item Number, Quantity

Fase 1: generar_csv() → descarga manual
Fase 2: subir_csv_auto() → Playwright sube el CSV con sesión persistente
"""

import io
import csv
import os
import tempfile

HD_QUICKORDER_URL = 'https://www.homedepot.com/account/quickorder'
HD_BASE = 'https://www.homedepot.com'
HD_LOGIN = f'{HD_BASE}/auth/view/signin'


def generar_csv(orden) -> tuple[bytes, list[str]]:
    """
    Genera el CSV para HD Pro Quick Order a partir de una OrdenCompra.

    Usa producto.hd_sku si existe; si no, usa producto.codigo.
    Excluye detalles sin producto válido o sin cantidad.

    Returns:
        (csv_bytes, omitidos) — bytes UTF-8 sin BOM y lista de nombres omitidos.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['Item Number', 'Quantity'])

    omitidos = []
    for detalle in orden.detalles:
        if not detalle.producto:
            omitidos.append(f'Detalle #{detalle.id} sin producto')
            continue
        cantidad = detalle.cantidad_solicitada or 0
        if cantidad <= 0:
            omitidos.append(detalle.producto.nombre)
            continue
        sku = detalle.producto.hd_sku or detalle.producto.codigo
        writer.writerow([sku, int(cantidad)])

    return buf.getvalue().encode('utf-8'), omitidos


def generar_csv_proyecto(proyecto_oc) -> tuple[bytes, list[str], int]:
    """
    Genera el CSV para HD Pro Quick Order desde una OC de Proyecto.

    Prioridad de Item Number:
      - Detalle de catálogo: usa producto.hd_sku si existe, sino producto.codigo
      - Detalle externo: usa descripcion_nuevo (el usuario puede editar el CSV)

    Filtra a ítems donde proveedor_sugerido contiene "home depot" (case-insensitive)
    O donde producto.hd_sku está definido. Si no hay ítems calificados, exporta todos.

    Returns:
        (csv_bytes, omitidos, total_exportados)
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['Item Number', 'Quantity'])

    def _es_hd(detalle) -> bool:
        if detalle.producto and detalle.producto.hd_sku:
            return True
        prov = (detalle.proveedor_sugerido or '').lower()
        return 'home depot' in prov or 'homedepot' in prov or 'hd pro' in prov

    hd_detalles = [d for d in proyecto_oc.detalles if _es_hd(d)]
    # Si no hay ítems identificados como HD, exportar todos
    detalles_export = hd_detalles if hd_detalles else list(proyecto_oc.detalles)

    omitidos = []
    exportados = 0
    for detalle in detalles_export:
        cantidad = detalle.cantidad or 0
        if cantidad <= 0:
            nombre = detalle.producto.nombre if detalle.producto else detalle.descripcion_nuevo
            omitidos.append(nombre or f'Detalle #{detalle.id}')
            continue
        if detalle.producto:
            sku = detalle.producto.hd_sku or detalle.producto.codigo
        else:
            sku = (detalle.descripcion_nuevo or '').strip()
        if not sku:
            omitidos.append(f'Detalle #{detalle.id} sin nombre/SKU')
            continue
        writer.writerow([sku, int(cantidad)])
        exportados += 1

    return buf.getvalue().encode('utf-8'), omitidos, exportados


def subir_csv_auto(credenciales: dict, csv_bytes: bytes, sesion=None, db=None,
                   HDSesion=None, org_id: int = None, proveedor_id: int = None) -> dict:
    """
    Sube el CSV a HD Pro Quick Order usando Playwright con sesión persistente.

    Intenta restaurar cookies guardadas. Si la sesión expiró o no existe,
    hace login completo y guarda las nuevas cookies.

    Args:
        credenciales: {'usuario': str, 'password': str}
        csv_bytes: CSV generado por generar_csv()
        sesion: objeto HDSesion activo (puede ser None)
        db, HDSesion, org_id, proveedor_id: para guardar sesión nueva

    Returns:
        {'ok': bool, 'carrito_url': str, 'items_agregados': int,
         'items_omitidos': list, 'error': str|None}
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    from integrations.hd_session import restaurar_sesion, sesion_valida, guardar_sesion

    try:
        from playwright_stealth import stealth_sync
        _stealth = True
    except ImportError:
        _stealth = False

    # Escribir CSV en archivo temporal para set_input_files
    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False, mode='wb') as f:
        f.write(csv_bytes)
        tmp_csv_path = f.name

    try:
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
            if _stealth:
                stealth_sync(page)

            sesion_restaurada = False
            if sesion_valida(sesion):
                sesion_restaurada = restaurar_sesion(page, sesion)

            if not sesion_restaurada:
                # Login completo
                try:
                    page.goto(HD_LOGIN, timeout=30_000)
                    page.fill('#username', credenciales['usuario'])
                    page.fill('#password', credenciales['password'])
                    page.click('button[type="submit"]')
                    page.wait_for_url(f'{HD_BASE}/**', timeout=25_000)
                except PWTimeout:
                    browser.close()
                    return {'ok': False, 'error': 'error_login', 'items_agregados': 0, 'items_omitidos': []}

                # Guardar nueva sesión
                if db is not None and HDSesion is not None and org_id and proveedor_id:
                    try:
                        guardar_sesion(page, db, HDSesion, org_id, proveedor_id)
                    except Exception:
                        pass

            # Navegar a Quick Order
            try:
                page.goto(HD_QUICKORDER_URL, timeout=25_000)
            except PWTimeout:
                browser.close()
                return {'ok': False, 'error': 'timeout_quickorder', 'items_agregados': 0, 'items_omitidos': []}

            # Subir CSV mediante input[type=file]
            try:
                file_input = page.locator('input[type="file"]').first
                file_input.set_input_files(tmp_csv_path)
                # Esperar a que HD procese el CSV (botón submit o cambio de estado)
                page.wait_for_timeout(3000)

                # Intentar confirmar la carga si hay botón explícito
                submit_btn = page.locator(
                    'button:has-text("Add to Cart"), button:has-text("Add Items"), '
                    'button[type="submit"]'
                ).first
                if submit_btn.is_visible(timeout=5000):
                    submit_btn.click()
                    page.wait_for_timeout(4000)

            except PWTimeout:
                browser.close()
                return {'ok': False, 'error': 'timeout_upload', 'items_agregados': 0, 'items_omitidos': []}

            # Contar ítems agregados (heurística: filas en tabla de resultado)
            items_agregados = 0
            items_omitidos = []
            try:
                rows = page.locator('table tr, [data-testid*="item-row"]').all()
                items_agregados = max(0, len(rows) - 1)  # descontar header
            except Exception:
                pass

            carrito_url = f'{HD_BASE}/mycart/home'
            browser.close()

        return {
            'ok': True,
            'carrito_url': carrito_url,
            'items_agregados': items_agregados,
            'items_omitidos': items_omitidos,
            'error': None,
        }

    finally:
        try:
            os.unlink(tmp_csv_path)
        except OSError:
            pass
