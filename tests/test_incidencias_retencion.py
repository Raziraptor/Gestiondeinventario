from datetime import datetime, timedelta

from app.extensions import db
from app.models import AuditLog, Incidencia, Notificacion
from app.services import incidencias_retencion
from app.services.incidencias_retencion import ejecutar_retencion
from tests.fixtures_incidencias import agregar_foto, crear_incidencia, entrar, mundo, uploads_tmp  # noqa: F401

AHORA = datetime(2026, 11, 24, 3, 30, 0)


def _cerrada(m, dias, estado='Resuelto'):
    inc = crear_incidencia(m.org, m.creador, estado=estado)
    inc.expira_en = AHORA + timedelta(days=dias)
    db.session.commit()
    return inc


def _foto(uploads, inc, nombre):
    carpeta = uploads / 'incidencias' / str(inc.organizacion_id)
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / nombre).write_bytes(b'x')
    agregar_foto(inc.pendientes[0], f'uploads/incidencias/{inc.organizacion_id}/{nombre}')
    return carpeta / nombre


def test_dry_run_no_cambia_nada(mundo, uploads_tmp):
    inc = _cerrada(mundo, -1)
    archivo = _foto(uploads_tmp, inc, 'a.png')
    lineas = []
    r = ejecutar_retencion(AHORA, dry_run=True, echo=lineas.append)
    assert r['por_eliminar'] == 1 and r['eliminadas'] == 0
    assert any(l.startswith(f'ELIMINAR {inc.folio}') for l in lineas)
    assert db.session.get(Incidencia, inc.id) is not None and archivo.exists()


def test_borra_solo_cerradas_vencidas_y_sus_archivos(mundo, uploads_tmp):
    vieja = _cerrada(mundo, -1)
    csr = _cerrada(mundo, -2, estado='Cerrado sin resolver')
    vigente = _cerrada(mundo, 10)
    escalada = _cerrada(mundo, -5, estado='Escalado')
    archivo = _foto(uploads_tmp, vieja, 'b.png')
    ids = (vieja.id, csr.id, vigente.id, escalada.id)
    r = ejecutar_retencion(AHORA, echo=lambda *_: None)
    assert r['eliminadas'] == 2 and r['archivos_borrados'] == 1 and not archivo.exists()
    assert db.session.get(Incidencia, ids[0]) is None and db.session.get(Incidencia, ids[1]) is None
    assert db.session.get(Incidencia, ids[2]) is not None and db.session.get(Incidencia, ids[3]) is not None
    assert AuditLog.query.filter(AuditLog.descripcion.like('%eliminada por vigencia')).count() == 2


def test_guardia_path_traversal(mundo, uploads_tmp):
    inc = _cerrada(mundo, -1)
    fuera = uploads_tmp.parent.parent / 'fuera.txt'
    fuera.write_bytes(b'no tocar')
    agregar_foto(inc.pendientes[0], '../fuera.txt')  # -> tmp_path/fuera.txt, fuera de UPLOAD_FOLDER
    r = ejecutar_retencion(AHORA, echo=lambda *_: None)
    assert r['eliminadas'] == 1 and r['archivos_rechazados'] == 1 and fuera.exists()


def test_aviso_una_sola_vez(mundo):
    inc = _cerrada(mundo, 3)
    _cerrada(mundo, 10)
    r = ejecutar_retencion(AHORA, echo=lambda *_: None)
    assert r['avisadas'] == 1 and inc.aviso_expiracion_enviado is True
    destinatarios = {n.user_id for n in Notificacion.query.all()}
    assert destinatarios == {mundo.creador.id, mundo.admin.id}
    assert 'descarga el PDF' in Notificacion.query.first().cuerpo
    r2 = ejecutar_retencion(AHORA, echo=lambda *_: None)
    assert r2['avisadas'] == 0 and Notificacion.query.count() == 2


def test_comando_cli(app):
    r = app.test_cli_runner().invoke(args=['limpiar-incidencias-cerradas', '--dry-run'])
    assert r.exit_code == 0, r.output
    assert 'limpiar-incidencias-cerradas (dry-run): por_avisar=0' in r.output


def test_un_fallo_no_detiene_la_corrida(mundo, monkeypatch):
    mala = _cerrada(mundo, -1)
    buena = _cerrada(mundo, -1)
    original = incidencias_retencion.rutas_fotos

    def rutas(inc):
        if inc.id == mala.id:
            raise RuntimeError('boom')
        return original(inc)
    monkeypatch.setattr(incidencias_retencion, 'rutas_fotos', rutas)
    ids = (mala.id, buena.id)
    r = ejecutar_retencion(AHORA, echo=lambda *_: None)
    assert r['errores'] == 1 and r['eliminadas'] == 1
    assert db.session.get(Incidencia, ids[0]) is not None and db.session.get(Incidencia, ids[1]) is None


def test_fecha_de_eliminacion_en_detalle_y_lista(client, mundo):
    inc = crear_incidencia(mundo.org, mundo.creador, estado='Resuelto')
    inc.expira_en = datetime(2026, 12, 24, 9, 0)
    db.session.commit()
    entrar(client, mundo.creador)
    assert 'Se eliminará el 24/12/2026' in client.get(f'/incidencias/{inc.id}').get_data(as_text=True)
    assert 'Se eliminará el 24/12/2026' in client.get('/incidencias/').get_data(as_text=True)


def test_eliminar_a_mano_borra_los_archivos(client, mundo, uploads_tmp):
    inc = crear_incidencia(mundo.org, mundo.creador)
    archivo = _foto(uploads_tmp, inc, 'manual.png')
    entrar(client, mundo.admin)
    assert client.post(f'/incidencias/{inc.id}/eliminar').status_code == 302
    assert db.session.get(Incidencia, inc.id) is None and not archivo.exists()


def test_quitar_pendiente_borra_solo_sus_archivos(client, mundo, uploads_tmp):
    inc = crear_incidencia(mundo.org, mundo.creador, pendientes=[('Uno', None), ('Dos', None)])
    uno, dos = inc.pendientes
    f_uno = _foto_en(uploads_tmp, inc, uno, 'uno.png')
    f_dos = _foto_en(uploads_tmp, inc, dos, 'dos.png')
    entrar(client, mundo.creador)
    client.post(f'/incidencias/{inc.id}/editar', data={
        'titulo': 'T', 'fecha': '2026-11-24', 'hora': '10:00', 'ubicacion': 'U', 'tipo': 'Infraestructura',
        'prioridad': 'Media', 'severidad': 'Menor', 'descripcion': 'D',
        'pendiente_uid[]': [f'p{dos.id}'], 'pendiente_descripcion[]': ['Dos'], 'pendiente_departamento[]': [''],
        'pendiente_eliminar[]': [f'p{uno.id}'],
    })
    assert not f_uno.exists() and f_dos.exists()


def _foto_en(uploads, inc, pendiente, nombre):
    carpeta = uploads / 'incidencias' / str(inc.organizacion_id)
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / nombre).write_bytes(b'x')
    agregar_foto(pendiente, f'uploads/incidencias/{inc.organizacion_id}/{nombre}')
    return carpeta / nombre
