"""
Selección de ofertas para los videos/imágenes de Facebook (script aparte).

Flujo:
  1. Cada vez que se publica una oferta de verdad (auto o aprobada manual),
     revisar_canales.py llama a registrar_oferta_para_video() -- si el
     título cae en una categoría de interés (tecnología o ropa/calzado),
     queda guardada en data/historial_video.json con toda la info que la
     otra IA de videos va a necesitar.
  2. Todos los días a una hora fija (workflow aparte) o cuando tú mandes
     el comando "/elegir" al bot, enviar_candidatas_para_elegir() te manda
     un álbum de fotos numerado por Telegram con las mejores candidatas
     recientes.
  3. Le respondes al bot con los números que quieras (ej. "1,3,5") y
     confirmar_seleccion() arma data/seleccion_video.json -- el archivo
     final que la otra IA debería leer para generar los videos.
"""

import os
import re
import html
import json
import time
import requests
import unicodedata
from pathlib import Path
from datetime import datetime, timezone, timedelta

from config import ADMIN_CHAT_ID

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

HISTORIAL_FILE = Path(__file__).parent / "data" / "historial_video.json"
PENDIENTE_FILE = Path(__file__).parent / "data" / "pendiente_seleccion_video.json"
SELECCION_FILE = Path(__file__).parent / "data" / "seleccion_video.json"

DIAS_RETENCION_HISTORIAL = 14  # no tiene sentido acumular más que eso
ZONA_COLOMBIA = timezone(timedelta(hours=-5))

# Palabras clave para decidir si una oferta aplica a este nicho de video.
# Si el título no cae en ninguna, no se guarda en el historial (no todo lo
# que se publica es útil para el video -- ej. cosas de cocina, bebés, etc.
# quedan fuera hasta que agregues esas categorías si algún día las quieres).
CATEGORIAS_VIDEO = {
    "tecnologia": [
        # Gadgets pequeños / accesorios
        "cargador", "audifono", "auricular", "smartwatch", "reloj inteligente",
        "camara", "tablet", "laptop", "bluetooth", "usb-c", "usb c", "altavoz",
        "parlante", "bocina", "power bank", "batería externa", "bateria externa",
        "drone", "dron", "monitor", "teclado", "mouse", "proyector", "gadget",
        "smart", "led", "gaming", "consola", "impresora", "router", "gps",
        "airtag", "localizador", "rastreador", "cable", "adaptador", "hub",
        "disco duro", "ssd", "memoria usb", "lector", "escaner", "calculadora",
        "extensor wifi", "power strip", "regulador de voltaje", "estabilizador",
        # Cámaras / seguridad / hogar inteligente
        "camara de seguridad", "timbre inteligente", "cerradura inteligente",
        "sensor de movimiento", "alarma",
        # Electrodomésticos / línea blanca y pequeña
        "cafetera", "licuadora", "batidora", "freidora de aire", "aspiradora",
        "robot aspirador", "microondas", "nevera", "lavadora", "secadora",
        "ventilador", "purificador de aire", "humidificador", "plancha",
        "olla", "sanduchera", "tostadora", "extractor de jugos",
        # Pantallas / entretenimiento
        "televisor", "pantalla", "smart tv", "soundbar", "home theater",
    ],
    "ropa_calzado": [
        "tenis", "zapatilla", "zapato", "bota", "sandalia", "chancla",
        "chaqueta", "abrigo", "sudadera", "hoodie", "camiseta", "camisa",
        "pantalon", "jean", "short", "gorra", "gafas de sol", "mochila",
        "correa", "cinturon",
    ],
}


def _sin_tildes(texto):
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def categorizar_para_video(titulo):
    """Devuelve 'tecnologia', 'ropa_calzado' o None si no aplica a ninguna."""
    titulo_norm = _sin_tildes(titulo.lower())
    for categoria, palabras in CATEGORIAS_VIDEO.items():
        if any(p in titulo_norm for p in palabras):
            return categoria
    return None


_RE_DESCUENTO = re.compile(r"(\d{1,2})\s*%\s*(?:off|dcto\.?|descuento)", re.IGNORECASE)


def extraer_descuento_pct(texto_original):
    """Lee el % de descuento tal cual lo escribió el canal (si lo menciona).
    No se calcula -- no hay precio 'antes' confiable guardado, se toma el
    dato tal como viene."""
    m = _RE_DESCUENTO.search(texto_original or "")
    return int(m.group(1)) if m else None


def _cargar_json(archivo, valor_default):
    if archivo.exists():
        try:
            return json.loads(archivo.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"[WARN] {archivo.name} no se pudo leer ({e}) -- "
                  f"si esto pasa con el historial de video, se perdería sin querer")
            return valor_default
    return valor_default


def _guardar_json(archivo, datos):
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(json.dumps(datos, indent=2, ensure_ascii=False))


def registrar_oferta_para_video(texto_original, texto_nuevo, url_imagen, url_oferta_radar=None):
    """Se llama justo cuando una oferta SE PUBLICÓ de verdad (no antes).
    Ya no exige imagen -- la lista de las 5pm es puro texto (título+precio),
    la foto solo hace falta después si eliges esa oferta para el video."""
    m_titulo = re.search(r"📦 <b>Producto:</b>\s*(.+)", texto_nuevo)
    m_precio = re.search(r"💸 Precio:\s*([^\n🔻(]+)", texto_nuevo)
    m_link = re.search(r"⚡ Ver oferta:\s*(\S+)", texto_nuevo)
    m_cupon = re.search(r"🏷️ Cupón:\s*(?:<code>)?([^<\n]+)", texto_nuevo)
    cupon = m_cupon.group(1).strip() if m_cupon and "No necesita" not in m_cupon.group(1) else None
    if not m_titulo or not m_precio:
        return

    titulo = html.unescape(m_titulo.group(1).strip())
    categoria = categorizar_para_video(titulo)  # se guarda como dato informativo, ya no filtra nada

    entrada = {
        "fecha": datetime.now(ZONA_COLOMBIA).isoformat(),
        "categoria": categoria,
        "titulo": titulo,
        "precio": m_precio.group(1).strip(),
        "descuento_pct": extraer_descuento_pct(texto_original),
        "cupon": cupon,
        "imagen": url_imagen,
        "link": url_oferta_radar or (m_link.group(1).strip() if m_link else None),
    }

    historial = _cargar_json(HISTORIAL_FILE, [])
    historial.append(entrada)

    corte = datetime.now(ZONA_COLOMBIA) - timedelta(days=DIAS_RETENCION_HISTORIAL)
    historial = [h for h in historial if datetime.fromisoformat(h["fecha"]) > corte]

    _guardar_json(HISTORIAL_FILE, historial)


def generar_candidatas(dias=1, top_n=40):
    """Ofertas de HOY (desde medianoche hora Colombia), no ventana rodante
    de 24h. Primero las que tienen % de descuento (de mayor a menor), luego
    el resto. No excluye ofertas ya elegidas antes -- si una sigue vigente
    semanas después y la vuelves a elegir, se procesa igual."""
    historial = _cargar_json(HISTORIAL_FILE, [])
    corte = datetime.now(ZONA_COLOMBIA).replace(hour=0, minute=0, second=0, microsecond=0)
    recientes = [h for h in historial if datetime.fromisoformat(h["fecha"]) > corte]
    recientes.sort(key=lambda h: h["descuento_pct"] if h["descuento_pct"] is not None else -1, reverse=True)
    return recientes[:top_n]


def enviar_candidatas_para_elegir(dias=1):
    """Manda la lista en texto plano (número + título + precio) al admin.
    Guarda la tanda enviada para poder interpretar tu respuesta después."""
    if not ADMIN_CHAT_ID:
        print("[VIDEO] ADMIN_CHAT_ID no configurado, no se puede enviar")
        return

    candidatas = generar_candidatas(dias=dias)
    if not candidatas:
        requests.post(f"{API}/sendMessage", data={
            "chat_id": ADMIN_CHAT_ID,
            "text": "🎬 No hay ofertas recientes para elegir hoy.",
        }, timeout=15)
        return

    lineas = [f"🎬 {len(candidatas)} ofertas de hoy, elige las que quieras para video:", ""]
    for i, c in enumerate(candidatas, start=1):
        descuento_txt = f" (-{c['descuento_pct']}%)" if c["descuento_pct"] else ""
        sin_foto = "" if c.get("imagen") else " 📵 sin foto"
        lineas.append(f"{i}) {c['titulo'][:120]} - {c['precio']}{descuento_txt}{sin_foto}")
    lineas.append("")
    lineas.append("Responde con los números o rangos que quieras (ej: 1-5, 15, 20-30).")

    # Telegram tiene un límite de 4096 caracteres por mensaje -- si el
    # listado no cabe, se manda partido en varios mensajes.
    texto_completo = "\n".join(lineas)
    for i in range(0, len(texto_completo), 4000):
        requests.post(f"{API}/sendMessage", data={
            "chat_id": ADMIN_CHAT_ID,
            "text": texto_completo[i:i + 4000],
        }, timeout=15)

    _guardar_json(PENDIENTE_FILE, {"candidatas": candidatas, "enviado": time.time()})


def hay_seleccion_pendiente():
    pendiente = _cargar_json(PENDIENTE_FILE, None)
    if not pendiente:
        return False
    # Si ya pasaron más de 48h sin que respondas, se considera vencida --
    # no queremos interpretar un mensaje tuyo de otro tema como si fueran
    # números de una tanda vieja que ya ni te acuerdas.
    return (time.time() - pendiente["enviado"]) < 48 * 3600


_RE_SOLO_NUMEROS = re.compile(r"^[\d,\s-]+$")


def _parsear_numeros_y_rangos(texto):
    """'1-5, 15, 20-30' -> [1,2,3,4,5,15,20,21,...,30]"""
    numeros = set()
    for parte in texto.split(","):
        parte = parte.strip()
        if not parte:
            continue
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", parte)
        if m:
            desde, hasta = int(m.group(1)), int(m.group(2))
            if desde > hasta:
                desde, hasta = hasta, desde
            numeros.update(range(desde, hasta + 1))
        elif parte.isdigit():
            numeros.add(int(parte))
    return sorted(numeros)


def procesar_respuesta_seleccion(texto_mensaje):
    """True si el mensaje se interpretó como una selección (y ya se
    procesó); False si no aplica (para que quien llama siga con lo suyo)."""
    if not hay_seleccion_pendiente():
        return False
    if not _RE_SOLO_NUMEROS.match(texto_mensaje.strip()):
        return False

    pendiente = _cargar_json(PENDIENTE_FILE, {})
    candidatas = pendiente.get("candidatas", [])
    numeros = _parsear_numeros_y_rangos(texto_mensaje)
    elegidas = [candidatas[n - 1] for n in numeros if 1 <= n <= len(candidatas)]

    if not elegidas:
        requests.post(f"{API}/sendMessage", data={
            "chat_id": ADMIN_CHAT_ID,
            "text": "No reconocí ningún número válido de la lista, intenta de nuevo.",
        }, timeout=15)
        return True

    seleccion_previa = _cargar_json(SELECCION_FILE, [])
    seleccion_previa.extend(elegidas)
    _guardar_json(SELECCION_FILE, seleccion_previa)

    if PENDIENTE_FILE.exists():
        PENDIENTE_FILE.unlink()

    requests.post(f"{API}/sendMessage", data={
        "chat_id": ADMIN_CHAT_ID,
        "text": f"✅ {len(elegidas)} ofertas guardadas en la selección para video.",
    }, timeout=15)
    return True
