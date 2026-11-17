"""
Encabezado personalizado del PDF de OC por proveedor.

Cada proveedor puede tener un EncabezadoOCProveedor con:
  - Membrete propio (logo, título, línea de dirección/RFC, correos de factura).
    Sin logo propio se usa el membrete de la plantilla; lo demás vacío se toma
    de la organización.
  - Campos del formulario de la plantilla (activables, renombrables, con valor
    predeterminado) + campos extra propios.

Al exportar, los campos se dibujan como campos AcroForm editables (precargados),
para poder corregirlos en Acrobat / Edge / Chrome antes de enviar la OC.
"""

import logging
import os
import re
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    Flowable, Paragraph, Table, TableStyle, Spacer, Image as ReportLabImage,
)

# Membrete de la plantilla original (logo + razón social + dirección/RFC en una
# sola imagen). Se imprime cuando el proveedor no tiene logo propio.
MEMBRETE_PREDETERMINADO = 'img/membrete_oc_predeterminado.jpg'   # relativo a static/
MEMBRETE_PREDETERMINADO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', MEMBRETE_PREDETERMINADO)

# ── Catálogo de campos de la plantilla ────────────────────────────────────────
# seccion 'encabezado' = cuadrícula arriba de la tabla; 'pie' = debajo del total.
CAMPOS_PLANTILLA = [
    {'clave': 'fecha',           'etiqueta': 'FECHA',                    'valor': '{fecha}',          'multilinea': False, 'seccion': 'encabezado'},
    {'clave': 'no_contrato',     'etiqueta': 'No. CONTRATO DE SERVICIO', 'valor': 'OC-{id}',          'multilinea': False, 'seccion': 'encabezado'},
    {'clave': 'no_cuenta',       'etiqueta': 'No. CUENTA ABIERTA',       'valor': '',                 'multilinea': False, 'seccion': 'encabezado'},
    {'clave': 'proveedor',       'etiqueta': 'PROVEEDOR',                'valor': '{proveedor}\n{telefono}', 'multilinea': True, 'seccion': 'encabezado'},
    {'clave': 'direccion_envio', 'etiqueta': 'DIRECCIÓN DE ENVÍO',       'valor': '',                 'multilinea': True,  'seccion': 'encabezado'},
    {'clave': 'fecha_entrega',   'etiqueta': 'FECHA DE ENTREGA',         'valor': '',                 'multilinea': False, 'seccion': 'encabezado'},
    {'clave': 'entregar_a',      'etiqueta': 'ENTREGAR A',               'valor': '{almacen}',        'multilinea': False, 'seccion': 'encabezado'},
    {'clave': 'departamento',    'etiqueta': 'DEPARTAMENTO SOLICITANTE', 'valor': '',                 'multilinea': False, 'seccion': 'encabezado'},
    {'clave': 'observaciones',   'etiqueta': 'OBSERVACIONES',            'valor': '',                 'multilinea': True,  'seccion': 'pie'},
    {'clave': 'firma',           'etiqueta': 'FIRMA AUTORIZADA',         'valor': '',                 'multilinea': True,  'seccion': 'pie'},
]
_CATALOGO = {c['clave']: c for c in CAMPOS_PLANTILLA}

# Placeholders permitidos en los valores predeterminados (lista blanca).
PLACEHOLDERS = [
    ('{id}',          'Número de la OC'),
    ('{consecutivo}', 'Consecutivo de OC con este proveedor (001, 002…)'),
    ('{fecha}',       'Fecha de la OC (13-Oct-2026)'),
    ('{proveedor}',   'Nombre del proveedor'),
    ('{telefono}',    'Teléfono del proveedor'),
    ('{email}',       'Email del proveedor'),
    ('{almacen}',     'Almacén de la OC'),
]

MAX_EXTRAS     = 8
MAX_ETIQUETA   = 60
MAX_VALOR      = 500
MAX_TITULO     = 200
MAX_LINEAS     = 6       # membrete: el Table de una fila no puede partirse entre páginas

_RE_CLAVE_EXTRA = re.compile(r'^extra_(\d{1,2})$')
_RE_CLAVE_NUEVA = re.compile(r'^nuevo_\d{1,4}$')

_log = logging.getLogger(__name__)

_MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
          'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']


def campos_por_defecto() -> list[dict]:
    """Configuración inicial: todos los campos de la plantilla activos."""
    return [dict(c, activo=True) for c in CAMPOS_PLANTILLA]


def _limpiar(texto, limite: int, multilinea: bool) -> str:
    texto = (texto or '').replace('\r\n', '\n').replace('\r', '\n')
    if not multilinea:
        texto = ' '.join(texto.split('\n'))
    return texto.strip()[:limite]


def limpiar_texto_largo(texto) -> str:
    """Para subtítulo / correos de factura del membrete (multilínea, recortado)."""
    lineas = [l for l in _limpiar(texto, MAX_VALOR, multilinea=True).split('\n') if l.strip()]
    return '\n'.join(lineas[:MAX_LINEAS])


def normalizar_campos(form, campos_actuales=None) -> list[dict]:
    """
    Construye la lista de campos a partir del formulario.

    Espera `campo_clave[]` (en el orden deseado) y, por clave:
    `etiqueta_<clave>`, `valor_<clave>`, `activo_<clave>`, `multilinea_<clave>`.
    Claves válidas: las del catálogo, `extra_N` existentes y `nuevo_N` (extras
    nuevos, a los que el servidor asigna `extra_N`). Todo lo demás se ignora.
    """
    extras_existentes = {
        c['clave'] for c in (campos_actuales or [])
        if _RE_CLAVE_EXTRA.match(c.get('clave', ''))
    }
    usados = {int(_RE_CLAVE_EXTRA.match(k).group(1)) for k in extras_existentes}

    def _siguiente_extra():
        n = 1
        while n in usados:
            n += 1
        usados.add(n)
        return f'extra_{n}'

    resultado, vistos, n_extras = [], set(), 0
    for clave in form.getlist('campo_clave[]'):
        clave = (clave or '').strip()
        if not clave or clave in vistos:
            continue
        vistos.add(clave)

        catalogo = _CATALOGO.get(clave)
        es_extra = clave in extras_existentes or bool(_RE_CLAVE_NUEVA.match(clave))
        if not catalogo and not es_extra:
            continue

        multilinea = form.get(f'multilinea_{clave}') == '1'
        etiqueta = _limpiar(form.get(f'etiqueta_{clave}'), MAX_ETIQUETA, False)
        valor    = _limpiar(form.get(f'valor_{clave}'), MAX_VALOR, multilinea)
        activo   = form.get(f'activo_{clave}') == '1'

        if catalogo:
            resultado.append({
                'clave': clave, 'etiqueta': etiqueta or catalogo['etiqueta'],
                'valor': valor, 'activo': activo, 'multilinea': multilinea,
                'seccion': catalogo['seccion'],
            })
            continue

        if not etiqueta or n_extras >= MAX_EXTRAS:
            continue
        n_extras += 1
        if _RE_CLAVE_NUEVA.match(clave):
            clave = _siguiente_extra()
        resultado.append({
            'clave': clave, 'etiqueta': etiqueta, 'valor': valor,
            'activo': activo, 'multilinea': multilinea, 'seccion': 'encabezado',
        })

    # Los campos de la plantilla siempre existen (aunque falten en el form).
    presentes = {c['clave'] for c in resultado}
    for c in CAMPOS_PLANTILLA:
        if c['clave'] not in presentes:
            resultado.append(dict(c, activo=False))
    return resultado


# ── Placeholders ──────────────────────────────────────────────────────────────

def contexto_orden(orden, consecutivo: int) -> dict[str, str]:
    """Valores de los placeholders para una OC concreta."""
    prv, f = orden.proveedor, orden.fecha_creacion
    return {
        '{id}':          str(orden.id),
        '{consecutivo}': f'{consecutivo:03d}',
        '{fecha}':       f'{f.day:02d}-{_MESES[f.month - 1]}-{f.year}' if f else '',
        '{proveedor}':   (prv.nombre if prv else '') or '',
        '{telefono}':    (prv.contacto_telefono if prv else '') or '',
        '{email}':       (prv.contacto_email if prv else '') or '',
        '{almacen}':     orden.almacen.nombre if orden.almacen else '',
    }


def resolver_valor(texto: str, contexto: dict[str, str]) -> str:
    """Sustituye solo los placeholders de la lista blanca (nunca str.format)."""
    texto = texto or ''
    for token, valor in contexto.items():
        texto = texto.replace(token, valor)
    # Líneas que quedaron vacías por un placeholder sin dato (ej. {telefono}).
    return '\n'.join(l for l in texto.split('\n') if l.strip())


# ── PDF: membrete ─────────────────────────────────────────────────────────────

def _imagen(path: str, max_w: float, max_h: float):
    """Imagen escalada para caber en max_w × max_h, o None si no se puede leer."""
    try:
        img = ReportLabImage(path)
        escala = min(max_w / img.imageWidth, max_h / img.imageHeight)
        img.drawWidth, img.drawHeight = img.imageWidth * escala, img.imageHeight * escala
        return img
    except Exception as e:                       # imagen corrupta: PDF sin logo
        _log.warning('No se pudo cargar la imagen %s para el PDF de OC: %s', path, e)
        return None


def _cargar_logo(upload_folder: str, rel_path: str | None, max_h: float):
    if not rel_path:
        return None
    base = os.path.realpath(upload_folder)
    path = os.path.realpath(os.path.join(base, rel_path))
    if not path.startswith(base + os.sep) or not os.path.exists(path):
        return None
    return _imagen(path, 1.6 * inch, max_h)


def _parrafo_multilinea(texto: str, estilo) -> Paragraph:
    return Paragraph('<br/>'.join(_xml_escape(l) for l in texto.split('\n')), estilo)


def construir_membrete(story, enc, org, upload_folder, fuente, fuente_bold, c_pri, ancho):
    """Membrete: título + subtítulo | logo | ENVIAR FACTURA A. Respaldo: datos de la org.

    Sin logo propio se usa el membrete de la plantilla (MEMBRETE_PREDETERMINADO),
    que ya trae nombre, dirección y RFC; por eso entonces no se imprimen título
    ni subtítulo.
    """
    facturar_a = enc.facturar_a or org.correo_empresa or ''
    s_flbl = ParagraphStyle('_EncFL', fontName=fuente_bold, fontSize=7.5, leading=10,
                            textColor=colors.HexColor('#1f4e5f'), alignment=1)
    s_fval = ParagraphStyle('_EncFV', fontName=fuente_bold, fontSize=8, leading=11, alignment=1)
    col_factura = []
    if facturar_a:
        col_factura = [Paragraph('ENVIAR FACTURA A', s_flbl), Spacer(1, 2),
                       _parrafo_multilinea(facturar_a, s_fval)]
    w_fac = 2.0 * inch if col_factura else 0

    logo = _cargar_logo(upload_folder, enc.logo_url, 0.8 * inch)
    membrete = None if logo else _imagen(MEMBRETE_PREDETERMINADO_PATH, ancho - w_fac - 0.1 * inch,
                                         1.1 * inch)
    if membrete:
        fila, anchos = [membrete], [ancho - w_fac]
    else:
        titulo = enc.titulo or org.header_titulo or org.nombre or ''
        if enc.subtitulo:
            subtitulo = enc.subtitulo
        else:
            partes = [p for p in (org.direccion, f'RFC: {org.rfc}' if org.rfc else None) if p]
            subtitulo = ' | '.join(partes)
        s_titulo = ParagraphStyle('_EncTit', fontName=fuente_bold, fontSize=17, leading=20,
                                  textColor=c_pri)
        s_sub = ParagraphStyle('_EncSub', fontName=fuente, fontSize=7, leading=9,
                               textColor=colors.HexColor('#5b7a99'))
        col_titulo = [Paragraph(_xml_escape(titulo), s_titulo)]
        if subtitulo:
            col_titulo += [Spacer(1, 3), _parrafo_multilinea(subtitulo, s_sub)]
        w_logo = (logo.drawWidth + 0.15 * inch) if logo else 0
        fila, anchos = [col_titulo], [ancho - w_fac - w_logo]
        if logo:
            fila.append(logo); anchos.append(w_logo)
    if col_factura:
        fila.append(col_factura); anchos.append(w_fac)

    t = Table([fila], colWidths=anchos)
    t.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.15 * inch))


# ── PDF: cuadrícula de campos rellenables ─────────────────────────────────────

class CamposFormulario(Flowable):
    """
    Cuadrícula de celdas "ETIQUETA / campo editable", `columnas` por fila.
    Cada campo es un textfield AcroForm (relative=True para respetar la posición
    del flowable dentro del SimpleDocTemplate), precargado con su valor.
    """
    BANDA_H   = 13      # alto de la banda de etiqueta
    LINEA_H   = 11      # alto por línea de texto
    PAD       = 3
    FONT_SIZE = 9

    def __init__(self, campos, contexto, fuente_bold, c_banda, c_etiqueta, columnas=3, ancho=None):
        super().__init__()
        self.ancho       = ancho          # fijo para alinear con la tabla de productos
        self.hAlign      = 'CENTER'
        self.campos      = campos
        self.contexto    = contexto
        self.fuente_bold = fuente_bold
        self.c_banda     = c_banda
        self.c_etiqueta  = c_etiqueta
        self.columnas    = columnas
        self.filas = [campos[i:i + columnas] for i in range(0, len(campos), columnas)]

    def _alto_campo(self, campo) -> float:
        if not campo['multilinea']:
            return self.LINEA_H + 2 * self.PAD + 4
        lineas = resolver_valor(campo['valor'], self.contexto).count('\n') + 1
        return self.LINEA_H * min(max(3, lineas), 6) + 2 * self.PAD

    def _alto_fila(self, fila) -> float:
        return self.BANDA_H + max(self._alto_campo(c) for c in fila)

    def wrap(self, avail_w, avail_h):
        self.width  = self.ancho or avail_w
        self.height = sum(self._alto_fila(f) for f in self.filas)
        return self.width, self.height

    def draw(self):
        c = self.canv
        borde = colors.HexColor('#cfd8dc')
        cell_w = self.width / self.columnas
        y_top = self.height
        for fila in self.filas:
            fila_h = self._alto_fila(fila)
            y = y_top - fila_h
            for i, campo in enumerate(fila):
                x = i * cell_w
                # Banda de etiqueta
                c.setFillColor(self.c_banda)
                c.setStrokeColor(borde)
                c.setLineWidth(0.5)
                c.rect(x, y + fila_h - self.BANDA_H, cell_w, self.BANDA_H, stroke=1, fill=1)
                c.setFillColor(self.c_etiqueta)
                c.setFont(self.fuente_bold, 7)
                etiqueta = campo['etiqueta'].upper()
                while etiqueta and c.stringWidth(etiqueta, self.fuente_bold, 7) > cell_w - 2 * self.PAD - 4:
                    etiqueta = etiqueta[:-1]
                c.drawString(x + self.PAD + 2, y + fila_h - self.BANDA_H + 4, etiqueta)
                # Caja del campo
                campo_h = fila_h - self.BANDA_H
                c.setFillColor(colors.white)
                c.rect(x, y, cell_w, campo_h, stroke=1, fill=1)
                c.acroForm.textfield(
                    name=f"enc_{campo['clave']}",
                    tooltip=_latin1(campo['etiqueta']),
                    value=_latin1(resolver_valor(campo['valor'], self.contexto)),
                    x=x + self.PAD, y=y + self.PAD,
                    width=cell_w - 2 * self.PAD, height=campo_h - 2 * self.PAD,
                    relative=True, borderWidth=0, forceBorder=False,
                    fillColor=colors.white, textColor=colors.black,
                    fontName='Helvetica', fontSize=self.FONT_SIZE,
                    fieldFlags='multiline' if campo['multilinea'] else '',
                    maxlen=0,
                )
            y_top -= fila_h


_SUSTITUTOS_LATIN1 = str.maketrans({
    '—': '-', '–': '-', '−': '-', '‘': "'", '’': "'",
    '“': '"', '”': '"', '…': '...', '•': '-', ' ': ' ',
})


def _latin1(texto: str) -> str:
    """Los campos AcroForm usan Helvetica (WinAnsi): reportlab truena con caracteres
    fuera de Latin-1 (p. ej. '—'). Se sustituyen los comunes y el resto queda como '?'."""
    return (texto or '').translate(_SUSTITUTOS_LATIN1).encode('latin-1', 'replace').decode('latin-1')


def campos_activos(enc, seccion: str) -> list[dict]:
    return [c for c in (enc.campos or []) if c.get('activo') and c.get('seccion') == seccion]
