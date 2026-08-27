# Arbitraje de Ofertas — Republicador Automático de Telegram

Revisa canales públicos de ofertas cada 20 minutos, reescribe el contenido y
lo republica en tu propio canal (VIP primero, gratis con retraso) y en
Facebook — sin intervención manual, y sin costo de hosting.

## Costo: $0
- GitHub Actions en repo público: minutos gratis en la práctica
- Telethon (librería) y tu cuenta de Telegram: gratis
- LLM: la misma API que ya usas

**Nota sobre el diseño**: en vez de un proceso "escuchando" 24/7 (que hoy
requiere hosting pagado — Render, Railway y Fly.io ya no ofrecen eso gratis
en 2026), este proyecto revisa los canales por lotes cada 20 minutos usando
GitHub Actions, igual que el otro proyecto de alertas. La diferencia práctica
es la inmediatez: en vez de segundos, una oferta tarda hasta 20 min en
detectarse. A cambio, es completamente gratis y no depende de ningún
proveedor de hosting.

## ⚠️ Antes de empezar — puntos importantes

1. **Esto usa tu cuenta personal de Telegram** (no un bot) para poder leer
   canales que no son tuyos. Únete gradualmente a los canales que sigues, no
   a muchos de golpe con una cuenta nueva.
2. **No copies el link de afiliado ajeno.** Si el mensaje original ya trae un
   link de afiliado de otra persona, este sistema NO lo reutiliza — solo lo
   publica tal cual mientras tú no tengas afiliado activo en esa tienda (ver
   `config.py`). Usar el link de otro para quedarte con su comisión es
   apropiarte de un ingreso ajeno, y varios programas de afiliados lo prohíben.
3. **El texto se reescribe siempre**, nunca se republica copia idéntica.

## Pasos de configuración

### 1. Credenciales de API de Telegram (2 min)
1. Ve a https://my.telegram.org, inicia sesión con tu número
2. "API development tools" → crea una app (cualquier nombre)
3. Te da `API_ID` y `API_HASH` — guárdalos

### 2. Genera tu session string (una sola vez, en TU computador)
```
pip install telethon
python generar_sesion.py
```
Pide el API_ID, API_HASH, tu número y el código que llega por Telegram.
Al final imprime un texto largo — ese es tu `TELEGRAM_SESSION`.
⚠️ Es sensible, equivale a la clave de tu cuenta: no lo subas a GitHub ni lo
compartas. Solo va como Secret en el paso 6.

### 3. Completa `config.py`
- `CANALES_ORIGEN`: los `@username` de los canales públicos que quieres seguir
- `CANAL_DESTINO_GRATIS` / `CANAL_DESTINO_VIP`: el chat_id de tus propios
  canales (agrega tu bot como **administrador** del canal, manda un mensaje
  de prueba, y saca el chat_id visitando
  `https://api.telegram.org/bot<TU_TOKEN>/getUpdates`)

### 4. Sube tu logo
Coloca un archivo `logo.png` (fondo transparente recomendado) en la misma
carpeta antes de subir a GitHub. Se superpone automáticamente sobre la foto
del producto extraída de la tienda.

### 5. Configura Facebook (opcional)
1. https://developers.facebook.com → crea una app tipo "Business"
2. "Graph API Explorer" → selecciona tu página → pide permisos
   `pages_manage_posts` y `pages_read_engagement`
3. Genera un token de página y conviértelo a uno de **larga duración**
   (el corto expira en 1-2 horas)
4. Guarda el Page ID y el token — van como Secrets en el paso 6, no en
   `config.py` directamente

Si no configuras esto, el sistema simplemente no publica en Facebook y sigue
funcionando normal en Telegram.

### 6. Sube el proyecto a GitHub y configura los Secrets
1. Crea un repo (puede ser público, igual que el otro proyecto, para
   aprovechar los minutos gratis de Actions)
2. Sube todo el contenido de esta carpeta
3. `Settings > Secrets and variables > Actions > New repository secret`,
   agrega:
   - `TELEGRAM_API_ID`
   - `TELEGRAM_API_HASH`
   - `TELEGRAM_SESSION`
   - `TELEGRAM_BOT_TOKEN`
   - `ANTHROPIC_API_KEY`
   - `FACEBOOK_PAGE_ID` / `FACEBOOK_PAGE_ACCESS_TOKEN` (si aplica)

### 7. Probar
Pestaña **Actions > Revisar Canales de Ofertas > Run workflow** — así lo
corres sin esperar el cron, para confirmar que todo funciona. Revisa los
logs: `[OFERTA] ... -> publicando en VIP` confirma que detectó y publicó algo;
`[INFO] canal: sin mensajes nuevos` es normal si no hubo ofertas en esa
ventana de tiempo.

### 8. Activar comisión cuando te aprueben un afiliado
Edita `config.py`: cambia `afiliado_activo` a `True` para la tienda
aprobada y agrega tu ID de afiliado. En `revisar_canales.py`, función
`generar_link_afiliado()`, conectamos la transformación específica de esa
tienda cuando llegues a este punto.

## Sobre los links "en cascada" (Facebook, sitios propios)
El sistema intenta resolver el link final en dos pasos: redirect HTTP simple
primero, y si no llega a una tienda conocida, navegador headless para
redirects hechos con JavaScript.

**Los links que pasan por Facebook son los menos confiables de resolver** —
Facebook bloquea navegación automatizada agresivamente. Si notas que un canal
casi nunca se resuelve, probablemente use Facebook como intermediario;
prioriza canales que enlazan directo a un sitio propio o a la tienda.

## Limitaciones conocidas
- El retraso del canal gratis se logra guardando la oferta como "pendiente"
  y publicándola en una ejecución posterior del cron una vez pasa el tiempo
  de espera — no es un temporizador exacto al segundo, pero cumple el
  propósito (VIP siempre primero).
- Si en algún momento migras a un proceso 24/7 de verdad (por ejemplo si más
  adelante decides pagar un hosting), este mismo código sirve de base, solo
  habría que volver al modelo de "escuchar" en vez de "revisar por lotes".
