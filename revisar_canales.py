"""
Revisa los canales de ofertas configurados (mensajes nuevos desde la última
ejecución). Por cada oferta detectada:
  1. Resuelve el link final (directo o en cascada)
  2. Genera el link con tu afiliado (si tienes uno activo en esa tienda)
  3. Reescribe el texto con IA (Groq gratis, o Anthropic si prefieres)
  4. Si MODO_REVISION está activo: te la manda a aprobar antes de publicar
     Si no: publica directo en tu canal (VIP primero, gratis con retraso) y Facebook

También revisa, al inicio de cada ejecución, si aprobaste o descartaste
ofertas pendientes de revisiones anteriores.

Pensado para correr por CRON cada 15-20 min (GitHub Actions, gratis).

Variables de entorno necesarias:
- TELEGRAM_API_ID, TELEGRAM_API_HASH   (de my.telegram.org)
- TELEGRAM_SESSION                     (generado con generar_sesion.py)
- TELEGRAM_BOT_TOKEN                   (el mismo bot de BotFather)
- GROQ_API_KEY  (o ANTHROPIC_API_KEY como alternativa)
"""

import os
import re
import json
import time
import html
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import requests
from pathlib import Path
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

from config import (
    CANALES_ORIGEN, CANAL_DESTINO_GRATIS, CANAL_DESTINO_VIP, TIENDAS,
    MODO_REVISION, MODELO_GROQ, MAX_OFERTAS_POR_CORRIDA, MAX_ANTIGUEDAD_OFERTA_HORAS,
)
from procesar_oferta import resolver_link_final, extraer_imagen_producto, preparar_imagen_con_logo
from publicar_facebook import publicar_facebook
from aprobaciones import enviar_para_revision, revisar_actividad_admin
from alertas import registrar_fallo, avisar_si_hubo_fallos, avisar_corrida_caida

API_ID = os.environ["TELEGRAM_API_ID"]
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_SESSION"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

RETRASO_GRATIS_SEGUNDOS = 15 * 60  # ventaja del canal VIP sobre el gratis
ESTADO_FILE = Path(__file__).parent / "data" / "ultimo_id.json"


def cargar_estado():
    if ESTADO_FILE.exists():
        return json.loads(ESTADO_FILE.read_text())
    return {}


def guardar_estado(estado):
    ESTADO_FILE.parent.mkdir(parents=True, exist_ok=True)
    ESTADO_FILE.write_text(json.dumps(estado, indent=2, ensure_ascii=False))


def limpiar_link_tienda(link, dominio):
    """
    Quita todo el 'ruido' de tracking que traía el link original (del canal
    de origen) y deja solo lo esencial: dominio + identificador de producto.
    Devuelve None si el link no es un producto válido (ej. página de error).
    """
    if dominio == "amazon.":
        if "/errors/" in link or "/error/" in link:
            return None  # el canal original ya traía un link roto

        match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", link, re.IGNORECASE)
        if not match:
            return None  # no se encontró un código de producto (ASIN) válido

        asin = match.group(1).upper()
        netloc = urlsplit(link).netloc
        return f"https://{netloc}/dp/{asin}"

    # Otras tiendas: por ahora se dejan tal cual (se puede limpiar cada una
    # cuando conectemos su afiliado específico).
    return link


def detectar_dominio_tienda(link):
    for dominio in TIENDAS:
        if dominio in link:
            return dominio
    return None


def extraer_links(texto):
    return re.findall(r"https?://\S+", texto)


def _agregar_parametro_url(url, clave, valor):
    partes = urlsplit(url)
    query = dict(parse_qsl(partes.query))
    query[clave] = valor
    return urlunsplit((partes.scheme, partes.netloc, partes.path, urlencode(query), partes.fragment))


def generar_link_afiliado(link, dominio):
    info = TIENDAS.get(dominio, {})
    if not info.get("afiliado_activo") or not info.get("id_afiliado"):
        return link  # sin afiliado activo todavía: se publica tal cual, sin comisión

    if dominio == "amazon.":
        return _agregar_parametro_url(link, "tag", info["id_afiliado"])

    # TODO: otras tiendas (AliExpress, Mercado Libre, etc.) tienen su propio
    # formato de link de afiliado -- lo conectamos cuando actives cada una.
    return link


def _llamar_groq(prompt, reintentos=2):
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": MODELO_GROQ,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
            },
            timeout=30,
        )
        if response.status_code == 429 and reintentos > 0:
            # Límite de peticiones por minuto de Groq -- espera y reintenta
            espera = max(int(response.headers.get("retry-after", 12)), 12)
            print(f"[INFO] Groq con rate limit, esperando {espera}s antes de reintentar")
            time.sleep(espera)
            return _llamar_groq(prompt, reintentos=reintentos - 1)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[WARN] Groq falló: {e}")
        registrar_fallo("Groq")
        return None


def _llamar_anthropic(prompt):
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"[WARN] Anthropic falló: {e}")
        return None


def extraer_cupon(texto_original):
    """
    Busca un cupón/código de descuento en el mensaje original con patrones
    comunes (CODE:, Cupón:, Código:). Filtra los casos donde el canal dice
    explícitamente que no hace falta cupón, y también frases descriptivas
    que no son un código real (ej. "cupón seleccionable en la página").
    """
    match = re.search(r"(?:c[oó]digo|cup[oó]n|code)[:\s]+([^\n]{2,25})", texto_original, re.IGNORECASE)
    if not match:
        return None

    candidato = match.group(1).strip()
    candidato = re.sub(r"[^\w\s-]", "", candidato).strip()  # quita emojis/puntuación

    negativos = {"no necesita", "ninguno", "no aplica", "sin cupon", "no requiere", "no aplica ninguno"}
    if not candidato or candidato.lower() in negativos:
        return None

    # Un código real no tiene espacios (es un token tipo "2TQYIBPW" o
    # "AHORRA10") -- si trae espacios, es una frase descriptiva del canal
    # origen ("cupón seleccionable", "aplica en el carrito", etc.), no un
    # código utilizable, así que se descarta.
    if " " in candidato:
        return None

    # Debe verse como un código: solo letras/números/guiones, largo razonable.
    if not re.match(r"^[A-Za-z0-9-]{3,20}$", candidato):
        return None

    return candidato


def extraer_precio(texto_original, link):
    """
    Busca el primer valor de precio ($XX.XX o similar) en el mensaje original.
    Prioridad para la moneda:
      1. Si el propio mensaje ya trae la moneda escrita junto al precio
         (ej. "$70.249 COP"), se respeta esa -- el canal origen ya la
         convirtió y sabe mejor que nosotros qué moneda es.
      2. Si no la trae, se adivina por el dominio de la tienda (con la
         salvedad de que amazon.com siempre es USD salvo que el texto diga
         lo contrario, como en el caso de arriba).
    """
    match = re.search(r"\$\s?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?", texto_original)
    if not match:
        return None

    precio = match.group(0).strip()

    # ¿El texto ya trae la moneda pegada justo después del precio?
    resto = texto_original[match.end():match.end() + 6]
    moneda_explicita = re.match(r"\s*(COP|USD|MXN|JPY|PEN|ARS|CLP)\b", resto)
    if moneda_explicita:
        return f"{precio} {moneda_explicita.group(1)}"

    netloc = urlsplit(link).netloc

    if netloc.endswith("amazon.com"):
        return f"{precio} USD"
    if netloc.endswith("amazon.com.mx"):
        return f"{precio} MXN"
    if netloc.endswith("amazon.co.jp"):
        return f"{precio} JPY"
    # Otros dominios (o cuando el canal ya vende en pesos colombianos):
    # se deja el símbolo tal cual, sin adivinar la moneda.
    return precio


def extraer_calificacion(texto_original):
    """Busca un patrón tipo '4.5 (3.962)' -- calificación + número de reseñas."""
    match = re.search(r"(\d(?:[.,]\d)?)\s*\(([\d.,]+)\)", texto_original)
    if match:
        return f"{match.group(1)} ({match.group(2)})"
    return None


def _extraer_titulo(texto_original):
    """Le pide a la IA SOLO el nombre corto del producto (más liviano y
    rápido que pedir una descripción completa, y menos propenso al límite
    de peticiones de Groq)."""
    prompt = (
        "Extrae el nombre del producto de este mensaje de oferta de Telegram, "
        "en español, máximo 14 palabras. Incluye marca, modelo y la "
        "característica principal si el mensaje la menciona (ej. capacidad, "
        "tamaño, color) -- sin comillas ni texto adicional, responde "
        "ÚNICAMENTE con el nombre del producto.\n\n"
        f"Mensaje original:\n{texto_original}"
    )
    resultado = None
    if GROQ_API_KEY:
        resultado = _llamar_groq(prompt)
        time.sleep(2)  # respiro entre llamadas para no pegarle al límite por minuto
    if not resultado and ANTHROPIC_API_KEY:
        resultado = _llamar_anthropic(prompt)
    if resultado:
        resultado = resultado.strip().strip('"').strip("'").split("\n")[0]
    return resultado


def reescribir_texto(texto_original, link):
    """
    Arma el mensaje final con campos fijos: producto, calificación (si se
    detecta), precio (si se detecta), cupón (o "no necesita"), link, y aviso
    de vigencia -- igual al formato que usan varios canales de ofertas.
    Calificación y precio se extraen del texto original con reglas simples
    (no con IA), para no inventar datos que no estaban ahí.

    Devuelve (mensaje, titulo, precio) -- titulo y precio se devuelven
    aparte para que quien llama pueda decidir si la oferta cumple el
    mínimo de campos requeridos antes de mandarla a revisión.
    """
    titulo = _extraer_titulo(texto_original)
    precio = extraer_precio(texto_original, link)
    calificacion = extraer_calificacion(texto_original)
    cupon = extraer_cupon(texto_original)

    lineas = [f"📦 <b>Producto:</b> {html.escape(titulo) if titulo else 'Oferta encontrada'}", ""]
    if calificacion:
        lineas.append(f"⭐️ Calificación: {html.escape(calificacion)}")
    if precio:
        lineas.append(f"💸 Precio: {html.escape(precio)}")
    lineas.append(f"🏷️ Cupón: {'<code>' + html.escape(cupon) + '</code>' if cupon else '¡No necesita!'}")
    lineas.append(f"🔗 Ir a la tienda: {link}")
    lineas.append("")
    lineas.append("⚠️ La oferta puede expirar en cualquier momento.")
    lineas.append("#ad")

    return "\n".join(lineas), titulo, precio


def publicar(chat_id, texto, imagen_bytes=None):
    if not chat_id:
        return
    try:
        if imagen_bytes:
            imagen_bytes.seek(0)
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            files = {"photo": ("oferta.jpg", imagen_bytes, "image/jpeg")}
            data = {"chat_id": chat_id, "caption": texto, "parse_mode": "HTML"}
            resp = requests.post(url, data=data, files=files, timeout=30)
        else:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            resp = requests.post(url, json={"chat_id": chat_id, "text": texto, "parse_mode": "HTML"}, timeout=15)

        # Antes esto no se revisaba: Telegram puede responder 200 o 4xx con
        # {"ok": false, "description": "..."} (ej. el bot no es admin del
        # canal) sin lanzar una excepción de red -- si no se chequea, el
        # fallo queda invisible y parece que "no pasó nada".
        if not resp.ok or not resp.json().get("ok", False):
            print(f"[WARN] Telegram rechazó la publicación (chat {chat_id}): {resp.text}")
            registrar_fallo("Publicar en Telegram")
    except Exception as e:
        print(f"[WARN] No se pudo publicar en Telegram (chat {chat_id}): {e}")
        registrar_fallo("Publicar en Telegram")


def publicar_oferta_completa(texto_nuevo, url_imagen=None, imagen_bytes=None):
    """Publica de verdad: prepara la imagen con logo (o usa la que ya viene
    lista, ej. una foto que subiste tú a mano), publica VIP+Facebook ya, y
    programa el canal gratis con retraso. Usada tanto en modo directo como
    después de una aprobación manual."""
    if imagen_bytes is None and url_imagen:
        imagen_bytes = preparar_imagen_con_logo(url_imagen)

    publicar(CANAL_DESTINO_VIP, texto_nuevo, imagen_bytes)
    publicar_facebook(texto_nuevo, imagen_bytes)

    if not CANAL_DESTINO_VIP:
        # No hay canal VIP todavía -- no tiene sentido hacer esperar al
        # canal gratis por un VIP que no existe, se publica ya mismo.
        publicar(CANAL_DESTINO_GRATIS, texto_nuevo, imagen_bytes)
        return

    pendientes_gratis = cargar_estado().get("pendientes_gratis", [])
    pendientes_gratis.append({"texto": texto_nuevo, "hora": time.time()})
    estado = cargar_estado()
    estado["pendientes_gratis"] = pendientes_gratis
    guardar_estado(estado)


def publicar_pendientes_gratis():
    estado = cargar_estado()
    pendientes = estado.get("pendientes_gratis", [])
    quedan = []
    for item in pendientes:
        if time.time() - item["hora"] >= RETRASO_GRATIS_SEGUNDOS:
            publicar(CANAL_DESTINO_GRATIS, item["texto"])
        else:
            quedan.append(item)
    estado["pendientes_gratis"] = quedan
    guardar_estado(estado)


def procesar_mensaje(oferta_id, texto):
    links_en_mensaje = extraer_links(texto)
    if not links_en_mensaje:
        return

    link_final = None
    dominio = None
    for link in links_en_mensaje:
        dominio = detectar_dominio_tienda(link)
        if dominio:
            link_final = link
            break

    if not link_final:
        resuelto = resolver_link_final(links_en_mensaje[0])
        if resuelto:
            dominio = detectar_dominio_tienda(resuelto)
            link_final = resuelto

    if not link_final or not dominio:
        print("[SKIP] No se pudo resolver un link de tienda válido")
        return

    link_limpio = limpiar_link_tienda(link_final, dominio)
    if not link_limpio:
        print(f"[SKIP] Link de {dominio} inválido o roto, se descarta")
        return

    link_con_afiliado = generar_link_afiliado(link_limpio, dominio)
    texto_nuevo, titulo, precio = reescribir_texto(texto, link_con_afiliado)

    # Filtro de mínimos: si no se pudo sacar título o precio, no vale la
    # pena mandarla a revisión -- el link (link_con_afiliado) ya está
    # garantizado en este punto, siempre lo tiene toda oferta que llega aquí.
    if not titulo or not precio:
        faltante = "título" if not titulo else "precio"
        print(f"[SKIP] {oferta_id}: sin {faltante}, no cumple el mínimo, se descarta")
        return

    url_imagen = extraer_imagen_producto(link_con_afiliado)

    if MODO_REVISION:
        print(f"[OFERTA] {dominio} -> enviada a revisión ({oferta_id})")
        enviar_para_revision(oferta_id, texto_nuevo, url_imagen)
    else:
        print(f"[OFERTA] {dominio} -> publicando directo")
        publicar_oferta_completa(texto_nuevo, url_imagen)
    return True  # sí contó como oferta procesada, para el tope por corrida


def main():
    # 1. Revisa si el admin aprobó/descartó ofertas, o mandó una foto propia
    revisar_actividad_admin(publicar_oferta_completa)

    # 2. Revisa canales por mensajes nuevos, respetando el tope por corrida
    # Se reparte el tope EN PARTES IGUALES entre canales (en vez de dejar que
    # el primer canal con mensajes se coma todo el cupo) -- así ningún canal
    # acapara la corrida y todos avanzan cada vez, aunque uno publique mucho
    # más seguido que los otros.
    estado = cargar_estado()
    ofertas_procesadas = 0
    tope_por_canal = max(1, MAX_OFERTAS_POR_CORRIDA // len(CANALES_ORIGEN))

    with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        for canal in CANALES_ORIGEN:
            if ofertas_procesadas >= MAX_OFERTAS_POR_CORRIDA:
                print(f"[INFO] Tope de {MAX_OFERTAS_POR_CORRIDA} alcanzado, "
                      f"{canal} se revisa en la próxima corrida")
                break

            ultimo_id = estado.get(canal, 0)
            mensajes_nuevos = list(client.iter_messages(canal, min_id=ultimo_id, limit=50))

            if not mensajes_nuevos:
                print(f"[INFO] {canal}: sin mensajes nuevos")
                continue

            ofertas_de_este_canal = 0
            ultimo_evaluado = ultimo_id
            for msg in reversed(mensajes_nuevos):  # orden cronológico
                if ofertas_procesadas >= MAX_OFERTAS_POR_CORRIDA:
                    break
                if ofertas_de_este_canal >= tope_por_canal:
                    print(f"[INFO] {canal}: alcanzó su cuota de esta corrida "
                          f"({tope_por_canal}), sigue en la próxima")
                    break
                antiguedad = datetime.now(timezone.utc) - msg.date
                if antiguedad > timedelta(hours=MAX_ANTIGUEDAD_OFERTA_HORAS):
                    print(f"[SKIP] Mensaje {canal}:{msg.id} tiene "
                          f"{antiguedad.total_seconds() / 3600:.1f}h, "
                          f"posible oferta ya expirada, se descarta")
                    ultimo_evaluado = msg.id
                    continue
                if msg.raw_text:
                    oferta_id = f"{canal}:{msg.id}"
                    if procesar_mensaje(oferta_id, msg.raw_text):
                        ofertas_procesadas += 1
                        ofertas_de_este_canal += 1
                ultimo_evaluado = msg.id

            estado[canal] = ultimo_evaluado
            guardar_estado(estado)

    # 3. Publica lo que ya cumplió el tiempo de espera para el canal gratis
    publicar_pendientes_gratis()

    avisar_si_hubo_fallos()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        avisar_corrida_caida(e)
        raise  # que GitHub Actions siga marcando la corrida como fallida
