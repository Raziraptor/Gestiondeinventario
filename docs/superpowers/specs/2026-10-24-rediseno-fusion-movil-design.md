# Rediseño "Fusion refinada" + experiencia móvil tipo app

Fecha: 2026-10-24 · Estado: borrador para aprobación

## 1. Intención y el porqué

El sistema ya tiene una primera capa del sistema visual **Fusion** (commit `fda812a`, `static/css/fusion.css`) y un paquete de diseño hifi en `design_handoff_rediseno_inventario/` (11 pantallas). El usuario aportó además `DESIGN.md`, una referencia de estilo tipo Perplexity: lienzo cálido, un solo acento, pesos contenidos, superficies planas con línea fina.

El objetivo **no es reemplazar Fusion**, sino **fusionarlo con la disciplina de DESIGN.md** para que la app se vea más profesional y detallada, y a la par **arreglar a fondo la experiencia móvil**, que hoy es deficiente:

- La página se puede arrastrar hacia los lados; la barra superior se sale de la pantalla por la derecha y al deslizar "te sales" del contenido.
- Hay zoom automático al tocar campos, que saca al usuario del área de trabajo.
- El teclado y los modales desplazan la vista.
- No se respetan bordes seguros (notch, barra de gestos), sobre todo en la PWA instalada.
- En el **Dashboard** (la pantalla más usada) hay que deslizar la tabla de productos y es fácil salirse por accidente.

Éxito = en el celular (navegador y PWA) la app se siente como una **app nativa**: un marco fijo que nunca se mueve de lado, solo el área de trabajo hace scroll vertical; en escritorio se ve sobria, cuidada y consistente.

## 2. Metas, no-metas, anti-metas

**Metas**
1. Cero desplazamiento horizontal de la página en cualquier pantalla, en anchos desde 320px.
2. Sin zoom de interfaz (ni automático al enfocar campos ni por pellizco), **excepto en imágenes**, que sí se pueden ampliar.
3. Respeto de bordes seguros (`safe-area-inset-*`) en barra superior, navegación inferior, FAB, barras sticky y banners.
4. Marco estable: barra superior y navegación inferior fijas; teclado y modales no hacen saltar la vista.
5. Nuevo lenguaje visual (sección 4) aplicado a **todas** las plantillas, con modo claro y oscuro.
6. Las 11 pantallas del paquete `design_handoff_rediseno_inventario/` recreadas con su estructura (wizard, carrito de salida, comparador de ajuste, etc.) pero con los tokens refinados de este documento, no con los brillos/gradientes originales.

**No-metas**
- No cambia la lógica de negocio, rutas, modelos, permisos ni seguridad (multi-tenant, CSRF, CSP).
- No se migra de Bootstrap a otro framework; Bootstrap 5.3.3 sigue como base de grid/modales/dropdowns.
- No se cambia la estructura del menú (secciones Inventario, Compras, Finanzas, Incidencias, Soporte, Sistema).
- El módulo de incidencias tiene su propio paquete (`design_handoff_reporte_incidencias/`, sistema Nocturne); **queda fuera de este proyecto** salvo que herede automáticamente el marco y tokens nuevos.

**Anti-metas (sería un fracaso aunque "funcione")**
- Que en algún teléfono todavía se pueda arrastrar la página de lado o que la barra superior se corte.
- Que se rompan funciones existentes por el cambio de markup: filtros/orden del Dashboard, escáner QR (cámara), cola offline, push, chatbot, modales.
- Que se viole la CSP con nonces: **nada de handlers inline** (`onclick=` etc.) ni `<script>` sin `nonce="{{ csp_nonce() }}"` (commits 7490183, 62d9e57).
- Que el look quede "a medias": mezcla visible de estilo viejo (indigo/Precision Operations) y nuevo.

## 3. Restricciones

- Stack: Flask + Jinja2 (`templates/*.html` heredan de `templates/base.html`), Bootstrap 5.3.3, Chart.js, PWA (manifest + SW), vanilla JS.
- CSP estricta con nonces; scripts externos solo los ya permitidos por la CSP actual (revisar `app/__init__.py` o donde se arme el header antes de agregar CDNs).
- Iconos: Phosphor (ya cargado). Fuentes: Inter + Archivo (Google Fonts, ya cargadas).
- Cámara permitida en Permissions-Policy (escáner QR).
- GOTCHA conocido: animaciones con `transform` en el keyframe `to` sobre `<main>` crean stacking context y bloquean modales. Mantener keyframes `to` solo con `opacity`.
- Modales de páginas hijas van en `{% block modals %}` (fuera de `<main>`).
- Archivos Python con `encoding='utf-8'`; commits seguidos de `git push origin main`.

## 4. Lenguaje visual (decidido por el usuario)

**Tema oscuro = "Fusion refinada"** · **Tema claro = "Pergamino + terracota"**. Se conserva el toggle de tema actual (`data-theme` en `<html>`, localStorage `erp_theme`, aplicado antes del primer paint).

Referencia visual aprobada: maquetas B (oscuro) y C (claro) en `.superpowers/brainstorm/*/content/direccion-visual.html`.

### 4.1 Tokens

| Token | Oscuro | Claro |
|---|---|---|
| `--bg` | `#15161c` (sólido, sin gradiente radial) | `#f6f2ea` |
| `--card` | `#1c1e26` | `#fdfaf4` |
| `--card-2` (inputs, fondos secundarios) | `#20232c` | `#f7f1e6` |
| `--text` | `#ececef` | `#201e1d` |
| `--muted` | `#8e909d` | `#6d675e` |
| `--faint` | `#6a6e82` | `#98917f` |
| `--border` (línea fina) | `rgba(236,236,239,.08)` | `#e2dccf` |
| `--border-strong` (regla bajo títulos) | `rgba(236,236,239,.14)` | `#201e1d` |
| `--accent` | `#9184d9` | `#c67139` |
| `--accent-deep` | `#b3a9e6` | `#8f4e22` |
| `--accent-tint` | `rgba(145,132,217,.14)` | `rgba(198,113,57,.12)` |
| `--on-accent` (texto sobre acento) | `#15161c` | `#ffffff` |
| `--sage` / tint (OK, dinero) | `#a3b285` / `.13` | `#5f7044` / `#e8ecdc` |
| `--warn` / tint (bajo) | `#d9a95b` / `.13` | `#94661f` / `#f3e7cf` |
| `--danger` / tint (agotado, error) | `#e0716d` / `.13` | `#b0473b` / `#f4ddd8` |
| `--info` / tint | `#7fb3d9` / `.13` | `#4a7fa5` / `.11` |
| `--glow` | `none` | `none` |

`theme-color` (meta + manifest) y `background_color` del manifest se alinean a `--bg` de cada tema (meta `theme-color` con `media="(prefers-color-scheme: …)"` y actualizada por JS al cambiar el toggle).

### 4.2 Reglas tomadas de DESIGN.md
- **Un solo acento por tema.** Verde/ámbar/rojo/azul solo para estados con significado (stock, montos, errores, avisos), en tonos apagados; nunca decorativos. Los iconos de menú y KPIs dejan de usar colores variados: van en `--muted` o `--accent`.
- **Pesos contenidos.** Archivo 600–700 para títulos, kickers y cifras KPI (sin 800). Inter 400–500 en cuerpo; 600 solo en botones y etiquetas cortas.
- **Superficies planas.** Sin `box-shadow` en tarjetas en reposo; separación por color + borde 1px. Sombra suave solo en elementos flotantes (dropdowns, modales, toasts, FAB) y en hover de tarjetas en escritorio (`@media (hover:hover)`).
- **Sin brillos ni gradientes** decorativos: se elimina `--glow`, el gradiente radial del fondo, el gradiente del logo y del avatar (pasan a color sólido acento/tinta).
- **Reglas editoriales**: regla de 2px (`--border-strong`) bajo el encabezado de página; kicker uppercase (0.62–0.68rem, tracking .13–.16em) sobre el título.
- **Animación sobria**: se mantienen fadeUp escalonado y contadores de KPIs; se eliminan el punto pulsante de la campana, el rebote de dropdowns (`cubic-bezier(.34,1.2,…)`) y el `translateX` en hover del sidebar. `prefers-reduced-motion` respetado.
- **Un solo set de iconos**: Phosphor en todo; se retiran los Bootstrap Icons de las plantillas y se elimina su `<link>` cuando ya no queden usos.

### 4.3 Forma y tipografía
- Radios: tarjetas 14px, inputs 10px, botones y chips pill (999px), miniaturas 10px.
- Texto base 14px en escritorio; **todos los campos de formulario a 16px en móvil** (ver 5.3).
- Números en `font-variant-numeric: tabular-nums`.
- Ancho de contenido en escritorio: se mantiene `max-width: 1440px` (no el 900px de DESIGN.md: las tablas de inventario lo necesitan).

## 5. Experiencia móvil (decidida con el usuario; detalles marcados como decisión del diseñador)

Aplica a < 900px (punto de quiebre actual de Fusion) en navegador y PWA.

### 5.1 Marco fijo, sin desplazamiento lateral
- `html, body { overflow-x: clip; }` y `overscroll-behavior: none` en `html` (sin rebote que muestre el fondo; sin "pull to refresh" accidental en la PWA).
- `body` y sidebar con `100dvh` en lugar de `100vh`.
- Todo hijo flex/grid del marco con `min-width: 0`.
- Lo que no quepa (tablas anchas) hace scroll **dentro de su contenedor** (`.table-responsive` con `overscroll-behavior-x: contain`), nunca la página.

### 5.2 Barra superior compacta (causa principal hoy)
En móvil la barra solo contiene: **hamburguesa · buscador (se encoge, `min-width:0`) · campana · avatar/menú**. Todo lo demás se mueve al menú del avatar: cambio de tema, notificaciones push (+ prueba), cerrar sesión, cuenta y opciones admin. El indicador de pendientes offline se muestra como punto sobre el avatar o como banner, no como botón extra. En escritorio se mantiene la barra completa. (Decisión del diseñador.)

### 5.3 Zoom
- `<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content">`.
- Campos (`input`, `select`, `textarea`, `.form-control`, `.form-select`, `.input`) a `font-size: 16px` en `@media (max-width: 899.98px)` → elimina el zoom automático de iOS.
- Pellizco bloqueado en la interfaz con `touch-action: pan-x pan-y` en `html` (en iOS Safari `user-scalable=no` se ignora, por eso también se usa `touch-action`; y `maximum-scale=1` en el viewport para Android). (Decisión del diseñador.)
- **Imágenes sí ampliables:** las fotos de producto (y las de incidencias/avances) abren un **visor a pantalla completa** con pellizco/doble-tap para zoom y arrastre, y botón cerrar respetando safe-area. Componente reusable en vanilla JS (`static/js/`), activado por atributo (p.ej. `data-zoomable`) para no meter handlers inline.

### 5.4 Bordes seguros
`env(safe-area-inset-*)` aplicado a: barra superior (padding-top), navegación inferior y barras sticky (padding-bottom), FAB, toasts, banner offline, banner de instalación PWA, sidebar off-canvas y modales a pantalla completa.

### 5.5 Navegación inferior tipo app (decidido por el usuario)
Barra fija abajo en móvil con 5 destinos: **Panel** (`main.dashboard`) · **Almacenes** (`inventory.lista_almacenes`) · **Nueva salida** (`inventory.registrar_salida`) · **Órdenes** (`purchasing.lista_ordenes`) · **Más** (abre el sidebar off-canvas actual). Ítem activo = pastilla `--accent-tint` + color acento. Se oculta en escritorio. Respeta permisos: si el usuario no tiene permiso para un destino, se sustituye o se omite (el builder decide la regla concreta, siguiendo los mismos checks del sidebar). El FAB actual se reubica sobre la barra o se integra (decisión del builder, sin tapar contenido).

### 5.6 Tablas → tarjetas en móvil
En móvil las tablas de listado principales se presentan como **lista de tarjetas** (miniatura · nombre · código/cantidad · tag de estado) que solo hacen scroll vertical — esto resuelve el caso del Dashboard. Implementación preferida: **reflujo por CSS de las mismas filas `<tr>`** (p.ej. `tr` como grid en `< 640px`) para no duplicar markup y no romper el JS existente de filtrado/orden (`tr.fila-producto` en `dashboard.html`).

**Qué tablas (decisión del diseñador):** las de páginas cuyo contenido principal es un listado: `dashboard` (inventario), `index` (alertas), `almacen_inventario`, `ordenes` (ya pasa a grid de tarjetas por el paquete), `salidas`, `gastos`, `facturas_lista`, `servicios_lista`, `presupuestos_lista`, `centros_costo_lista`, `proyecto_oc_lista`, `proveedores`, `categorias`, `almacenes`, `usuarios`, `productos_sin_almacen`, `aprobaciones_inbox`, `actividad`, `incidencias/lista`. Las tablas de **detalle** (artículos de una OC, líneas de recepción, historial de un producto, configuraciones) se quedan como tabla con scroll interno contenido.

### 5.7 Teclado, modales y dropdowns
- `interactive-widget=resizes-content` + campo enfocado con `scrollIntoView({block:'center'})` cuando el teclado lo tape (solo si hace falta tras probar).
- Modales en móvil: `modal-fullscreen-sm-down` o ancho `min(…, 100vw - 2rem)`; nada de anchos fijos en px.
- Dropdowns (campana 310–340px, menús 220px): ancho máximo `calc(100vw - 2rem)` y anclados dentro de la pantalla.
- Barras sticky (resumen de Salida) quedan encima del teclado o se ocultan mientras está abierto (decisión del builder tras probar).

### 5.8 Pantallas con anchos fijos
Revisar y corregir anchos en línea ≥300px (`width:`/`min-width:` sin `max-width`) en: `actividad.html`, `almacenes.html`, `excel_config.html` (incluye tabla sin `.table-responsive`), `etiqueta_personalizar.html`, `orden_form.html`, `plantilla_config.html`, `login.html`, errores 403/404/500, `offline.html`, y cualquier otro que aparezca al probar a 320px.

## 6. Arquitectura CSS

Hoy hay **cuatro capas** que compiten: `fusion.css` (tokens + componentes), `compat.css` (puente de tokens legacy → fusion), `design-system.css` ("Precision Operations", indigo, sidebar oscuro propio) y ~600 líneas de `<style>` inline en `base.html`.

Objetivo:
- `fusion.css` = **única fuente de tokens** (sección 4.1) y componentes nuevos.
- `compat.css` = puente para clases Bootstrap/legacy usadas en plantillas (`.btn-primary`, `.card`, `.badge-*`, `.form-control`…) mapeadas a tokens Fusion. Absorbe las reglas útiles del `<style>` de `base.html`.
- `design-system.css`: eliminar sus tokens/colores propios (indigo, `--status-*` hex fijos, `--sidebar-*`). Lo que se siga usando se migra a `compat.css`; el archivo se borra si queda vacío.
- `<style>` inline de `base.html`: se mueve a archivo estático (además ayuda a la CSP).
- Nuevo `static/css/mobile.css` (o sección dedicada en fusion.css, decisión del builder) con todo lo de la sección 5.

## 7. Alcance por pantallas y entrega

**Entrega (decidido por el usuario): directo a `main` por fases**, como el resto del proyecto (`git push origin main` tras cada commit; el servidor despliega desde main). Para no caer en la anti-meta de "look a medias", la **Fase 1 cambia tokens y marco de forma global**, de modo que todas las pantallas adoptan el look nuevo a la vez; las fases siguientes reestructuran pantallas, no colores. Cada fase debe dejar la app completamente funcional y sin regresiones móviles. El usuario valida en su teléfono tras cada fase.

**Estructura en todos los tamaños (decidido por el usuario):** las reestructuras del paquete (Órdenes como grid de tarjetas, Producto Form como wizard de 3 pasos, Salida tipo carrito, etc.) aplican en escritorio y móvil. **Ningún campo ni acción actual se pierde**: los que el prototipo no muestra (HD SKU, imagen IA, proveedor, unidades por caja, etc.) se acomodan en el paso/sección que les corresponda.

Fases:

1. **Marco común** (`base.html`): viewport, safe-area, barra superior compacta, navegación inferior, sidebar off-canvas con `dvh`, toasts/FAB/banners, theme-color, consolidación CSS. Corrige todas las pantallas de una vez.
2. **Dashboard** (`dashboard.html`) — primera pantalla de validación: KPIs, salud del almacén, gráficas, tabla → tarjetas en móvil.
3. **Las otras 10 del paquete**: Login (sin sidebar), Producto Form (wizard 3 pasos), Salida (carrito + barra sticky), Ajuste, Órdenes, Orden Detalle, Gastos, Finanzas, Reportes, Usuarios.
4. **Resto de plantillas** (~50): heredan marco y tokens; pasada de pulido para quitar colores hardcodeados (hex indigo/slate, `bg-*` de Bootstrap con colores fuera de sistema), Bootstrap Icons → Phosphor, anchos fijos, tablas sin contenedor.

Gráficas Chart.js: leer colores de los tokens con `getComputedStyle` y redibujar al cambiar tema (ya descrito en el README del paquete).

## 8. Verificación

- Probar cada pantalla en 320, 375, 390 y 430px de ancho y en escritorio (1280+), en ambos temas.
- Criterio duro: `document.documentElement.scrollWidth <= window.innerWidth` en todas las pantallas a 320px.
- El builder verifica con emulación de dispositivo en escritorio antes de cada commit; **el usuario prueba en teléfonos reales contra el servidor de producción** tras cada fase. La app Android empaquetada (`twa/`) **no está publicada**, así que el manifest (`theme_color`, `background_color`, `display_override`) se puede cambiar libremente.
- Probar en iPhone real (Safari + PWA instalada) y Android (Chrome + PWA): sin arrastre lateral, sin zoom al enfocar, notch/barra de gestos respetados, teclado no saca de la vista, zoom funcionando en el visor de imágenes.
- Regresión funcional: filtros/orden del Dashboard, escáner QR, salida/ajuste/recepción, modales, chatbot, push, cola offline.
- CSP: consola sin violaciones.
- Revisión final con `/ponytail-review` y code-review (Opus).

## 9. Lo que queda a criterio del builder
- Orden exacto de commits/fases dentro del alcance de la sección 7 (con Marco + Dashboard primero).
- Si la capa móvil va en archivo propio o dentro de fusion.css.
- Regla concreta de permisos en la navegación inferior y ubicación final del FAB.
- Comportamiento de barras sticky con teclado abierto.
- Librería o implementación propia del visor de imágenes (vanilla, compatible con CSP; si es librería, desde CDN permitido y con versión fija).
