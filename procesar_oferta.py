"""
Funciones para:
1. Resolver un link que pasa por páginas intermedias hasta llegar a la tienda real
2. Extraer la foto oficial del producto desde la tienda
3. Ponerle tu logo encima antes de publicar
"""

import re
import io
import requests
from PIL import Image

from config import DOMINIOS_TIENDA_FINAL, LOGO_PATH

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def es_tienda_final(url):
    return any(dominio in url for dominio in DOMINIOS_TIENDA_FINAL)


def resolver_link_final(url):
    """
    Sigue redirects hasta llegar a la tienda real.
    Intenta primero con un request simple (rápido, cubre la mayoría de casos:
    sitio propio con redirect de servidor). Si no llega a un dominio de
    tienda conocido, intenta con navegador headless (cubre redirects hechos
    con JavaScript, típico de páginas "landing" antes del link final).
    Nota: links de Facebook son los más propensos a fallar aquí -- Facebook
    bloquea navegación automatizada agresivamente.
    """
    # Intento 1: redirect simple por HTTP
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if es_tienda_final(resp.url):
            return resp.url
    except Exception as e:
        print(f"[WARN] Redirect simple falló para {url}: {e}")

    # Intento 2: navegador headless, para redirects hechos con JS
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(extra_http_headers=HEADERS)
            page.goto(url, timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(2000)

            if es_tienda_final(page.url):
                resultado = page.url
            else:
                # busca un enlace clicable que ya apunte a una tienda conocida
                resultado = None
                for enlace in page.query_selector_all("a"):
                    href = enlace.get_attribute("href") or ""
                    if es_tienda_final(href):
                        resultado = href
                        break

            browser.close()
            return resultado
    except Exception as e:
        print(f"[WARN] Resolución con navegador falló para {url}: {e}")
        return None


def extraer_imagen_producto(url_tienda):
    """
    Extrae la URL de la foto oficial del producto (meta tag og:image, o
    directamente la imagen principal del producto si el meta tag no está).
    Primero intenta con un request simple (rápido). Amazon en particular
    suele bloquear ese request simple (lo detecta como bot) -- en ese caso
    reintenta con navegador headless con más señales de "navegador real".
    Nota: Amazon bloquea agresivamente los IPs de servidores en la nube
    (incluido GitHub Actions), así que esto puede seguir fallando para
    varios productos incluso con este intento -- es una limitación conocida
    del scraping gratuito, no un bug puntual.
    """
    try:
        resp = requests.get(url_tienda, headers=HEADERS, timeout=15)
        match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', resp.text)
        if match:
            return match.group(1)
    except Exception as e:
        print(f"[WARN] Request simple para imagen falló ({url_tienda}): {e}")

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = browser.new_page(
                extra_http_headers=HEADERS,
                viewport={"width": 1366, "height": 900},
                locale="es-US",
            )
            page.goto(url_tienda, timeout=30000, wait_until="load")
            page.wait_for_timeout(2500)

            contenido = None
            elemento = page.query_selector('meta[property="og:image"]')
            if elemento:
                contenido = elemento.get_attribute("content")

            if not contenido:
                # Respaldo: la imagen principal del producto en la página de Amazon
                for selector in ["#landingImage", "#imgBlkFront", ".a-dynamic-image"]:
                    img = page.query_selector(selector)
                    if img:
                        contenido = img.get_attribute("src")
                        if contenido:
                            break

            browser.close()
            return contenido
    except Exception as e:
        print(f"[WARN] No se pudo extraer imagen con navegador ({url_tienda}): {e}")
        return None


def preparar_imagen_con_logo(url_imagen_producto):
    """
    Descarga la imagen del producto, le superpone tu logo en la esquina
    inferior derecha, y devuelve los bytes de la imagen final en memoria
    (no se guarda en disco, para no acumular archivos en el hosting).
    """
    try:
        img_resp = requests.get(url_imagen_producto, headers=HEADERS, timeout=15)
        producto = Image.open(io.BytesIO(img_resp.content)).convert("RGBA")

        logo = Image.open(LOGO_PATH).convert("RGBA")
        # Redimensiona el logo a ~15% del ancho de la imagen del producto
        ancho_logo = int(producto.width * 0.15)
        alto_logo = int(logo.height * (ancho_logo / logo.width))
        logo = logo.resize((ancho_logo, alto_logo))

        posicion = (producto.width - ancho_logo - 15, producto.height - alto_logo - 15)
        producto.paste(logo, posicion, logo)  # usa el canal alfa del logo como máscara

        buffer = io.BytesIO()
        producto.convert("RGB").save(buffer, format="JPEG", quality=90)
        buffer.seek(0)
        return buffer
    except Exception as e:
        print(f"[WARN] No se pudo preparar imagen con logo: {e}")
        return None
