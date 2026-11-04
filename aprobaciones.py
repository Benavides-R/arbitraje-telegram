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

# Link que parece una imagen (.jpg/.png/.webp o del servidor de imágenes de Amazon)
_RE_LINK_IMAGEN = re.compile(
    r"https?://(?:\S*media-amazon\.com/images/\S+|\S*?\.(?:jpe?g|png|webp)\b\S*)", re.IGNORECASE
)

PENDIENTES_FILE = Path(__file__).parent / "data" / "pendientes_revision.json"
OFFSET_FILE = Path(__file__).parent / "data" / "ultimo_update_id.txt"


def _cargar_pendientes():
    if PENDIENTES_FILE.exists():
        # encoding explícito: sin él, Windows leería con cp1252 y truena con
        # los emojis (💸 📸) del texto; en Actions (Linux) daba igual, pero
        # así es robusto en cualquier plataforma.
        return json.loads(PENDIENTES_FILE.read_text(encoding="utf-8"))
    return {}


def _guardar_pendientes(pendientes):
    PENDIENTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    PENDIENTES_FILE.write_text(json.dumps(pendientes, indent=2, ensure_ascii=False), encoding="utf-8")


# Cuánto dura una oferta en la cola de revisión antes de descartarse sola.
# Con cupón dura menos: el código de descuento suele vencer rápido y una
# oferta de hace 6h ya no le sirve a nadie. Sin cupón aguanta más (24h)
# porque el precio todavía puede estar vigente.
HORAS_PENDIENTE_CON_CUPON = 6
HORAS_PENDIENTE_SIN_CUPON = 24

# Mismo criterio que extraer_cupon() de revisar_canales.py, copiado aquí
# porque ese módulo ya importa este (importarlo al revés sería circular).
_RE_CUPON = re.compile(r"(?:c[oó]digo|cup[oó]n|code)[:\s]+([^\n]+)", re.IGNORECASE)
_CUPON_NEGATIVOS = {
    "no necesita", "ninguno", "no aplica", "sin cupon", "no requiere",
    "no aplica ninguno",
}


def _pendiente_tenia_cupon(datos):
    """True si la oferta original traía un cupón/código REAL (no la frase
    'no necesita cupón'). Se mira el texto original del canal y el mensaje
    ya armado, porque el armado repite la línea '🎟️ Cupón: ...'."""
    texto = " ".join(
        parte for parte in (datos.get("texto_original"), datos.get("texto")) if parte
    )
    for match in _RE_CUPON.finditer(texto):
        for parte in re.split(r"\s*(?:\+|,|/|\by\b)\s*", match.group(1)):
            candidato = re.sub(r"[^\w\s%-]", "", parte).strip()
            if not candidato or candidato.lower() in _CUPON_NEGATIVOS:
                continue
            if re.match(r"^[A-Za-z0-9-]{3,20}$", candidato):
                return True
            if re.match(r"^seleccionable\s+\d{1,2}\s*%$", candidato, re.IGNORECASE):
                return True
    return False


def limpiar_pendientes_viejos(ahora=None):
    """Descarta de la cola de revisión lo que ya no sirve: las ofertas con
    cupón que llevan más de 6h esperando y las demás que llevan más de 24h.
    Devuelve cuántas se borraron. Solo escribe el archivo si de verdad borró
    algo (no lo reescribe en cada corrida sin motivo)."""
    pendientes = _cargar_pendientes()
    if not pendientes:
        return 0

    ahora = time.time() if ahora is None else ahora
    quedan = {}
    con_cupon = sin_cupon = 0
    for oferta_id, datos in pendientes.items():
        horas = (ahora - (datos.get("creado") or 0)) / 3600
        limite = HORAS_PENDIENTE_CON_CUPON if _pendiente_tenia_cupon(datos) \
            else HORAS_PENDIENTE_SIN_CUPON
        if horas >= limite:
            if limite == HORAS_PENDIENTE_CON_CUPON:
                con_cupon += 1
            else:
                sin_cupon += 1
            continue
        quedan[oferta_id] = datos

    borrados = len(pendientes) - len(quedan)
    if borrados:
        _guardar_pendientes(quedan)
        print(f"[INFO] Cola de revisión: {borrados} oferta(s) vieja(s) descartada(s) "
              f"({con_cupon} con cupón de más de {HORAS_PENDIENTE_CON_CUPON}h, "
              f"{sin_cupon} sin cupón de más de {HORAS_PENDIENTE_SIN_CUPON}h) -- "
              f"quedan {len(quedan)}")
    return borrados


def _cargar_offset():
    if OFFSET_FILE.exists():
        contenido = OFFSET_FILE.read_text().strip()
        return int(contenido) if contenido else 0
    return 0


def _guardar_offset(offset):
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(str(offset))


def _quitar_tag_de_url(url):
    """Saca el parámetro 'tag' de la query de UNA url, sin tocar ni
    re-codificar el resto de parámetros (importante: nunca reescribir otros
    parámetros, que en algunos links van firmados)."""
    base, hash_, fragmento = url.partition("#")
    ruta, sep, query = base.partition("?")
    if not sep:
        return url
    querystring = [p for p in query.split("&") if not p.lower().startswith("tag=")]
    limpio = ruta + ("?" + "&".join(querystring) if querystring else "")
    if hash_:
        limpio += "#" + fragmento
    return limpio


def quitar_tag_afiliado(texto):
    """Quita el parámetro 'tag' (el tag de afiliado de Amazon) de los links
    SOLO para mostrarlos en el mensaje de revisión: así, cuando tú abres el
    link para revisar la oferta, ese clic NO se cuenta como venta/referido en
    el reporte de afiliado. El texto que se guarda y se publica al aprobar
    conserva su tag intacto (esa sí es la venta legítima)."""
    return re.sub(r"https?://\S+", lambda m: _quitar_tag_de_url(m.group(0)), texto)


def enviar_para_revision(oferta_id, texto, url_imagen, texto_original=None, asin=None):
    """Manda la oferta candidata al chat del admin, con botones para decidir.
    Guarda el message_id del envío, para poder detectar después si le
    respondes con una foto propia. Guarda también el ASIN: solo se marcará
    como "usado" (bloqueo 12h) si la oferta termina PUBLICADA (✅), no al
    mandarla a revisión."""
    if not ADMIN_CHAT_ID:
        print("[WARN] MODO_REVISION activo pero ADMIN_CHAT_ID no está configurado -- se descarta")
        return

    pendientes = _cargar_pendientes()
    pendientes[oferta_id] = {
        "texto": texto, "url_imagen": url_imagen, "creado": time.time(),
        "texto_original": texto_original, "asin": asin,
    }
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

    # En el mensaje que ves tú, los links van SIN el tag de afiliado (tus
    # clics de revisión no engañan el reporte de ventas). En `pendientes` se
    # guardó el `texto` original CON tag: al aprobar se publica ese, así que
    # la venta real sí queda atribuida.
    texto_visible = quitar_tag_afiliado(texto)

    if imagen_bytes:
        cuerpo_texto = encabezado + texto_visible + pie
    else:
        cuerpo_texto = (encabezado + texto_visible + "\n\n📸 <i>Sin imagen -- responde a "
                         "este mensaje con una foto tuya, o pega el link de la imagen "
                         "(el que copia la extensión de Chrome) y la uso.</i>" + pie)

    # Telegram limita el "caption" de una foto a 1024 caracteres -- los links
    # de afiliado de AliExpress son muy largos y lo pueden superar. Si pasa,
    # se manda la foto SIN texto, y el texto completo (con los botones) va
    # aparte, en un mensaje normal sin ese límite.
    caption_muy_largo = imagen_bytes is not None and len(cuerpo_texto) > 1024

    respuesta = None
    try:
        if imagen_bytes and not caption_muy_largo:
            imagen_bytes.seek(0)
            respuesta = requests.post(f"{API}/sendPhoto", data={
                "chat_id": ADMIN_CHAT_ID,
                "caption": cuerpo_texto,
                "reply_markup": json.dumps(teclado),
                "parse_mode": "HTML",
            }, files={"photo": ("oferta.jpg", imagen_bytes, "image/jpeg")}, timeout=60)
        else:
            if imagen_bytes:
                imagen_bytes.seek(0)
                requests.post(f"{API}/sendPhoto", data={"chat_id": ADMIN_CHAT_ID},
                               files={"photo": ("oferta.jpg", imagen_bytes, "image/jpeg")}, timeout=60)
            respuesta = requests.post(f"{API}/sendMessage", data={
                "chat_id": ADMIN_CHAT_ID,
                "text": cuerpo_texto,
                "reply_markup": json.dumps(teclado),
                "parse_mode": "HTML",
            }, timeout=20)
    except Exception as e:
        print(f"[WARN] No se pudo enviar oferta a revisión: {e}")
        return False

    try:
        cuerpo_respuesta = respuesta.json()
    except Exception as e:
        print(f"[WARN] Respuesta de Telegram no es JSON válido: {respuesta.text[:300]}")
        return False

    if not cuerpo_respuesta.get("ok"):
        print(f"[WARN] Telegram rechazó el envío a revisión: {cuerpo_respuesta}")
        return False

    try:
        message_id = cuerpo_respuesta["result"]["message_id"]
        pendientes = _cargar_pendientes()
        if oferta_id in pendientes:
            pendientes[oferta_id]["message_id"] = message_id
            _guardar_pendientes(pendientes)
    except Exception as e:
        print(f"[WARN] No se pudo guardar el message_id de la revisión: {e}")

    return True


def _descargar_archivo_telegram(file_id):
    info = requests.get(f"{API}/getFile", params={"file_id": file_id}, timeout=15).json()
    file_path = info["result"]["file_path"]
    archivo = requests.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}", timeout=20)
    return archivo.content


def _avisar_no_encontrada():
    """Le avisa al admin que su respuesta no encontró ninguna oferta
    pendiente -- antes esto pasaba en silencio (foto o corrección se
    perdían sin que el admin se enterara)."""
    try:
        requests.post(f"{API}/sendMessage", data={
            "chat_id": ADMIN_CHAT_ID,
            "text": (
                "⚠️ No encontré a qué oferta corresponde ese mensaje -- puede "
                "que ya se haya publicado, descartado, o vencido (+48h). "
                "Verifica que respondiste al mensaje ORIGINAL de esa oferta."
            ),
        }, timeout=15)
    except Exception:
        pass


def revisar_actividad_admin(publicar_func, manual_func=None, marcar_publicado_func=None, asin_publicado_func=None):
    """
    Revisa en un solo paso: (1) si aprobaste/descartaste alguna oferta con
    los botones, (2) si respondiste a alguna oferta con una foto propia, y
    (3) si mandaste un mensaje NUEVO (no respuesta) con una URL -- oferta
    manual, se procesa con `manual_func(oferta_id, texto)` reutilizando el
    mismo pipeline de las ofertas automáticas (extracción, imagen, envío a
    revisión, todo igual).
    `publicar_func(texto, url_imagen, imagen_bytes, imagen_original_bytes)` es
    la función real de publicación -- se llama solo cuando apruebas, y
    DEVUELVE True/False (False = no salió). Si devuelve False no se marca el
    ASIN ni se cuenta como publicada, y te avisa para que la reenvíes.
    `imagen_original_bytes` (sin logo) solo viene poblado cuando subiste la
    foto a mano; se usa para Oferta Radar/Storage, nunca para Telegram/FB.
    `marcar_publicado_func(asin)` se llama SOLO cuando la oferta se publica
    de verdad (✅) -- así el bloqueo de 12h es únicamente por publicación.
    `asin_publicado_func(asin)` devuelve True si ese producto ya se publicó
    hace menos de 12h: evita publicar dos copias de la misma oferta.
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
    # Línea base de claves al INICIO de la corrida -- sirve para identificar
    # más abajo qué claves son NUEVAS (creadas en disco por esta misma
    # corrida) sin revivir las que ya se aprobaron/descartaron en ella.
    pendientes_base = set(pendientes)
    max_update_id = offset - 1
    hubo_cambios_pendientes = False

    for update in data.get("result", []):
        max_update_id = max(max_update_id, update["update_id"])

        # Caso 1: botón de aprobar/descartar
        callback = update.get("callback_query")
        if callback and "data" in callback and ":" in callback["data"]:
            accion, oferta_id = callback["data"].split(":", 1)

            oferta = pendientes.pop(oferta_id, None)
            hubo_cambios_pendientes = True
            if not oferta:
                # La oferta ya no está en la cola: o ya se publicó/descartó,
                # o se perdió su registro (p. ej. una corrida que falló al
                # guardar el estado). Antes se respondía "Publicado ✅" y no
                # se publicaba nada: eso confundía. Ahora se avisa claro.
                print(f"[REVISION] {oferta_id}: no está en la cola, no se publica")
                try:
                    requests.post(f"{API}/answerCallbackQuery", data={
                        "callback_query_id": callback["id"],
                        "text": "⚠️ Esa oferta ya no está en la cola",
                    }, timeout=15)
                except Exception as e:
                    print(f"[WARN] No se pudo responder al botón: {e}")
                try:
                    requests.post(f"{API}/sendMessage", data={
                        "chat_id": ADMIN_CHAT_ID,
                        "text": "⚠️ Esa oferta ya no está en la cola del bot, así que NO se publicó. "
                                "Si la quieres, mándamela de nuevo.",
                    }, timeout=15)
                except Exception:
                    pass
                continue

            try:
                requests.post(f"{API}/answerCallbackQuery", data={
                    "callback_query_id": callback["id"],
                    "text": "Publicado ✅" if accion == "aprobar" else "Descartado ❌",
                }, timeout=15)
            except Exception as e:
                print(f"[WARN] No se pudo responder al botón: {e}")

            if accion == "aprobar":
                asin = oferta.get("asin")
                # Anti-duplicado: si el mismo producto ya se publicó hace
                # menos de 12h (p. ej. te llegaron dos copias de la misma
                # oferta), esta segunda copia NO se publica.
                if asin_publicado_func and asin_publicado_func(asin):
                    print(f"[REVISION] {oferta_id}: ASIN {asin} ya publicado hace <12h, se evita duplicado")
                    try:
                        requests.post(f"{API}/sendMessage", data={
                            "chat_id": ADMIN_CHAT_ID,
                            "text": "⚠️ No se publicó: ese mismo producto ya salió hace menos de 12h (duplicado evitado).",
                        }, timeout=15)
                    except Exception:
                        pass
                    continue
                print(f"[REVISION] Aprobada por admin: {oferta_id}")
                try:
                    imagen_bytes = None
                    imagen_original_bytes = None
                    if oferta.get("imagen_base64"):
                        imagen_bytes = io.BytesIO(base64.b64decode(oferta["imagen_base64"]))
                    if oferta.get("imagen_original_base64"):
                        imagen_original_bytes = io.BytesIO(base64.b64decode(oferta["imagen_original_base64"]))
                    publicado = publicar_func(oferta["texto"], oferta.get("url_imagen"), imagen_bytes, imagen_original_bytes,
                                              texto_original=oferta.get("texto_original"))
                    if publicado is False:
                        # No salió: NO se marca el ASIN ni se cuenta como
                        # publicada, y se avisa para que la reenvíes.
                        print(f"[WARN] {oferta_id}: no se pudo publicar, no se marca el ASIN")
                        try:
                            requests.post(f"{API}/sendMessage", data={
                                "chat_id": ADMIN_CHAT_ID,
                                "text": "⚠️ No se pudo publicar esa oferta. No se marcó como usada, "
                                        "así que puedes volver a mandarla cuando quieras.",
                            }, timeout=15)
                        except Exception:
                            pass
                        continue
                    # El ASIN se marca como USADO recién aquí: la oferta ya
                    # salió de verdad. Si publicar falla, no se marca.
                    if marcar_publicado_func:
                        marcar_publicado_func(asin)
                    registrar_publicacion(
                        oferta_id.split(":", 1)[0],
                        texto=oferta["texto"],
                        con_imagen=bool(oferta.get("url_imagen") or oferta.get("imagen_base64")),
                    )
                    time.sleep(60)  # espacia publicaciones en Facebook si apruebas varias juntas
                except Exception as e:
                    # Si UNA oferta falla al publicar, no se debe perder el
                    # resto del lote -- antes esto tumbaba toda la corrida y
                    # como el offset de Telegram no avanza hasta el final de
                    # la función, esa misma oferta rota se reintentaba (y
                    # fallaba) en cada corrida, bloqueando todo lo que venía
                    # después de ella en la cola, indefinidamente.
                    print(f"[ERROR] Falló publicar {oferta_id}, se sigue con las demás: {e}")
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
            # manual_func (vía enviar_para_revision) ya guardó la oferta nueva
            # en disco por su cuenta -- se trae SOLO esa clave nueva a esta
            # copia en memoria. Antes se recargaba el archivo entero aquí, y
            # eso restauraba las ofertas aprobadas/descartadas EN ESTA MISMA
            # corrida (se habían quitado arriba pero todavía no se habían
            # guardado): una aprobada volvía a la cola y su botón viejo
            # volvía a poder publicarla (duplicado).
            for oid_nuevo, datos_nuevos in _cargar_pendientes().items():
                if oid_nuevo not in pendientes_base:
                    pendientes[oid_nuevo] = datos_nuevos
            continue

        if msg and "photo" in msg and "reply_to_message" in msg:
            respondido_id = msg["reply_to_message"]["message_id"]
            oferta_id_encontrada = next(
                (oid for oid, datos in pendientes.items() if datos.get("message_id") == respondido_id),
                None,
            )
            if not oferta_id_encontrada:
                _avisar_no_encontrada()
                continue

            guardada = False
            try:
                file_id = msg["photo"][-1]["file_id"]  # la de mayor resolución
                imagen_original = _descargar_archivo_telegram(file_id)
                m = re.search(r"💸 Precio: (.+)", pendientes[oferta_id_encontrada]["texto"])
                precio_para_badge = m.group(1).strip().lstrip("~").strip() if m else None
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
                    # (A) Persistir la foto YA, no al final de la corrida --
                    # entre este punto y el guardado final pasaban 5-20 min
                    # de memoria volátil: si la corrida moría ahí (crash,
                    # timeout), la foto se perdía y la oferta salía sin ella.
                    _guardar_pendientes(pendientes)
                    guardada = True
                    requests.post(f"{API}/sendMessage", data={
                        "chat_id": ADMIN_CHAT_ID,
                        "text": "📸 Imagen actualizada para esa oferta. Toca Publicar cuando quieras.",
                    }, timeout=15)
            except Exception as e:
                print(f"[WARN] No se pudo procesar la foto manual: {e}")
            if not guardada:
                # (B) Antes esto fallaba en silencio (solo un WARN en los logs
                # de Actions) y el admin aprobaba creyendo que su foto quedó
                # guardada -- terminaba en publicación SIN imagen. Ahora avisa
                # en el chat para que la reenvíe ANTES de tocar Publicar.
                try:
                    requests.post(f"{API}/sendMessage", data={
                        "chat_id": ADMIN_CHAT_ID,
                        "text": ("⚠️ No pude guardar tu foto de esa oferta -- vuelve a responder "
                                 "al mensaje de revisión con tu foto y espera el 📸 antes de publicar."),
                    }, timeout=15)
                except Exception:
                    pass
            continue

        # Caso 2b: respondiste con un LINK DE IMAGEN (ej. el que copia la
        # extensión de Chrome) a una oferta de revisión que llegó sin foto.
        # Se descarga (desde el servidor de imágenes, no la página del
        # producto: no da captcha), se comprueba y queda como imagen de la
        # oferta; el logo y el precio se ponen al publicar, como siempre.
        if msg and "text" in msg and "reply_to_message" in msg:
            m_img = _RE_LINK_IMAGEN.search(msg["text"])
            if m_img:
                respondido_id = msg["reply_to_message"]["message_id"]
                oferta_id_encontrada = next(
                    (oid for oid, datos in pendientes.items() if datos.get("message_id") == respondido_id),
                    None,
                )
                if not oferta_id_encontrada:
                    _avisar_no_encontrada()
                    continue
                url_img = m_img.group(0)
                aviso = "⚠️ No pude descargar esa imagen -- revisa el link o responde con una foto."
                try:
                    m = re.search(r"💸 Precio: (.+)", pendientes[oferta_id_encontrada]["texto"])
                    precio_badge = m.group(1).strip().lstrip("~").strip() if m else None
                    if preparar_imagen_con_logo(url_img, precio_texto=precio_badge):
                        pendientes[oferta_id_encontrada]["url_imagen"] = url_img
                        hubo_cambios_pendientes = True
                        _guardar_pendientes(pendientes)
                        aviso = "📸 Imagen actualizada para esa oferta. Toca Publicar cuando quieras."
                except Exception as e:
                    print(f"[WARN] No se pudo procesar el link de imagen: {e}")
                try:
                    requests.post(f"{API}/sendMessage", data={"chat_id": ADMIN_CHAT_ID, "text": aviso}, timeout=15)
                except Exception:
                    pass
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
                _avisar_no_encontrada()
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
                    publicada_ok = None
                    try:
                        imagen_bytes = None
                        imagen_original_bytes = None
                        if oferta.get("imagen_base64"):
                            imagen_bytes = io.BytesIO(base64.b64decode(oferta["imagen_base64"]))
                        if oferta.get("imagen_original_base64"):
                            imagen_original_bytes = io.BytesIO(base64.b64decode(oferta["imagen_original_base64"]))
                        publicada_ok = publicar_func(oferta["texto"], oferta.get("url_imagen"), imagen_bytes, imagen_original_bytes,
                                                     texto_original=oferta.get("texto_original"))
                        if publicada_ok is False:
                            print(f"[WARN] {oferta_id_encontrada}: no se pudo publicar, no se marca el ASIN")
                        else:
                            # Solo si salió de verdad: se marca el ASIN (antes
                            # esta vía ni siquiera lo marcaba) y se cuenta.
                            if marcar_publicado_func:
                                marcar_publicado_func(oferta.get("asin"))
                            registrar_publicacion(
                                oferta_id_encontrada.split(":", 1)[0],
                                texto=oferta["texto"],
                                con_imagen=bool(oferta.get("url_imagen") or oferta.get("imagen_base64")),
                            )
                            time.sleep(60)  # espacia publicaciones en Facebook si apruebas varias juntas
                    except Exception as e:
                        publicada_ok = False
                        print(f"[ERROR] Falló publicar {oferta_id_encontrada}, se sigue con las demás: {e}")
                else:
                    print(f"[REVISION] Descartada por texto: {oferta_id_encontrada}")
                try:
                    if palabra in aprobar_palabras:
                        respuesta = "Listo ✅" if publicada_ok is not False else \
                            "⚠️ No se pudo publicar. No se marcó como usada, puedes volver a mandarla."
                    else:
                        respuesta = "Descartada ❌"
                    requests.post(f"{API}/sendMessage", data={
                        "chat_id": ADMIN_CHAT_ID,
                        "text": respuesta,
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
                # Acepta uno o varios cupones separados por "+" o ",".
                _codigos = [c.strip() for c in re.split(r"[+,]", nuevo_valor) if c.strip()]
                reemplazo = ("🏷️ Cupón: " + " + ".join(f"<code>{c}</code>" for c in _codigos)) if _codigos and nuevo_valor.lower() not in {"no", "ninguno", "no necesita"} else "🏷️ Cupón: ¡No necesita!"
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
