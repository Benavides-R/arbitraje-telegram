"""
Funciones para:
1. Resolver un link que pasa por páginas intermedias hasta llegar a la tienda real
2. Extraer la foto oficial del producto desde la tienda
3. Ponerle tu logo encima antes de publicar
"""

import re
import io
import requests
from PIL import Image, ImageDraw, ImageFont

from config import DOMINIOS_TIENDA_FINAL, LOGO_PATH, REDES_SOCIALES_LINEAS

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


TAMANO_ESTANDAR = 1080  # cuadrado, el formato que mejor se ve en FB/Instagram


def _recortar_cuadrado_centrado(imagen):
    """
    Encaja la imagen COMPLETA dentro de un cuadrado blanco (sin cortar
    nada), centrada -- antes se recortaba a la fuerza y con fotos que no
    eran cuadradas (ej. varios productos en fila) se perdían los bordes.
    """
    imagen = imagen.convert("RGBA")
    imagen.thumbnail((TAMANO_ESTANDAR, TAMANO_ESTANDAR), Image.LANCZOS)

    fondo = Image.new("RGBA", (TAMANO_ESTANDAR, TAMANO_ESTANDAR), (255, 255, 255, 255))
    posicion = ((TAMANO_ESTANDAR - imagen.width) // 2, (TAMANO_ESTANDAR - imagen.height) // 2)
    fondo.paste(imagen, posicion, imagen)
    return fondo


def _cargar_fuente(tamano):
    """Busca una fuente bold del sistema (los runners de GitHub Actions/
    Ubuntu la traen preinstalada); si no la encuentra, usa la fuente por
    defecto de Pillow (se ve peor, pero nunca revienta por esto)."""
    rutas_posibles = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for ruta in rutas_posibles:
        try:
            return ImageFont.truetype(ruta, tamano)
        except Exception:
            continue
    return ImageFont.load_default()


def _dibujar_badge_precio(producto, precio_texto):
    """Badge oscuro con el precio en grande, esquina superior izquierda --
    genérico para cualquier tienda (sin ícono de marca)."""
    if not precio_texto:
        return
    draw = ImageDraw.Draw(producto, "RGBA")
    fuente = _cargar_fuente(int(producto.width * 0.06))

    padding_x, padding_y = 24, 16
    caja_texto = draw.textbbox((0, 0), precio_texto, font=fuente)
    ancho_texto = caja_texto[2] - caja_texto[0]
    alto_texto = caja_texto[3] - caja_texto[1]

    margen = 24
    x0, y0 = margen, margen
    x1 = x0 + ancho_texto + padding_x * 2
    y1 = y0 + alto_texto + padding_y * 2
    radio = (y1 - y0) // 2

    draw.rounded_rectangle((x0, y0, x1, y1), radius=radio, fill=(15, 15, 15, 235))
    draw.rounded_rectangle((x0, y0, x1, y1), radius=radio, outline=(255, 176, 32, 255), width=3)
    draw.text((x0 + padding_x, y0 + padding_y - caja_texto[1]), precio_texto, font=fuente, fill=(255, 255, 255, 255))


def _dibujar_redes_sociales(producto):
    """Tus redes sociales, abajo a la izquierda -- configurable en
    config.py (REDES_SOCIALES_LINEAS); si está vacío, no dibuja nada."""
    if not REDES_SOCIALES_LINEAS:
        return
    draw = ImageDraw.Draw(producto, "RGBA")
    tamano_fuente = int(producto.width * 0.028)
    fuente = _cargar_fuente(tamano_fuente)

    margen = 20
    interlineado = int(tamano_fuente * 1.35)
    y = producto.height - margen - interlineado * len(REDES_SOCIALES_LINEAS)

    for linea in REDES_SOCIALES_LINEAS:
        # Contorno negro + relleno blanco -- se lee bien sobre cualquier
        # fondo, claro u oscuro.
        x = margen
        for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2), (-2, 2), (2, -2)]:
            draw.text((x + dx, y + dy), linea, font=fuente, fill=(0, 0, 0, 255))
        draw.text((x, y), linea, font=fuente, fill=(255, 255, 255, 255))
        y += interlineado


def aplicar_logo_a_bytes(imagen_bytes_original, precio_texto=None):
    """
    Toma los bytes de una imagen (ya descargada, ej. la que tú subes a mano),
    la encaja en un cuadrado centrado de tamaño estándar, y le agrega el
    badge de precio (si se pasa), tus redes sociales, y tu logo.
    """
    try:
        producto = Image.open(io.BytesIO(imagen_bytes_original)).convert("RGBA")
        producto = _recortar_cuadrado_centrado(producto)

        _dibujar_badge_precio(producto, precio_texto)
        _dibujar_redes_sociales(producto)

        logo = Image.open(LOGO_PATH).convert("RGBA")
        ancho_logo = int(producto.width * 0.18)
        alto_logo = int(logo.height * (ancho_logo / logo.width))
        logo = logo.resize((ancho_logo, alto_logo))

        posicion = (producto.width - ancho_logo - 15, producto.height - alto_logo - 15)
        producto.paste(logo, posicion, logo)

        buffer = io.BytesIO()
        producto.convert("RGB").save(buffer, format="JPEG", quality=90)
        buffer.seek(0)
        return buffer
    except Exception as e:
        print(f"[WARN] No se pudo aplicar el logo a la imagen: {e}")
        return None


def preparar_imagen_con_logo(url_imagen_producto, precio_texto=None):
    """
    Descarga la imagen del producto desde una URL y le superpone tu logo
    (versión automática, para las imágenes que el sistema extrae solo).
    """
    try:
        img_resp = requests.get(url_imagen_producto, headers=HEADERS, timeout=15)
        return aplicar_logo_a_bytes(img_resp.content, precio_texto=precio_texto)
    except Exception as e:
        print(f"[WARN] No se pudo descargar la imagen del producto: {e}")
        return None
