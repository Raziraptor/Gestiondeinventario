from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.services.incidencias import (
    aplicar_estado_manual, progreso_departamento, progreso_desde_avance, promedio,
    reabrir_incidencia, registrar_avance,
)
from tests.fixtures_incidencias import crear_incidencia, mundo  # noqa: F401

AHORA = datetime(2026, 11, 24, 12, 0, 0)


def _tres_pendientes(m):
    inc = crear_incidencia(m.org, m.creador, pendientes=[
        ('A1', m.depto_a), ('A2', m.depto_a), ('B1', m.depto_b)])
    a1, a2, b1 = inc.pendientes
    return inc, a1, a2, b1


def test_promedio_y_acotado():
    assert promedio([]) == 0
    assert promedio([100, 0, 0]) == 33
    assert promedio([100, 100, 0]) == 67
    assert promedio([1, 0]) == 1
    assert progreso_desde_avance(150, False) == 100
    assert progreso_desde_avance(-5, False) == 0
    assert progreso_desde_avance(40, True) == 100


def test_peso_igual_tres_pendientes_dos_departamentos(mundo):
    inc, a1, a2, b1 = _tres_pendientes(mundo)
    _, ev = registrar_avance(a1, mundo.enc_a.id, 'listo A1', 100, ahora=AHORA)
    assert ('iniciada', mundo.depto_a.id) in ev
    assert inc.estado == 'En proceso' and inc.progreso == 33
    assert progreso_departamento(inc, mundo.depto_a.id) == 50
    _, ev = registrar_avance(a2, mundo.aux_a.id, 'listo A2', 100, ahora=AHORA)
    assert ev == [('departamento_completado', mundo.depto_a.id)]
    assert inc.progreso == 67 and progreso_departamento(inc, mundo.depto_a.id) == 100
    _, ev = registrar_avance(b1, mundo.enc_b.id, 'listo B1', 40, concluido=True, ahora=AHORA)
    assert ('departamento_completado', mundo.depto_b.id) in ev and ('completada', None) in ev
    assert inc.estado == 'Resuelto' and inc.progreso == 100
    assert inc.fecha_cierre == AHORA.date()
    assert inc.expira_en == AHORA + timedelta(days=30)
    assert inc.aviso_expiracion_enviado is False
    assert b1.completado_en == AHORA


def test_estados_fijos_no_se_pisan(mundo):
    inc = crear_incidencia(mundo.org, mundo.creador, estado='Escalado')
    registrar_avance(inc.pendientes[0], mundo.admin.id, 'todo', 100, ahora=AHORA)
    assert inc.estado == 'Escalado' and inc.progreso == 100


def test_estado_manual(mundo):
    inc = crear_incidencia(mundo.org, mundo.creador)
    aplicar_estado_manual(inc, 'Cerrado sin resolver', ahora=AHORA)
    assert inc.expira_en == AHORA + timedelta(days=30)
    aplicar_estado_manual(inc, 'Escalado', ahora=AHORA)
    assert inc.expira_en is None
    with pytest.raises(ValueError):
        aplicar_estado_manual(inc, 'Resuelto', ahora=AHORA)


def test_reabrir(mundo):
    inc, a1, a2, b1 = _tres_pendientes(mundo)
    for p in (a1, a2, b1):
        registrar_avance(p, mundo.admin.id, 'ok', 100, ahora=AHORA)
    db.session.commit()
    assert inc.estado == 'Resuelto'
    with pytest.raises(ValueError):
        reabrir_incidencia(inc, [])
    reabrir_incidencia(inc, [a1.id])
    assert inc.estado == 'En proceso' and a1.progreso == 0 and a1.completado_en is None
    assert inc.fecha_cierre is None and inc.expira_en is None and inc.progreso == 67
    with pytest.raises(ValueError):
        reabrir_incidencia(inc, [a1.id])
    otra = crear_incidencia(mundo.org, mundo.creador)
    aplicar_estado_manual(otra, 'Cerrado sin resolver', ahora=AHORA)
    assert reabrir_incidencia(otra) is None and otra.estado == 'En proceso' and otra.expira_en is None
    res = crear_incidencia(mundo.org, mundo.creador)
    registrar_avance(res.pendientes[0], mundo.admin.id, 'ok', 100, ahora=AHORA)
    nuevo = reabrir_incidencia(res, [], 'Revisar de nuevo', mundo.depto_b.id)
    db.session.commit()
    assert nuevo.id and nuevo.departamento_id == mundo.depto_b.id and res.progreso == 50
