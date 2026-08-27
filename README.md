# Arbitraje de Ofertas — Republicador Automático de Telegram

Escucha canales públicos de ofertas, reescribe el contenido y lo republica en
tu propio canal (VIP primero, gratis con retraso), 24/7, sin intervención manual.

## Costo: $0 para arrancar
- Telethon (librería) y tu cuenta de Telegram: gratis
- Hosting 24/7: Render.com plan free (background worker) o Railway free tier
- LLM: la misma API que ya usas

## ⚠️ Antes de empezar — puntos importantes

1. **Esto usa tu cuenta personal de Telegram** (no un bot) para poder "escuchar"
   canales que no son tuyos. Úsalo con criterio: unirte a decenas de canales de
   golpe con una cuenta nueva puede verse sospechoso para Telegram. Ve
   uniéndote gradualmente a los canales que ya sigues.
2. **No copies el link de afiliado ajeno.** Si el mensaje original ya trae un
   link de afiliado de otra persona, este sistema NO lo reutiliza — solo lo
   publica tal cual mientras tú no tengas afiliado activo en esa tienda (ver
   `config.py`). Usar el link de otro para quedarte con SU comisión es
   apropiarte de un ingreso ajeno, y varios programas de afiliados lo prohíben
   explícitamente.
3. **El texto se reescribe siempre**, nunca se republica copia idéntica del
   canal original.

## Pasos de configuración

### 1. Obtén tus credenciales de API de Telegram (2 min)
1. Ve a https://my.telegram.org, inicia sesión con tu número
2. "API development tools" → crea una app (cualquier nombre)
3. Te da `API_ID` y `API_HASH` — guárdalos

### 2. Genera tu session string (una sola vez, en TU computador)
```
pip install telethon
python generar_sesion.py
```
Te pide el API_ID, API_HASH, tu número y el código que llega por Telegram.
Al final imprime un texto largo — ese es tu `TELEGRAM_SESSION`. Guárdalo,
es sensible (no lo subas a GitHub, no lo compartas).

### 3. Completa `config.py`
- `CANALES_ORIGEN`: los `@username` de los canales públicos que quieres seguir
- `CANAL_DESTINO_GRATIS` / `CANAL_DESTINO_VIP`: el chat_id de tus propios
  canales (mismo proceso que en el proyecto anterior: agrega tu bot como
  admin y saca el chat_id con `getUpdates`)

### 5. Sube tu logo
Coloca un archivo `logo.png` (fondo transparente recomendado) en la misma
carpeta del proyecto antes de subir a GitHub. Se superpone automáticamente
sobre la foto del producto extraída de la tienda.

### 6. Configura Facebook (opcional)
1. Ve a https://developers.facebook.com → crea una app tipo "Business"
2. En "Graph API Explorer", selecciona tu página de Facebook y pide los
   permisos `pages_manage_posts` y `pages_read_engagement`
3. Genera un token de acceso de página, y conviértelo a uno de **larga
   duración** (el corto expira en 1-2 horas) usando el endpoint de Meta para
   extender tokens -- si te trabas en este paso, dime y lo resolvemos juntos
4. Guarda el `Page ID` y el token como `FACEBOOK_PAGE_ID` y
   `FACEBOOK_PAGE_ACCESS_TOKEN` en `config.py` (o mejor, como variables de
   entorno en Render, igual que los demás secrets)

Si no configuras esto, el sistema simplemente no publica en Facebook y sigue
funcionando normal en Telegram.

### 7. Despliega en Render (gratis, corre 24/7)
1. Crea cuenta en render.com, conecta tu repo de GitHub con esta carpeta
2. "New > Background Worker" (no "Web Service" — esto no expone un puerto web)
3. Build command: `pip install -r requirements.txt && playwright install --with-deps chromium`
4. Start command: `python listener.py`
5. En "Environment", agrega estas variables:
   - `TELEGRAM_API_ID`
   - `TELEGRAM_API_HASH`
   - `TELEGRAM_SESSION`
   - `TELEGRAM_BOT_TOKEN` (el mismo bot de BotFather del otro proyecto)
   - `ANTHROPIC_API_KEY`
   - `FACEBOOK_PAGE_ID` / `FACEBOOK_PAGE_ACCESS_TOKEN` (si configuraste Facebook)

El plan free de Render puede "dormir" procesos web por inactividad, pero un
**Background Worker no recibe tráfico web**, así que no aplica ese sueño de
la misma forma — igual revisa los límites de horas gratis del plan al
momento de desplegar, porque cambian con el tiempo.

### 5. Activar comisión cuando te aprueben un afiliado
Edita `config.py`: cambia `afiliado_activo` a `True` para la tienda que te
aprobó y agrega tu ID de afiliado. Luego, en `listener.py`, función
`generar_link_afiliado()`, agregamos la transformación específica de esa
tienda (cada una tiene su propio formato de link de afiliado).

## Limitación conocida
El deduplicado de mensajes ya vistos vive en memoria — si el proceso se
reinicia, técnicamente podría reprocesar el último mensaje si llega justo en
ese momento. Para un proyecto en marcha y con volumen real, esto se puede
mejorar guardando el estado en un archivo o base de datos ligera — lo
dejamos así para no complicar el arranque.

## Sobre los links "en cascada" (Facebook, sitios propios)
El sistema intenta resolver el link final en dos pasos: primero un redirect
HTTP simple (rápido, cubre sitios propios con redirect de servidor), y si
eso no llega a una tienda conocida, abre la página con navegador headless
para manejar redirects hechos con JavaScript.

**Los links que pasan por Facebook son los menos confiables de resolver**:
Facebook bloquea navegación automatizada de forma agresiva y muchas veces
exige inicio de sesión para ver el contenido. Si notas que las ofertas de un
canal en particular casi nunca se resuelven, probablemente sea uno que usa
Facebook como intermediario -- vale la pena priorizar canales que enlazan
directo a un sitio propio o directo a la tienda.
