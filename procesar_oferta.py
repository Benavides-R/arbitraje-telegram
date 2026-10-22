"""
Funciones para:
1. Resolver un link que pasa por páginas intermedias hasta llegar a la tienda real
2. Extraer la foto oficial del producto desde la tienda
3. Ponerle tu logo encima antes de publicar
"""

import re
import io
import json
import html
import time
import requests
from PIL import Image, ImageDraw, ImageFont

from config import DOMINIOS_TIENDA_FINAL, LOGO_PATH, REDES_SOCIALES_LINEAS
from estadisticas import registrar_imagen_origen

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-US,es;q=0.9,en;q=0.8",
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


_PATRONES_IMAGEN_INVALIDA = re.compile(
    r"(sprite|icon|loading|transparent-pixel|grey-pixel|nav-sprite|"
    r"gift-card|logo|placeholder)",
    re.IGNORECASE,
)


def _es_imagen_valida(url):
    """Filtro de seguridad: rechaza iconos, sprites de navegación, logos
    y placeholders -- solo deja pasar lo que parece una foto real de
    producto. Nunca acepta nada que no sea una URL http(s)."""
    if not url or not isinstance(url, str) or not url.startswith("http"):
        return False
    return not _PATRONES_IMAGEN_INVALIDA.search(url)


def _imagen_desde_json_ld(html_texto):
    """Busca bloques <script type="application/ld+json"> con un campo
    "image" -- lo usan las páginas de producto que siguen el estándar
    schema.org/Product (Amazon lo trae en varias plantillas)."""
    for bloque in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html_texto, re.DOTALL | re.IGNORECASE,
    ):
        try:
            data = json.loads(bloque.strip())
        except Exception:
            continue
        for item in (data if isinstance(data, list) else [data]):
            if not isinstance(item, dict):
                continue
            imagen = item.get("image")
            if isinstance(imagen, list) and imagen:
                imagen = imagen[0]
            if isinstance(imagen, dict):
                imagen = imagen.get("url")
            if _es_imagen_valida(imagen):
                return imagen
    return None


def _imagen_desde_galeria_amazon(html_texto):
    """Busca el atributo data-a-dynamic-image que Amazon incrusta en el
    HTML del producto -- es un diccionario {url: [ancho, alto]} con TODAS
    las resoluciones disponibles de la imagen PRINCIPAL (no de productos
    relacionados). Se elige la de mayor resolución -- las miniaturas de
    navegación no sirven para publicar."""
    match = re.search(r'data-a-dynamic-image="([^"]+)"', html_texto)
    if not match:
        return None
    try:
        mapa = json.loads(html.unescape(match.group(1)))
    except Exception:
        return None

    mejor_url, mejor_area = None, 0
    for url, dimensiones in mapa.items():
        if not _es_imagen_valida(url):
            continue
        area = dimensiones[0] * dimensiones[1] if isinstance(dimensiones, list) and len(dimensiones) == 2 else 0
        if area >= mejor_area:
            mejor_area, mejor_url = area, url
    return mejor_url


def _es_captcha_amazon(texto_html):
    """True cuando la respuesta de Amazon es su desafío "no eres un robot"
    en vez de la página del producto (bloqueo por IP -- típico desde las
    IPs de GitHub Actions). Sirve para contarlo aparte en las estadísticas:
    si domina "captcha", el problema es la IP y ningún truco de navegador
    lo arregla; si domina "fallo", sí vale la pena seguir afinando."""
    bajo = texto_html.lower()
    return any(m in bajo for m in (
        "validatecaptcha", "cvf_captcha", "api-services-support@amazon",
        "type the characters you see", "not a robot", "no es un robot",
    ))


def _extraer_por_html(url_tienda):
    """Intento A→C sobre el HTML que el servidor devuelve tal cual (sin
    navegador): og:image, JSON-LD y galería de Amazon. Rápido y es lo que
    más funciona cuando Amazon no bloquea la IP. Devuelve (imagen, captcha):
    captcha=True cuando respondieron con el desafío de robot."""
    try:
        resp = requests.get(url_tienda, headers=HEADERS, timeout=15)
        texto_html = resp.text

        if _es_captcha_amazon(texto_html):
            print(f"[CAPTCHA] Amazon devolvió el desafío de robot ({url_tienda})")
            return None, True

        match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', texto_html)
        if match and _es_imagen_valida(match.group(1)):
            return match.group(1), False

        candidato = _imagen_desde_json_ld(texto_html)
        if candidato:
            return candidato, False

        candidato = _imagen_desde_galeria_amazon(texto_html)
        if candidato:
            return candidato, False
    except Exception as e:
        print(f"[WARN] Request simple para imagen falló ({url_tienda}): {e}")
    return None, False


def _extraer_por_navegador(url_tienda):
    """Intento D con navegador headless (último recurso). Devuelve
    (imagen, hubo_error, captcha): hubo_error=True cuando la excepción vino
    de la infraestructura del navegador (chromium no arrancó, timeout, ...),
    que es el único caso donde reintentarlo merece la pena; captcha=True
    cuando Amazon mostró su desafío de robot (bloqueo por IP -- reintentar
    no sirve, hay que cambiar de IP o usar la API oficial)."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            # UA alineado a la versión REAL de chromium instalado: si el UA
            # dice otra versión que los client-hints (sec-ch-ua), Amazon lo
            # toma como señal de automatización de una sola mirada.
            version_mayor = (browser.version or "").split(".")[0] or "140"
            ua_navegador = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{version_mayor}.0.0.0 Safari/537.36"
            )
            page = browser.new_page(
                user_agent=ua_navegador,
                extra_http_headers={**HEADERS, "User-Agent": ua_navegador},
                viewport={"width": 1366, "height": 900},
                locale="es-US",
            )
            # Sin esto, navigator.webdriver=true delata el navegador
            # automatizado en las pruebas de bot de Amazon.
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            page.goto(url_tienda, timeout=30000, wait_until="load")
            page.wait_for_timeout(2500)

            html_render = page.content()
            if _es_captcha_amazon(html_render):
                print(f"[CAPTCHA] El navegador recibió el desafío de robot ({url_tienda})")
                browser.close()
                return None, False, True

            contenido = None
            elemento = page.query_selector('meta[property="og:image"]')
            if elemento:
                candidato = elemento.get_attribute("content")
                if _es_imagen_valida(candidato):
                    contenido = candidato

            if not contenido:
                # Con la página ya renderizada por JS, reintenta B y C sobre
                # el HTML final (a veces solo aparecen después de cargar).
                contenido = _imagen_desde_json_ld(html_render) or _imagen_desde_galeria_amazon(html_render)

            if not contenido:
                for selector in ["#landingImage", "#imgBlkFront", ".a-dynamic-image"]:
                    img = page.query_selector(selector)
                    if img:
                        candidato = img.get_attribute("src")
                        if _es_imagen_valida(candidato):
                            contenido = candidato
                            break

            browser.close()
            return contenido, False, False
    except Exception as e:
        print(f"[WARN] No se pudo extraer imagen con navegador ({url_tienda}): {e}")
        return None, True, False


def extraer_imagen_producto(url_tienda):
    """
    Extrae la URL de la foto oficial del producto, probando varias fuentes
    en orden (A→D), todas sacadas de la MISMA página del producto -- nunca
    se busca una imagen en Google/Pexels/Pixabay ni en ningún sitio externo,
    así que lo que se encuentra siempre pertenece de verdad a esa oferta,
    o si no se encuentra nada confiable, se devuelve None (va a revisión
    manual en vez de arriesgar una imagen que no corresponde):
      A) meta og:image
      B) JSON-LD (schema.org/Product)
      C) galería embebida de Amazon (data-a-dynamic-image), la de mayor resolución
      D) selectores HTML de la imagen principal (con navegador, último recurso)

    Si el primer par (HTML simple → navegador) falla, espera 5s y repite --
    hay días donde GitHub Actions/Amazon bloquea el primer intento de forma
    transitoria y el reintento sí pasa (la extracción histórica variaba de
    0% a 94% según el día). El navegador solo se relanza si antes ERRO
    (infraestructura caída), no si simplemente no halló imagen.

    Cada resultado queda registrado en estadísticas: html / navegador /
    captcha (Amazon devolvió el desafío "no eres un robot" -- bloqueo por
    IP) / fallo, para poder medir la tasa de éxito día a día y saber si el
    cuello de botella es la IP o el navegador.
    """
    vio_captcha = False

    imagen, captcha = _extraer_por_html(url_tienda)
    if imagen:
        _registrar_origen_seguro("html")
        return imagen
    vio_captcha = vio_captcha or captcha

    imagen, error_navegador, captcha = _extraer_por_navegador(url_tienda)
    if imagen:
        _registrar_origen_seguro("navegador")
        return imagen
    vio_captcha = vio_captcha or captcha

    # Reintento del par completo tras una pausa corta.
    time.sleep(5)
    imagen, captcha = _extraer_por_html(url_tienda)
    if imagen:
        _registrar_origen_seguro("html")
        return imagen
    vio_captcha = vio_captcha or captcha

    if error_navegador:
        imagen, _, captcha = _extraer_por_navegador(url_tienda)
        if imagen:
            _registrar_origen_seguro("navegador")
            return imagen
        vio_captcha = vio_captcha or captcha

    _registrar_origen_seguro("captcha" if vio_captcha else "fallo")
    return None


def _registrar_origen_seguro(origen):
    """La métrica de extracción NUNCA debe tumbar la oferta -- si el
    archivo de estadísticas falla, se ignora silenciosamente."""
    try:
        registrar_imagen_origen(origen)
    except Exception:
        pass



TAMANO_ESTANDAR = 1100  # todas las ofertas quedan exactamente en este tamaño


def _normalizar_tamano(imagen):
    """
    Formato fijo 1100x1100, cuadrado 1:1, para TODAS las ofertas -- el
    producto se escala para verse lo más grande posible dentro del
    cuadrado (se agranda si la foto original es chica, se achica si es
    grande), sin recortar nunca nada y sin deformar, centrado, con fondo
    blanco limpio.
    """
    imagen = imagen.convert("RGBA")
    ancho, alto = imagen.size
    escala = min(TAMANO_ESTANDAR / ancho, TAMANO_ESTANDAR / alto)
    nuevo_ancho, nuevo_alto = round(ancho * escala), round(alto * escala)
    imagen = imagen.resize((nuevo_ancho, nuevo_alto), Image.LANCZOS)

    lienzo = Image.new("RGBA", (TAMANO_ESTANDAR, TAMANO_ESTANDAR), (255, 255, 255, 255))
    posicion = ((TAMANO_ESTANDAR - nuevo_ancho) // 2, (TAMANO_ESTANDAR - nuevo_alto) // 2)
    lienzo.paste(imagen, posicion, imagen)
    return lienzo


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
    la encaja completa con un margen blanco mínimo (sin recortar ni deformar), y le agrega el
    badge de precio (si se pasa), tus redes sociales, y tu logo.
    """
    try:
        producto = Image.open(io.BytesIO(imagen_bytes_original)).convert("RGBA")
        producto = _normalizar_tamano(producto)

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
