import pytest

from app.extensions import db
from app.models import AuditLog, Departamento, DepartamentoMiembro
from app.services.departamentos import departamento_valido, guardar_departamento
from tests.fixtures_incidencias import crear_incidencia, entrar, mundo  # noqa: F401


def test_servicio(mundo):
    m = mundo
    d = guardar_departamento(m.org.id, ' Compras  ', m.ajeno.id, [m.ajeno.id, m.aux_a.id, m.enc_b.id])
    db.session.commit()
    roles = sorted((x.user_id, x.rol) for x in DepartamentoMiembro.query.filter_by(departamento_id=d.id))
    assert d.nombre == 'Compras'
    assert roles == sorted([(m.ajeno.id, 'encargado'), (m.aux_a.id, 'auxiliar'), (m.enc_b.id, 'auxiliar')])
    with pytest.raises(ValueError):
        guardar_departamento(m.org.id, 'compras')
    with pytest.raises(ValueError):
        guardar_departamento(m.org.id, 'Otro', m.user_beta.id)
    guardar_departamento(m.org.id, 'Compras', m.enc_b.id, [], depto=d)
    db.session.commit()
    assert [(x.user_id, x.rol) for x in d.miembros] == [(m.enc_b.id, 'encargado')]
    assert departamento_valido(str(m.depto_beta.id), m.org.id) is None
    assert departamento_valido(m.depto_a.id, m.org.id) is m.depto_a


def _flashes(client):
    with client.session_transaction() as s:
        return s.get('_flashes', [])


def test_admin_crea_departamento(client, mundo):
    m = mundo
    entrar(client, m.admin)
    r = client.post('/admin/departamentos/nuevo', data={
        'nombre': 'Compras', 'encargado_id': m.enc_b.id, 'auxiliar_ids': [m.ajeno.id, m.aux_a.id]})
    assert r.status_code == 302
    d = Departamento.query.filter_by(organizacion_id=m.org.id, nombre='Compras').one()
    roles = sorted(x.rol for x in d.miembros)
    assert roles == ['auxiliar', 'auxiliar', 'encargado']
    assert AuditLog.query.filter_by(entidad='departamento').count() >= 1


def test_encargado_tambien_en_auxiliares_se_guarda_una_vez(client, mundo):
    m = mundo
    entrar(client, m.admin)
    client.post('/admin/departamentos/nuevo', data={
        'nombre': 'Compras', 'encargado_id': m.enc_b.id, 'auxiliar_ids': [m.enc_b.id, m.ajeno.id]})
    d = Departamento.query.filter_by(nombre='Compras', organizacion_id=m.org.id).one()
    assert sorted((x.user_id, x.rol) for x in d.miembros) == sorted(
        [(m.enc_b.id, 'encargado'), (m.ajeno.id, 'auxiliar')])


def test_nombre_repetido_o_usuario_ajeno_no_escribe(client, mundo):
    m = mundo
    entrar(client, m.admin)
    antes = Departamento.query.count()
    client.post('/admin/departamentos/nuevo', data={'nombre': 'mantenimiento'})
    assert Departamento.query.count() == antes
    assert any(cat == 'danger' for cat, _ in _flashes(client))
    client.post('/admin/departamentos/nuevo', data={'nombre': 'Nuevo', 'encargado_id': m.user_beta.id})
    assert Departamento.query.count() == antes


def test_no_admin_403_y_otra_org_404(client, mundo):
    m = mundo
    entrar(client, m.aux_a)
    assert client.get('/admin/departamentos').status_code == 403
    assert client.post('/admin/departamentos/nuevo', data={'nombre': 'X1'}).status_code == 403
    client.post('/logout')
    entrar(client, m.admin_beta)
    assert client.post(f'/admin/departamentos/{m.depto_a.id}/editar', data={'nombre': 'Hack'}).status_code == 404


def test_eliminar_solo_sin_pendientes_y_alternar_estado(client, mundo):
    m = mundo
    crear_incidencia(m.org, m.creador, pendientes=[('X', m.depto_a)])
    entrar(client, m.admin)
    client.post(f'/admin/departamentos/{m.depto_a.id}/eliminar')
    assert db.session.get(Departamento, m.depto_a.id) is not None
    libre_id = m.depto_b.id
    client.post(f'/admin/departamentos/{libre_id}/eliminar')
    assert db.session.get(Departamento, libre_id) is None
    activo = m.depto_a.activo
    client.post(f'/admin/departamentos/{m.depto_a.id}/estado')
    db.session.refresh(m.depto_a)
    assert m.depto_a.activo is (not activo)


def test_lista_muestra_nombres(client, mundo):
    entrar(client, mundo.admin)
    html = client.get('/admin/departamentos').get_data(as_text=True)
    assert 'Elena Encargada (inc_enc_a)' in html


def test_buscar_usuarios_por_nombre_y_por_usuario(client, mundo):
    entrar(client, mundo.admin)
    r = client.get('/admin/departamentos/buscar-usuarios?q=elena')
    assert r.status_code == 200
    assert [u['texto'] for u in r.get_json()] == ['Elena Encargada (inc_enc_a)']
    por_usuario = client.get('/admin/departamentos/buscar-usuarios?q=INC_AUX').get_json()
    assert [u['id'] for u in por_usuario] == [mundo.aux_a.id]
    assert client.get('/admin/departamentos/buscar-usuarios?q=').get_json() == []


def test_busqueda_solo_de_la_org_y_activos_y_sin_comodines(client, mundo):
    from app.models import User
    entrar(client, mundo.admin)
    assert client.get('/admin/departamentos/buscar-usuarios?q=berta').get_json() == []  # otra organización
    mundo.ajeno.is_active = False
    db.session.commit()
    assert client.get('/admin/departamentos/buscar-usuarios?q=pedro').get_json() == []
    assert client.get('/admin/departamentos/buscar-usuarios?q=%25').get_json() == []     # '%' no es comodín
    assert len(client.get('/admin/departamentos/buscar-usuarios?q=inc_').get_json()) <= 15
    assert db.session.get(User, mundo.ajeno.id) is not None


def test_busqueda_solo_para_admins(client, mundo):
    entrar(client, mundo.aux_a)
    assert client.get('/admin/departamentos/buscar-usuarios?q=elena').status_code == 403


def test_la_pagina_no_lista_a_todos_los_usuarios(client, mundo):
    entrar(client, mundo.admin)
    html = client.get('/admin/departamentos').get_data(as_text=True)
    assert 'Pedro Ajeno' not in html                      # no pertenece a ningún departamento
    assert 'buscar-usuarios' in html and 'type="search"' in html
    assert 'Elena Encargada (inc_enc_a)' in html          # el encargado actual sí aparece como chip
