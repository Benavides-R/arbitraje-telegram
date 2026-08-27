"""
EJECUTA ESTO UNA SOLA VEZ, EN TU COMPUTADOR (no en la nube, no lo subas a GitHub).
Genera un "session string" que representa tu sesión de Telegram ya autenticada.
Ese string es sensible -- equivale a estar logueado en tu cuenta. Guárdalo
solo como variable de entorno/secret en el hosting, nunca en el código.

Requisitos previos:
1. Ve a https://my.telegram.org, inicia sesión con tu número
2. Entra a "API development tools"
3. Crea una app (cualquier nombre), te da API_ID y API_HASH
4. pip install telethon
5. Corre este script: python generar_sesion.py
6. Te va a pedir tu número de teléfono y el código que te llegue por Telegram
7. Al final imprime el session string -- cópialo
"""

from telethon.sync import TelegramClient
from telethon.sessions import StringSession

API_ID = input("Pega tu API_ID: ").strip()
API_HASH = input("Pega tu API_HASH: ").strip()

with TelegramClient(StringSession(), API_ID, API_HASH) as client:
    print("\n--- Copia este session string y guárdalo como secret (TELEGRAM_SESSION) ---\n")
    print(client.session.save())
    print("\n--- No lo compartas ni lo subas a GitHub ---\n")
