"""
Publicación en Facebook (Meta Graph API).

Requiere:
- FACEBOOK_PAGE_ID: el ID numérico de tu página de Facebook
- FACEBOOK_PAGE_ACCESS_TOKEN: token de acceso de la página (de larga duración)

Cómo conseguirlos (resumen -- el detalle completo está en el README):
1. Crea una app en https://developers.facebook.com
2. En "Graph API Explorer", selecciona tu página, pide los permisos
   pages_manage_posts y pages_read_engagement
3. Genera un token de página y conviértelo a uno de larga duración
   (sin esto, el token expira en ~1-2 horas)
"""

import re
import html
import requests

from config import FACEBOOK_PAGE_ID, FACEBOOK_PAGE_ACCESS_TOKEN

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


def _html_a_texto_plano(texto_html):
    """
    El texto que arma revisar_canales.py trae etiquetas HTML (<b>, <a href>)
    pensadas para Telegram (parse_mode=HTML) -- Facebook no las interpreta,
    las muestra literal. Aquí se limpian: los enlaces <a href="URL">texto</a>
    se convierten en "texto: URL" (para no perder el link), y el resto de
    etiquetas simplemente se quitan.
    """
    texto = re.sub(
        r'<a\s+href="([^"]+)">(.*?)</a>',
        lambda m: f"{m.group(2)}: {m.group(1)}",
        texto_html,
    )
    texto = re.sub(r"<[^>]+>", "", texto)
    return html.unescape(texto)


def publicar_facebook(texto, imagen_bytes=None):
    if not FACEBOOK_PAGE_ID or not FACEBOOK_PAGE_ACCESS_TOKEN:
        print("[SKIP] Facebook no configurado todavía")
        return

    texto = _html_a_texto_plano(texto)

    try:
        if imagen_bytes:
            url = f"{GRAPH_API_BASE}/{FACEBOOK_PAGE_ID}/photos"
            files = {"source": ("oferta.jpg", imagen_bytes, "image/jpeg")}
            data = {"caption": texto, "access_token": FACEBOOK_PAGE_ACCESS_TOKEN}
            resp = requests.post(url, data=data, files=files, timeout=30)
        else:
            url = f"{GRAPH_API_BASE}/{FACEBOOK_PAGE_ID}/feed"
            data = {"message": texto, "access_token": FACEBOOK_PAGE_ACCESS_TOKEN}
            resp = requests.post(url, data=data, timeout=30)

        if resp.status_code != 200:
            print(f"[WARN] Facebook respondió con error: {resp.text}")
    except Exception as e:
        print(f"[ERROR] Fallo al publicar en Facebook: {e}")
