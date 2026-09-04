"""
Cola de revisión manual. Cuando MODO_REVISION está activo, las ofertas
candidatas no se publican directo -- se mandan al chat privado del admin
con dos botones ("Publicar" / "Descartar"), y solo se publican si el admin
aprueba. También puedes responder a esa oferta con una foto propia (se le
pone tu logo automático) para reemplazar la imagen si no llegó ninguna.

Todo esto se resuelve en la SIGUIENTE ejecución del cron después de que el
admin responde (no en tiempo real, igual que el resto del sistema).
"""

import os
import io
import re
import json
import base64
import time
import requests
from pathlib import Path

from config import ADMIN_CHAT_ID
from procesar_oferta import preparar_imagen_con_logo, aplicar_logo_a_bytes
from estadisticas import registrar_publicacion

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
    """Manda la oferta candidata al chat del admin, con botones para decidir.
    Guarda el message_id del envío, para poder detectar después si le
    respondes con una foto propia."""
    if not ADMIN_CHAT_ID:
        print("[WARN] MODO_REVISION activo pero ADMIN_CHAT_ID no está configurado -- se descarta")
        return

    pendientes = _cargar_pendientes()
    pendientes[oferta_id] = {"texto": texto, "url_imagen": url_imagen, "creado": time.time()}
    _guardar_pendientes(pendientes)

    teclado = {
        "inline_keyboard": [[
            {"text": "✅ Publicar", "callback_data": f"aprobar:{oferta_id}"},
            {"text": "❌ Descartar", "callback_data": f"rechazar:{oferta_id}"},
        ]]
    }
    pie = "\n\n💬 <i>O responde a este mensaje con \"si\" para publicar, o \"no\" para descartar.</i>"

    encabezado = "🕵️ <b>Oferta pendiente de revisión</b>\n\n"
    imagen_bytes = preparar_imagen_con_logo(url_imagen) if url_imagen else None

    respuesta = None
    try:
        if imagen_bytes:
            imagen_bytes.seek(0)
            respuesta = requests.post(f"{API}/sendPhoto", data={
                "chat_id": ADMIN_CHAT_ID,
                "caption": encabezado + texto + pie,
                "reply_markup": json.dumps(teclado),
                "parse_mode": "HTML",
            }, files={"photo": ("oferta.jpg", imagen_bytes, "image/jpeg")}, timeout=30)
        else:
            respuesta = requests.post(f"{API}/sendMessage", data={
                "chat_id": ADMIN_CHAT_ID,
                "text": encabezado + texto + "\n\n📸 <i>Sin imagen -- puedes responder a "
                        "este mensaje con una foto tuya para usarla en su lugar.</i>" + pie,
                "reply_markup": json.dumps(teclado),
                "parse_mode": "HTML",
            }, timeout=20)
    except Exception as e:
        print(f"[WARN] No se pudo enviar oferta a revisión: {e}")
        return

    try:
        message_id = respuesta.json()["result"]["message_id"]
        pendientes = _cargar_pendientes()
        if oferta_id in pendientes:
            pendientes[oferta_id]["message_id"] = message_id
            _guardar_pendientes(pendientes)
    except Exception as e:
        print(f"[WARN] No se pudo guardar el message_id de la revisión: {e}")


def _descargar_archivo_telegram(file_id):
    info = requests.get(f"{API}/getFile", params={"file_id": file_id}, timeout=15).json()
    file_path = info["result"]["file_path"]
    archivo = requests.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}", timeout=20)
    return archivo.content


def revisar_actividad_admin(publicar_func, manual_func=None):
    """
    Revisa en un solo paso: (1) si aprobaste/descartaste alguna oferta con
    los botones, (2) si respondiste a alguna oferta con una foto propia, y
    (3) si mandaste un mensaje NUEVO (no respuesta) con una URL -- oferta
    manual, se procesa con `manual_func(oferta_id, texto)` reutilizando el
    mismo pipeline de las ofertas automáticas (extracción, imagen, envío a
    revisión, todo igual).
    `publicar_func(texto, url_imagen, imagen_bytes, imagen_original_bytes)` es
    la función real de publicación -- se llama solo cuando apruebas.
    `imagen_original_bytes` (sin logo) solo viene poblado cuando subiste la
    foto a mano; se usa para Oferta Radar/Storage, nunca para Telegram/FB.
    """
    offset = _cargar_offset()
    try:
        resp = requests.get(f"{API}/getUpdates", params={
            "offset": offset,
            "allowed_updates": json.dumps(["callback_query", "message"]),
        }, timeout=20)
        data = resp.json()
    except Exception as e:
        print(f"[WARN] No se pudo consultar getUpdates: {e}")
        return

    if not data.get("ok"):
        # Causa típica: hay un webhook configurado en el bot, lo cual bloquea
        # getUpdates por completo. Se revisa y se limpia automáticamente.
        print(f"[WARN] getUpdates devolvió error: {data.get('description')}")
        try:
            info = requests.get(f"{API}/getWebhookInfo", timeout=15).json()
            url_webhook = info.get("result", {}).get("url")
            if url_webhook:
                print(f"[WARN] Hay un webhook configurado ({url_webhook}) -- eso bloquea getUpdates. Se elimina.")
                requests.get(f"{API}/deleteWebhook", timeout=15)
        except Exception as e:
            print(f"[WARN] No se pudo revisar/limpiar el webhook: {e}")
        return

    pendientes = _cargar_pendientes()
    max_update_id = offset - 1
    hubo_cambios_pendientes = False

    for update in data.get("result", []):
        max_update_id = max(max_update_id, update["update_id"])

        # Caso 1: botón de aprobar/descartar
        callback = update.get("callback_query")
        if callback and "data" in callback and ":" in callback["data"]:
            accion, oferta_id = callback["data"].split(":", 1)
            try:
                requests.post(f"{API}/answerCallbackQuery", data={
                    "callback_query_id": callback["id"],
                    "text": "Publicado ✅" if accion == "aprobar" else "Descartado ❌",
                }, timeout=15)
            except Exception as e:
                print(f"[WARN] No se pudo responder al botón: {e}")

            oferta = pendientes.pop(oferta_id, None)
            hubo_cambios_pendientes = True
            if not oferta:
                continue

            if accion == "aprobar":
                print(f"[REVISION] Aprobada por admin: {oferta_id}")
                imagen_bytes = None
                imagen_original_bytes = None
                if oferta.get("imagen_base64"):
                    imagen_bytes = io.BytesIO(base64.b64decode(oferta["imagen_base64"]))
                if oferta.get("imagen_original_base64"):
                    imagen_original_bytes = io.BytesIO(base64.b64decode(oferta["imagen_original_base64"]))
                publicar_func(oferta["texto"], oferta.get("url_imagen"), imagen_bytes, imagen_original_bytes)
                registrar_publicacion(oferta_id.split(":", 1)[0])
            else:
                print(f"[REVISION] Descartada por admin: {oferta_id}")
            continue

        # Caso 2: respondiste con una foto a un mensaje de revisión
        msg = update.get("message")

        # Caso 0: mensaje NUEVO (no respuesta) del admin con una URL --
        # oferta manual tuya, se procesa con el mismo pipeline de las
        # automáticas (extracción, imagen, revisión) vía manual_func.
        if (
            manual_func and msg and "text" in msg
            and "reply_to_message" not in msg
            and str(msg.get("chat", {}).get("id")) == str(ADMIN_CHAT_ID)
            and re.search(r"https?://", msg["text"])
        ):
            oferta_id = f"Manual:{msg['message_id']}"
            print(f"[MANUAL] URL recibida del admin, procesando como oferta nueva ({oferta_id})")
            try:
                manual_func(oferta_id, msg["text"])
            except Exception as e:
                print(f"[WARN] No se pudo procesar la URL manual: {e}")
            continue

        if msg and "photo" in msg and "reply_to_message" in msg:
            respondido_id = msg["reply_to_message"]["message_id"]
            oferta_id_encontrada = next(
                (oid for oid, datos in pendientes.items() if datos.get("message_id") == respondido_id),
                None,
            )
            if not oferta_id_encontrada:
                continue

            try:
                file_id = msg["photo"][-1]["file_id"]  # la de mayor resolución
                imagen_original = _descargar_archivo_telegram(file_id)
                m = re.search(r"💸 Precio: (.+)", pendientes[oferta_id_encontrada]["texto"])
                precio_para_badge = m.group(1).strip() if m else None
                imagen_con_logo = aplicar_logo_a_bytes(imagen_original, precio_texto=precio_para_badge)
                if imagen_con_logo:
                    pendientes[oferta_id_encontrada]["imagen_base64"] = base64.b64encode(
                        imagen_con_logo.getvalue()
                    ).decode()
                    # Versión LIMPIA (sin logo, tal cual llegó de Telegram) --
                    # se guarda aparte para Oferta Radar/Supabase Storage;
                    # Telegram/Facebook siguen usando la versión con logo.
                    pendientes[oferta_id_encontrada]["imagen_original_base64"] = base64.b64encode(
                        imagen_original
                    ).decode()
                    hubo_cambios_pendientes = True
                    requests.post(f"{API}/sendMessage", data={
                        "chat_id": ADMIN_CHAT_ID,
                        "text": "📸 Imagen actualizada para esa oferta. Toca Publicar cuando quieras.",
                    }, timeout=15)
            except Exception as e:
                print(f"[WARN] No se pudo procesar la foto manual: {e}")
            continue

        # Caso 3: respondiste con una PALABRA (alternativa a los botones, por
        # si el botón falla) -- "si"/"publicar"/"aprobar" para publicar,
        # "no"/"descartar"/"rechazar" para descartar.
        if msg and "text" in msg and "reply_to_message" in msg:
            respondido_id = msg["reply_to_message"]["message_id"]
            oferta_id_encontrada = next(
                (oid for oid, datos in pendientes.items() if datos.get("message_id") == respondido_id),
                None,
            )
            if not oferta_id_encontrada:
                continue

            palabra = msg["text"].strip().lower()
            aprobar_palabras = {"si", "sí", "publicar", "aprobar", "publica", "aprueba"}
            rechazar_palabras = {"no", "descartar", "rechazar", "descarta", "rechaza"}

            if palabra in aprobar_palabras or palabra in rechazar_palabras:
                oferta = pendientes.pop(oferta_id_encontrada, None)
                hubo_cambios_pendientes = True
                if not oferta:
                    continue
                if palabra in aprobar_palabras:
                    print(f"[REVISION] Aprobada por texto: {oferta_id_encontrada}")
                    imagen_bytes = None
                    imagen_original_bytes = None
                    if oferta.get("imagen_base64"):
                        imagen_bytes = io.BytesIO(base64.b64decode(oferta["imagen_base64"]))
                    if oferta.get("imagen_original_base64"):
                        imagen_original_bytes = io.BytesIO(base64.b64decode(oferta["imagen_original_base64"]))
                    publicar_func(oferta["texto"], oferta.get("url_imagen"), imagen_bytes, imagen_original_bytes)
                    registrar_publicacion(oferta_id_encontrada.split(":", 1)[0])
                else:
                    print(f"[REVISION] Descartada por texto: {oferta_id_encontrada}")
                try:
                    requests.post(f"{API}/sendMessage", data={
                        "chat_id": ADMIN_CHAT_ID,
                        "text": "Listo ✅" if palabra in aprobar_palabras else "Descartada ❌",
                    }, timeout=15)
                except Exception:
                    pass
                continue

            # Caso 4: cualquier otro texto de respuesta = corrección manual.
            # "precio: $X" o "título: X" corrigen ese campo puntual; texto
            # sin prefijo se toma como corrección del título (lo más común
            # cuando la IA lo saca mal o muy corto).
            texto_respuesta = msg["text"].strip()
            texto_lower = texto_respuesta.lower()
            if texto_lower.startswith(("precio:", "precio ")):
                nuevo_valor = texto_respuesta.split(":", 1)[-1].strip() if ":" in texto_respuesta else texto_respuesta[7:].strip()
                patron, reemplazo, etiqueta = r"💸 Precio: .*", f"💸 Precio: {nuevo_valor}", "Precio"
            elif texto_lower.startswith(("titulo:", "título:", "nombre:")):
                nuevo_valor = texto_respuesta.split(":", 1)[-1].strip()
                patron, reemplazo, etiqueta = r"📦 <b>Producto:</b> .*", f"📦 <b>Producto:</b> {nuevo_valor}", "Título"
            elif texto_lower.startswith(("cupon:", "cupón:", "codigo:", "código:")):
                nuevo_valor = texto_respuesta.split(":", 1)[-1].strip()
                patron = r"🏷️ Cupón: .*"
                reemplazo = f"🏷️ Cupón: <code>{nuevo_valor}</code>" if nuevo_valor.lower() not in {"no", "ninguno", "no necesita"} else "🏷️ Cupón: ¡No necesita!"
                etiqueta = "Cupón"
            elif texto_lower.startswith(("link:", "url:", "enlace:")):
                nuevo_valor = texto_respuesta.split(":", 1)[-1].strip()
                patron, reemplazo, etiqueta = r"⚡ Ver oferta: .*", f"⚡ Ver oferta: {nuevo_valor}", "Link"
            else:
                nuevo_valor = texto_respuesta
                patron, reemplazo, etiqueta = r"📦 <b>Producto:</b> .*", f"📦 <b>Producto:</b> {nuevo_valor}", "Título"

            texto_actualizado, n = re.subn(patron, reemplazo, pendientes[oferta_id_encontrada]["texto"], count=1)
            if n == 0:
                # No había esa línea (ej. oferta sin precio detectado) -- se
                # agrega después de la línea del producto en vez de perderla.
                texto_actualizado = re.sub(
                    r"(📦 <b>Producto:</b> .*)",
                    r"\1\n" + reemplazo,
                    pendientes[oferta_id_encontrada]["texto"],
                    count=1,
                )
            pendientes[oferta_id_encontrada]["texto"] = texto_actualizado
            hubo_cambios_pendientes = True
            try:
                requests.post(f"{API}/sendMessage", data={
                    "chat_id": ADMIN_CHAT_ID,
                    "text": f"✏️ {etiqueta} actualizado. Toca Publicar (o responde \"si\") cuando quieras.",
                }, timeout=15)
            except Exception:
                pass
            continue

    # Limpieza: descarta ofertas pendientes de más de 48h sin respuesta, para
    # que no se acumulen para siempre si alguna vez quedaron huérfanas.
    ahora = time.time()
    vencidas = [oid for oid, datos in pendientes.items() if ahora - datos.get("creado", ahora) > 48 * 3600]
    for oid in vencidas:
        pendientes.pop(oid, None)
        hubo_cambios_pendientes = True
    if vencidas:
        print(f"[INFO] Se descartaron {len(vencidas)} ofertas pendientes vencidas (+48h sin respuesta)")

    if hubo_cambios_pendientes:
        _guardar_pendientes(pendientes)
    if max_update_id >= offset:
        _guardar_offset(max_update_id + 1)
