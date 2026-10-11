"""
Insignias (badges) del mensaje final -- fuente UNICA.

Las mismas cadenas se usan en dos lugares:
  * revisar_canales.py las ESCRIBE en la linea de insignias del mensaje.
  * oferta_radar.py las LEE de vuelta para armar shipping/isPrime.

Antes cada archivo tenia su propia copia del texto: si cambiabas una y
te olvidabas de la otra, Oferta Radar dejaba de leer el envio en
silencio. Aqui se cambian una sola vez y cambian en los dos lados.
"""

import re
import unicodedata

# Texto EXACTO de cada insignia, tal como aparece en el mensaje publicado.
BADGE_ENVIO_CASILLERO = "📦 Requiere Casillero USA"
BADGE_ENVIO_PRIME = "🅿️ ¡Envío Gratis Con PRIME!"
BADGE_ENVIO_ELEGIBLE = "🚚 ¡Elegible para envío GRATIS!"
BADGE_ENVIO_GRATIS = "🚚 ¡Envío GRATIS!"
BADGE_RELAMPAGO = "⚡️¡Oferta Relámpago!"

# (valor para Oferta Radar, insignia). El ORDEN importa: de mas
# especifica a mas generica ("Envio Gratis Con PRIME" y "Elegible para
# envio GRATIS" contienen "envio gratis", asi que el generico va al
# final). Solo UNA de envio puede salir a la vez.
BADGES_ENVIO = [
    ("prime", BADGE_ENVIO_PRIME),
    ("elegible", BADGE_ENVIO_ELEGIBLE),
    ("gratis", BADGE_ENVIO_GRATIS),
    ("casillero", BADGE_ENVIO_CASILLERO),
]


def _normalizar(texto):
    """Minusculas, sin tildes y espacios colapsados -- para que una
    correccion manual del mensaje (mas minusculas, sin tildes, doble
    espacio) siga coincidiendo con la insignia."""
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto)


def _nucleo(insignia):
    """Solo letras y espacios de la insignia (sin emoji, sin signos):
    si alguien edita el mensaje a mano y quita el "¡...!" o el emoji,
    sigue coincidiendo sin tener que reescribir el texto en ningun
    otro archivo."""
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-z ]+", " ", _normalizar(insignia))).strip()


# (valor, nucleo de la insignia) calculado una sola vez, en orden de
# mas especifico a mas generico.
_NUCLEOS = [(valor, _nucleo(insignia)) for valor, insignia in BADGES_ENVIO]


def detectar_envio(texto):
    """Devuelve "prime" | "elegible" | "gratis" | "casillero" segun la
    insignia que aparezca en el texto del mensaje aprobado, o None si no
    hay ninguna (nunca inventa envio)."""
    if not texto:
        return None
    normalizado = _normalizar(texto)
    for valor, nucleo in _NUCLEOS:
        if nucleo in normalizado:
            return valor
    return None
