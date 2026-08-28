"""
Cola de revisión manual. Cuando MODO_REVISION está activo, las ofertas
candidatas no se publican directo -- se mandan al chat privado del admin
con dos botones ("Publicar" / "Descartar"), y solo se publican si el admin
aprueba. Esto se resuelve en la SIGUIENTE ejecución del cron después de que
el admin responde (no en tiempo real, por el mismo motivo que el resto del
sistema corre por lotes cada 20 min).
"""

import os
import json
import requests
from pathlib import Path

from config import ADMIN_CHAT_ID
from procesar_oferta import preparar_imagen_con_logo

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

PENDIENTES_FILE = Path(__file__).parent / "data" / "pendientes_revision.json"
OFFSET_FILE = Path(__file__).parent / "data" / "ultimo_update_id.txt"


def _cargar_pendientes():
    if PENDIENTES_FILE.exists():
        return json.loads(PENDIENTES_FILE.read_text())
    return {}


def _guardar_pendientes(pendientes):
    PENDIENTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    PENDIENTES_FILE.write_text(json.dumps(pendientes, indent=2, ensure_ascii=False))


def _cargar_offset():
    if OFFSET_FILE.exists():
        contenido = OFFSET_FILE.read_text().strip()
        return int(contenido) if contenido else 0
    return 0


def _guardar_offset(offset):
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(str(offset))


def enviar_para_revision(oferta_id, texto, url_imagen):
    """Manda la oferta candidata al chat del admin, con botones para decidir."""
    if not ADMIN_CHAT_ID:
        print("[WARN] MODO_REVISION activo pero ADMIN_CHAT_ID no está configurado -- se descarta")
        return

    pendientes = _cargar_pendientes()
    pendientes[oferta_id] = {"texto": texto, "url_imagen": url_imagen}
    _guardar_pendientes(pendientes)

    teclado = {
        "inline_keyboard": [[
            {"text": "✅ Publicar", "callback_data": f"aprobar:{oferta_id}"},
            {"text": "❌ Descartar", "callback_data": f"rechazar:{oferta_id}"},
        ]]
    }

    encabezado = "🕵️ <b>Oferta pendiente de revisión</b>\n\n"
    imagen_bytes = preparar_imagen_con_logo(url_imagen) if url_imagen else None

    if imagen_bytes:
        imagen_bytes.seek(0)
        requests.post(f"{API}/sendPhoto", data={
            "chat_id": ADMIN_CHAT_ID,
            "caption": encabezado + texto,
            "reply_markup": json.dumps(teclado),
            "parse_mode": "HTML",
        }, files={"photo": ("oferta.jpg", imagen_bytes, "image/jpeg")}, timeout=30)
    else:
        requests.post(f"{API}/sendMessage", data={
            "chat_id": ADMIN_CHAT_ID,
            "text": encabezado + texto,
            "reply_markup": json.dumps(teclado),
            "parse_mode": "HTML",
        }, timeout=20)


def revisar_respuestas(publicar_func):
    """
    Revisa si el admin aprobó o descartó alguna oferta pendiente desde la
    última ejecución. `publicar_func(texto, url_imagen)` es la función real
    de publicación (Telegram + Facebook), se llama solo si se aprueba.
    """
    offset = _cargar_offset()
    resp = requests.get(f"{API}/getUpdates", params={
        "offset": offset,
        "allowed_updates": json.dumps(["callback_query"]),
    }, timeout=20)
    data = resp.json()

    pendientes = _cargar_pendientes()
    max_update_id = offset - 1

    for update in data.get("result", []):
        max_update_id = max(max_update_id, update["update_id"])
        callback = update.get("callback_query")
        if not callback or "data" not in callback:
            continue

        accion_data = callback["data"]
        if ":" not in accion_data:
            continue
        accion, oferta_id = accion_data.split(":", 1)

        texto_respuesta = "Publicado ✅" if accion == "aprobar" else "Descartado ❌"
        requests.post(f"{API}/answerCallbackQuery", data={
            "callback_query_id": callback["id"],
            "text": texto_respuesta,
        }, timeout=15)

        oferta = pendientes.pop(oferta_id, None)
        if not oferta:
            continue  # ya procesada o vencida

        if accion == "aprobar":
            print(f"[REVISION] Aprobada por admin: {oferta_id}")
            publicar_func(oferta["texto"], oferta["url_imagen"])
        else:
            print(f"[REVISION] Descartada por admin: {oferta_id}")

    _guardar_pendientes(pendientes)
    if max_update_id >= offset:
        _guardar_offset(max_update_id + 1)
