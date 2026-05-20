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

## Helpers y patrones clave en app.py
- `get_item_or_404(model, id)` — SEGURO: filtra por `organizacion_id` automáticamente. Usar siempre en lugar de `Model.query.get_or_404(id)` (INSEGURO — sin filtro de org).
- `Model.query.filter_by(id=x, organizacion_id=org_id).first_or_404()` — patrón correcto para rutas que no usan `get_item_or_404`.
- `Stock` no tiene `organizacion_id` propio — filtrar siempre vía join: `Stock.query.filter_by(...).join(Almacen).filter(Almacen.organizacion_id == org_id)`.
- `@check_org_permission` — NO filtra datos, solo bloquea usuarios sin org asignada. Debe estar en TODAS las rutas incluso si los queries ya filtran por org_id.
- IDOR oracle: para rutas admin con `<user_id>`: hacer `filter_by(id=x, organizacion_id=org_id).first_or_404()` ANTES del org-check, no después.
- `SolicitudAprobacion` tiene `organizacion_id` — siempre incluirlo en queries aunque el padre ya esté validado.
- `log_actividad(accion, entidad, detalle, user_id, org_id)` — llamar ANTES de `db.session.commit()`.
- `_flash_err(user_msg, exc)` — loguea excepción al servidor, muestra mensaje seguro al usuario.
- `CATEGORIAS_GASTO` — whitelist: `['Servicios', 'Nómina', 'Mantenimiento', 'Insumos', 'Inventario', 'Otros']`.

## Estado actual — Fase 2 completa
- FIN-01 ✅ — RATE-01 ✅ — AUTH-02 ✅ — Multi-tenant isolation ✅ (commits 0db5e87, 4d63d06)
- Pendiente en servidor: correr los 3 comandos CLI de migración mencionados arriba.
- Sin tareas pendientes de seguridad en la hoja de ruta original.
