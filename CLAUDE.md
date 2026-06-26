# Gestión de Inventario — Instrucciones del Proyecto

## Stack
Flask + SQLAlchemy + PostgreSQL + Bootstrap 5.3.3 + Gunicorn (servidor: /root/venv/)
DM Sans (Google Fonts) + Bootstrap Icons 1.11.3 + Chart.js + PWA (manifest + SW)

## Herramientas activas — SIEMPRE usar la herramienta adecuada según la tarea

### Plugins oficiales (siempre disponibles)
- **superpowers**: Tareas grandes, múltiples pasos, subagentes paralelos, worktrees.
- **code-review**: Revisar código antes de commits importantes o PRs.
- **frontend-design**: Consultar ANTES de implementar cualquier componente o página nueva.
- **claude-md-management** (`/revise-claude-md`): Actualizar CLAUDE.md al final de cada sesión significativa.
- **pr-review-toolkit**: Antes de abrir PRs — code-reviewer, test-analyzer, silent-failure-hunter.

### Skills (invocar con Skill tool o `/nombre`)
- **andrej-karpathy**: Análisis técnico profundo, arquitectura, decisiones de ML/AI.
- **antigravity-skill-orchestrator**: Coordinar múltiples skills en tareas complejas multietapa.
- **ui-ux-pro-max**: Todo diseño UI/UX. Script: `.claude/skills/ui-ux-pro-max/scripts/search.py`.
- **update-config**: Cambios a `settings.json`, permisos, hooks de Claude Code.

### MCP — ruflo (usar cuando esté conectado)
- Inicio de sesión: `memory_retrieve` con tags del proyecto para recuperar contexto previo.
- Fin de sesión importante: `memory_store` con resumen de cambios, patrones y decisiones.
- Búsqueda de contexto: `memory_search` antes de implementar algo que ya pudo haberse resuelto.
- Tareas largas automatizables: `workflow_*` y `agent_*`.
- Si ruflo NO conecta en la sesión: usar `/revise-claude-md` al final como memoria persistente alternativa.

## Workflow de modelos — OBLIGATORIO en todo momento

### Regla de selección de modelo (no negociable)
| Fase | Modelo | Cuándo |
|------|--------|--------|
| **Planear** | `opus` | Diseñar arquitectura, evaluar opciones, definir pasos, leer y entender archivos grandes |
| **Ejecutar** | `sonnet` | Escribir código, editar archivos, correr comandos, implementar lo que Opus planeó |
| **Revisar** | `opus` | Code-review, pr-review-toolkit, audits de seguridad, verificación final |

- Antes de cualquier tarea no trivial: planear con Opus primero, luego ejecutar con Sonnet.
- Para leer archivos y entender la base de código: usar Opus (subagente o modo `/opus`).
- Para revisiones de código (plugins `code-review`, `pr-review-toolkit`, agente `code-reviewer`): siempre Opus.
- Tareas simples de una línea (renombrar, agregar import): Sonnet directo, sin cambio de modelo.

### Skills y plugins — usar SIEMPRE que aplique
- Ante cualquier duda (≥1% de probabilidad de que aplique un skill): invocar el skill ANTES de actuar.
- Skills disponibles: `the-architect`, `graphify`, `andrej-karpathy`, `antigravity-skill-orchestrator`, `ui-ux-pro-max`, `update-config`.
- Plugins disponibles: `superpowers`, `code-review`, `frontend-design`, `claude-md-management`, `pr-review-toolkit`.
- No improvisar lo que un skill/plugin ya sabe hacer mejor.

## Reglas generales
- Siempre usar ruflo (MCP) cuando esté disponible para memoria persistente y contexto.
- Siempre hacer `git push origin main` después de cada commit (sin preguntar).
- Los pip install en el servidor van en `/root/venv/bin/pip install`, NO en el venv local.
- La cámara NO debe bloquearse en Permissions-Policy (se usa para escáner QR).
- Archivos Python: siempre abrir con `encoding='utf-8'` en Windows.

## Seguridad — Todo implementado (commits 317ea9e, 5ca3759, aeef44c, 3988e87, 0db5e87, 4d63d06)

### Multi-tenant isolation (commits 0db5e87, 4d63d06) ✅ COMPLETO
- Audit con 4 agentes paralelos (superpowers) cubrió: listas, detalle, servicios, APIs.
- Rutas con `@check_org_permission` añadido: `ver_orden`, `editar_orden`, `nueva_orden_manual`, `ver_proyecto_oc`, `lista_servicios`, `nuevo/editar/eliminar_servicio`, `detalle_servicio`, `nuevo/marcar/eliminar pago_servicio`, `api_productos_con_stock`.
- Fugas corregidas: `historial_producto` (stocks sin filtro Almacen.org), `ver_proyecto_oc` (SolicitudAprobacion sin org_id), `api_toggle_permiso` (IDOR oracle en fetch pre-check).

### Rutas financieras (commit 317ea9e)
- Montos siempre validados > 0 server-side en: gastos, facturas, pagos de servicio.
- Categorías de gasto validadas contra whitelist `CATEGORIAS_GASTO`.
- Audit log `log_actividad()` en todas las operaciones financieras (crear/editar/pagar/eliminar).
- `_flash_err(user_msg, exc)` — no expone excepciones internas al usuario.
- Rate limiting: login 10/min, register 10/min, forgot-password 5/min + 20/hora.

### FIN-01 — Float → Numeric (commit aeef44c) ✅ COMPLETO
- `db.Numeric(10,2)` en: `Gasto.monto`, `PagoServicio.monto`, `FacturaProveedor.monto`,
  `Producto.precio_unitario`, `OrdenCompraDetalle.costo_unitario_estimado`, `ProyectoOCDetalle.costo_unitario`.
- `_JSONProvider` custom serializa `Decimal` → `float` para `jsonify()`.
- CLI: `flask fix-float-to-numeric` (idempotente, verifica `information_schema.columns`).
- **Correr en servidor**: `flask fix-float-to-numeric && sudo systemctl restart inventario`

### AUTH-02 — Tokens de reset single-use (commit 3988e87) ✅ COMPLETO
- Modelo `TokenUsado` (tabla `token_usado`): `token_hash` SHA-256, `usado_en`, `expira_en`.
- CLI: `flask fix-add-token-usado` (CREATE TABLE IF NOT EXISTS — idempotente).
- CLI: `flask limpiar-tokens-expirados` (para cron mensual).
- Ruta `reset_password`: verifica hash antes de procesar; inserta hash + commit atómicos.
- **Correr en servidor**: `flask fix-add-token-usado && sudo systemctl restart inventario`

### RATE-01 — Redis para Flask-Limiter (commit 3988e87) ✅ COMPLETO
- `storage_uri` lee `REDIS_URL` env var; fallback a `"memory://"` si no existe.
- `redis` agregado a `requirements.txt`.
- **Activar en servidor**: `export REDIS_URL=redis://localhost:6379/0` en el entorno de systemd,
  luego `/root/venv/bin/pip install redis && sudo systemctl restart inventario`.

## Frontend / UI (commit 30278db)
- Design system: tokens CSS en `base.html` (`--primary`, `--surface`, `--border`, etc.), dark/light mode.
- Glassmorphism navbar, animaciones con `prefers-reduced-motion`, focus visible WCAG.
- Skip link, `<main id="main-content">`, `font-display: swap`.
- **GOTCHA CSS stacking context**: `animation-fill-mode: both` + `transform` en keyframe `to` crea stacking context
  permanente en `<main>`, haciendo que el backdrop de Bootstrap (z-index 1040) bloquee modales dentro de `<main>`.
  Fix: keyframe `to` solo con `opacity:1`, sin `transform`. Commit: `37426b4`.
- **Patrón modales de página**: usar `{% block modals %}{% endblock %}` en `base.html` (después de `</main>`).
  Los modales de plantillas hijas van en `{% block modals %}`, nunca dentro de `{% block content %}`.

### 9 mejoras UI/UX aplicadas en dashboard (commit 30278db)
1. Emojis → Bootstrap Icons en leyenda de barra de salud.
2. `alt` + `loading="lazy"` en imágenes de productos (WCAG 1.1.1).
3. `aria-label` en botones icon-only + `aria-hidden` en íconos decorativos (WCAG 4.1.2).
4. `role="link"` + `tabindex="0"` + `onkeydown` en filas de tabla (WCAG 2.1.1).
5. Touch targets: clase `btn-accion` 36px desktop / 44px en `pointer:coarse` (WCAG 2.5.5).
6. `fila-producto:focus-visible` con outline para teclado.
7. Estado "Sin resultados" con botón "Limpiar filtros" (resetea todos los dropdowns).
8. Font-size floor: `.68rem`/`.7rem`/`.72rem` → `.75rem` (12px mínimo legible).
9. Progress bar CSS: `transition: width` (los bars usan `width:%` inline, no transform).

## Knowledge Graph (graphify)
- Grafo generado en `graphify-out/` (785 nodos, 1293 edges, 114 comunidades).
- God nodes: `base.html` (58 edges), `now_mx()` (53), `Index template` (45), `log_actividad()` (27), `get_item_or_404()` (25).
- Actualizar tras cambios grandes: `/graphify . --update` (usa caché, solo re-extrae archivos modificados).
- Ver grafo interactivo: abrir `graphify-out/graph.html` en browser.

## Helpers y patrones clave en app.py
- `get_item_or_404(model, id)` — SEGURO: filtra por `organizacion_id` automáticamente. Usar siempre en lugar de `Model.query.get_or_404(id)` (INSEGURO — sin filtro de org).
- `Model.query.filter_by(id=x, organizacion_id=org_id).first_or_404()` — patrón correcto para rutas que no usan `get_item_or_404`.
- `Stock` no tiene `organizacion_id` propio — filtrar siempre vía join: `Stock.query.filter_by(...).join(Almacen).filter(Almacen.organizacion_id == org_id)`.
- `@check_org_permission` — NO filtra datos, solo bloquea usuarios sin org asignada. Debe estar en TODAS las rutas incluso si los queries ya filtran por org_id.
- IDOR oracle: para rutas admin con `<user_id>`: hacer `filter_by(id=x, organizacion_id=org_id).first_or_404()` ANTES del org-check, no después.
- `SolicitudAprobacion` tiene `organizacion_id` — siempre incluirlo en queries aunque el padre ya esté validado.
- `log_actividad(accion, entidad, descripcion, entidad_id=None)` — lee user/org de `current_user` automáticamente. Llamar ANTES de `db.session.commit()`.
- `_flash_err(user_msg, exc)` — loguea excepción al servidor, muestra mensaje seguro al usuario.
- `CATEGORIAS_GASTO` — whitelist: `['Servicios', 'Nómina', 'Mantenimiento', 'Insumos', 'Inventario', 'Otros']`.
- `with db.session.no_autoflush:` — envolver loops que mezclan queries + mutaciones del mismo modelo (evita flush intermedio que propaga excepciones entre ítems).
- En loops de recepción/procesamiento: `omitidos = []` + `if not obj: omitidos.append(...); continue` para no revertir toda la operación por un ítem inválido.

## HD Pro Quick Order (commits 49ccf47, c83aa82, 89900fa) — reemplaza PunchOut cXML
- PunchOut eliminado: no hay modelo PunchOutSession ni rutas punchout_* en el código.
  La columna `punchout_url` puede seguir en la BD del servidor (inofensiva, ignorada).
- `integrations/hd_quickorder.py`: `generar_csv(orden)` y `generar_csv_proyecto(proyecto_oc)` → `(bytes, omitidos)`
- `integrations/hd_session.py`: `guardar_sesion()`, `restaurar_sesion()`, `sesion_valida()` — cookies Fernet, TTL 7 días.
- Modelo `HDSesion` (tabla `hd_sesion`): unique(org_id, proveedor_id). CLI: `flask add-hd-session-table`.
- **Correr en servidor**: `flask add-hd-session-table && sudo systemctl restart inventario`
- Rutas HD: `GET /ordenes/<id>/exportar-hd-csv`, `POST /ordenes/<id>/subir-hd-auto`,
  `GET /proyecto-oc/<id>/exportar-hd-csv` (requiere `perm_create_oc_proyecto`).
- `ProveedorIntegracion.credenciales` = `{'usuario': str, 'password': str}` (no más network_id/shared_secret).
- Visibilidad botones en `orden_detalle.html`: CSV cuando `tiene_hd_sku OR tiene_integracion`;
  auto-upload solo cuando `integracion.activo`; link "Configurar HD Pro" cuando hd_sku sin integración activa.
- `ProyectoOCDetalle` NO tiene hd_sku: usa `producto.hd_sku or producto.codigo` para catálogo,
  `descripcion_nuevo` para externos. Filtra por `proveedor_sugerido` contiene "home depot".

## GOTCHAs
- **PowerShell BOM**: `Out-File -Encoding utf8` en PS 5.1 escribe BOM; Python falla con `json.JSONDecodeError: Unexpected UTF-8 BOM`. Fix: `$noBom = [System.Text.UTF8Encoding]::new($false); [System.IO.File]::WriteAllText($path, $content, $noBom)`. El flag `-NoBom` no existe en PS 5.1.
- **Jinja2 doble `>`**: `{% else %}">{% endif %}>` produce `">>` (el `>` visible en pantalla). Patrón correcto: `{% else %}"{% endif %}>`.
- **`del` no existe en Bash/Linux**: en la Bash tool usar `rm -f archivo`, no `del archivo`.

## OC Rápida — agrupación por proveedor (commit pendiente)
- OC Rápida ahora agrupa por **proveedor** (accordion exterior) en lugar de almacén.
- Una sola OC puede incluir productos de múltiples almacenes.
- `OrdenCompraDetalle.almacen_id` (nullable FK) — almacén por ítem.
- `OrdenCompra.almacen_id` ahora nullable; se puebla con el almacén dominante para retrocompat de templates.
- `recibir_orden` usa `detalle.almacen_id or orden.almacen_id` (backward compat con OCs legacy).
- Form envía `name="item" value="prod_id:alm_id"` por checkbox (ya no `producto_id` + `almacen_id` oculto).
- **Correr en servidor**: `flask fix-oc-detalle-almacen && sudo systemctl restart inventario`

## Estado actual
- FIN-01 ✅ — RATE-01 ✅ — AUTH-02 ✅ — Multi-tenant isolation ✅ (commits 0db5e87, 4d63d06)
- HD Pro Quick Order ✅ Fase 1 (CSV) + Fase 2 (sesión persistente) — commits 49ccf47–89900fa.
- Dashboard KPIs restringidos a `super_admin` y `admin` (commit db05095).
- `recibir_orden` con guards para producto=None, cantidad≤0, y `no_autoflush` (commit 20ba5b4).
- Almacenes ordenados por `.order_by(Almacen.id)` (commit 72a8afd).
- **Pendiente en servidor**: `flask add-hd-session-table && sudo systemctl restart inventario`
- Sin tareas pendientes de seguridad en la hoja de ruta original.
