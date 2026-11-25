# Runbook — Incidencias v3 (pendientes por departamento)

Todo se corre en el servidor, como root, en el directorio de la app (el `WorkingDirectory` de la
unidad: `systemctl show -p WorkingDirectory --value inventario`), con el venv `/root/venv`.

## Paso 1 — Respaldo (antes del primer borrado real)

pg_dump "$DATABASE_URL" -Fc -f /root/backup-pre-incidencias-v3.dump

## Paso 2 — Migración (idempotente; se puede correr dos veces)

flask fix-incidencias-v3 && sudo systemctl restart inventario

La segunda corrida debe imprimir `fix-incidencias-v3: pendientes creados=0 fotos=0 avances=0 gracia=0`.

La primera corrida concede `perm_crear_incidencias` a quien ya había creado incidencias (la línea
`permiso perm_crear_incidencias concedido a N usuario(s)…`). Antes cualquiera podía crear; ahora hace
falta el permiso. A los demás hay que activárselo en el panel de administración (columna Incidencias).

El límite de subida de la app subió a 64 MB por petición (fotos ilimitadas por pendiente). Si hay nginx
delante, sube también `client_max_body_size 64m;` o las fotos grandes fallarán con 413.

## Paso 3 — Revisión de la retención

flask limpiar-incidencias-cerradas --dry-run

Tras la migración debe decir `por_eliminar=0` (todo lo cerrado recibió 30 días de gracia).

## Paso 4 — Cron diario (03:30)

El cron no hereda el entorno de systemd. Mira de dónde lo toma la unidad con `systemctl cat inventario`:
si usa `EnvironmentFile=<archivo>`, la línea lo carga; si las variables están en `.env` del directorio
de la app, `load_dotenv()` de `app/config.py` las lee solo y puedes quitar el `. <archivo>`.

30 3 * * * cd <WorkingDirectory> && set -a && . <EnvironmentFile> && set +a && /root/venv/bin/flask limpiar-incidencias-cerradas >> /var/log/inventario-retencion.log 2>&1

## Paso 5 — Rollback

Desplegar el código anterior y `sudo systemctl restart inventario`; quitar la línea del cron. Las
tablas y columnas nuevas se quedan (el código anterior las ignora). Restaurar el respaldo del punto 1
solo si el cron borró algo por error: `pg_restore --clean -d "$DATABASE_URL" /root/backup-pre-incidencias-v3.dump`.

## Paso 6 — Avisar a los usuarios

Desde v3 cada quien ve solo las incidencias con pendientes de su departamento; admins y creadores ven
todo lo suyo. Las incidencias migradas no tienen departamento: un admin las asigna desde el detalle.
