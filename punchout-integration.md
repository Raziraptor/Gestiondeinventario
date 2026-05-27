# PunchOut cXML — Integración con Home Depot Pro

## Goal
Implementar el protocolo cXML PunchOut en el lado del comprador (Flask app), para que al iniciar una OC con Home Depot el usuario sea redirigido al catálogo HD autenticado automáticamente, haga su selección, y el carrito regrese estructurado a nuestra OC.

## Contexto
- **Protocolo**: cXML 1.2 (estándar industrial B2B — Ariba, Coupa, SAP usan esto)
- **Umbral HD directo**: $50K/año (no calificamos hoy → usar TradeCentric de puente)
- **TradeCentric**: middleware que tiene relación con HD; acepta cuentas menores
- **Nuestro código es idéntico** ya sea HD directo o TradeCentric como gateway
- **Playwright existente**: queda como fallback; PunchOut es el canal principal

## Flujo técnico
```
1. Usuario abre OC → click "Comprar en Home Depot"
2. Flask POST cXML PunchOutSetupRequest → HD (o TradeCentric gateway)
3. HD responde con URL de sesión autenticada
4. Flask redirect → usuario navega el catálogo HD en su browser
5. Usuario selecciona productos → "Regresar al sistema"
6. HD POST PunchOutOrderMessage → /api/punchout/retorno (nuestro endpoint)
7. Flask parsea XML → llena detalles de la OC automáticamente
8. Usuario regresa a la OC con todos los ítems importados
```

## Tasks

- [ ] **T1 — Modelo PunchOutSession**
  - Nuevo modelo `PunchOutSession(id, buyer_cookie, orden_id, user_id, org_id, status, cart_xml, creado_en)`
  - `buyer_cookie` = UUID único por sesión (lo que HD devuelve para identificar al comprador)
  - `status`: `'iniciada'` | `'completada'` | `'expirada'`
  - CLI idempotente `flask add-punchout-tables` (CREATE TABLE IF NOT EXISTS)
  - Verify: `flask add-punchout-tables` sin errores; modelo accesible en shell Flask

- [ ] **T2 — Módulo cXML (`integrations/punchout_cxml.py`)**
  - `build_setup_request(creds, buyer_cookie, return_url, user) → str` — genera el XML del PunchOutSetupRequest
  - `send_setup_request(punchout_url, xml_str) → str` — POST HTTP, devuelve URL de sesión del response
  - `parse_order_message(xml_str) → list[dict]` — parsea PunchOutOrderMessage, devuelve ítems `[{sku, nombre, cantidad, precio_unitario, unidad}]`
  - Usa solo `xml.etree.ElementTree` (stdlib) + `requests` (ya en requirements)
  - Verify: unittest con XML de ejemplo de cXML.org devuelve ítems correctamente

- [ ] **T3 — Actualizar `ProveedorIntegracion`**
  - Añadir campo `punchout_url = db.Column(db.Text, nullable=True)` (URL del gateway HD o TradeCentric)
  - Actualizar `tipo` para soportar `'punchout'` además de `'homedepot'`
  - CLI `flask add-punchout-tables` incluye `ALTER TABLE IF NOT EXISTS` para la columna
  - Actualizar sección en `proveedor_form.html`: mostrar campo "PunchOut URL" + relabeling de campos existentes
  - Verify: formulario guarda `punchout_url`; campo aparece en página de editar proveedor

- [ ] **T4 — Routes Flask**
  - `GET /ordenes/<orden_id>/punchout/iniciar` (solo admin, `@check_org_permission`):
    - Crea `PunchOutSession` con UUID como `buyer_cookie`
    - Llama `send_setup_request` → obtiene URL de sesión HD
    - Guarda session en DB, redirige usuario a URL HD
  - `POST /api/punchout/retorno` (público — HD hace POST aquí, sin login):
    - Recibe `cxml-urlencoded` o XML directo del body
    - Extrae `BuyerCookie`, busca `PunchOutSession`
    - Parsea ítems del `PunchOutOrderMessage`
    - Crea/actualiza `OrdenCompraDetalle` con los ítems recibidos
    - Marca session como `'completada'`
    - Retorna HTTP 200 + HTML minimal que hace `window.location` de vuelta a la OC
  - Verify: test con Postman enviando PunchOutOrderMessage de ejemplo → OC se llena

- [ ] **T5 — UI en `orden_detalle.html`**
  - Cambiar botón "Enviar a Home Depot Pro" (Playwright) por "Comprar en Home Depot"
  - Click → `window.open(url_iniciar, '_blank')` para abrir catálogo en nueva pestaña
  - Polling cada 5s a `GET /api/ordenes/<id>/punchout-status` para detectar cuando `PunchOutSession.status == 'completada'`
  - Al completar: recargar la tabla de detalles de la OC (o reload completo) mostrando los ítems importados
  - Verify: flujo completo end-to-end con sandbox TradeCentric; ítems aparecen en OC

## Pasos previos (business, no código)
1. **Opción A — HD directo**: Llamar a HD Pro eProcurement, pedir PunchOut aunque <$50K. Contacto: buscar "Home Depot Pro eProcurement" o pedir a tu rep de cuenta.
2. **Opción B — TradeCentric**: Registrarse en tradecentric.com (~$200-300/mes). Ellos tienen acuerdo con HD y dan las credenciales de gateway sin umbral de gasto.
3. Credenciales que necesitarás (cualquiera de las dos vías):
   - **PunchOut URL** (endpoint al que enviamos el SetupRequest)
   - **Buyer Network ID** (tu identidad en la red)
   - **Shared Secret** (para validación del header cXML)

## Done When
- [ ] Click "Comprar en Home Depot" → abre catálogo HD auto-autenticado
- [ ] Selección en HD → regresa y llena la OC automáticamente sin intervención manual
- [ ] Playwright queda como fallback si PunchOut falla (no se elimina)
- [ ] Credenciales cifradas con la misma Fernet key existente

## Notas técnicas
- El endpoint `/api/punchout/retorno` debe estar en HTTPS público (ya tenemos esto ✅)
- Validar el `BuyerCookie` en el retorno — evita que alguien inyecte ítems falsos en una OC
- `PunchOutOrderMessage` puede llegar como `application/x-www-form-urlencoded` (campo `cXML-urlencoded`) o como body XML directo — manejar ambos casos
- cXML timestamp format: `2026-05-26T18:30:00-06:00` (ISO 8601 con timezone)
- PayloadID format: `timestamp.randomhex@tudominio.com`
