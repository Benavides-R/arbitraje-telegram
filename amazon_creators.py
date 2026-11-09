"""
Cliente mínimo de la Amazon Creators API (credenciales v3.1 = región NA:
amazon.com, .ca, .com.mx, .com.br; autenticación Login with Amazon, OAuth2
client-credentials).

Uso desde el resto del proyecto:
    from amazon_creators import obtener_item
    datos = obtener_item("B0XXXXXXXX")   # dict o None
    # datos = {"titulo": ..., "imagen": ..., "precio": 12.99, "moneda": "USD"}

Reglas de diseño:
- NUNCA lanza excepciones hacia afuera: si algo falla devuelve None y el
  flujo sigue con el método anterior (scraping). La API es un "plus", no
  un punto único de falla.
- NUNCA imprime el token ni el secreto (los logs de GitHub Actions pueden
  ser públicos si el repo es público).
- Solo se activa si existen los Secrets CREATORS_CREDENTIAL_ID y
  CREATORS_CREDENTIAL_SECRET. Sin ellos, no hace nada.
"""

import os
import time
import requests

CREDENTIAL_ID = os.environ.get("CREATORS_CREDENTIAL_ID")
CREDENTIAL_SECRET = os.environ.get("CREATORS_CREDENTIAL_SECRET")
PARTNER_TAG = os.environ.get("CREATORS_PARTNER_TAG", "benatechs00-20")

# v3.1 (NA). Solo cambia de dónde se pide el token.
TOKEN_URL = "https://api.amazon.com/auth/o2/token"
GET_ITEMS_URL = "https://creatorsapi.amazon/catalog/v1/getItems"
MARKETPLACE = "www.amazon.com"

# Segundos mínimos entre llamadas (Amazon no publica el límite exacto).
SEGUNDOS_ENTRE_LLAMADAS = 1.1
# Tras un 429/403 de la API, no se vuelve a llamar en el resto de la corrida
# (evita insistir y que te limiten más).
_bloqueada_hasta = 0.0

_token = {"valor": None, "expira": 0.0}
_ultima_llamada = 0.0


def disponible():
    return bool(CREDENTIAL_ID and CREDENTIAL_SECRET)


def _obtener_token():
    """Token OAuth (dura 3600 s). Se reutiliza dentro de la misma corrida."""
    if _token["valor"] and time.time() < _token["expira"] - 60:
        return _token["valor"]
    resp = requests.post(
        TOKEN_URL,
        json={
            "grant_type": "client_credentials",
            "client_id": CREDENTIAL_ID,
            "client_secret": CREDENTIAL_SECRET,
            "scope": "creatorsapi::default",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        # Solo el código y el tipo de error, nunca el cuerpo completo.
        try:
            tipo = resp.json().get("error", "?")
        except Exception:
            tipo = "?"
        raise RuntimeError(f"token HTTP {resp.status_code} ({tipo})")
    datos = resp.json()
    _token["valor"] = datos["access_token"]
    _token["expira"] = time.time() + int(datos.get("expires_in", 3600))
    return _token["valor"]


def _g(d, *claves):
    """Lee d[clave] probando camelCase y snake_case; None si no existe."""
    for c in claves:
        if isinstance(d, dict) and c in d:
            return d[c]
    return None


def obtener_item(asin):
    """Datos oficiales de un ASIN en amazon.com, o None si no se pudo."""
    global _ultima_llamada, _bloqueada_hasta
    if not disponible() or not asin:
        return None
    if time.time() < _bloqueada_hasta:
        return None

    try:
        espera = SEGUNDOS_ENTRE_LLAMADAS - (time.time() - _ultima_llamada)
        if espera > 0:
            time.sleep(espera)
        _ultima_llamada = time.time()

        resp = requests.post(
            GET_ITEMS_URL,
            headers={
                "Authorization": f"Bearer {_obtener_token()}",
                "Content-Type": "application/json",
                "x-marketplace": MARKETPLACE,
            },
            json={
                "itemIds": [asin],
                "itemIdType": "ASIN",
                "marketplace": MARKETPLACE,
                "partnerTag": PARTNER_TAG,
                "resources": [
                    "itemInfo.title",
                    "images.primary.large",
                    "offersV2.listings.price",
                ],
            },
            timeout=15,
        )
        if resp.status_code in (429, 403):
            _bloqueada_hasta = time.time() + 15 * 60
            print(f"[WARN] Creators API respondió {resp.status_code}: "
                  f"se pausa 15 min y se usa el método anterior")
            return None
        if resp.status_code != 200:
            print(f"[WARN] Creators API respondió {resp.status_code} para {asin}")
            return None

        cuerpo = resp.json()
        resultado = _g(cuerpo, "itemsResult", "items_result") or {}
        items = _g(resultado, "items") or []
        if not items:
            # Sin ítems = el ASIN no existe / no está disponible en amazon.com.
            return None
        item = items[0]

        titulo = _g(_g(_g(item, "itemInfo", "item_info") or {}, "title") or {},
                    "displayValue", "display_value")
        imagen = _g(_g(_g(_g(item, "images") or {}, "primary") or {}, "large") or {}, "url")

        precio, moneda = None, None
        listings = _g(_g(item, "offersV2", "offers_v2") or {}, "listings") or []
        if listings:
            dinero = _g(_g(listings[0], "price") or {}, "money") or {}
            precio = _g(dinero, "amount")
            moneda = _g(dinero, "currency")

        return {"titulo": titulo, "imagen": imagen, "precio": precio, "moneda": moneda}

    except Exception as e:
        # Mensaje corto, sin volcar headers/cuerpos (pueden llevar el token).
        print(f"[WARN] Creators API falló para {asin}: {type(e).__name__}: {e}")
        return None
