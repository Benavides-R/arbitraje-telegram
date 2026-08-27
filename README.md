# Arbitraje de Ofertas — Republicador Automático de Telegram

Revisa canales públicos de ofertas cada 20 minutos, reescribe el contenido
con IA, y (si activaste revisión manual) te la manda a aprobar antes de
publicarla en tu canal (VIP primero, gratis con retraso) y en Facebook.

## Costo: $0
- GitHub Actions en repo público: minutos gratis en la práctica
- Telethon + tu cuenta de Telegram: gratis
- Groq (LLM gratis, modelo open-source `gpt-oss`) para reescribir el texto

## ⚠️ Antes de empezar

1. **Esto usa tu cuenta personal de Telegram** (no un bot) para leer canales
   que no son tuyos. Únete gradualmente, no a muchos de golpe.
2. **No se reutiliza el link de afiliado de nadie más.** Mientras no tengas
   afiliado activo en una tienda, el link se publica tal cual, sin comisión.
3. **El texto siempre se reescribe**, nunca se republica copia idéntica.
4. Un bot puede publicar en **canales o grupos** por igual — en canales debe
   ser administrador; en grupos normales basta con que sea miembro.

## Pasos de configuración

### 1. Credenciales de API de Telegram
1. https://my.telegram.org → inicia sesión con tu número
2. "API development tools" → crea una app (cualquier nombre)
3. Te da `API_ID` y `API_HASH` — guárdalos

### 2. Session string (una sola vez, en TU computador)
```
pip install telethon
python generar_sesion.py
```
Al final imprime un texto largo — es tu `TELEGRAM_SESSION`. Sensible, no lo
subas a GitHub, va solo como Secret (paso 8).

### 3. Tu bot de Telegram
En Telegram, busca **@BotFather** → `/newbot` → ponle nombre → te da el
**`TELEGRAM_BOT_TOKEN`**. Si ya tienes uno de este proyecto, reutilízalo.

### 4. Chat_id de tus canales de destino
Agrega el bot como **administrador** en tu canal gratis y tu canal VIP.
Manda un mensaje de prueba en cada uno, luego visita:
`https://api.telegram.org/bot<TU_TOKEN>/getUpdates`
Busca `"chat":{"id": -100...}` — ese número (con el `-100`) es el chat_id.

### 5. Tu chat_id personal (para recibir las ofertas a revisar)
Abre un chat privado con tu bot, mándale `/start`. Vuelve a visitar la
misma URL de `getUpdates` — ahí vas a ver otro `"chat":{"id": ...}`, esta
vez un número normal (sin `-100`, puede que sin signo negativo). Ese es tu
`ADMIN_CHAT_ID`.

### 6. Completa `config.py`
- `CANALES_ORIGEN`: los `@username` de los canales públicos que sigues
  (puedes poner tantos como quieras)
- `CANAL_DESTINO_GRATIS` / `CANAL_DESTINO_VIP`: chat_id del paso 4
- `ADMIN_CHAT_ID`: tu chat_id del paso 5
- `MODO_REVISION`: déjalo en `True` para revisar cada oferta antes de que
  llegue a tus 70 usuarios; cámbialo a `False` el día que confíes en el
  sistema y quieras que publique directo
- `TIENDAS["amazon."]["id_afiliado"]`: tu tracking ID de Amazon Associates
  en cuanto te registres (puedes ponerlo desde el día 1, no hay que esperar
  las ventas) y `afiliado_activo` en `True`

### 7. Tu logo y Facebook (igual que antes)
`logo.png` en la carpeta del proyecto. Facebook es opcional -- ver sección
más abajo si quieres activarlo.

### 8. Sube el proyecto a GitHub y configura los Secrets
`Settings > Secrets and variables > Actions > New repository secret`:
- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION`, `TELEGRAM_BOT_TOKEN`
- `GROQ_API_KEY` (ve a https://console.groq.com, crea cuenta gratis, sección
  "API Keys" → "Create API Key")
- `FACEBOOK_PAGE_ID` / `FACEBOOK_PAGE_ACCESS_TOKEN` (si aplica)

### 9. Probar
**Actions > Revisar Canales de Ofertas > Run workflow**. Con `MODO_REVISION`
en `True`, si hay una oferta nueva, te debería llegar un mensaje al chat
privado con el bot, con foto, texto y dos botones: "✅ Publicar" /
"❌ Descartar". Al tocar uno, se procesa en la **siguiente** ejecución del
cron (máximo 20 min después) — no es instantáneo, pero sí automático.

## Configura Facebook (opcional)
1. https://developers.facebook.com → app tipo "Business"
2. "Graph API Explorer" → tu página → permisos `pages_manage_posts` y
   `pages_read_engagement`
3. Token de página → conviértelo a uno de **larga duración**
4. Guarda Page ID y token como Secrets (paso 8)

## Cómo funciona la revisión manual, explicado
1. El cron detecta una oferta candidata, la reescribe, resuelve la imagen
2. En vez de publicarla, te la manda a TU chat con el bot + 2 botones
3. Tú tocas "Publicar" o "Descartar" cuando quieras
4. En la siguiente ejecución del cron (cada 20 min), el sistema revisa si
   respondiste, y si dijiste que sí, ahí sí publica en tus canales y Facebook
5. Si nunca respondes, la oferta simplemente queda pendiente sin publicarse
   — no hay problema, no vence ni genera error

## Sobre los links "en cascada" (Facebook, sitios propios)
Redirect HTTP simple primero; si no llega a una tienda conocida, navegador
headless para redirects con JavaScript. **Los links que pasan por Facebook
son los menos confiables** — Facebook bloquea navegación automatizada
agresivamente.

## Sobre el LLM (Groq)
Se usa el modelo gratuito `openai/gpt-oss-120b` en Groq por defecto (variable
`MODELO_GROQ` en `config.py`, por si quieres cambiarlo). Si no configuras
`GROQ_API_KEY`, el sistema intenta con `ANTHROPIC_API_KEY` como respaldo; si
ninguna está disponible, publica un texto simple sin reescritura.
