"""
Escucha en tiempo real los canales de ofertas configurados, y cuando llega
un mensaje con un link de tienda reconocida:
  1. Extrae el link del producto
  2. Genera (o deja pasar) el link con tu afiliado, según la tienda
  3. Reescribe el texto con el LLM para no republicar copia idéntica
  4. Publica en tu canal propio (VIP primero, gratis con retraso)

Corre 24/7 -- pensado para desplegarse como "background worker" en un
hosting gratuito (Render, Railway), no en GitHub Actions.

Variables de entorno necesarias:
- TELEGRAM_API_ID, TELEGRAM_API_HASH   (de my.telegram.org)
- TELEGRAM_SESSION                     (generado con generar_sesion.py)
- TELEGRAM_BOT_TOKEN                   (el mismo bot de BotFather, para PUBLICAR)
- ANTHROPIC_API_KEY
"""

import os
import re
import asyncio
import requests
from telethon import TelegramClient, events
from telethon.sessions import StringSession

from config import CANALES_ORIGEN, CANAL_DESTINO_GRATIS, CANAL_DESTINO_VIP, TIENDAS
from procesar_oferta import resolver_link_final, extraer_imagen_producto, preparar_imagen_con_logo, es_tienda_final
from publicar_facebook import publicar_facebook

API_ID = os.environ["TELEGRAM_API_ID"]
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_SESSION"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

RETRASO_GRATIS_SEGUNDOS = 15 * 60  # 15 min de ventaja para el canal VIP

# Deduplicado simple en memoria (se reinicia si el proceso se reinicia)
mensajes_procesados = set()

client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)


def detectar_dominio_tienda(link):
    for dominio in TIENDAS:
        if dominio in link:
            return dominio
    return None


def extraer_links(texto):
    return re.findall(r"https?://\S+", texto)


def generar_link_afiliado(link, dominio):
    info = TIENDAS.get(dominio, {})
    if not info.get("afiliado_activo"):
        # Sin afiliado activo todavía: se publica el link tal cual, sin comisión
        return link
    # TODO: cuando actives un afiliado, aquí va la lógica específica de esa
    # tienda para transformar `link` en tu link de comisión (cada tienda
    # tiene su propio formato -- lo conectamos cuando llegues a este punto).
    return link


def reescribir_texto(texto_original, link):
    prompt = (
        "Reescribe este mensaje de oferta de Telegram con tus propias palabras, "
        "en español, tono directo, máximo 3 líneas, sin copiar frases textuales "
        "del original. Termina con el link. No agregues comillas ni encabezados.\n\n"
        f"Mensaje original:\n{texto_original}\n\nLink: {link}"
    )
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
        print(f"[WARN] LLM falló, publicando versión simple: {e}")
        return f"Nueva oferta encontrada:\n{link}"


def publicar(chat_id, texto, imagen_bytes=None):
    if not chat_id:
        return
    if imagen_bytes:
        imagen_bytes.seek(0)
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        files = {"photo": ("oferta.jpg", imagen_bytes, "image/jpeg")}
        data = {"chat_id": chat_id, "caption": texto}
        requests.post(url, data=data, files=files, timeout=30)
    else:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": texto}, timeout=15)


@client.on(events.NewMessage(chats=CANALES_ORIGEN))
async def manejar_mensaje(event):
    texto = event.raw_text or ""
    msg_id = f"{event.chat_id}:{event.id}"

    if msg_id in mensajes_procesados:
        return
    mensajes_procesados.add(msg_id)

    links_en_mensaje = extraer_links(texto)
    if not links_en_mensaje:
        return

    # Busca, entre todos los links del mensaje, uno que ya sea de tienda,
    # o resuelve el primero que encuentre por si pasa por página intermedia
    # (sitio propio, acortador, etc. -- Facebook es el caso menos confiable).
    link_final = None
    dominio = None
    for link in links_en_mensaje:
        dominio = detectar_dominio_tienda(link)
        if dominio:
            link_final = link
            break

    if not link_final:
        candidato = links_en_mensaje[0]
        resuelto = resolver_link_final(candidato)
        if resuelto:
            dominio = detectar_dominio_tienda(resuelto)
            link_final = resuelto

    if not link_final or not dominio:
        print("[SKIP] No se pudo resolver un link de tienda válido")
        return

    link_con_afiliado = generar_link_afiliado(link_final, dominio)
    texto_nuevo = reescribir_texto(texto, link_con_afiliado)

    imagen_bytes = None
    url_imagen = extraer_imagen_producto(link_con_afiliado)
    if url_imagen:
        imagen_bytes = preparar_imagen_con_logo(url_imagen)

    print(f"[OFERTA] {dominio} -> publicando en VIP")
    publicar(CANAL_DESTINO_VIP, f"🔥 {texto_nuevo}", imagen_bytes)
    publicar_facebook(f"🔥 {texto_nuevo}", imagen_bytes)

    print(f"[OFERTA] Programada para canal gratis en {RETRASO_GRATIS_SEGUNDOS // 60} min")
    asyncio.create_task(publicar_con_retraso(texto_nuevo, imagen_bytes))


async def publicar_con_retraso(texto, imagen_bytes=None):
    await asyncio.sleep(RETRASO_GRATIS_SEGUNDOS)  # no bloquea otros mensajes mientras espera
    publicar(CANAL_DESTINO_GRATIS, texto, imagen_bytes)


print("Escuchando canales:", CANALES_ORIGEN)
client.start()
client.run_until_disconnected()
