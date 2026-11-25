from tests.fixtures_incidencias import (
    agregar_foto, crear_incidencia, entrar, mundo, png_bytes, uploads_tmp,  # noqa: F401
)

_n = {'i': 0}


def _foto(m, uploads_tmp, pendiente, color):
    """Escribe un PNG en el UPLOAD_FOLDER temporal y lo registra en el pendiente."""
    _n['i'] += 1
    nombre = f'f{_n["i"]}.png'
    carpeta = uploads_tmp / 'incidencias' / str(m.org.id)
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / nombre).write_bytes(png_bytes(color).read())
    agregar_foto(pendiente, f'uploads/incidencias/{m.org.id}/{nombre}', f'foto {nombre}')


def _pdf(client, inc):
    r = client.get(f'/incidencias/{inc.id}/pdf')
    assert r.status_code == 200
    assert r.mimetype == 'application/pdf' and r.data.startswith(b'%PDF')
    return r.data


def test_cinco_fotos_en_un_pendiente(client, mundo, uploads_tmp):
    inc = crear_incidencia(mundo.org, mundo.creador)
    for i in range(5):
        _foto(mundo, uploads_tmp, inc.pendientes[0], (10 + i * 40, 20, 200 - i * 30))
    entrar(client, mundo.admin)
    assert _pdf(client, inc).count(b'/Subtype /Image') == 5


def test_miembro_solo_ve_las_fotos_de_sus_pendientes(client, mundo, uploads_tmp):
    m = mundo
    inc = crear_incidencia(m.org, m.creador, pendientes=[('A1', m.depto_a), ('B1', m.depto_b)])
    a1, b1 = inc.pendientes
    _foto(m, uploads_tmp, a1, (200, 10, 10))
    _foto(m, uploads_tmp, b1, (10, 200, 10))
    _foto(m, uploads_tmp, b1, (10, 10, 200))
    entrar(client, m.admin)
    assert _pdf(client, inc).count(b'/Subtype /Image') == 3
    client.post('/logout')
    entrar(client, m.aux_a)
    assert _pdf(client, inc).count(b'/Subtype /Image') == 1


def test_foto_inexistente_no_rompe_el_pdf(client, mundo, uploads_tmp):
    inc = crear_incidencia(mundo.org, mundo.creador)
    agregar_foto(inc.pendientes[0], f'uploads/incidencias/{mundo.org.id}/no-existe.png', 'x')
    entrar(client, mundo.admin)
    assert _pdf(client, inc).count(b'/Subtype /Image') == 0
