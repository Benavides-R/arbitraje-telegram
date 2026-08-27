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
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import requests
from pathlib import Path
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

from config import (
    CANALES_ORIGEN, CANAL_DESTINO_GRATIS, CANAL_DESTINO_VIP, TIENDAS,
    MODO_REVISION, MODELO_GROQ,
)
from procesar_oferta import resolver_link_final, extraer_imagen_producto, preparar_imagen_con_logo
from publicar_facebook import publicar_facebook
from aprobaciones import enviar_para_revision, revisar_respuestas

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


def _llamar_groq(prompt):
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
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[WARN] Groq falló: {e}")
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


def reescribir_texto(texto_original, link):
    prompt = (
        "Reescribe este mensaje de oferta de Telegram con tus propias palabras, "
        "en español, tono directo, máximo 3 líneas, sin copiar frases textuales "
        "del original. Termina con el link. No agregues comillas ni encabezados.\n\n"
        f"Mensaje original:\n{texto_original}\n\nLink: {link}"
    )
    resultado = None
    if GROQ_API_KEY:
        resultado = _llamar_groq(prompt)
    if not resultado and ANTHROPIC_API_KEY:
        resultado = _llamar_anthropic(prompt)
    if not resultado:
        resultado = f"Nueva oferta encontrada:\n{link}"
    return resultado


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


def publicar_oferta_completa(texto_nuevo, url_imagen):
    """Publica de verdad: prepara la imagen con logo, publica VIP+Facebook ya,
    y programa el canal gratis con retraso. Usada tanto en modo directo como
    después de una aprobación manual."""
    imagen_bytes = preparar_imagen_con_logo(url_imagen) if url_imagen else None

    publicar(CANAL_DESTINO_VIP, f"🔥 {texto_nuevo}", imagen_bytes)
    publicar_facebook(f"🔥 {texto_nuevo}", imagen_bytes)

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

    link_con_afiliado = generar_link_afiliado(link_final, dominio)
    texto_nuevo = reescribir_texto(texto, link_con_afiliado)
    url_imagen = extraer_imagen_producto(link_con_afiliado)

    if MODO_REVISION:
        print(f"[OFERTA] {dominio} -> enviada a revisión ({oferta_id})")
        enviar_para_revision(oferta_id, texto_nuevo, url_imagen)
    else:
        print(f"[OFERTA] {dominio} -> publicando directo")
        publicar_oferta_completa(texto_nuevo, url_imagen)


def main():
    # 1. Revisa si el admin aprobó/descartó ofertas pendientes de antes
    revisar_respuestas(publicar_oferta_completa)

    # 2. Revisa canales por mensajes nuevos
    estado = cargar_estado()
    with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        for canal in CANALES_ORIGEN:
            ultimo_id = estado.get(canal, 0)
            mensajes_nuevos = list(client.iter_messages(canal, min_id=ultimo_id, limit=50))

            if not mensajes_nuevos:
                print(f"[INFO] {canal}: sin mensajes nuevos")
                continue

            for msg in reversed(mensajes_nuevos):  # orden cronológico
                if msg.raw_text:
                    oferta_id = f"{canal}:{msg.id}"
                    procesar_mensaje(oferta_id, msg.raw_text)

            estado[canal] = mensajes_nuevos[0].id
            guardar_estado(estado)

    # 3. Publica lo que ya cumplió el tiempo de espera para el canal gratis
    publicar_pendientes_gratis()


if __name__ == "__main__":
    main()
