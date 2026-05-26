# Home Depot Pro — Integración Semi-Automática de Pedidos

## Goal
Al enviar una OC cuyo proveedor es Home Depot, el sistema hace login automático en homedepot.com/pro y agrega los ítems al carrito; el usuario revisa y confirma el checkout manualmente.

## Prerequisito crítico — SKU mapping
Cada `Producto` necesita el número de artículo de Home Depot.  
Sin SKU: la búsqueda es por nombre → frágil, puede agregar el producto equivocado.  
**Decisión antes de T1:** ¿usar campo `hd_sku` en Producto (simple) o tabla `ProductoProveedorSKU` (escalable a más proveedores)?

## Tasks

- [ ] **T1 — DB: SKUs y credenciales**
  - Añadir `hd_sku = db.Column(db.String(30), nullable=True)` a modelo `Producto`
  - Nuevo modelo `ProveedorIntegracion(id, org_id, proveedor_id, tipo='homedepot', _credenciales TEXT)` con propiedades `@property`/`@setter` que cifran/descifran con `cryptography.fernet.Fernet` (key en env var `FERNET_KEY`)
  - Añadir `integracion_status = db.Column(db.String(20), nullable=True)` a `OrdenCompra`
  - CLI idempotente `flask add-hd-integration` (CREATE TABLE IF NOT EXISTS + ALTER COLUMN IF NOT EXISTS)
  - Verify: `flask add-hd-integration` sin errores; `ProveedorIntegracion().credenciales = {'user':'x'}` guarda cifrado en DB

- [ ] **T2 — Instalar Playwright**
  - Local: `pip install playwright playwright-stealth && playwright install chromium`
  - Servidor (anotar en CLAUDE.md): `/root/venv/bin/pip install playwright playwright-stealth && /root/venv/bin/playwright install chromium --with-deps`
  - Verify: `python -c "from playwright.sync_api import sync_playwright; print('ok')"` sin error

- [ ] **T3 — Script de automatización `integrations/homedepot.py`**
  - Función `fill_cart(credenciales: dict, items: list[dict]) -> dict`
    - `items` = `[{sku, nombre, cantidad}, ...]`
    - Login en `https://www.homedepot.com/auth/view/signin`
    - Por cada ítem: buscar por SKU en barra de búsqueda → añadir al carrito con cantidad
    - Si SKU no encontrado: agregar a lista `omitidos`
    - Returns `{cart_url, agregados: int, omitidos: list}`
  - Usar `playwright_stealth.stealth_sync(page)` para evitar detección de bot
  - Verify: script standalone (`python integrations/homedepot.py --test`) hace login y agrega 1 producto real

- [ ] **T4 — Route Flask + background worker**
  - `POST /api/enviar_oc_hd/<orden_id>` (solo admin, `@check_org_permission`)
    - Valida que la OC tenga proveedor con `ProveedorIntegracion` tipo `homedepot`
    - Marca `orden.integracion_status = 'procesando'` + commit
    - Lanza `threading.Thread` con app context para ejecutar `fill_cart`
    - Al terminar: actualiza `integracion_status` a `'listo'` o `'error'` + guarda resultado JSON en campo `integracion_resultado TEXT`
  - `GET /api/enviar_oc_hd/<orden_id>/status` → returns `{status, agregados, omitidos, cart_url}`
  - Verify: POST retorna 202, GET retorna status `procesando` → luego `listo`

- [ ] **T5 — UI en `ver_orden.html`**
  - Mostrar botón "Enviar a Home Depot Pro" solo si `proveedor.integracion` existe y `orden.estado` es `'aprobada'`
  - Click → POST a `/api/enviar_oc_hd/<id>` → badge "Procesando..." con spinner
  - Polling cada 3s con `setInterval` + fetch a `/status` → actualiza badge a "Carrito listo — Ver en HD" (link) o "Error: ..."
  - Items omitidos mostrados como warning en badge
  - Verify: flujo completo en browser; badge cambia de estado sin recargar la página

## Done When
- [ ] OC aprobada de Home Depot → click botón → carrito llenado en HD Pro sin intervención adicional
- [ ] Items sin SKU → badge de advertencia con lista, el resto sí se agrega
- [ ] Credenciales HD almacenadas cifradas (Fernet), nunca en texto plano
- [ ] Funciona con cuenta HD Pro real (verificar en staging/test antes de producción)

## Notes
- **Bot detection**: Home Depot usa Akamai. `playwright-stealth` ayuda pero no es garantía. Si bloquean: considerar añadir delay random entre acciones (1-3s).
- **Sesión HD**: el login puede requerir 2FA o CAPTCHA en la primera vez. Configurar desde IP fija del servidor.
- **Error frecuente**: si el SKU ya no existe en HD, el script lo registra en `omitidos` — nunca debe fallar silenciosamente.
- **No usar en producción sin prueba real** con credenciales de staging o una orden de $0.01 primero.
- **Fernet key**: generar con `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` y guardar en `.env` como `FERNET_KEY=...`
