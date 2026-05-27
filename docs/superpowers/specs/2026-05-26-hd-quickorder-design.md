# HD Pro Quick Order — Diseño de Integración Propia

**Fecha:** 2026-05-26  
**Estado:** Aprobado para implementación  
**Contexto:** Home Depot denegó credenciales PunchOut cXML. Playwright puro es frágil por bot detection. Volumen: 11-50 pedidos/mes.

---

## Objetivo

Eliminar la reingreso manual de productos al hacer pedidos en Home Depot Pro, usando la función nativa **Quick Order / Bulk Order** del portal HD que acepta una lista de ítems (SKU + cantidad) en lugar de agregar productos uno por uno.

---

## Arquitectura en dos fases

### Fase 1 — CSV Export (entrega inmediata, sin riesgo)

El sistema genera un archivo CSV compatible con HD Pro Quick Order. El usuario lo descarga y lo sube manualmente al portal. Elimina el 90% del trabajo de reingreso sin ninguna automatización de navegador.

**Componentes:**
- `integrations/hd_quickorder.py` — función `generar_csv(orden) → bytes`
  - Columnas: `Item Number` (usa `producto.hd_sku` si existe, sino `producto.codigo`), `Quantity`
  - Encoding UTF-8, sin BOM
  - Excluye detalles sin producto válido, los reporta en header de respuesta
- Ruta `GET /ordenes/<id>/exportar-hd-csv` — sirve el archivo como descarga `attachment`
- Botón **"Exportar para HD Pro"** en `orden_detalle.html` (visible si proveedor es HD y hay detalles)

**Flujo Fase 1:**
```
OC con detalles → click "Exportar para HD Pro"
→ Flask genera CSV en memoria (sin tocar disco)
→ Descarga automática en browser del usuario
→ Usuario entra a homedepot.com/pro → Quick Order → sube CSV
→ HD llena el carrito → usuario revisa y hace checkout
```

---

### Fase 2 — Upload automático con sesión persistente

Playwright se loguea **una sola vez** y guarda las cookies en BD (cifradas con Fernet). Para cada pedido, restaura la sesión guardada y navega a Quick Order para subir el CSV programáticamente. Si la sesión expiró, re-login automático.

**Componentes:**
- Modelo `HDSesion(id, org_id, proveedor_id, cookies_json_cifrado, expira_en, creada_en)`
- `integrations/hd_session.py` — `guardar_sesion(page, org_id, proveedor_id)` y `restaurar_sesion(page, sesion)`
- `integrations/hd_quickorder.py` — añadir `subir_csv_auto(creds, csv_bytes, sesion) → dict`
  - Navega a HD Pro Quick Order URL
  - Usa `page.set_input_files()` para subir el CSV (un solo gesto = mínimo bot detection)
  - Verifica que los ítems quedaron en el carrito
  - Returns `{ok, carrito_url, items_agregados, items_omitidos}`
- Ruta `POST /ordenes/<id>/subir-hd-auto` — background thread (igual que Playwright actual)
- Ruta `GET /api/ordenes/<id>/hd-upload-status` — polling
- UI: badge de estado en `orden_detalle.html` (reutiliza el patrón de polling existente)

**Flujo Fase 2:**
```
OC aprobada → click "Enviar automáticamente a HD Pro"
→ Flask genera CSV en memoria
→ hd_session: busca HDSesion activa para esta org
→ Si sesión válida: Playwright restaura cookies → navega a Quick Order → sube CSV
→ Si sesión expirada: Playwright hace login completo → guarda nueva sesión → sube CSV
→ HD procesa el CSV → carrito llenado
→ Polling badge → "X ítems en carrito — Ver carrito" con link
```

---

## Modelo de datos

```
HDSesion
├── id (PK)
├── org_id (FK organizacion)
├── proveedor_id (FK proveedor)
├── _cookies (TEXT, cifrado Fernet — JSON de cookies Playwright)
├── expira_en (DATETIME — típicamente now + 7 días)
└── creada_en (DATETIME)
```

CLI idempotente: `flask add-hd-session-table`

---

## Manejo de errores

| Error | Comportamiento |
|-------|---------------|
| SKU no encontrado en HD Pro | Item registrado en `omitidos`, los demás continúan |
| Sesión expirada | Re-login automático, nueva sesión guardada |
| Login falla (credenciales erróneas) | Status `'error_login'`, flash al usuario |
| CSV vacío (ningún ítem válido) | Ruta retorna 400 con mensaje claro |
| Playwright timeout | Status `'error'`, mensaje de retry disponible |

---

## Criterios de éxito

- [ ] Fase 1: OC con 10 ítems → CSV descargado → subido a HD Quick Order en <2 minutos total
- [ ] Fase 2: Click → carrito llenado automáticamente en <60 segundos sin intervención
- [ ] Sesión persiste entre pedidos (no re-login en cada OC)
- [ ] Ítems sin SKU de HD quedan marcados como omitidos, no bloquean el resto
- [ ] Playwright solo para login + file upload (no DOM scraping de ítems)

---

## Lo que NO se construye aquí

- No se modifica el checkout (el humano siempre revisa y confirma el pago)
- No se reemplaza el código PunchOut existente (queda para cuando HD cambie de postura)
- No se agrega soporte para otros proveedores en esta iteración
