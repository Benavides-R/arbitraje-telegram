"""
Busca ofertas de AliExpress directo de su API (sin depender de canales de
Telegram), y las manda a revisión manual -- nunca automático, aunque
vengan completas, porque es contenido nuevo sin validar todavía.
"""

import os
import time
import hashlib
import requests

from aliexpress_afiliado import APP_KEY, APP_SECRET, ENDPOINT, _firmar

LIMITE_POR_CORRIDA = 5


def obtener_ofertas_calientes():
    if not APP_KEY or not APP_SECRET:
        return []

    params = {
        "app_key": APP_KEY,
        "method": "aliexpress.affiliate.hotproduct.query",
        "sign_method": "md5",
        "timestamp": str(int(time.time() * 1000)),
        "v": "2.0",
        "format": "json",
        "page_size": str(LIMITE_POR_CORRIDA),
        "target_currency": "USD",
        "target_language": "ES",
    }
    params["sign"] = _firmar(params)

    try:
        resp = requests.get(ENDPOINT, params=params, timeout=15).json()
        productos = (
            resp.get("aliexpress_affiliate_hotproduct_query_response", {})
            .get("resp_result", {})
            .get("result", {})
            .get("products", {})
            .get("product", [])
        )
        ofertas = []
        for p in productos:
            ofertas.append({
                "id": str(p.get("product_id")),
                "titulo": p.get("product_title", "Producto AliExpress"),
                "precio": f"${p.get('target_sale_price')} {p.get('target_sale_price_currency', 'USD')}",
                "imagen": p.get("product_main_image_url"),
                "link": p.get("promotion_link") or p.get("product_detail_url"),
            })
        return ofertas
    except Exception as e:
        print(f"[WARN] Fallo consultando ofertas calientes de AliExpress: {e}")
        return []


def construir_texto(oferta):
    return (
        f"📦 <b>Producto:</b> {oferta['titulo'][:120]}\n\n"
        f"💸 Precio: {oferta['precio']}\n"
        f"🏷️ Cupón: ¡No necesita!\n"
        f"🔗 Ir a la tienda: {oferta['link']}\n\n"
        f"⚠️ La oferta puede expirar en cualquier momento.\n#ad"
    )
