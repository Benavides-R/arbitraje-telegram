"""
Configuración del sistema de arbitraje de ofertas.
"""

import os

# Canales PÚBLICOS de los que vas a leer ofertas (usa el @username, sin arroba)
CANALES_ORIGEN = [
    "ReviuDescuentos",
    "ElPromoHunter",       # a prueba
    "Clubgratis",  # a prueba
    "ofertu",  # Amazon con links joylink.io; ~30 mensajes/hora (canal muy activo)
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
TIENDAS_SIEMPRE_MANUAL = ["temu.com", "aliexpress.com", "mercadolibre.com"]

# Ofertas que se DESCARTAN al instante: ni a revisión ni a auto-publicación
# (se saltan apenas se detecta el dominio). Ahorra tiempo de revisión con
# tiendas que hoy no publicas. Para reactivar una tienda más adelante,
# simplemente quítala de esta lista -- sus entradas en TIENDAS siguen ahí.
#
# 2026-11-12: MercadoLibre se pausa TEMPORALMENTE (pedido del dueño: estaban
# llegando ofertas de MercadoLibre desde los canales que vigila). Cubre todas
# sus variantes por substring: mercadolibre.com.co, articulo.mercadolibre.com.co,
# mercadolibre.com.ar, mercadolibre.com.mx, etc. Para reactivarla, bórrala de
# aquí y de TIENDAS_SIEMPRE_MANUAL (volvería a revisión manual, no automática).
TIENDAS_IGNORADAS = ["temu.com", "aliexpress.com", "mercadolibre.com"]

# --- Modo de decisión: LISTA NEGRA (2026-11-18) ---
# Antes se usaba una LISTA BLANCA (PALABRAS_AUTO_PERMITIDAS): una oferta
# completa solo se publicaba sola si el título traía alguna de esas ~211
# palabras. Medido con datos reales, eso era el cuello de botella #1: 63 de
# 99 pendientes ya tenían foto, título y precio y solo se frenaban por no
# traer la palabra exacta.
#
# Ahora (pedido del dueño) es al revés: TODO lo que llegue completo
# (imagen+título+precio) se publica solo, y lo único que lo frena es:
#   1. la lista negra de abajo (PALABRAS_NO_AUTO),
#   2. que la tienda esté en TIENDAS_IGNORADAS (se descarta antes),
#   3. que la tienda esté en TIENDAS_SIEMPRE_MANUAL,
#   4. que requiera casillero (envío a Colombia).
#
# Para volver al modelo viejo: pon USAR_LISTA_BLANCA = True. La lista blanca
# quedó intacta abajo (solo dejó de usarse) y además está documentada en
# LISTA_BLANCA_HISTORICA.md.
USAR_LISTA_BLANCA = False

# LISTA BLANCA HISTÓRICA -- ya NO se usa para decidir mientras
# USAR_LISTA_BLANCA sea False. Se conserva tal cual para poder revertir.
# Documentada también en LISTA_BLANCA_HISTORICA.md.
PALABRAS_AUTO_PERMITIDAS = [
    # --- banco original (tecnología/seguridad) ---
    "camara", "camara de seguridad", "seguridad", "alarma", "cerradura",
    "sensor", "timbre inteligente", "rastreador", "localizador", "gps",
    "tablet", "inflador", "compresor", "drone", "dron",
    "audifono", "auricular", "smartwatch", "reloj inteligente", "laptop",
    "monitor", "disco duro", "ssd", "router", "proyector", "impresora",
    # --- expansión 1: audio/cámaras/gadgets de escritorio ---
    "cable", "cargador", "cargador rapido", "power bank", "altavoz",
    "soundbar", "teclado", "mouse", "webcam", "audifonos inalambricos",
    "audifonos gamer", "diadema", "camara deportiva", "lupa",
    "termometro", "balanza",
    # --- expansión 1: gadgets "wow" de hogar ---
    "ventilador", "purificador de aire", "bombillo", "lampara", "led",
    "aspiradora", "freidora de aire", "foco",
    # --- expansión 1: accesorios personales y herramientas ---
    "mochila", "reloj", "gafas de sol", "guantes",
    "herramienta", "taladro", "bateria", "memoria",
    # --- expansión 2: cubre ~55 ofertas foto+precio que estaban varadas ---
    "portatil", "telefono", "bluetooth", "inalambrico", "recargable",
    "karaoke", "juego", "pieza", "paquete", "acero", "sarten",
    "cuchillo", "toalla", "edredon", "manta", "organizador",
    "facial", "cabello", "cepillo", "serum",
    # --- expansión 3: marcas deportivas top (talla/calidad más predecible) ---
    "nike", "adidas", "puma", "reebok", "balance", "garmin",
    "columbia", "under armour", "saucony", "fila", "champion",
    "jordan", "asics",
    # --- expansión 4 (2026-10-25): minería de TUS aprobaciones manuales ---
    # Top de los títulos que aprobabas a mano estando completos (foto+precio)
    # pero que no matcheaban ninguna palabra; impacto medido en la cola real.
    # 2026-11-09: se QUITARON "hombre" y "mujer". Eran un comodín que
    # auto-publicaba cualquier prenda ("bikini para mujer", "botas para
    # mujer", "vestido para mujer"). Ahora solo pasa la ropa/accesorio que
    # tenga su propia palabra; lo que sí te gusta (zapatillas, collares,
    # bolsos) sigue abajo por su propio nombre.
    # Ropa/accesorios que se repetían en aprobadas y en la cola:
    "sudadera", "tenis", "capucha", "sueter", "zapatillas", "camiseta", "chaqueta",
    "camisa", "pantalones", "polo", "calzado", "ninos", "cuero",
    "collar", "aretes", "pulsera", "anillo", "joyeria",
    "hanes", "skechers", "nautica", "tommy",
    # Tech/futuro: poco en la cola hoy, pero salen seguido en aprobadas:
    "rtx", "geforce", "grafica", "escritorio", "billetera", "rfid",
    "usb", "molinillo", "controlador", "microscopio",
    # --- expansión 5 (2026-10-28): lo que el admin quiere publicar ---
    # Televisores (categoría que pidió y es "lo mejor de lo mejor"):
    "tv", "smart tv", "fire tv", "televisor",
    "hisense", "tcl", "roku", "samsung", "philips", "sony",
    # Zapatos/calzado de marcas y tipos (se quitaron sandalias/botas/botines/
    # mocasines/chanclas/crocs: no los quiere el admin):
    "zapatos", "converse", "vans",
    # Cuidado personal -- marcas que pidió:
    "medicube", "cerave", "dove", "johnson", "listerine", "colgate",
    "gillette", "nivea", "palmolive", "pantene", "schick", "eucerin",
    "neutrogena", "cetaphil", "vaseline", "oral-b", "oral b",
    "sensodyne", "chapstick",
    # Cuidado personal -- categorías (para las que no son marca):
    "crema", "shampoo", "champu", "acondicionador", "jabon",
    "desodorante", "locion", "balsamo", "pasta dental", "enjuague",
    "protector solar", "hidratante", "limpiador", "suero", "antitranspirante",
    # Bolsos (bandolera se quitó el 2026-11-09: el admin no la quiere):
    "bolso",
    # --- expansión 6 (2026-11-03): el nicho real, con el nombre que la
    # gente usa en Colombia ("parlante", "celular") y no el técnico
    # ("altavoz", "teléfono") -- antes se iban a revisión sin necesidad ---
    "parlante", "bocina", "celular", "computador",
    "consola", "playstation", "xbox", "nintendo", "control",
    "silla gamer", "aire acondicionado", "colchon",
    # Cocina y casa:
    "cafetera", "licuadora", "olla", "vajilla", "secador",
    # Herramientas y electricidad:
    "afeitadora", "cortadora", "multimetro", "destornillador",
    "extensor", "regulador",
    # Hogar:
    "videoportero", "videopuerto",
    # --- expansión 7 (2026-11-15): huecos medidos en la cola real ---
    # Tecnología que quedaba en revisión SOLO por no tener su palabra:
    "grabadora", "tripode", "raton",
    "alexa", "echo dot", "rgb",
    # Luces de exterior/permanentes. NO se pone "luces" a secas: reencendería
    # las luces de Navidad que el admin sacó a propósito.
    "luces permanentes", "luces exteriores", "cadena de luces",
    # Marcas de tecnología: hay títulos que solo traen marca + modelo
    # ("Razer DeathAdder Essential") y sin la marca no matcheaban nada.
    "razer", "logitech", "corsair", "anker", "jbl", "redragon",
]

# Lista negra (2026-11-18): si el título trae ALGUNA de estas, la oferta
# NUNCA se publica sola -- va a revisión manual, aunque esté completa.
# Se compara sobre el título ya normalizado (sin tildes, minúsculas) y por
# SUBSTRING, así que una palabra corta bloquea todo lo que la contenga.
#
# OJO al agregar palabras cortas: "mono" bloquearía "monitor", "top"
# bloquearía "laptop"/"desktop" y "cartera" bloquearía "billetera" (que en
# Colombia es lo que sí se quiere publicar). Por eso esas no están.
#
# "body" y "sosten" se revisan aparte, con palabra completa, en
# _titulo_en_lista_negra (revisar_canales.py): como substring "body" pegaba
# en "Crossbody" y "sosten" en "sostenible".
PALABRAS_NO_AUTO = [
    # --- Ropa interior / lencería ---
    "braga", "panti", "panty", "brasier", "brassiere", "sosten", "sujetador",
    "lenceria", "ropa interior", "calzoncillo", "boxer",
    "tanga", "culotte", "body", "babydoll", "corse", "corset", "liguero",
    "camison", "pijama", "bata de bano", "albornoz", "encaje",
    # --- Trajes de baño ---
    # "bikini"/"monokini" se revisan aparte: un aparato de depilación
    # ("Recortadora de bikini") no es una prenda y no se bloquea.
    "bikini", "monokini", "traje de bano", "vestido de bano", "salida de bano",
    "banador", "swimsuit", "tankini", "pareo",
    # --- Moda femenina ---
    "vestido", "falda", "blusa", "bluson", "crop", "tank top", "enterizo",
    "legging", "leggings", "short", "shorts", "jumpsuit", "overol", "kimono",
    "poncho", "chaleco", "cardigan", "sueter", "abrigo", "gabardina",
    "blazer", "americana", "esmoquin",
    # --- Calzado de moda ---
    "bota", "botin", "botines", "mocasin", "sandalia", "chancla", "crocs",
    "tacon", "tacones", "stiletto", "plataforma", "cuna", "alpargata",
    "baleta", "ballet",
    # --- Bolsos / marroquinería ---
    # "cartera" sola NO va: en Colombia es la billetera, que sí se publica.
    "bandolera", "clutch", "rinonera", "cangurera", "tote", "shopper",
    "satchel", "crossbody", "hobo", "cartera de mano", "cartera de mujer",
    # --- Salud / vicios ---
    "vape", "vapeador", "cigarrillo", "tabaco", "suplemento", "pastillas",
    "capsulas", "medicamento", "colageno", "creatina", "quemador de grasa",
    "detox", "melatonina",
    # --- Armas ---
    "navaja", "cuchilla de afeitar",
    # --- Usados ---
    # "usada"/"usadas" también: la mayoría de avisos de segunda mano son en
    # femenino ("consola usada", "nevera usada") y "usado" no las atrapaba.
    "usado", "usada", "usados", "usadas", "reacondicionado", "reacondicionada",
    "renewed", "refurbished", "open box", "segunda mano", "seminuevo",
    # "consola" está en la lista blanca y matchea por substring: sin esto,
    # un consolador se publicaría solo.
    "consolador",
    # --- Otros que el dueño no quiere ver ---
    "disfraz", "peluca", "unas postizas", "pestanas postizas",
    # "moldeador" solo NO va: atrapa secadores y planchas de cabello
    # ("moldeador de aire"). Se piden las variantes de shapewear.
    "tatuaje temporal", "faja", "moldeador corporal", "moldeador de cuerpo",
    "moldeadora corporal", "push up", "realce", "sexy",
    "sensual", "erotico",
    # "medias" (pantimedias/medias veladas) se mantiene desde 2026-11-09.
    "medias",
]

# Palabras de tecnología: no cambian si algo se publica, solo el ORDEN.
# En la Fase 2 se publican/mandan primero las ofertas de tecnología para
# que, cuando la corrida se llena, lo tech salga antes que la moda.
PALABRAS_TECNOLOGIA = [
    "camara", "celular", "telefono", "portatil", "laptop", "computador",
    "tablet", "monitor", "teclado", "mouse", "audifono", "auricular",
    "parlante", "bocina", "smartwatch", "reloj inteligente",
    "tv", "televisor", "smart tv", "fire tv", "consola", "playstation",
    "xbox", "nintendo", "drone", "dron", "proyector", "impresora",
    "router", "ssd", "disco duro", "memoria", "usb", "cargador",
    "power bank", "bluetooth", "gps", "rastreador", "alarma", "seguridad",
    "cerradura", "sensor", "rtx", "geforce", "grafica", "microscopio",
    "multimetro", "taladro", "aspiradora", "freidora de aire", "cafetera",
    "licuadora", "aire acondicionado", "videoportero", "controlador",
]

# Buscador de ofertas directo de AliExpress (sin depender de canales de
# Telegram). Desactivado: el pool de "hot products" que trae es chico (~10
# fijos que se repiten) y de categorías que no encajan con el nicho de
# tecnología (disfraces, accesorios). El link de afiliado para AliExpress
# que SÍ aparezca en los canales sigue funcionando normal, esto solo apaga
# el buscador aparte.
ACTIVAR_BUSCADOR_ALIEXPRESS = False

# Si está en True, las publicaciones de Telegram y Facebook usan el link de
# tu página (oferta-radar.com/oferta/xxx) en vez del link directo de Amazon
# -- útil cuando corras anuncios pagados (mejor tracking/retargeting).
# Si Oferta Radar falla al crear la oferta, se usa el link de Amazon esa
# vez (nunca se pierde la publicación por eso).
USAR_BRIDGE_OFERTA_RADAR = False

# Tu chat_id personal (no el del canal) -- para que el bot te mande las
# ofertas a revisar. Sácalo así: mándale /start a tu bot en un chat privado,
# luego visita https://api.telegram.org/bot<TU_TOKEN>/getUpdates y busca
# "chat":{"id": ...} -- va a ser un número normal, sin el -100 al inicio.
ADMIN_CHAT_ID = 6100796756

# Dominios de tiendas que reconocemos, y si ya tienes afiliado activo en cada una.
# Mientras "afiliado_activo" sea False, el link se publica tal cual (sin comisión),
# apenas te aprueben cambias esto a True y agregas tu ID de afiliado.
TIENDAS = {
    "aliexpress.com": {"afiliado_activo": True, "id_afiliado": None},
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

# Texto de tus redes que se dibuja abajo a la izquierda de cada imagen
# (una línea por elemento de la lista). Vacío = no se dibuja nada.
# Ejemplo: ["fb.com/TuPagina", "t.me/TuCanal"]
REDES_SOCIALES_LINEAS = ["fb.com/Benatechs.Descuentos", "t.me/Benatechs_Descuentos", "oferta-radar.com"]

# Facebook (Meta Graph API) -- opcional, se lee de variables de entorno/Secrets.
# Si prefieres, también puedes escribir los valores aquí directamente (menos
# recomendado si el repo llegara a ser público).
FACEBOOK_PAGE_ID = os.environ.get("FACEBOOK_PAGE_ID")
FACEBOOK_PAGE_ACCESS_TOKEN = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN")

# Espera mínima (en segundos) entre un post de Facebook y el siguiente --
# Meta no publica su límite exacto de "spam" (error 368), pero publicar
# varias ofertas de golpe en pocos segundos es un patrón típico que lo
# dispara. 60s = como mucho 1 post por minuto, algo que cualquier página
# activa hace sin problema.
FACEBOOK_SEGUNDOS_ENTRE_POSTS = 60

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
MAX_OFERTAS_POR_CORRIDA = 40

# Cuota por canal (en vez de repartir parejo) -- los que más rinden reciben
# más cupo. Si un canal no está aquí, usa 5 por defecto.
# Reparto: 12 + 12 + 8 + 8 = 40 (justo el tope de la corrida).
CUOTA_POR_CANAL = {
    "ElPromoHunter": 12,
    "ReviuDescuentos": 12,
    # Clubgratis subió de 4 a 8: es el canal con mejor rendimiento por
    # oferta (8 de las últimas 48 aprobaciones, con la menor cantidad de
    # ofertas enviadas a revisión).
    "Clubgratis": 8,
    # ofertU publica ~30 mensajes/hora y casi todo es Amazon, así que entra
    # con cupo propio. Medido sobre 20 mensajes seguidos: 35% eran
    # duplicados de otros canales, 15% caían en lista negra y la mitad eran
    # nuevas (3 de tecnología, 2 con Prime, 3 con cupón).
    "ofertu": 8,
}

# Si el mismo producto de Amazon (mismo ASIN) ya se publicó hace menos de
# este tiempo, se descarta como duplicado -- pasado ese tiempo, se permite
# de nuevo (la oferta pudo seguir vigente o repetirse un día después).
HORAS_BLOQUEO_DUPLICADO = 12

# Si un mensaje del canal origen ya es más viejo que esto, se descarta sin
# procesar -- evita mandar a revisión (o publicar) ofertas relámpago que ya
# expiraron, por ejemplo si el bot se atrasó y apenas ahora le toca revisar
# mensajes de hace rato.
MAX_ANTIGUEDAD_OFERTA_HORAS = 6
