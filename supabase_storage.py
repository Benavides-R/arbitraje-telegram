"""
Sube a Supabase Storage la MISMA imagen que ya se publica en Telegram/
Facebook (con el logo de BenaTechs) -- no se descarga ni se genera una
segunda versión de la imagen.

Requiere en GitHub Secrets:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY

Si cualquiera de las dos falta, o si algo falla, devuelve None -- quien
llame a esto debe seguir funcionando igual usando la URL de respaldo.
"""

import io
import hashlib
import requests
from PIL import Image

from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

BUCKET = "ofertas-images"
TIMEOUT_SEGUNDOS = 20
MAX_LADO = 1000
CALIDAD_WEBP = 85


def _optimizar_a_webp(imagen_bytes):
    """Toma los bytes YA procesados (con logo) y los convierte a WebP,
    máximo 1000x1000 (mantiene proporción, no recorta de nuevo).
    Acepta tanto bytes crudos como un io.BytesIO ya abierto (que es lo que
    realmente le llega desde aplicar_logo_a_bytes/preparar_imagen_con_logo
    -- volver a envolverlo en otro BytesIO() lanzaba TypeError)."""
    if isinstance(imagen_bytes, io.BytesIO):
        imagen_bytes.seek(0)
        img = Image.open(imagen_bytes).convert("RGB")
    else:
        img = Image.open(io.BytesIO(imagen_bytes)).convert("RGB")
    img.thumbnail((MAX_LADO, MAX_LADO))
    buffer = io.BytesIO()
    img.save(buffer, format="WEBP", quality=CALIDAD_WEBP)
    return buffer.getvalue()


def subir_a_supabase(imagen_bytes):
    """
    Recibe los bytes de imagen que el sistema YA generó (con logo) y
    devuelve la URL pública en Supabase Storage, o None si no se pudo
    (Supabase no configurado, o cualquier error -- nunca lanza excepción
    hacia afuera).
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY or not imagen_bytes:
        return None

    try:
        webp_bytes = _optimizar_a_webp(imagen_bytes)
    except Exception as e:
        print(f"[Supabase Storage] No se pudo optimizar la imagen a WebP: {e}")
        return None

    sha256 = hashlib.sha256(webp_bytes).hexdigest()
    ruta = f"ofertas/{sha256}.webp"
    url_publica = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{BUCKET}/{ruta}"

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "image/webp",
    }

    try:
        resp = requests.post(
            f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{BUCKET}/{ruta}",
            headers=headers,
            data=webp_bytes,
            timeout=TIMEOUT_SEGUNDOS,
        )
    except Exception as e:
        # Nunca se imprime la service role key -- solo el tipo de problema.
        print(f"[Supabase Storage] error al subir (sin conexión/timeout: {e})")
        return None

    if resp.status_code in (200, 201):
        print(f"[Supabase Storage] OK: {ruta}")
        return url_publica

    if resp.status_code in (400, 409) and "duplicate" in resp.text.lower():
        # El mismo SHA-256 ya existe -- es el mismo archivo, se reutiliza
        # la misma URL sin volver a subir nada.
        print(f"[Supabase Storage] ya existía (mismo hash), reutilizando: {ruta}")
        return url_publica

    print(f"[Supabase Storage] error al subir (HTTP {resp.status_code}): {resp.text[:300]}")
    return None
