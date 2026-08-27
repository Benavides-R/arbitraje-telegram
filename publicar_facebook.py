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

import requests

from config import FACEBOOK_PAGE_ID, FACEBOOK_PAGE_ACCESS_TOKEN

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


def publicar_facebook(texto, imagen_bytes=None):
    if not FACEBOOK_PAGE_ID or not FACEBOOK_PAGE_ACCESS_TOKEN:
        print("[SKIP] Facebook no configurado todavía")
        return

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
