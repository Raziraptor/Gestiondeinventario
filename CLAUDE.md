# Gestión de Inventario — Instrucciones del Proyecto

## Stack
Flask + SQLAlchemy + PostgreSQL + Bootstrap 5.3.3 + Gunicorn (servidor: /root/venv/)

## Skills activos en este proyecto
- **andrej-karpathy**: Usar para análisis técnico profundo, decisiones de arquitectura y razonamiento sobre ML/AI.
- **antigravity-skill-orchestrator**: Usar para coordinar múltiples skills en tareas complejas de varias etapas.
- **ui-ux-pro-max**: Usar para cualquier trabajo de diseño UI/UX.

## Reglas generales
- Siempre usar ruflo (MCP) cuando esté disponible para memoria persistente y contexto.
- Siempre hacer `git push origin main` después de cada commit.
- Los pip install en el servidor van en `/root/venv/bin/pip install`, NO en el venv local.
- La cámara NO debe bloquearse en Permissions-Policy (se usa para escáner QR).

## Seguridad financiera (implementado)
- Montos siempre validados > 0 server-side.
- Todas las operaciones financieras tienen audit log (log_actividad).
- `_flash_err()` en lugar de `flash(f'Error: {e}')` en rutas críticas.
- Rate limiting: login 10/min, register 10/min, forgot-password 5/min.

## Pendiente (segunda fase)
- FIN-01: Migrar db.Float → db.Numeric(10,2) en tablas financieras (requiere planear migración de BD).
- AUTH-02: Token de reset single-use (requiere tabla de tokens usados).
- RATE-01: Limiter a Redis en producción.
