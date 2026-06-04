# ERP Gestión de Inventario — Blueprint de Reestructura y Rediseño

> Generado por The Architect · 2026-05-27
> Archetype: Internal Tool / ERP Operations Dashboard
> Stack: Flask (existente, sin migración) + PostgreSQL + Bootstrap 5.3.3 + DM Sans
> Modo: REESTRUCTURA incremental — cero cambios de esquema BD, cero cambios de URL

---

## 1. Visión del Proyecto

### Estado Actual
Sistema ERP interno de inventario construido en Flask monolítico (~4,000+ líneas en `app.py`). El sistema controla inventario, órdenes de compra (estándar y de proyectos), gastos, facturas, servicios, presupuestos, centros de costo y proveedores. Tiene multi-tenancy, roles granulares, PWA offline, integración HD Pro Quick Order y OCR de recibos.

### El Problema
Un único archivo `app.py` mezcla modelos, rutas, lógica de negocio, configuración y comandos CLI. Un error en finanzas puede romper el módulo de inventario. Imposible trabajar en dos módulos en paralelo. La navegación actual (top navbar) se satura con 8+ módulos.

### Objetivos de la Reestructura
1. **Modularidad**: Flask Blueprints — un blueprint por dominio de negocio
2. **Resiliencia**: Un bug en un módulo no colapsa los demás
3. **Claridad visual**: Sidebar de navegación + sistema de estado unificado
4. **Intuitividad**: Barra de comando global, acciones inline, feedback inmediato
5. **Mantenibilidad**: Capa de servicios separada de las rutas, tests por módulo

### Éxito medible
- Cualquier ruta es editable sin abrir `app.py`
- Un nuevo colaborador entiende dónde vive cada feature en < 5 minutos
- El sistema de estado (colores) funciona sin leer el texto del badge
- El sidebar muestra conteos de items pendientes en tiempo real

---

## 2. Tech Stack

| Capa | Tecnología | Razón |
|------|-----------|-------|
| Framework | Flask (existente) | No migrar — mantener continuidad operacional |
| Modularización | Flask Blueprints | Patrón oficial Flask para separar dominios |
| ORM | SQLAlchemy (existente) | Sin cambios |
| BD | PostgreSQL (existente) | Sin cambios |
| Auth | Flask-Login (existente) | Sin cambios |
| Frontend | Bootstrap 5.3.3 + Jinja2 (existente) | Sin cambios — redesign via CSS variables |
| Tipografía | DM Sans (existente) | Conservar, añadir `font-variant-numeric: tabular-nums` |
| Iconos | Bootstrap Icons 1.11.3 (existente) | Sin cambios |
| Charts | Chart.js (existente) | Sin cambios |
| PDF | ReportLab (existente) | Sin cambios |
| Excel | openpyxl (existente) | Sin cambios |
| Background tasks | Python `threading.Thread` (existente) | Sin cambios (Celery si se necesita escalar) |
| PWA | Service Worker + IndexedDB (existente) | Sin cambios |
| Integración HD | `integrations/` (existente) | Sin cambios |

**Lo que NO cambia:** URLs, templates HTML, static files, esquema de BD, servidor Gunicorn, variables de entorno.

---

## 3. Nueva Estructura de Directorios

```
Gestiondeinventario/
│
├── app/                          ← NUEVO — paquete principal
│   ├── __init__.py               ← create_app() factory
│   ├── config.py                 ← Config classes: Dev / Prod / Test
│   ├── extensions.py             ← db, login_manager, csrf, limiter, mail, csrf
│   ├── helpers.py                ← now_mx(), get_item_or_404(), _flash_err(),
│   │                                check_org_permission, admin_required,
│   │                                check_permission, CATEGORIAS_GASTO
│   │
│   ├── models/                   ← modelos separados por dominio (sin tocar BD)
│   │   ├── __init__.py           ← exporta todos los modelos
│   │   ├── auth.py               ← User, Organizacion, TokenUsado
│   │   ├── inventory.py          ← Producto, Almacen, Stock, Movimiento,
│   │   │                            Salida, SalidaItem, Categoria, Etiqueta
│   │   ├── purchasing.py         ← OrdenCompra, OrdenCompraDetalle, Proveedor,
│   │   │                            ProveedorIntegracion, HDSesion,
│   │   │                            ProyectoOC, ProyectoOCDetalle
│   │   ├── finance.py            ← Gasto, PagoServicio, FacturaProveedor,
│   │   │                            Servicio, CentroCosto, Presupuesto
│   │   └── system.py             ← AuditLog, SolicitudAprobacion,
│   │                                PushSubscription, Actividad
│   │
│   ├── blueprints/               ← un sub-paquete por dominio
│   │   ├── auth/
│   │   │   ├── __init__.py
│   │   │   └── routes.py         ← login, register, logout, forgot_password,
│   │   │                            reset_password, account, change_password
│   │   ├── inventory/
│   │   │   ├── __init__.py
│   │   │   └── routes.py         ← productos, almacenes, stock, movimientos,
│   │   │                            salidas, transferencias, kardex, etiquetas
│   │   ├── purchasing/
│   │   │   ├── __init__.py
│   │   │   └── routes.py         ← ordenes_compra, proyecto_oc,
│   │   │                            proveedores, aprobaciones, HD Pro
│   │   ├── finance/
│   │   │   ├── __init__.py
│   │   │   └── routes.py         ← gastos, facturas, servicios, pagos,
│   │   │                            presupuestos, centros_costo
│   │   ├── admin/
│   │   │   ├── __init__.py
│   │   │   └── routes.py         ← admin_panel, usuarios, organizaciones,
│   │   │                            permisos, super_admin
│   │   ├── reports/
│   │   │   ├── __init__.py
│   │   │   └── routes.py         ← Excel, PDF, reportes, valorización
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── routes.py         ← todos los /api/* (JSON endpoints):
│   │   │                            stock alerts, push, sync, ai, ocr,
│   │   │                            finanzas chart, hd upload status
│   │   └── main/
│   │       ├── __init__.py
│   │       └── routes.py         ← dashboard (index), seleccionar_almacen,
│   │                                búsqueda global (/api/buscar)
│   │
│   ├── services/                 ← NUEVO — lógica de negocio fuera de rutas
│   │   ├── __init__.py
│   │   ├── inventory.py          ← stock_movement(), check_stock_alert(),
│   │   │                            kardex_query(), assign_product()
│   │   ├── purchasing.py         ← oc_lifecycle(), approve_oc(),
│   │   │                            generate_hd_csv()
│   │   ├── finance.py            ← record_expense(), budget_semaphore(),
│   │   │                            update_payment_status()
│   │   └── notifications.py      ← push_notification(), whatsapp_alert()
│   │
│   └── cli/
│       ├── __init__.py
│       └── commands.py           ← todos los flask CLI commands agrupados
│
├── integrations/                 ← sin cambios (ya bien estructurado)
│   ├── hd_quickorder.py
│   ├── hd_session.py
│   └── homedepot.py
│
├── templates/                    ← sin cambios estructurales
│   ├── base.html                 ← REDISEÑADO: sidebar + nuevos CSS tokens
│   └── (todos los demás sin tocar)
│
├── static/                       ← sin cambios en archivos existentes
│   └── css/
│       └── design-system.css     ← NUEVO: variables CSS centralizadas
│
├── tests/                        ← NUEVO
│   ├── conftest.py               ← fixtures: app, db, client, usuarios de prueba
│   ├── test_inventory.py         ← stock movements, alerts
│   ├── test_finance.py           ← budget semaphore, expense recording
│   ├── test_purchasing.py        ← OC lifecycle, approvals
│   └── test_auth.py              ← login, tokens, rate limiting
│
├── docs/superpowers/specs/       ← ya existe
│   └── erp-reestructura-blueprint.md  ← este archivo (copia)
│
├── .env                          ← sin cambios
├── requirements.txt              ← agregar: pytest, pytest-flask
├── run.py                        ← NUEVO: python run.py (dev)
├── wsgi.py                       ← NUEVO: gunicorn wsgi:app (prod)
└── CLAUDE.md                     ← actualizar al final
```

---

## 4. Modelo de Datos

**Sin cambios de esquema.** La reorganización es puramente en Python — los modelos se mueven a archivos separados pero las tablas en PostgreSQL quedan idénticas.

### Mapa de modelos por archivo

| Archivo | Modelos |
|---------|---------|
| `models/auth.py` | `User`, `Organizacion`, `TokenUsado` |
| `models/inventory.py` | `Producto`, `Almacen`, `Stock`, `Movimiento`, `Salida`, `SalidaItem`, `Categoria` |
| `models/purchasing.py` | `OrdenCompra`, `OrdenCompraDetalle`, `Proveedor`, `ProveedorIntegracion`, `HDSesion`, `ProyectoOC`, `ProyectoOCDetalle` |
| `models/finance.py` | `Gasto`, `PagoServicio`, `FacturaProveedor`, `Servicio`, `CentroCosto`, `Presupuesto` |
| `models/system.py` | `AuditLog`, `SolicitudAprobacion`, `PushSubscription`, `Actividad` |

### `models/__init__.py` — exportación centralizada
```python
from .auth import User, Organizacion, TokenUsado
from .inventory import Producto, Almacen, Stock, Movimiento, Salida, SalidaItem, Categoria
from .purchasing import (OrdenCompra, OrdenCompraDetalle, Proveedor,
                         ProveedorIntegracion, HDSesion, ProyectoOC, ProyectoOCDetalle)
from .finance import Gasto, PagoServicio, FacturaProveedor, Servicio, CentroCosto, Presupuesto
from .system import AuditLog, SolicitudAprobacion, PushSubscription, Actividad
```

---

## 5. Application Factory Pattern

### `app/__init__.py`
```python
from flask import Flask
from .config import config
from .extensions import db, login_manager, csrf, limiter, mail

def create_app(config_name=None):
    if config_name is None:
        import os
        config_name = os.environ.get('FLASK_ENV', 'production')

    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.config.from_object(config[config_name])

    # Extensiones
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    mail.init_app(app)

    # Blueprints
    from .blueprints.main import main_bp
    from .blueprints.auth import auth_bp
    from .blueprints.inventory import inventory_bp
    from .blueprints.purchasing import purchasing_bp
    from .blueprints.finance import finance_bp
    from .blueprints.admin import admin_bp
    from .blueprints.reports import reports_bp
    from .blueprints.api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(purchasing_bp)
    app.register_blueprint(finance_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(api_bp)

    # CLI commands
    from .cli.commands import register_commands
    register_commands(app)

    # JSON provider (Decimal → float)
    from flask.json.provider import DefaultJSONProvider
    from decimal import Decimal
    class _JSONProvider(DefaultJSONProvider):
        def default(self, o):
            if isinstance(o, Decimal):
                return float(o)
            return super().default(o)
    app.json_provider_class = _JSONProvider
    app.json = _JSONProvider(app)

    # Jinja2 filters
    import json as _json
    app.jinja_env.filters['fromjson'] = _json.loads

    return app
```

### `run.py`
```python
from app import create_app
app = create_app('development')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
```

### `wsgi.py`
```python
from app import create_app
app = create_app('production')
# gunicorn wsgi:app — sin cambios en el servidor
```

---

## 6. Diseño Visual — "Precision Operations"

> Dirección estética: **Industrial Minimal con acento naranja**
> DFII Score: **14/15** — Ejecutar completamente

### 6.1 Sistema de Colores (CSS Variables)

```css
/* static/css/design-system.css */

:root {
  /* === SIDEBAR / CHROME === */
  --sidebar-bg:          #0F172A;
  --sidebar-width:       248px;
  --sidebar-accent:      #F97316;
  --sidebar-text:        #94A3B8;
  --sidebar-text-active: #F8FAFC;
  --sidebar-item-active: rgba(249,115,22,.15);
  --sidebar-border:      rgba(255,255,255,.06);

  /* === CONTENIDO === */
  --bg-page:    #F1F5F9;
  --bg-card:    #FFFFFF;
  --bg-raised:  #FFFFFF;
  --border:     #E2E8F0;
  --border-focus: #F97316;

  /* === TIPOGRAFÍA === */
  --text-body:  #1E293B;
  --text-muted: #64748B;
  --text-xs:    0.75rem;
  --text-sm:    0.875rem;
  --text-base:  1rem;
  --text-lg:    1.125rem;
  --text-xl:    1.25rem;

  /* === ESTADO UNIFICADO === */
  --status-ok:        #10B981;
  --status-ok-bg:     rgba(16,185,129,.12);
  --status-warn:      #F59E0B;
  --status-warn-bg:   rgba(245,158,11,.12);
  --status-danger:    #EF4444;
  --status-danger-bg: rgba(239,68,68,.12);
  --status-info:      #0EA5E9;
  --status-info-bg:   rgba(14,165,233,.12);
  --status-neutral:   #94A3B8;
  --status-neutral-bg:rgba(148,163,184,.12);

  /* === ACCIÓN === */
  --primary:       #F97316;
  --primary-hover: #EA6C0A;
  --primary-tonal: rgba(249,115,22,.10);
  --primary-text:  #FFFFFF;

  /* === TOKENS HEREDADOS (mantener para compatibilidad templates) === */
  --surface:       var(--bg-card);
  --surface-raised:var(--bg-raised);
  --hover-bg:      #F1F5F9;
}

/* Dark mode — conservar soporte existente */
[data-bs-theme="dark"] {
  --bg-page:    #0F172A;
  --bg-card:    #1E293B;
  --border:     rgba(255,255,255,.08);
  --text-body:  #F1F5F9;
  --text-muted: #94A3B8;
  --hover-bg:   rgba(255,255,255,.05);
  --sidebar-bg: #020617;
}
```

### 6.2 Sistema de Estado Universal

```css
/* Badge de estado — mismo sistema en todos los módulos */
.status-pill {
  display: inline-flex; align-items: center; gap: .35rem;
  padding: .2rem .65rem; border-radius: 999px;
  font-size: .72rem; font-weight: 700; letter-spacing: .3px;
}
.status-pill::before {
  content: ''; width: 6px; height: 6px;
  border-radius: 50%; flex-shrink: 0;
}
/* Variantes */
.status-ok      { background: var(--status-ok-bg);      color: var(--status-ok); }
.status-ok::before      { background: var(--status-ok); }
.status-warn    { background: var(--status-warn-bg);    color: var(--status-warn); }
.status-warn::before    { background: var(--status-warn); }
.status-danger  { background: var(--status-danger-bg);  color: var(--status-danger); }
.status-danger::before  { background: var(--status-danger); }
.status-info    { background: var(--status-info-bg);    color: var(--status-info); }
.status-info::before    { background: var(--status-info); }
.status-neutral { background: var(--status-neutral-bg); color: var(--status-neutral); }
.status-neutral::before { background: var(--status-neutral); }
```

**Mapa de estados a clases:**

| Estado | Clase | Aplica en |
|--------|-------|-----------|
| Recibida / Pagado / Stock OK | `.status-ok` | OC, Facturas, Stock |
| Aprobada / En proceso / Borrador | `.status-info` | OC, ProyectoOC |
| Pendiente / Stock bajo / 75%+ presupuesto | `.status-warn` | OC, Stock, Presupuesto |
| Vencida / Sin stock / Presupuesto agotado | `.status-danger` | Facturas, Stock, Presupuesto |
| Cancelado / Inactivo | `.status-neutral` | Cualquier entidad |

### 6.3 Nueva Navegación — Sidebar

El cambio más impactante del rediseño. El `base.html` se refactoriza para incluir:

```html
<!-- Estructura de layout principal -->
<div class="erp-shell">

  <!-- SIDEBAR -->
  <aside class="erp-sidebar" id="erpSidebar">
    <div class="sidebar-brand">
      <span class="brand-icon"><i class="bi bi-boxes"></i></span>
      <span class="brand-name">{{ current_user.organizacion.nombre }}</span>
      <button class="sidebar-toggle" id="sidebarToggle" aria-label="Colapsar menú">
        <i class="bi bi-chevron-left"></i>
      </button>
    </div>

    <nav class="sidebar-nav" role="navigation" aria-label="Navegación principal">
      <!-- Dashboard -->
      <a href="{{ url_for('main.dashboard') }}"
         class="nav-item {% if request.endpoint == 'main.dashboard' %}active{% endif %}">
        <i class="bi bi-grid-fill nav-icon"></i>
        <span class="nav-label">Dashboard</span>
      </a>

      <!-- Inventario -->
      <div class="nav-group">
        <div class="nav-group-label">Inventario</div>
        <a href="{{ url_for('inventory.lista_productos') }}" class="nav-item ...">
          <i class="bi bi-box-seam nav-icon"></i>
          <span class="nav-label">Productos</span>
        </a>
        <a href="{{ url_for('inventory.lista_almacenes') }}" class="nav-item ...">
          <i class="bi bi-building nav-icon"></i>
          <span class="nav-label">Almacenes</span>
        </a>
        <a href="{{ url_for('inventory.historial_salidas') }}" class="nav-item ...">
          <i class="bi bi-arrow-up-right-circle nav-icon"></i>
          <span class="nav-label">Salidas</span>
        </a>
      </div>

      <!-- Compras -->
      <div class="nav-group">
        <div class="nav-group-label">Compras</div>
        <a href="{{ url_for('purchasing.lista_ordenes') }}" class="nav-item ...">
          <i class="bi bi-file-earmark-text nav-icon"></i>
          <span class="nav-label">Órdenes de Compra</span>
          {% if nav_badges.oc_pendientes %}
          <span class="nav-badge">{{ nav_badges.oc_pendientes }}</span>
          {% endif %}
        </a>
        <a href="{{ url_for('purchasing.lista_proyectos_oc') }}" class="nav-item ...">
          <i class="bi bi-briefcase nav-icon"></i>
          <span class="nav-label">OC Proyectos</span>
        </a>
        <a href="{{ url_for('purchasing.lista_proveedores') }}" class="nav-item ...">
          <i class="bi bi-truck nav-icon"></i>
          <span class="nav-label">Proveedores</span>
        </a>
      </div>

      <!-- Finanzas -->
      <div class="nav-group">
        <div class="nav-group-label">Finanzas</div>
        <!-- gastos, facturas, servicios, presupuestos, centros de costo -->
      </div>

      <!-- Reportes -->
      <a href="{{ url_for('reports.reportes') }}" class="nav-item ...">
        <i class="bi bi-bar-chart-fill nav-icon"></i>
        <span class="nav-label">Reportes</span>
      </a>

      <!-- Configuración (solo admin) -->
      {% if current_user.rol in ['admin', 'super_admin'] %}
      <a href="{{ url_for('admin.admin_panel') }}" class="nav-item ...">
        <i class="bi bi-gear-fill nav-icon"></i>
        <span class="nav-label">Configuración</span>
      </a>
      {% endif %}
    </nav>

    <!-- Footer del sidebar -->
    <div class="sidebar-footer">
      <a href="{{ url_for('auth.account') }}" class="nav-item">
        <span class="avatar-circle">{{ current_user.username[0]|upper }}</span>
        <span class="nav-label">{{ current_user.username }}</span>
      </a>
    </div>
  </aside>

  <!-- CONTENIDO PRINCIPAL -->
  <main class="erp-content" id="main-content">
    <!-- Command bar -->
    <div class="command-bar">
      <button class="cmd-trigger" id="cmdTrigger" aria-label="Búsqueda global (Ctrl+K)">
        <i class="bi bi-search"></i>
        <span>Buscar...</span>
        <kbd>Ctrl K</kbd>
      </button>
      <div class="topbar-actions">
        <!-- notificaciones, dark mode toggle -->
      </div>
    </div>

    <!-- Contenido de la página -->
    <div class="page-container">
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% for category, message in messages %}
        <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
          {{ message }}
          <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
        {% endfor %}
      {% endwith %}

      {% block content %}{% endblock %}
    </div>
  </main>
</div>

<!-- Command Palette Modal -->
<div class="cmd-palette" id="cmdPalette" role="dialog" aria-label="Búsqueda global" hidden>
  <div class="cmd-backdrop" id="cmdBackdrop"></div>
  <div class="cmd-modal">
    <div class="cmd-search-row">
      <i class="bi bi-search cmd-search-icon"></i>
      <input type="text" id="cmdInput" placeholder="Buscar producto, OC, gasto, proveedor..."
             autocomplete="off" aria-autocomplete="list">
    </div>
    <div class="cmd-results" id="cmdResults" role="listbox">
      <!-- Resultados via AJAX a /api/buscar?q= -->
    </div>
    <div class="cmd-footer">
      <span><kbd>↑↓</kbd> navegar</span>
      <span><kbd>↵</kbd> abrir</span>
      <span><kbd>Esc</kbd> cerrar</span>
    </div>
  </div>
</div>
```

### 6.4 Barra de Comando Global — `/api/buscar`

Nuevo endpoint JSON que busca en paralelo en todas las entidades:

```python
# blueprints/api/routes.py
@api_bp.get('/api/buscar')
@login_required
def buscar_global():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    org_id = current_user.organizacion_id
    like = f'%{q}%'
    results = []

    # Productos
    for p in Producto.query.filter_by(organizacion_id=org_id)\
             .filter(Producto.nombre.ilike(like)).limit(4):
        results.append({'tipo': 'Producto', 'icon': 'bi-box-seam',
                        'label': p.nombre, 'sub': p.codigo,
                        'url': url_for('inventory.historial_producto', id=p.id)})
    # Órdenes de Compra
    for o in OrdenCompra.query.filter_by(organizacion_id=org_id)\
             .filter(OrdenCompra.id.in_(...))\
             .limit(3):
        results.append({'tipo': 'OC', 'icon': 'bi-file-earmark-text',
                        'label': f'OC #{o.id} — {o.proveedor.nombre}',
                        'sub': o.estado, 'url': url_for('purchasing.ver_orden', id=o.id)})
    # Proveedores
    for p in Proveedor.query.filter_by(organizacion_id=org_id)\
             .filter(Proveedor.nombre.ilike(like)).limit(3):
        results.append({'tipo': 'Proveedor', 'icon': 'bi-truck',
                        'label': p.nombre, 'sub': p.contacto_email or '',
                        'url': url_for('purchasing.editar_proveedor', id=p.id)})
    # Gastos
    for g in Gasto.query.filter_by(organizacion_id=org_id)\
             .filter(Gasto.descripcion.ilike(like)).limit(3):
        results.append({'tipo': 'Gasto', 'icon': 'bi-receipt',
                        'label': g.descripcion, 'sub': g.categoria,
                        'url': url_for('finance.lista_gastos')})

    return jsonify(results[:12])
```

### 6.5 Nav Badges — Conteos en tiempo real

Un nuevo context processor inyecta los conteos en TODOS los templates:

```python
# app/__init__.py — dentro de create_app()
@app.context_processor
def inject_nav_badges():
    if not current_user.is_authenticated:
        return {'nav_badges': {}}
    org_id = current_user.organizacion_id
    from datetime import date
    return {'nav_badges': {
        'oc_pendientes': OrdenCompra.query.filter_by(
            organizacion_id=org_id, estado='aprobada').count(),
        'servicios_vencidos': PagoServicio.query.join(Servicio)\
            .filter(Servicio.organizacion_id == org_id,
                    PagoServicio.pagado == False,
                    PagoServicio.fecha_vencimiento < date.today()).count(),
        'stock_critico': Stock.query.join(Almacen)\
            .filter(Almacen.organizacion_id == org_id,
                    Stock.cantidad <= Stock.minimo).count(),
    }}
```

---

## 7. Mejoras por Módulo (features, no solo estructura)

### Dashboard
- **KPI cards con tendencia**: mostrar % cambio vs mes anterior (↑ verde / ↓ rojo)
- **Pipeline OC visual**: barra de progreso horizontal con etapas (Borrador → Aprobada → Recibida)
- **Stock crítico quickview**: top 5 productos más urgentes con botón "Crear OC"
- **Semáforo de presupuesto**: tarjeta compacta por centro de costo

### Tablas de datos (todas)
- Columna de estado **siempre a la derecha del nombre** (no al final)
- Hover row: `background: var(--primary-tonal)` + cursor pointer
- Acciones inline al hacer hover (no menú dropdown de 3 puntos cuando hay 1-2 acciones)
- Paginación consistente con el macro `_macros.html` ya existente

### Formularios (todos)
- Validación inline: borde rojo + mensaje debajo del campo al perder foco
- Botón submit: spinner durante el POST, no simple disable
- Confirmaciones destructivas: modal Bootstrap, no `window.confirm()`

### OC Standard
- Badge de días transcurridos desde creación (detecta OCs abandonadas)
- Botón "Exportar HD Pro" visible sin requerir integración activa si hay hd_sku

### OC Proyectos
- Timeline de estado más prominente (ya existe, mejorarlo)
- Badge naranja HD en ítems identificados como HD Pro

### Inventario
- Barra de nivel de stock visual en la tabla (mini progress bar inline)
- Indicador "sin movimiento en 30 días" en productos inactivos

---

## 8. Autenticación y Autorización

Sin cambios funcionales. La reestructura preserva:
- `Flask-Login` con `@login_required`
- `@admin_required` decorator
- `@check_org_permission` decorator
- `@check_permission('perm_*')` decorator
- `TokenUsado` blocklist para reset de contraseña
- Rate limiting con Flask-Limiter
- CSRF con Flask-WTF
- Contraseñas con Werkzeug PBKDF2

Los decorators migran de `app.py` → `app/helpers.py` y se importan en cada blueprint.

### Roles

| Rol | Acceso |
|-----|--------|
| `super_admin` | Todo, todas las organizaciones |
| `admin` | Todo dentro de su organización |
| `user` | Solo lo que sus `perm_*` permiten |

---

## 9. Orden de Migración (El más crítico)

**Regla de oro**: Cada paso termina con el sistema corriendo. Nunca avanzar al siguiente si el actual falla. Usar `superpowers:dispatching-parallel-agents` para los pasos 7-12 (independientes entre sí).

---

### FASE 0 — Preparación (sin tocar app.py)
**Paso 1: Crear estructura de directorios vacíos**
```bash
mkdir -p app/models app/blueprints/{auth,inventory,purchasing,finance,admin,reports,api,main}
mkdir -p app/services app/cli tests static/css
touch app/__init__.py app/config.py app/extensions.py app/helpers.py
touch app/models/__init__.py app/models/{auth,inventory,purchasing,finance,system}.py
touch app/services/__init__.py app/services/{inventory,purchasing,finance,notifications}.py
touch app/cli/__init__.py app/cli/commands.py
touch run.py wsgi.py
```
Verificación: `python -c "import app"` no lanza error.

---

### FASE 1 — Infraestructura compartida

**Paso 2: `app/extensions.py`**
Extraer `db`, `login_manager`, `csrf`, `limiter`, `mail` de `app.py`.
```python
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)
mail = Mail()
```
Verificación: `from app.extensions import db` sin error.

**Paso 3: `app/config.py`**
Extraer toda la configuración (SECRET_KEY, DATABASE_URI, MAIL_*, etc.).
```python
import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # ... todos los demás config keys

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = False  # True para debug SQL

class ProductionConfig(Config):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': ProductionConfig,
}
```

**Paso 4: `app/helpers.py`**
Extraer: `now_mx()`, `_TZ_MX`, `CATEGORIAS_GASTO`, `MESES_ES`,
`get_item_or_404()`, `_flash_err()`, `check_org_permission`,
`admin_required`, `check_permission`, `_JSONProvider`.
Verificación: `from app.helpers import now_mx, get_item_or_404` sin error.

**Paso 5: `app/models/`**
Extraer todos los modelos, uno por archivo de dominio.
- Cada modelo importa `db` desde `app.extensions`
- `models/__init__.py` exporta todo
- **Cero cambios en `__tablename__`, columnas o relaciones**

Verificación: `from app.models import Producto, OrdenCompra, Gasto` sin error.

---

### FASE 2 — Application Factory

**Paso 6: `app/__init__.py` + `run.py` + `wsgi.py`**
Crear `create_app()` registrando blueprints vacíos (solo `__init__.py` con blueprint object).
El `app.py` original sigue funcionando en paralelo.

```python
# Verificación rápida:
python run.py  # debe arrancar sin error, aunque las rutas no existan aún
```

---

### FASE 3 — Migración de Blueprints (paralelo con agentes)

Cada blueprint se puede migrar de forma independiente. Usar `superpowers:dispatching-parallel-agents` con 4 agentes simultáneos: auth+admin, inventory, finance, purchasing+reports+api.

**Paso 7: Blueprint `auth`** (el más simple)
Migrar: login, logout, register, forgot_password, reset_password, account, change_password.
Verificación: poder loguearse en `http://localhost:5000/login`.

**Paso 8: Blueprint `admin`**
Migrar: admin_panel, nueva_organizacion, asignar_usuario, api_permisos, super_admin, etc.
Verificación: panel admin funcional.

**Paso 9: Blueprint `api`** (todos los endpoints JSON)
Migrar: api_alertas_stock_bajo, api_sync, api_push_*, api_finanzas_mensual, api_chart_*, api_buscar (nuevo), api_hd_*, etc.
Verificación: endpoints responden JSON correcto.

**Paso 10: Blueprint `reports`**
Migrar: exportar_inventario_excel, exportar_movimientos_excel, exportar_valorizacion_pdf, exportar_gastos_excel, reportes.
Verificación: descargas funcionan.

**Paso 11: Blueprint `inventory`**
Migrar: productos, almacenes, stock, movimientos, salidas, transferencias, kardex, etiquetas.
Verificación: registrar una salida end-to-end.

**Paso 12: Blueprint `finance`**
Migrar: gastos, facturas, servicios, pagos, presupuestos, centros_costo.
Verificación: registrar un gasto con centro de costo.

**Paso 13: Blueprint `purchasing`**
Migrar: ordenes_compra, proyecto_oc, proveedores, aprobaciones, HD Pro routes.
Verificación: crear OC, aprobar, exportar CSV para HD Pro.

**Paso 14: Blueprint `main`**
Migrar: dashboard (index), seleccionar_almacen, historial_actividad, manual_usuario.
Verificación: dashboard carga con KPIs correctos.

---

### FASE 4 — Capa de Servicios

**Paso 15: `app/services/`**
Extraer lógica de negocio de las rutas hacia services.
Prioridad: funciones que se llaman desde múltiples rutas o que tienen >30 líneas de lógica.

```python
# services/inventory.py — ejemplo
def apply_stock_movement(producto_id, almacen_id, cantidad, tipo, user_id, org_id):
    """Aplica movimiento de stock con validación y audit log."""
    # lógica extraída de registrar_salida, nueva_transferencia, recibir_orden
    ...
```

---

### FASE 5 — Rediseño UI/UX

**Paso 16: `static/css/design-system.css`**
Crear archivo con todas las CSS variables del sistema "Precision Operations".
Enlazar en `base.html` antes del CSS de Bootstrap.

Consultar `ui-ux-pro-max` para cada componente nuevo antes de implementar.

**Paso 17: Rediseñar `base.html`**
- Reemplazar navbar horizontal → sidebar izquierdo
- Agregar command bar (Ctrl+K)
- Implementar sistema de badges en nav
- Mantener dark mode toggle
- Mantener todos los scripts existentes (Chart.js, Bootstrap, QR scanner, SW)

Usar `frontend-design` para el CSS del sidebar y `ui-ux-pro-max` para validar contraste y accesibilidad.

**Paso 18: Sistema de estado unificado**
Reemplazar badges de estado ad-hoc en templates → clases `.status-ok`, `.status-warn`, etc.
Solo modificar los templates que tienen badges inconsistentes.

**Paso 19: Mejoras de UX por módulo** (prioridad por impacto)
1. Dashboard: KPI cards con tendencia, pipeline OC, semáforo presupuesto
2. Tablas: hover row, acciones inline
3. Formularios: validación inline, spinner en submit
4. OC Standard: badge de días, visibilidad HD Pro mejorada

---

### FASE 6 — Tests y Cleanup

**Paso 20: Tests básicos**
```python
# tests/conftest.py
import pytest
from app import create_app
from app.extensions import db as _db

@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()
```
Tests de humo: login, dashboard, crear producto, registrar gasto.

**Paso 21: Eliminar `app.py` original**
Una vez que todos los blueprints estén activos y los tests pasen:
```bash
git mv app.py archive/app-monolith-original.py  # archivar, no eliminar
git commit -m "refactor: completar migración a Flask Blueprints"
```

---

## 10. Variables de Entorno

Sin cambios — todas las existentes se preservan. Agregar:

| Variable | Descripción | Nuevo |
|----------|-------------|-------|
| `FLASK_ENV` | `development` / `production` | Nuevo (antes era `FLASK_DEBUG`) |
| Las demás | Sin cambios | — |

---

## 11. Dependencias

Agregar a `requirements.txt`:
```
pytest>=8.0
pytest-flask>=1.3
```

Todo lo demás ya está instalado.

---

## 12. Deployment

Sin cambios en el servidor. El único cambio:

```bash
# Antes (en systemd service):
ExecStart=/root/venv/bin/gunicorn --workers 2 --bind 0.0.0.0:8000 app:app

# Después:
ExecStart=/root/venv/bin/gunicorn --workers 2 --bind 0.0.0.0:8000 wsgi:app
```

Nada más cambia. Las URLs, la BD, los archivos static, los templates: todo igual.

---

## 13. Testing Strategy

### Unit Tests (pytest)
- `test_auth.py`: login, reset token single-use, rate limiting
- `test_inventory.py`: stock movement logic, alertas de stock bajo
- `test_finance.py`: semáforo presupuesto, validación de montos
- `test_purchasing.py`: OC lifecycle, CSV HD Pro generation

### Smoke Tests (manual)
Por cada blueprint migrado, verificar el happy path completo antes de continuar.

### E2E (futuro)
No en esta iteración. Agregar Playwright en una fase posterior si se necesita CI/CD completo.

---

## 14. Skills a Usar Durante la Ejecución

| Skill | En qué pasos | Para qué |
|-------|-------------|----------|
| `superpowers:dispatching-parallel-agents` | Pasos 7-14 | Migrar 4 blueprints simultáneos |
| `superpowers:systematic-debugging` | Cualquier paso que falla | Root cause antes de parchear |
| `superpowers:verification-before-completion` | Cada fase | Verificar que el sistema funciona antes de avanzar |
| `superpowers:writing-plans` | Inicio de cada fase | Plan detallado por fase |
| `ui-ux-pro-max` | Pasos 16-19 | Validar cada componente UI antes de implementar |
| `frontend-design` | Paso 17 (base.html) | CSS del sidebar y command bar |
| `claude-md-management:revise-claude-md` | Al final | Actualizar CLAUDE.md con nueva arquitectura |

---

## 15. CLAUDE.md Actualizado (para el proyecto destino)

```markdown
# Gestión de Inventario ERP — Instrucciones del Proyecto

## Stack
Flask Blueprints + SQLAlchemy + PostgreSQL + Bootstrap 5.3.3 + Gunicorn (/root/venv/)
DM Sans + Bootstrap Icons 1.11.3 + Chart.js + PWA + Blueprints architecture

## Comandos
- `python run.py` — servidor de desarrollo
- `flask --app run:app <comando>` — CLI commands
- `pytest` — correr tests
- `gunicorn wsgi:app` — producción

## Arquitectura
Paquete `app/` con Application Factory pattern (`create_app()`).
Modelos en `app/models/` separados por dominio.
Rutas en `app/blueprints/<dominio>/routes.py`.
Lógica de negocio en `app/services/`.
Helpers globales en `app/helpers.py`.
Extensiones Flask en `app/extensions.py`.

## Blueprints registrados
- `main_bp` — dashboard, búsqueda global
- `auth_bp` — login, register, reset
- `inventory_bp` — productos, almacenes, stock, salidas
- `purchasing_bp` — OC standard, OC proyectos, proveedores, HD Pro
- `finance_bp` — gastos, facturas, servicios, presupuestos, centros costo
- `admin_bp` — usuarios, permisos, organizaciones
- `reports_bp` — Excel, PDF, reportes
- `api_bp` — todos los /api/* JSON endpoints

## Reglas No Negociables
1. NUNCA modificar `__tablename__` ni columnas — la BD no cambia
2. NUNCA cambiar URLs existentes — cero redirects nuevos
3. `get_item_or_404(Model, id)` en TODAS las rutas de detalle — filtra por org
4. `@check_org_permission` en TODAS las rutas incluso si el query ya filtra
5. `log_actividad()` ANTES de `db.session.commit()` en operaciones financieras
6. Consultar `ui-ux-pro-max` ANTES de implementar cualquier componente UI nuevo
7. Cada blueprint migrado: verificar en producción antes de migrar el siguiente
8. Todo CSS nuevo via variables CSS (`var(--primary)`, etc.), nunca valores hardcodeados

## Design System — "Precision Operations"
- Sidebar: `#0F172A` bg, `#F97316` accent (naranja)
- Página: `#F1F5F9` bg, `#FFFFFF` cards
- Estados: `.status-ok` (verde), `.status-warn` (amarillo), `.status-danger` (rojo), `.status-info` (azul), `.status-neutral` (gris)
- Font: DM Sans, `font-variant-numeric: tabular-nums` en montos
- CSS variables en `static/css/design-system.css`

## Helpers clave (app/helpers.py)
- `get_item_or_404(model, id)` — filtra por organizacion_id automáticamente
- `_flash_err(user_msg, exc)` — loguea al servidor, mensaje seguro al usuario
- `now_mx()` — hora actual en Mexico City (naive, para BD)
- `@check_org_permission` — bloquea usuarios sin org asignada
- `@admin_required` — solo admin/super_admin
- `@check_permission('perm_*')` — permiso granular por flag

## HD Pro Quick Order
- `integrations/hd_quickorder.py`: `generar_csv(orden)`, `generar_csv_proyecto(proyecto_oc)`, `subir_csv_auto()`
- `integrations/hd_session.py`: cookies Fernet, TTL 7 días
- Modelo `HDSesion` (tabla `hd_sesion`): unique(org_id, proveedor_id)
- Servidor pendiente: `flask add-hd-session-table && sudo systemctl restart inventario`
```

---

## 16. Reglas No Negociables

1. **Cero cambios de esquema** durante la reestructura. La BD es sagrada hasta que la migración esté completa.
2. **Cero cambios de URL**. Cada blueprint preserva exactamente las mismas rutas del `app.py` original.
3. **Un blueprint a la vez en producción**. Verificar antes de migrar el siguiente.
4. **`ui-ux-pro-max` antes de cualquier componente UI nuevo**. El diseño se valida antes de implementar.
5. **`superpowers:dispatching-parallel-agents`** para las fases 3 y 5 — no hacer migraciones secuenciales cuando son independientes.
6. **`get_item_or_404()` siempre** en rutas de detalle. Nunca `Model.query.get_or_404()` sin filtro de org.
7. **El `app.py` original se archiva, no se elimina** hasta que todos los tests pasen.
8. **Cada CSS nuevo usa variables CSS**. Ningún valor de color hardcodeado en templates.
9. **Los templates HTML no se tocan en la fase 1-4**. Solo se modifican en la fase 5 (UI).
10. **`log_actividad()` antes de `commit()`** en toda operación financiera o de inventario.
