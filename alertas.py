"""
Conteo de fallos durante una corrida + aviso al admin por Telegram.

Cualquier parte del bot puede llamar a registrar_fallo("categoria") cuando
algo no funcionó como se esperaba (sin frenar la corrida por eso). Al final
de main(), si hubo fallos, se manda un resumen -- y si la corrida entera se
cae con una excepción no controlada, también se avisa antes de terminar.
Así te enteras en Telegram en vez de tener que revisar el log de GitHub.
"""

import os
import traceback
import requests

from config import ADMIN_CHAT_ID

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

_contadores = {}


def registrar_fallo(categoria):
    _contadores[categoria] = _contadores.get(categoria, 0) + 1


def hubo_fallos():
    return bool(_contadores)


def resumen_fallos():
    return ", ".join(f"{v}x {k}" for k, v in _contadores.items())


def enviar_alerta(mensaje):
    if not BOT_TOKEN:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_CHAT_ID, "text": mensaje},
            timeout=15,
        )
    except Exception:
        pass  # si hasta el aviso falla, no hay mucho más que hacer desde aquí


def avisar_si_hubo_fallos():
    if hubo_fallos():
        enviar_alerta(
            f"⚠️ La corrida terminó bien, pero con fallos parciales: "
            f"{resumen_fallos()}. Revisa el log de Actions si se repite seguido."
        )


def avisar_corrida_caida(excepcion):
    detalle = "".join(traceback.format_exception_only(type(excepcion), excepcion)).strip()
    enviar_alerta(f"🔴 La corrida se cayó por completo:\n{detalle}\n\nRevisa el log de GitHub Actions.")
