"""
Revisa los canales de ofertas configurados (mensajes nuevos desde la última
ejecución), y por cada oferta detectada:
  1. Resuelve el link final (directo o en cascada)
  2. Extrae la foto del producto y le pone tu logo
  3. Reescribe el texto con el LLM
  4. Publica en tu canal propio (VIP primero, gratis con retraso) y en Facebook

Pensado para correr por CRON cada 15-30 min (GitHub Actions, gratis en repo
público) -- se conecta, procesa lo nuevo, guarda su estado, y termina.
No necesita ningún hosting pagado porque no corre 24/7 de forma continua.

Variables de entorno necesarias:
- TELEGRAM_API_ID, TELEGRAM_API_HASH   (de my.telegram.org)
- TELEGRAM_SESSION                     (generado con generar_sesion.py)
- TELEGRAM_BOT_TOKEN                   (el mismo bot de BotFather, para PUBLICAR)
- ANTHROPIC_API_KEY
"""

import os
import re
import json
import time
import requests
from pathlib import Path
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

from config import CANALES_ORIGEN, CANAL_DESTINO_GRATIS, CANAL_DESTINO_VIP, TIENDAS
from procesar_oferta import resolver_link_final, extraer_imagen_producto, preparar_imagen_con_logo
from publicar_facebook import publicar_facebook

API_ID = os.environ["TELEGRAM_API_ID"]
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_SESSION"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
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
        return link  # sin afiliado activo todavía: se publica tal cual, sin comisión
    # TODO: cuando actives un afiliado, aquí va la transformación específica de esa tienda
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


def procesar_mensaje(texto):
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

    link_con_afiliado = generar_link_afiliado(link_final, dominio)
    texto_nuevo = reescribir_texto(texto, link_con_afiliado)

    imagen_bytes = None
    url_imagen = extraer_imagen_producto(link_con_afiliado)
    if url_imagen:
        imagen_bytes = preparar_imagen_con_logo(url_imagen)

    print(f"[OFERTA] {dominio} -> publicando en VIP")
    publicar(CANAL_DESTINO_VIP, f"🔥 {texto_nuevo}", imagen_bytes)
    publicar_facebook(f"🔥 {texto_nuevo}", imagen_bytes)

    # Nota: aquí no se puede "esperar en segundo plano" como en un proceso
    # 24/7 -- este script termina después de procesar. El retraso del canal
    # gratis se logra guardando la oferta pendiente y publicándola en la
    # SIGUIENTE ejecución del cron (ver publicar_pendientes_gratis más abajo).
    pendientes = cargar_estado().get("pendientes_gratis", [])
    pendientes.append({"texto": texto_nuevo, "hora": time.time()})
    estado = cargar_estado()
    estado["pendientes_gratis"] = pendientes
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


def main():
    estado = cargar_estado()

    with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        for canal in CANALES_ORIGEN:
            ultimo_id = estado.get(canal, 0)
            mensajes_nuevos = list(client.iter_messages(canal, min_id=ultimo_id, limit=50))

            if not mensajes_nuevos:
                print(f"[INFO] {canal}: sin mensajes nuevos")
                continue

            # iter_messages trae del más nuevo al más viejo -- lo procesamos
            # en orden cronológico para no invertir el orden de publicación
            for msg in reversed(mensajes_nuevos):
                if msg.raw_text:
                    procesar_mensaje(msg.raw_text)

            estado[canal] = mensajes_nuevos[0].id  # el id más alto (más reciente)
            guardar_estado(estado)

    publicar_pendientes_gratis()


if __name__ == "__main__":
    main()
