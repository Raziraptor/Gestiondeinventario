from datetime import date, datetime, timedelta

from app.extensions import db
from app.models import IncidenciaAvance, Pendiente, PendienteFoto
from app.services.incidencias_migracion import backfill_pendientes
from tests.fixtures_incidencias import crear_incidencia, mundo  # noqa: F401

AHORA = datetime(2026, 11, 24, 12, 0, 0)


def _legada(m, estado='En proceso', progreso=40, fecha_cierre=None):
    inc = crear_incidencia(m.org, m.creador, pendientes=(), estado=estado)
    inc.progreso = progreso
    inc.fecha_cierre = fecha_cierre
    inc.foto1_path, inc.foto1_desc = 'uploads/incidencias/1/a.png', 'Fachada'
    inc.foto2_path, inc.foto2_desc = 'uploads/incidencias/1/b.png', None
    for t in ('uno', 'dos'):
        db.session.add(IncidenciaAvance(incidencia_id=inc.id, texto=t, porcentaje=progreso, autor_id=m.creador.id))
    db.session.commit()
    return inc


def test_backfill_crea_un_pendiente_con_fotos_y_avances(mundo):
    inc = _legada(mundo)
    c = backfill_pendientes(AHORA)
    assert c == {'pendientes': 1, 'fotos': 2, 'avances': 2, 'gracia': 0}
    (p,) = inc.pendientes
    assert p.descripcion == 'Descripcion de prueba' and p.progreso == 40 and p.departamento_id is None
    assert [(f.path, f.descripcion) for f in p.fotos] == [
        ('uploads/incidencias/1/a.png', 'Fachada'), ('uploads/incidencias/1/b.png', None)]
    assert IncidenciaAvance.query.filter_by(pendiente_id=p.id).count() == 2
    assert inc.foto1_path == 'uploads/incidencias/1/a.png'  # columnas legadas intactas


def test_gracia_para_cerradas_y_resuelta_completa(mundo):
    res = _legada(mundo, estado='Resuelto', progreso=80, fecha_cierre=date(2026, 1, 5))
    csr = _legada(mundo, estado='Cerrado sin resolver')
    c = backfill_pendientes(AHORA)
    assert c['gracia'] == 2
    assert res.expira_en == csr.expira_en == AHORA + timedelta(days=30)
    assert res.pendientes[0].progreso == 100
    assert res.pendientes[0].completado_en == datetime(2026, 1, 5, 0, 0)


def test_reejecutar_no_cambia_nada(mundo):
    _legada(mundo, estado='Resuelto')
    backfill_pendientes(AHORA)
    expira = Pendiente.query.first().incidencia.expira_en
    c = backfill_pendientes(AHORA + timedelta(days=3))
    assert c == {'pendientes': 0, 'fotos': 0, 'avances': 0, 'gracia': 0}
    assert Pendiente.query.count() == 1 and PendienteFoto.query.count() == 2
    assert Pendiente.query.first().incidencia.expira_en == expira


def test_comando_cli_dos_veces(app, mundo):
    _legada(mundo)
    runner = app.test_cli_runner()
    r1 = runner.invoke(args=['fix-incidencias-v3'])
    assert r1.exit_code == 0, r1.output
    assert 'fix-incidencias-v3: pendientes creados=1 fotos=2 avances=2 gracia=0' in r1.output
    r2 = runner.invoke(args=['fix-incidencias-v3'])
    assert r2.exit_code == 0, r2.output
    assert 'fix-incidencias-v3: pendientes creados=0 fotos=0 avances=0 gracia=0' in r2.output


def test_permiso_crear_se_concede_a_quien_ya_creo(mundo):
    from app.models import User
    from app.services.incidencias_migracion import conceder_permiso_crear_a_creadores
    crear_incidencia(mundo.org, mundo.ajeno)  # el 'ajeno' ya había creado una incidencia
    assert db.session.get(User, mundo.ajeno.id).perm_crear_incidencias is False
    assert db.session.get(User, mundo.enc_a.id).perm_crear_incidencias is False
    assert conceder_permiso_crear_a_creadores() == 1  # 'creador' del fixture ya lo tenía
    assert db.session.get(User, mundo.ajeno.id).perm_crear_incidencias is True
    assert db.session.get(User, mundo.enc_a.id).perm_crear_incidencias is False
    assert conceder_permiso_crear_a_creadores() == 0
