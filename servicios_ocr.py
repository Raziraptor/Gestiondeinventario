"""
OCR para recibos de servicios mexicanos.
Detecta: CFE, SADM (Agua Monterrey), Telmex, TotalPlay.
Fallback genérico para otros proveedores.
"""
import re
from datetime import date

# ── Mapeo de meses español/inglés ────────────────────────────────────────────
MESES = {
    'ene': 1, 'enero': 1,  'jan': 1,
    'feb': 2, 'febrero': 2,
    'mar': 3, 'marzo': 3,  'march': 3,
    'abr': 4, 'abril': 4,  'apr': 4,
    'may': 5, 'mayo': 5,
    'jun': 6, 'junio': 6,  'june': 6,
    'jul': 7, 'julio': 7,  'july': 7,
    'ago': 8, 'agosto': 8, 'aug': 8,
    'sep': 9, 'sept': 9,   'septiembre': 9, 'september': 9,
    'oct': 10,'octubre': 10,'october': 10,
    'nov': 11,'noviembre': 11,'november': 11,
    'dic': 12,'diciembre': 12,'december': 12,
}

# ── Detección de proveedor ────────────────────────────────────────────────────
_FIRMAS = {
    'cfe':      ['comisión federal de electricidad', 'c.f.e.', 'cfe '],
    'sadm':     ['agua y drenaje de monterrey', 'sadm', 'servicios de agua'],
    'telmex':   ['telmex', 'teléfonos de méxico', 'telefonos de mexico'],
    'totalplay':['totalplay', 'total play'],
}

def detectar_proveedor(texto: str) -> str:
    t = texto.lower()
    for proveedor, firmas in _FIRMAS.items():
        if any(f in t for f in firmas):
            return proveedor
    return 'desconocido'


# ── Helpers genéricos ─────────────────────────────────────────────────────────
def _limpiar_monto(s: str) -> float | None:
    """'1,234.56' o '1234.56' → 1234.56"""
    try:
        return float(s.replace(',', '').strip())
    except (ValueError, AttributeError):
        return None

def _fecha_numerica(d, m, y) -> date | None:
    """Construye un date controlando errores."""
    try:
        y = int(y); d = int(d); m = int(m)
        if y < 100: y += 2000
        return date(y, m, d)
    except Exception:
        return None

def _fecha_texto(d, mes_str, y) -> date | None:
    """Construye un date con mes en texto (ej. 'ENE', 'enero')."""
    mo = MESES.get(mes_str.lower()[:3])
    if not mo:
        mo = MESES.get(mes_str.lower())
    return _fecha_numerica(d, mo, y) if mo else None


# ── Parsers genéricos (fallback) ──────────────────────────────────────────────
_RE_MONTO_CONTEXTO = re.compile(
    r'(?:total\s*a\s*pagar|importe\s*a\s*pagar|total\s*facturado|'
    r'monto\s*total|pago\s*total|total\s*:)\s*[:\s]*\$?\s*([\d,]+\.?\d{0,2})',
    re.IGNORECASE,
)
_RE_MONTO_SUELTO = re.compile(r'\$\s*([\d,]+\.\d{2})', re.IGNORECASE)

def _extraer_monto_generico(texto: str) -> float | None:
    m = _RE_MONTO_CONTEXTO.search(texto)
    if m:
        return _limpiar_monto(m.group(1))
    # Toma el monto más grande encontrado con símbolo $
    candidatos = [_limpiar_monto(x) for x in _RE_MONTO_SUELTO.findall(texto)]
    candidatos = [v for v in candidatos if v is not None]
    return max(candidatos) if candidatos else None

_RE_FECHA_NUM = re.compile(
    r'(?:fecha\s*l[ií]mite|vence\s*el|vencimiento|pagar\s*antes\s*del|'
    r'limite\s*de\s*pago|fecha\s*limite)[^\d]{0,10}'
    r'(\d{1,2})[/\-\s](\d{1,2})[/\-\s](\d{2,4})',
    re.IGNORECASE,
)
_RE_FECHA_TXT = re.compile(
    r'(?:fecha\s*l[ií]mite|vence\s*el|vencimiento|pagar\s*antes\s*del|'
    r'limite\s*de\s*pago|fecha\s*limite)[^\d]{0,15}'
    r'(\d{1,2})\s+([A-Za-záéíóúüÁÉÍÓÚÜ]{3,12})\s+(\d{4})',
    re.IGNORECASE,
)

def _extraer_fecha_generica(texto: str) -> date | None:
    m = _RE_FECHA_NUM.search(texto)
    if m:
        return _fecha_numerica(m.group(1), m.group(2), m.group(3))
    m = _RE_FECHA_TXT.search(texto)
    if m:
        return _fecha_texto(m.group(1), m.group(2), m.group(3))
    return None


# ── Parsers específicos por proveedor ─────────────────────────────────────────
def _parse_cfe(texto: str):
    monto = None
    fecha = None

    # Monto opción 1: "IMPORTE A PAGAR $1,234.56" / "TOTAL A PAGAR 1,234.56"
    m = re.search(
        r'(?:importe|total)\s+a\s+pagar\s*\$?\s*([\d,]+\.?\d{0,2})',
        texto, re.IGNORECASE)
    if m:
        monto = _limpiar_monto(m.group(1))

    # Monto opción 2: "SS) 1,343.11" — OCR garbles "Total a pagar" en el resumen final
    # Patrón: pocos chars basura + ) + espacio + monto con centavos al final de línea
    if monto is None:
        m = re.search(
            r'^[A-Za-z\s]{0,8}\)\s*([\d,]+\.\d{2})\s*$',
            texto, re.MULTILINE)
        if m:
            monto = _limpiar_monto(m.group(1))

    # Monto opción 3: primer "$X,XXX" visible (monto prominente al inicio del recibo)
    if monto is None:
        m = re.search(r'\$\s*(\d[\d,]+\.?\d{0,2})', texto)
        if m:
            monto = _limpiar_monto(m.group(1))

    # Fecha opción 1: "FECHA LÍMITE DE PAGO 15/01/2025"
    m = re.search(
        r'(?:fecha\s+)?l[ií]mite\s+de\s+pago\s*:?\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})',
        texto, re.IGNORECASE)
    if m:
        fecha = _fecha_numerica(m.group(1), m.group(2), m.group(3))

    # Fecha opción 2: "LÍMITE DE PAGO:23 MAR 26" (formato real CFE — sin "fecha", con ":", año 2 dígitos)
    if not fecha:
        m = re.search(
            r'(?:fecha\s+)?l[ií]mite\s+de\s+pago\s*:?\s*(\d{1,2})\s+([A-Za-záéíóúÁÉÍÓÚ]{3,12})\s+(\d{2,4})',
            texto, re.IGNORECASE)
        if m:
            fecha = _fecha_texto(m.group(1), m.group(2), m.group(3))

    return monto, fecha


def _parse_sadm(texto: str):
    monto = None
    fecha = None

    # "TOTAL A PAGAR $1,234.56"  o "IMPORTE $1,234.56"
    m = re.search(
        r'(?:total\s+a\s+pagar|importe\s+total)\s*\$?\s*([\d,]+\.?\d{0,2})',
        texto, re.IGNORECASE)
    if m:
        monto = _limpiar_monto(m.group(1))

    # "PAGAR ANTES DEL 15 DE ENERO DE 2025"  o  "FECHA LÍMITE 15/01/2025"
    m = re.search(
        r'pagar\s+antes\s+del\s+(\d{1,2})\s+(?:de\s+)?([A-Za-záéíóú]{3,12})(?:\s+de)?\s+(\d{4})',
        texto, re.IGNORECASE)
    if m:
        fecha = _fecha_texto(m.group(1), m.group(2), m.group(3))
    if not fecha:
        m = re.search(
            r'fecha\s+l[ií]mite\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})',
            texto, re.IGNORECASE)
        if m:
            fecha = _fecha_numerica(m.group(1), m.group(2), m.group(3))

    return monto, fecha


def _parse_telmex(texto: str):
    monto = None
    fecha = None

    m = re.search(
        r'total\s+a\s+pagar\s*\$?\s*([\d,]+\.?\d{0,2})',
        texto, re.IGNORECASE)
    if m:
        monto = _limpiar_monto(m.group(1))

    # "Fecha límite de pago 15 Ene 2025"
    m = re.search(
        r'fecha\s+l[ií]mite\s+de\s+pago\s+(\d{1,2})\s+([A-Za-záéíóú]{3,12})\s+(\d{4})',
        texto, re.IGNORECASE)
    if m:
        fecha = _fecha_texto(m.group(1), m.group(2), m.group(3))
    if not fecha:
        m = re.search(
            r'fecha\s+l[ií]mite\s+de\s+pago\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})',
            texto, re.IGNORECASE)
        if m:
            fecha = _fecha_numerica(m.group(1), m.group(2), m.group(3))

    return monto, fecha


def _parse_totalplay(texto: str):
    monto = None
    fecha = None

    m = re.search(
        r'(?:total\s+a\s+pagar|monto\s+total|saldo\s+a\s+pagar)\s*\$?\s*([\d,]+\.?\d{0,2})',
        texto, re.IGNORECASE)
    if m:
        monto = _limpiar_monto(m.group(1))

    m = re.search(
        r'(?:fecha\s+l[ií]mite|fecha\s+de\s+vencimiento|vence)\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})',
        texto, re.IGNORECASE)
    if m:
        fecha = _fecha_numerica(m.group(1), m.group(2), m.group(3))
    if not fecha:
        m = re.search(
            r'(?:fecha\s+l[ií]mite|fecha\s+de\s+vencimiento|vence)\s+(\d{1,2})\s+([A-Za-záéíóú]{3,12})\s+(\d{4})',
            texto, re.IGNORECASE)
        if m:
            fecha = _fecha_texto(m.group(1), m.group(2), m.group(3))

    return monto, fecha


_PARSERS = {
    'cfe':       _parse_cfe,
    'sadm':      _parse_sadm,
    'telmex':    _parse_telmex,
    'totalplay': _parse_totalplay,
}

NOMBRES_PROVEEDOR = {
    'cfe':       'CFE',
    'sadm':      'Agua y Drenaje Monterrey',
    'telmex':    'Telmex',
    'totalplay': 'TotalPlay',
    'desconocido': 'Desconocido',
}


# ── Punto de entrada principal ────────────────────────────────────────────────
def analizar_recibo(texto: str) -> dict:
    """
    Analiza el texto OCR de un recibo y devuelve:
    {
        proveedor: str,
        nombre_proveedor: str,
        monto: float | None,
        fecha_vencimiento: str (YYYY-MM-DD) | None,
        confianza: 'alta' | 'media' | 'baja',
    }
    """
    proveedor = detectar_proveedor(texto)
    parser    = _PARSERS.get(proveedor)

    if parser:
        monto, fecha = parser(texto)
    else:
        monto, fecha = None, None

    # Fallback genérico si el parser específico no encontró algo
    if monto is None:
        monto = _extraer_monto_generico(texto)
    if fecha is None:
        fecha = _extraer_fecha_generica(texto)

    conocido    = proveedor != 'desconocido'
    tiene_monto = monto is not None
    tiene_fecha = fecha is not None

    if conocido and tiene_monto and tiene_fecha:
        confianza = 'alta'
    elif tiene_monto or tiene_fecha:
        confianza = 'media'
    else:
        confianza = 'baja'

    return {
        'proveedor':        proveedor,
        'nombre_proveedor': NOMBRES_PROVEEDOR.get(proveedor, 'Desconocido'),
        'monto':            round(monto, 2) if monto else None,
        'fecha_vencimiento': fecha.strftime('%Y-%m-%d') if fecha else None,
        'confianza':        confianza,
    }
