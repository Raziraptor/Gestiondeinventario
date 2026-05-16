# Gestión de Inventario — Instrucciones del Proyecto

## Stack
Flask + SQLAlchemy + PostgreSQL + Bootstrap 5.3.3 + Gunicorn (servidor: /root/venv/)
DM Sans (Google Fonts) + Bootstrap Icons 1.11.3 + Chart.js + PWA (manifest + SW)

## Skills activos en este proyecto
- **andrej-karpathy**: Usar para análisis técnico profundo, decisiones de arquitectura y razonamiento sobre ML/AI.
- **antigravity-skill-orchestrator**: Usar para coordinar múltiples skills en tareas complejas de varias etapas.
- **ui-ux-pro-max**: Usar para cualquier trabajo de diseño UI/UX. Script en `.claude/skills/ui-ux-pro-max/scripts/search.py`.
- **senior-frontend**: Referencias en `.claude/skills/senior-frontend/references/`.

## Reglas generales
- Siempre usar ruflo (MCP) cuando esté disponible para memoria persistente y contexto.
- Siempre hacer `git push origin main` después de cada commit (sin preguntar).
- Los pip install en el servidor van en `/root/venv/bin/pip install`, NO en el venv local.
- La cámara NO debe bloquearse en Permissions-Policy (se usa para escáner QR).
- Archivos Python: siempre abrir con `encoding='utf-8'` en Windows.

## Seguridad — Todo implementado (commits 317ea9e, 5ca3759, aeef44c, 3988e87)

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
- `get_item_or_404(model, id)` — filtra por `organizacion_id` automáticamente (seguridad multi-tenant).
- `log_actividad(accion, entidad, detalle, user_id, org_id)` — llamar ANTES de `db.session.commit()`.
- `_flash_err(user_msg, exc)` — loguea excepción al servidor, muestra mensaje seguro al usuario.
- `CATEGORIAS_GASTO` — whitelist: `['Servicios', 'Nómina', 'Mantenimiento', 'Insumos', 'Inventario', 'Otros']`.

## Estado actual — Fase 2 completa
- FIN-01 ✅ — RATE-01 ✅ — AUTH-02 ✅
- Pendiente en servidor: correr los 3 comandos CLI de migración mencionados arriba.
- Sin tareas pendientes de seguridad en la hoja de ruta original.
