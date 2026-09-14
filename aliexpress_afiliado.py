"""
Genera links de afiliado de AliExpress usando su API oficial
(aliexpress.affiliate.link.generate), que requiere firma MD5.

Variables de entorno necesarias:
- ALIEXPRESS_APP_KEY
- ALIEXPRESS_APP_SECRET
"""

import os
import time
import hashlib
import requests

from procesar_oferta import resolver_link_final

APP_KEY = os.environ.get("ALIEXPRESS_APP_KEY")
APP_SECRET = os.environ.get("ALIEXPRESS_APP_SECRET")
ENDPOINT = "https://api-sg.aliexpress.com/sync"


def _firmar(params):
    ordenado = "".join(f"{k}{v}" for k, v in sorted(params.items()))
    cadena = f"{APP_SECRET}{ordenado}{APP_SECRET}"
    return hashlib.md5(cadena.encode("utf-8")).hexdigest().upper()


def generar_link_afiliado_aliexpress(link_producto):
    if not APP_KEY or not APP_SECRET:
        return link_producto, False  # sin credenciales: se publica tal cual

    link_para_api = link_producto
    if "s.click.aliexpress.com" in link_producto:
        # Es un link corto (probablemente ya es el link de afiliado de OTRA
        # persona) -- se resuelve primero al producto real antes de pedirle
        # a la API que genere el TUYO.
        resuelto = resolver_link_final(link_producto)
        if resuelto:
            link_para_api = resuelto

    params = {
        "app_key": APP_KEY,
        "method": "aliexpress.affiliate.link.generate",
        "sign_method": "md5",
        "timestamp": str(int(time.time() * 1000)),
        "v": "2.0",
        "format": "json",
        "promotion_link_type": "0",
        "source_values": link_para_api,
    }
    params["sign"] = _firmar(params)

    try:
        resp = requests.get(ENDPOINT, params=params, timeout=15).json()
        resultado = (
            resp.get("aliexpress_affiliate_link_generate_response", {})
            .get("resp_result", {})
            .get("result", {})
            .get("promotion_links", {})
            .get("promotion_link", [])
        )
        if resultado:
            return resultado[0]["promotion_link"], True
        print(f"[WARN] AliExpress no devolvió link de afiliado: {resp}")
    except Exception as e:
        print(f"[WARN] Fallo generando link de afiliado AliExpress: {e}")

    # No se pudo generar TU link -- no se publica el original a ciegas
    # (podría ser el de comisión de otra persona).
    return None, False
