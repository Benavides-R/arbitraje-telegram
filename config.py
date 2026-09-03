"""
Configuración del sistema de arbitraje de ofertas.
"""

import os

# Canales PÚBLICOS de los que vas a leer ofertas (usa el @username, sin arroba)
CANALES_ORIGEN = [
    "ReviuDescuentos",
    "ElPromoHunter",       # a prueba
    "Clubgratis",  # a prueba
    # "Gio_Makers" -- quitado: falló en las 2 corridas (antes y después del
    # arreglo de Playwright), sus links de btz.es no se resuelven bien.
    # "DescuentosTech" -- quitado: usa Facebook como intermediario, 0 éxitos.
]

# Tu propio canal de Telegram donde se publica ya reescrito (el bot debe ser admin ahí)
# Usa el chat_id (número, con el signo -) igual que en el otro proyecto
CANAL_DESTINO_GRATIS = -1002533761428  # tu canal actual (70 usuarios)
CANAL_DESTINO_VIP = None  # aún no tienes uno -- se deja así hasta que crees el canal VIP

# --- Revisión manual antes de publicar ---
# Si MODO_REVISION es True, cada oferta candidata se te manda primero a TU
# chat privado con el bot (con botones "Publicar" / "Descartar"), y solo se
# publica en tus canales si le das "Publicar". Si es False, se publica directo.
MODO_REVISION = True

# Si AUTO_PUBLICAR_SI_COMPLETA es True, una oferta que SÍ tiene imagen,
# título y precio se publica automáticamente (sin pasar por tu revisión
# manual). Solo aplica cuando MODO_REVISION es True; si a la oferta le
# falta la imagen, igual te la manda a revisar como siempre, para que la
# completes a mano si quieres.
AUTO_PUBLICAR_SI_COMPLETA = True

# Tiendas que SIEMPRE van a revisión manual, aunque vengan completas
# (imagen+título+precio) -- para estas normalmente el link necesita que tú
# lo corrijas a mano antes de publicar (ej. sin afiliado activo todavía).
TIENDAS_SIEMPRE_MANUAL = ["temu.com", "aliexpress.com"]

# Tu chat_id personal (no el del canal) -- para que el bot te mande las
# ofertas a revisar. Sácalo así: mándale /start a tu bot en un chat privado,
# luego visita https://api.telegram.org/bot<TU_TOKEN>/getUpdates y busca
# "chat":{"id": ...} -- va a ser un número normal, sin el -100 al inicio.
ADMIN_CHAT_ID = 6100796756

# Dominios de tiendas que reconocemos, y si ya tienes afiliado activo en cada una.
# Mientras "afiliado_activo" sea False, el link se publica tal cual (sin comisión),
# apenas te aprueben cambias esto a True y agregas tu ID de afiliado.
TIENDAS = {
    "aliexpress.com": {"afiliado_activo": False, "id_afiliado": None},
    # Cuando te registres de nuevo en Amazon Associates, te dan tu "tracking
    # ID" (algo como "tuusuario-20") de inmediato -- ponlo aquí ya mismo,
    # no necesitas esperar a las 3 ventas para EMPEZAR a usarlo, solo para
    # que la cuenta se mantenga activa después de 180 días.
    "amazon.": {"afiliado_activo": True, "id_afiliado": "benatechs00-20"},
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

# Oferta Radar (tu página) -- opcional, salida ADICIONAL después de aprobar
# una oferta. Si no están configurados los dos, simplemente no se envía
# nada ahí (Telegram y Facebook siguen funcionando igual).
OFERTA_RADAR_API_KEY = os.environ.get("OFERTA_RADAR_API_KEY")
OFERTA_RADAR_URL = os.environ.get("OFERTA_RADAR_URL")

# Supabase Storage (bucket "ofertas-images") -- opcional, así todas las
# imágenes de las ofertas (manuales y automáticas) quedan también
# guardadas en tu propio Storage, en vez de depender del CDN de Amazon.
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

# Dominios que consideramos "destino final válido" al resolver redirects.
# Si tras seguir todos los saltos no llegamos a uno de estos, se descarta la oferta.
DOMINIOS_TIENDA_FINAL = list(TIENDAS.keys())

# LLM para reescribir el texto de las ofertas.
# Usa Groq (gratis) con un modelo open-source si GROQ_API_KEY está configurado.
# Si prefieres usar la API de Anthropic en su lugar, deja GROQ_API_KEY vacío
# y configura ANTHROPIC_API_KEY -- el sistema usa el que encuentre disponible.
MODELO_GROQ = "openai/gpt-oss-20b"

# Tope de ofertas procesadas por corrida del cron, para no saturarte el chat
# de revisión de golpe (por ejemplo, la primera vez que arranca, o si un
# canal publica muchísimo de una sola vez). Lo que no alcanza a procesar en
# una corrida, se retoma automáticamente en la siguiente -- no se pierde.
MAX_OFERTAS_POR_CORRIDA = 30

# Si un mensaje del canal origen ya es más viejo que esto, se descarta sin
# procesar -- evita mandar a revisión (o publicar) ofertas relámpago que ya
# expiraron, por ejemplo si el bot se atrasó y apenas ahora le toca revisar
# mensajes de hace rato.
MAX_ANTIGUEDAD_OFERTA_HORAS = 6
