"""
Integración con Oferta Radar (tu página) -- salida ADICIONAL después de que
una oferta se aprueba (o se publica automática por venir completa).

No reemplaza ni modifica Telegram ni Facebook: se llama DESPUÉS de esos dos,
y si falla, no los afecta -- solo se registra el error en el log.

Requiere en GitHub Secrets:
  OFERTA_RADAR_API_KEY
  OFERTA_RADAR_URL   (URL base de tu página, ej. https://ofertaradar.com)

Si cualquiera de las dos falta, este módulo simplemente no envía nada
(no rompe el resto del flujo).
"""

import re
import json
import html
import time
import requests
from pathlib import Path

from config import OFERTA_RADAR_API_KEY, OFERTA_RADAR_URL

TIMEOUT_SEGUNDOS = 20
COLA_FILE = Path(__file__).parent / "data" / "oferta_radar_pendientes.json"
MAX_INTENTOS = 5  # después de esto, se deja de reintentar (probablemente el dato está mal, no es un problema pasajero)

# Mismo formato que arma reescribir_texto() en revisar_canales.py -- si ese
# formato cambia algún día, estos patrones hay que actualizarlos junto con él.
_RE_PRODUCTO = re.compile(r"📦\s*<b>Producto:</b>\s*(.+)")
_RE_CALIFICACION = re.compile(r"⭐️?\s*Calificación:\s*([\d.,]+)\s*\(([\d.,]+)\)")
_RE_PRECIO = re.compile(r"💸\s*Precio:\s*(.+)")
_RE_CUPON_CON_CODIGO = re.compile(r"🏷️?\s*Cupón:\s*<code>(.+?)</code>")
_RE_LINK = re.compile(r"⚡\s*Ver oferta:\s*(\S+)")
_RE_HASHTAGS = re.compile(r"#ad\s+(.+)")
_RE_ASIN_EN_LINK = re.compile(r"/dp/([A-Za-z0-9]{10})", re.IGNORECASE)


def _parsear_precio(precio_texto):
    """
    Convierte '$159.895 COP' o '$45.99 USD' (el formato que arma
    extraer_precio) a (numero, moneda). Si no se detecta moneda explícita
    en el texto, se asume COP (mercado principal de este proyecto) -- se
    documenta la asunción en vez de dejarlo en blanco, ya que la API
    necesita un valor numérico de todas formas.
    """
    if not precio_texto:
        return None, None

    texto = precio_texto.strip()
    match_moneda = re.search(r"\b(COP|USD|MXN|JPY|PEN|ARS|CLP)\b", texto)
    moneda = match_moneda.group(1) if match_moneda else "COP"

    solo_numero = re.sub(r"[^\d.,]", "", texto)
    if not solo_numero:
        return None, moneda

    # ¿El último grupo tras un separador tiene 1-2 dígitos? -> es decimal
    # (centavos), no separador de miles (ej. "45.99" USD).
    partes = re.split(r"[.,]", solo_numero)
    if len(partes) > 1 and len(partes[-1]) in (1, 2):
        entero = "".join(partes[:-1])
        numero = float(f"{entero}.{partes[-1]}")
    else:
        numero = int("".join(partes))

    return numero, moneda


def _extraer_datos_de_texto(texto_nuevo):
    """Lee de vuelta los campos estructurados del mensaje final ya
    aprobado (el mismo que se publicó en Telegram/Facebook) -- así se
    respeta cualquier corrección manual que se le haya hecho antes de
    aprobar, sin tener que rehacer la extracción por separado."""
    datos = {
        "product": None, "rating": None, "reviews": None,
        "price": None, "currency": None, "coupon": None,
        "affiliateUrl": None, "amazonUrl": None, "externalId": None,
        "category": None,
    }

    m = _RE_PRODUCTO.search(texto_nuevo)
    if m:
        titulo_completo = html.unescape(m.group(1)).strip()
        # Oferta Radar tiene un límite de 160 caracteres para el título --
        # si se pasa, la API respondía con error 500 y la oferta se perdía.
        datos["product"] = titulo_completo if len(titulo_completo) <= 160 else titulo_completo[:157].rstrip() + "..."

    m = _RE_CALIFICACION.search(texto_nuevo)
    if m:
        try:
            datos["rating"] = float(m.group(1).replace(",", "."))
            datos["reviews"] = int(re.sub(r"[.,]", "", m.group(2)))
        except ValueError:
            pass  # no se pudo interpretar -- se deja en None, no se inventa

    m = _RE_PRECIO.search(texto_nuevo)
    if m:
        datos["price"], datos["currency"] = _parsear_precio(html.unescape(m.group(1)))

    m = _RE_CUPON_CON_CODIGO.search(texto_nuevo)
    if m:
        datos["coupon"] = html.unescape(m.group(1)).strip()[:80]
    # si no hay <code>...</code>, coupon se queda en None (-> null en el JSON)

    m = _RE_LINK.search(texto_nuevo)
    if m:
        link = html.unescape(m.group(1)).strip()
        datos["affiliateUrl"] = link
        m_asin = _RE_ASIN_EN_LINK.search(link)
        if m_asin:
            asin = m_asin.group(1).upper()
            datos["externalId"] = asin
            netloc = re.match(r"https?://([^/]+)", link)
            if netloc:
                datos["amazonUrl"] = f"https://{netloc.group(1)}/dp/{asin}"

    m = _RE_HASHTAGS.search(texto_nuevo)
    if m:
        primer_tag = m.group(1).strip().split()[0]
        datos["category"] = primer_tag.lstrip("#")[:50]

    return datos


def _cargar_cola():
    if COLA_FILE.exists():
        try:
            return json.loads(COLA_FILE.read_text())
        except Exception:
            return []
    return []


def _guardar_cola(cola):
    COLA_FILE.parent.mkdir(parents=True, exist_ok=True)
    COLA_FILE.write_text(json.dumps(cola, indent=2, ensure_ascii=False))


def _enviar_payload(payload):
    """Hace el POST real y decide qué significa la respuesta. Devuelve
    True si ya quedó resuelto (se creó bien, o ya existía -- duplicado),
    False si hay que reintentar más adelante."""
    try:
        resp = requests.post(
            f"{OFERTA_RADAR_URL.rstrip('/')}/api/offers/import",
            headers={
                "Authorization": f"Bearer {OFERTA_RADAR_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=TIMEOUT_SEGUNDOS,
        )
    except Exception as e:
        # Nunca se imprime la API key -- solo el tipo de problema de red.
        print(f"Oferta Radar: error al importar (sin conexión/timeout, se reintentará: {e})")
        return False

    if resp.status_code == 409:
        print("Oferta Radar: DUPLICATE")
        return True

    if not resp.ok:
        # Se registra el código y la respuesta, pero la API key nunca viaja
        # en la respuesta del servidor, así que no hay riesgo de imprimirla.
        print(f"Oferta Radar: error al importar (HTTP {resp.status_code}, se reintentará): {resp.text[:300]}")
        return False

    try:
        cuerpo = resp.json()
    except ValueError:
        cuerpo = {}

    if cuerpo.get("duplicate"):
        print("Oferta Radar: DUPLICATE")
        return True

    print("Oferta Radar: OK")
    if cuerpo.get("id"):
        print(f"Oferta Radar ID: {cuerpo['id']}")
    if cuerpo.get("url"):
        print(f"Oferta Radar URL: {cuerpo['url']}")
    return True


def reintentar_pendientes():
    """Reintenta las ofertas que fallaron al importar en corridas
    anteriores (ej. el error 500 por título muy largo, o Oferta Radar
    caído un rato) -- se llama UNA vez al principio de cada corrida,
    antes de procesar ofertas nuevas."""
    if not OFERTA_RADAR_API_KEY or not OFERTA_RADAR_URL:
        return
    cola = _cargar_cola()
    if not cola:
        return

    print(f"[Oferta Radar] Reintentando {len(cola)} oferta(s) pendiente(s) de corridas anteriores...")
    quedan = []
    for item in cola:
        if _enviar_payload(item["payload"]):
            continue  # resuelto (OK o duplicado) -- se saca de la cola
        item["intentos"] = item.get("intentos", 1) + 1
        if item["intentos"] < MAX_INTENTOS:
            quedan.append(item)
        else:
            print(f"[Oferta Radar] Se descarta tras {MAX_INTENTOS} intentos fallidos: {item['payload'].get('product')}")
    _guardar_cola(quedan)


def enviar_a_oferta_radar(texto_nuevo, url_imagen):
    """
    Envía la oferta ya aprobada a Oferta Radar. Se llama DESPUÉS de
    publicar en Telegram/Facebook y nunca lanza una excepción hacia
    afuera -- cualquier problema queda solo en el log.
    """
    if not OFERTA_RADAR_API_KEY or not OFERTA_RADAR_URL:
        return  # integración no configurada todavía -- no hace nada

    if not url_imagen:
        # No se descarga ni se genera otra imagen -- si la oferta se
        # aprobó con una foto subida a mano (sin URL pública), simplemente
        # no se manda a Oferta Radar esta vez.
        print("[Oferta Radar] SKIP: la oferta no tiene una URL de imagen pública")
        return

    datos = _extraer_datos_de_texto(texto_nuevo)
    if not datos["product"] or not datos["price"]:
        print("[Oferta Radar] SKIP: no se pudieron leer los datos mínimos del mensaje aprobado")
        return

    payload = {
        "externalId": datos["externalId"],
        "product": datos["product"],
        "rating": datos["rating"],
        "reviews": datos["reviews"],
        "price": datos["price"],
        "currency": datos["currency"] or "COP",
        "affiliateUrl": datos["affiliateUrl"],
        "amazonUrl": datos["amazonUrl"],
        "imageUrl": url_imagen,
        "category": datos["category"] or "Ofertas",
        "coupon": datos["coupon"],
        "source": "github",
        "approved": True,
    }

    if not _enviar_payload(payload):
        cola = _cargar_cola()
        cola.append({"payload": payload, "intentos": 1, "guardado": time.time()})
        _guardar_cola(cola)
        print("[Oferta Radar] Se guardó para reintentar en la próxima corrida")
