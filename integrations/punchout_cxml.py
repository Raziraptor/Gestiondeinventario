"""
cXML PunchOut — lado del comprador.

Protocolo estándar B2B para integración con catálogos de proveedores.
Soporta: Home Depot Pro directo (≥$50K/año) o TradeCentric como gateway.

Flujo:
  1. build_setup_request() → XML del PunchOutSetupRequest
  2. send_setup_request()  → POST a proveedor, retorna URL de sesión autenticada
  3. Usuario navega el catálogo del proveedor en browser
  4. parse_order_message() → parsea PunchOutOrderMessage recibido en /api/punchout/retorno
"""

import uuid
import secrets
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import requests


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')


def _payload_id(domain: str = 'inventario.local') -> str:
    ts = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    rand = secrets.token_hex(8)
    return f"{ts}.{rand}@{domain}"


def build_setup_request(
    network_id: str,
    shared_secret: str,
    buyer_cookie: str,
    return_url: str,
    user_email: str,
    user_name: str,
    supplier_identity: str = 'HomeDepot',
    domain: str = 'inventario.local',
) -> str:
    """
    Genera el XML de PunchOutSetupRequest (cXML 1.2).

    Args:
        network_id:        Buyer Network ID otorgado por HD / TradeCentric
        shared_secret:     Shared Secret para autenticación del header
        buyer_cookie:      UUID único de la sesión (lo devolvemos en el retorno)
        return_url:        URL HTTPS donde HD hará POST con el carrito
        user_email:        Email del usuario que inicia la sesión
        user_name:         Nombre del usuario
        supplier_identity: Identity del proveedor en cXML (por defecto 'HomeDepot')
        domain:            Dominio de tu sistema (para payloadID)

    Returns:
        XML string listo para enviar vía POST a la PunchOut URL del proveedor
    """
    payload_id = _payload_id(domain)
    timestamp = _now_iso()

    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE cXML SYSTEM "http://xml.cxml.org/schemas/cXML/1.2.014/cXML.dtd">
<cXML version="1.2.014" payloadID="{payload_id}" timestamp="{timestamp}">
  <Header>
    <From>
      <Credential domain="NetworkID">
        <Identity>{network_id}</Identity>
      </Credential>
    </From>
    <To>
      <Credential domain="NetworkID">
        <Identity>{supplier_identity}</Identity>
      </Credential>
    </To>
    <Sender>
      <Credential domain="NetworkID">
        <Identity>{network_id}</Identity>
        <SharedSecret>{shared_secret}</SharedSecret>
      </Credential>
      <UserAgent>GestionInventario/1.0</UserAgent>
    </Sender>
  </Header>
  <Request deploymentMode="production">
    <PunchOutSetupRequest operation="create">
      <BuyerCookie>{buyer_cookie}</BuyerCookie>
      <Extrinsic name="UserEmail">{user_email}</Extrinsic>
      <Extrinsic name="FirstName">{user_name.split()[0] if user_name else ''}</Extrinsic>
      <Extrinsic name="LastName">{' '.join(user_name.split()[1:]) if user_name else ''}</Extrinsic>
      <BrowserFormPost>
        <URL>{return_url}</URL>
      </BrowserFormPost>
      <Contact role="endUser">
        <Name xml:lang="en-US">{user_name}</Name>
        <Email>{user_email}</Email>
      </Contact>
    </PunchOutSetupRequest>
  </Request>
</cXML>'''
    return xml


def send_setup_request(punchout_url: str, xml_body: str, timeout: int = 15) -> str:
    """
    Envía PunchOutSetupRequest y extrae la URL de sesión del response.

    Returns:
        URL de sesión autenticada a la que redirigir al usuario

    Raises:
        RuntimeError si la respuesta es un error cXML o HTTP no-200
    """
    headers = {
        'Content-Type': 'text/xml; charset=UTF-8',
        'Accept': 'text/xml',
    }
    resp = requests.post(punchout_url, data=xml_body.encode('utf-8'),
                         headers=headers, timeout=timeout)
    resp.raise_for_status()

    root = ET.fromstring(resp.text)
    # Verificar código de respuesta cXML
    response_el = root.find('.//Response')
    status_el = root.find('.//Response/Status') if response_el is not None else None
    if status_el is not None:
        code = status_el.get('code', '200')
        if not code.startswith('2'):
            msg = status_el.text or status_el.get('text', 'Error desconocido')
            raise RuntimeError(f"cXML error {code}: {msg}")

    url_el = root.find('.//PunchOutSetupResponse/StartPage/URL')
    if url_el is None or not url_el.text:
        raise RuntimeError('PunchOutSetupResponse no contiene StartPage/URL')

    return url_el.text.strip()


def parse_order_message(xml_body: str) -> list[dict]:
    """
    Parsea PunchOutOrderMessage recibido del proveedor.

    El XML puede llegar como body directo o como valor del campo 'cxml-urlencoded'.

    Returns:
        Lista de ítems: [{sku, nombre, cantidad, precio_unitario, moneda, unidad}]
    """
    try:
        root = ET.fromstring(xml_body)
    except ET.ParseError as e:
        raise ValueError(f"XML inválido en PunchOutOrderMessage: {e}")

    items = []
    ns = {}  # cXML no usa namespaces en la mayoría de implementaciones

    for item_in in root.findall('.//ItemIn'):
        cantidad_str = item_in.get('quantity', '1')
        try:
            cantidad = int(float(cantidad_str))
        except ValueError:
            cantidad = 1

        sku = ''
        supplier_part = item_in.find('.//ItemID/SupplierPartID')
        if supplier_part is not None and supplier_part.text:
            sku = supplier_part.text.strip()

        nombre = ''
        desc = item_in.find('.//ItemDetail/Description')
        if desc is not None and desc.text:
            nombre = desc.text.strip()

        precio = 0.0
        money = item_in.find('.//ItemDetail/UnitPrice/Money')
        if money is not None and money.text:
            try:
                precio = float(money.text.strip())
            except ValueError:
                pass

        moneda = 'USD'
        if money is not None:
            moneda = money.get('currency', 'USD')

        unidad = 'EA'
        uom = item_in.find('.//ItemDetail/UnitOfMeasure')
        if uom is not None and uom.text:
            unidad = uom.text.strip()

        items.append({
            'sku': sku,
            'nombre': nombre,
            'cantidad': cantidad,
            'precio_unitario': precio,
            'moneda': moneda,
            'unidad': unidad,
        })

    return items


def extract_buyer_cookie(xml_body: str) -> str:
    """Extrae el BuyerCookie del PunchOutOrderMessage para identificar la sesión."""
    try:
        root = ET.fromstring(xml_body)
        cookie_el = root.find('.//BuyerCookie')
        if cookie_el is not None and cookie_el.text:
            return cookie_el.text.strip()
    except ET.ParseError:
        pass
    return ''
