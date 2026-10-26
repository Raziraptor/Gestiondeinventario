# Pendientes heredados de la Fase 1 (rediseño Fusión + móvil)

Origen: revisiones finales de la Fase 1 (fe52a16..a401351). Nada de esto bloquea; ordenado por impacto.

## Seguridad (pre-existente, antes de usar la PWA en dispositivos compartidos)
- **SW cachea HTML autenticado** (`static/sw.js` navigate → `CACHE`) y el logout no lo limpia: otro usuario offline ve páginas del anterior. Fix: `Cache-Control: no-store` en HTML autenticado + `Clear-Site-Data: "cache", "storage"` en logout (o `postMessage` al SW).
- **Cola offline sin dueño** (`static/js/offline-queue.js`, IndexedDB `pending_ops`): ops de A se reenvían con la sesión de B. Fix: guardar `user_id`/`org_id` por op, rechazar en `/api/sync` si no coincide, limpiar al logout.
- `presupuestos` / `centros-costo`: el sidebar los muestra solo a admin, pero las rutas aceptan `perm_view_gastos` (finance/routes.py ~529, ~654). Decidir: ¿`@admin_required`?
- `@check_org_permission` falta en `editar_producto`, `configurar_etiqueta`, `historial_producto` (inventory/routes.py).
- Links del sidebar/dashboard visibles sin el permiso que exige la ruta (dashboard, almacenes, proveedores, reportes, historial_salidas, editar_producto). Copiar los gates de `partials/bottom_nav.html`.
- Bootstrap JS sin SRI; `script-src` confía en todo `cdn.jsdelivr.net`.

## Accesibilidad / UI
- Sidebar móvil cerrado sigue en el orden de tabulación; abierto no atrapa foco → `inert` en estado cerrado.
- Tamaños de kicker < .75rem en sidebar/frame (fusion.css `.sb-kicker` .62rem, `.sb-badge`, `kbd`; inline en base.html). El spec 4.2 dice .62–.68rem y choca con el piso de .75rem: decidir.
- Sin `errorhandler(404)`: un 404 real es la página plana de Werkzeug sin meta viewport.
- CSP bloquea el sonido de soundjay en `/orden/nueva/manual`.
- `#ordenMovil` (dashboard) aparcado por Ruling 32.

## Limpieza (ponytail, requiere prueba visual)
- compat.css: puente de alias del tema claro (~L34-48), `min-height:100vh`/`overflow-x:hidden` sobreescritos por mobile.css, clases sin uso (`.dashboard-card`, `.animate-section`, `.badge-status`, `.rounded-apple*`, `.alert-premium`, `.kpi-stat*`).
- fusion.css: reglas sobreescritas por compat (`.page-title`, `.btn:active`, `.btn-primary`), clases sin uso (`.avatar.sage/warn/info`, `.notif-dot`, `.card-hover`, `.btn-outline`, `.btn-sage`, `.steps`, `.stagger`, `.hide-mobile`…), `@import` de Google Fonts duplicado.
- dashboard.html `<style>`: duplicados de `.page-head`, `.meter`, `.kpi-icon`, paginación.
- image-viewer.js: modal hecho a mano → `<dialog>.showModal()`.
- fusion.js: CSS inyectado desde JS → fusion.css; fallbacks hex de `tokens()` desfasados del CSS.
- tests: dos matchers de llaves duplicados (test_frame / test_dashboard_ui).
- Cache-busting `?v=` en los estáticos de base.html para no depender de subir `CACHE` en sw.js.
