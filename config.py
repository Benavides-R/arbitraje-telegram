"""
Configuración del sistema de arbitraje de ofertas.
"""

import os

# Canales PÚBLICOS de los que vas a leer ofertas (usa el @username, sin arroba)
CANALES_ORIGEN = [
    "nombre_canal_1",   # reemplaza con los @username reales de los canales que sigues
    "nombre_canal_2",
]

# Tu propio canal de Telegram donde se publica ya reescrito (el bot debe ser admin ahí)
# Usa el chat_id (número, con el signo -) igual que en el otro proyecto
CANAL_DESTINO_GRATIS = None  # ej: -1001234567890
CANAL_DESTINO_VIP = None

# Dominios de tiendas que reconocemos, y si ya tienes afiliado activo en cada una.
# Mientras "afiliado_activo" sea False, el link se publica tal cual (sin comisión),
# apenas te aprueben cambias esto a True y agregas tu ID de afiliado.
TIENDAS = {
    "aliexpress.com": {"afiliado_activo": False, "id_afiliado": None},
    "amazon.": {"afiliado_activo": False, "id_afiliado": None},        # cubre amazon.com, amazon.es, etc.
    "temu.com": {"afiliado_activo": False, "id_afiliado": None},
    "shein.com": {"afiliado_activo": False, "id_afiliado": None},
    "mercadolibre.com": {"afiliado_activo": False, "id_afiliado": None},
}

# Palabras clave: si el mensaje del canal origen NO contiene ninguno de estos
# dominios, se ignora (evita republicar contenido que no sea una oferta con link)

# Ruta a tu logo (PNG con fondo transparente funciona mejor) para marcar las
# imágenes de producto antes de publicarlas. Súbelo junto al proyecto.
LOGO_PATH = "logo.png"

# Facebook (Meta Graph API) -- opcional, se lee de variables de entorno/Secrets.
# Si prefieres, también puedes escribir los valores aquí directamente (menos
# recomendado si el repo llegara a ser público).
FACEBOOK_PAGE_ID = os.environ.get("FACEBOOK_PAGE_ID")
FACEBOOK_PAGE_ACCESS_TOKEN = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN")

# Dominios que consideramos "destino final válido" al resolver redirects.
# Si tras seguir todos los saltos no llegamos a uno de estos, se descarta la oferta.
DOMINIOS_TIENDA_FINAL = list(TIENDAS.keys())
