# Traspaso — estado del bot (22-nov-2026)

Documento para continuar el trabajo en otro equipo/IA. Resume qué quedó
desplegado, qué reglas rigen hoy, qué se midió con datos reales y qué falta
decidir. **No sustituye al código**: si algo aquí no coincide con
`config.py` / `revisar_canales.py`, manda el código.

Último commit de este cambio: el más reciente de `main` con fecha
**22-nov-2026** (para verlo: `git log --oneline -1`; el bot agrega después
commits de estado con los datos de `data/`).

---

## 1. Regla de publicación vigente (cambio importante)

Antes: **lista blanca**. Una oferta solo se auto-publicaba si el título
contenía alguna de las 211 palabras de `PALABRAS_AUTO_PERMITIDAS`.
Ese era el cuello de botella: ofertas buenas con foto, título y precio se
quedaban esperando aprobación manual solo por no traer la palabra exacta.

Ahora: **solo lista negra**. `config.py` → `USAR_LISTA_BLANCA = False`.
Todo lo que esté completo se auto-publica **salvo** lo que caiga en
`PALABRAS_NO_AUTO` (150 entradas).

La lista blanca histórica **no se borró**: sigue en `config.py` (marcada
como histórica, ya solo se consulta si `USAR_LISTA_BLANCA = True`) y está
copiada palabra por palabra en `LISTA_BLANCA_HISTORICA.md`, con los pasos
para revertir.

### Qué sigue frenando una oferta (no es la lista negra)
1. `requiere_casillero` — bloqueo duro en `finalizar_oferta`, no es una
   palabra de la lista.
2. Tiendas pausadas: `TIENDAS_IGNORADAS` / `TIENDAS_SIEMPRE_MANUAL`
   (MercadoLibre, Temu, AliExpress).
3. Sin imagen.
4. Antigüedad mayor a `MAX_ANTIGUEDAD_OFERTA_HORAS` (6 h).
5. Duplicado por ASIN dentro de `HORAS_BLOQUEO_DUPLICADO` (24 h).
6. Topes de la corrida: `MAX_OFERTAS_POR_CORRIDA = 31` y
   `CUOTA_POR_CANAL` (ElPromoHunter 15, ReviuDescuentos 12, Clubgratis 8).
7. **Amazon Japón** (`amazon.co.jp`): nunca se auto-publica, siempre va al
   interno (ver abajo).

### Amazon JP: no se pasa a amazon.com (resuelto el 22-nov-2026)
Antes, cualquier link de Amazon que no fuera de EE.UU. se verificaba en
`amazon.com` y, si el ASIN no existía, se descartaba (o se reescribía a
`amazon.com`). Con Japón eso no servía: el producto no está en el catálogo
de EE.UU. y se perdía.

Ahora, por decisión del dueño (hoy no le interesa JP):

- Se detecta por **sufijo de host**: `_es_amazon_jp()` → `host.endswith(
  "amazon.co.jp")`, así cubre `www.` y cualquier subdominio.
- El link se deja **en su propia tienda**, limpio:
  `https://www.amazon.co.jp/dp/ASIN` (con `smid` si venía). No se consulta
  `_asin_existe_en_amazon_com` para JP.
- Los **links cortos** que resuelven a JP también conservan la tienda JP
  (`host_destino` en `_limpiar_link_amazon_corto`).
- `preparar_oferta` pone `"revision_manual": True` y `finalizar_oferta`
  salta la auto-publicación y la manda al interno con el motivo
  **"Amazon JP — revisión manual"** (usa `enviar_para_revision`, el mismo
  camino de siempre; no hay ruta nueva).
- `amazon.ca` / `amazon.co.uk` siguen como antes (se verifican en
  `amazon.com`).

Prueba en seco: `pruebas_jp.py` (0 fallos) — JP conserva tienda y no
consulta amazon.com, US intacto, `amazon.ca` mantiene su comportamiento,
link corto JP conserva JP, y JP no publica ni marca el ASIN.

### Regla de oro que NO se debe romper
El ASIN se marca como publicado **solo cuando la oferta se publicó de
verdad** (`aprobaciones.py`). Nunca al aprobarla ni al prepararla. Mandar a
revisión (incluido Amazon JP) **no** marca nada.

---

## 2. Verificación hecha con datos reales (no estimaciones)

Sobre las 99 ofertas que estaban en `data/pendientes_revision.json`:

| Resultado con la regla nueva | Cantidad |
|---|---|
| Se auto-publicarían | **63** |
| Siguen bloqueadas por lista negra | 14 |
| Requieren casillero | 9 |
| Sin imagen | 13 |
| Otros motivos | 0 |

Además: `pruebas_seco.py` 30/30 OK, y un control de 30 títulos
(`spot_negra.py`) con solo un falso positivo aceptado (`americana`).

Los pendientes actuales **no se re-evalúan solos**: se van con la poda
(6 h con cupón / 24 h sin cupón). Las ofertas nuevas entran ya con la
regla nueva.

---

## 3. Detalles del match de la lista negra (para no romperlo)

El match es **substring** sobre el título normalizado (sin tildes,
minúsculas). Por eso:

- **No se pueden usar** estas palabras: `mono` (está dentro de "monitor"),
  `top` (dentro de "laptop"/"desktop"), `cartera` (en Colombia = billetera,
  ya permitida).
- `body` y `sosten` se buscan como **palabra completa** (`_RE_BODY_LENCERIA`,
  `_RE_SOSTEN`), porque como substring atrapaban "Crossbody" y "sostenible".
- `moldeador` a secas se descartó: atrapaba secadores y planchas de pelo.
  Solo se usan `moldeador corporal`, `moldeador de cuerpo`,
  `moldeadora corporal` (más `faja`).
- Se agregaron `usada` / `usadas` / `usados` / `reacondicionada`: con
  `usado` solo, los avisos en femenino se colaban.
- **Cocina y mesa (21-nov-2026)**: `plato`, `cuchara`, `cucharon`,
  `tenedor`, `cubiertos`, `vajilla`, `cuberteria`, `utensilio`,
  `escurridor`, `vaso`, `mantel`, `servilleta` y las 6 variantes de tazas.
  Se usó `cubiertos` (plural) y no `cubierto`, porque "cubierto" está dentro
  de "cubierta de celular".
- **Fuera de la lista a propósito**: `sarten`, `cuchillo` y `tabla de picar`
  se agregaron y el dueño los mandó a quitar el mismo día (22-nov-2026):
  los quiere seguir viendo. No volver a meterlos sin que lo pida.
- **Navidad (22-nov-2026)**: `navidad`, `navidena`, `navideno`. Van sin
  tilde porque el título se normaliza con `_sin_tildes` antes de comparar:
  `navidena` atrapa "navideña" y `navideno` atrapa "navideño". `navidad`
  cubre "árbol de navidad", "luces de navidad", "esfera navideña" cae por
  `navidena`.
- **"taza" sola NO se bloquea**: rompía "cafetera de goteo 12 tazas". Solo
  se bloquea con material (`taza/tazas de ceramica`, `de porcelana`) o en
  juego (`juego/set de tazas`).
- **Pestañas (21-nov-2026)**: `pestana`, `pestanina`, `rimel`,
  `mascara de pestanas`, `mascara para pestanas`, `pegante de pestanas`.
  `pestana` también atrapa bisagras ("pestaña de puerta"): se aceptó.

### Duplicados: solo por ASIN (decisión cerrada)
El bloqueo de repetidos es **únicamente por ASIN** durante 24 h. Se
descartó a propósito una segunda llave por título/marca: el usuario pidió
"solo ASIN" y preferir bloquear más productos por lista negra. Consecuencia
conocida: el mismo producto publicado por otro vendedor llega con ASIN
distinto y sí se vuelve a publicar (visto con PUMA `B0D7CRQJN5` vs
`B0FHB9YK3P` y Under Armour `B0CJW9YTZB` vs `B0874W4WS5`).

---

## 4. Ritmo de publicación (lo que no hay que tocar)

- Facebook: `FACEBOOK_SEGUNDOS_ENTRE_POSTS = 60` (1 por minuto), 20-40
  ofertas/hora. Es lo que evita que Facebook limite la página.
- Canal gratis: `RETRASO_GRATIS_SEGUNDOS = 15 min`, pero con
  `CANAL_DESTINO_VIP = None` **no aplica**: publica al instante y cuenta
  como publicado.
- Orden: Telegram primero, Facebook después (en fila).
- `concurrency: revisar-canales` con `cancel-in-progress: false`: dos
  corridas nunca se enciman, se encolan.

---

## 5. Por qué las ofertas salen con retraso (análisis)

Caso real reportado: una oferta del canal Reviu salió a la 1:00 y se
publicó a las 4:00 (≈3 h).

Tres causas, en orden de peso:

1. **Revisión manual (la principal, ya resuelta).** La oferta entraba a
   `pendientes_revision.json` y esperaba aprobación humana. Con la regla
   nueva eso deja de pasar para todo lo que no esté en lista negra.
2. **El disparador corre ~1 vez por hora.** Evidencia: los commits
   `Actualiza estado` salen a las 02:19, 03:21, 04:20, 05:16, 06:21,
   07:07, 08:05, 09:05, 10:04, 11:00, 12:00. Ahí se van hasta 60 min.
   El disparo es **externo** (cron-job.org llamando a `workflow_dispatch`);
   el `schedule` nativo de GitHub está comentado a propósito en
   `.github/workflows/revisar.yml`.
3. **Cola secuencial de publicación**: Telegram primero y Facebook a 1 por
   minuto; 31 ofertas ≈ 30 min de cola.

### Telegram NO es el cuello de botella
Los errores viejos (`Too many messages had to be ignored`,
`Server sent a very old message`) no los causaba el intervalo: los causaba
Telethon procesando **en vivo** todo lo que publican los canales de fondo
(la cuenta es miembro de todos). Eso está apagado con
`receive_updates=False` en la construcción del `TelegramClient`.

- Leer: 1 sola petición por canal por corrida (`iter_messages(limit=50)`).
- Publicar: 20-40 mensajes/hora en el propio canal está dentro de lo normal.
- Si Telegram frena, Telethon duerme solo (FloodWait hasta 60 s) y sigue.
- **Una falla de Telegram ya no tumba la corrida** (23-nov-2026): la lectura
  de cada canal pasa por `_leer_mensajes_canal()` con
  `INTENTOS_LECTURA_CANAL = 3` y esperas de 20 s y 40 s. Si aun así falla
  (p. ej. `ValueError: Request was unsuccessful 6 time(s)`), se salta **solo
  ese canal** y su estado no avanza, así que esos mensajes se retoman en la
  próxima corrida; las ofertas ya preparadas de los otros canales y la
  fase 2 de publicación siguen normales.

### Lo que sí cuesta y crece con más corridas: Amazon
`data/estadisticas.json` → `imagenes_origen`: api_creators 1079, captcha
5400, html 2620, navegador 587, asin 536, navegador_tras_captcha 100,
fallo 150. `tiempo_navegador`: 19.335 s en 5.808 intentos ≈ **3,3 s por
intento**. Ahí está el tiempo real de cada corrida.

### Recomendación
Poner el disparador externo en **20 minutos** (no 15): baja el retraso de
~60 a ~20 min y deja margen para que una corrida lenta no se encime.
Cómo verificarlo sin adivinar: en Actions, comparar la **duración de la
corrida** contra el intervalo. Si dura menos, sobra margen; si dura más,
subir a 30 min.

---

## 6. Pendientes de decisión (nada de esto está implementado)

1. **Joyería y maquillaje**: hoy pasarían (la base de maquillaje también,
   aunque las pestañas y el rímel ya se bloquean). ¿Se agregan a la lista
   negra?
2. ~~**Navidad**~~: **resuelto el 22-nov-2026**, ya está bloqueada
   (`navidad`, `navidena`, `navideno`).
3. **Los 9 de casillero**: ¿publicar con una etiqueta que avise, o seguir
   frenándolos?
4. **Contador de descartes**: hoy los `[SKIP]` solo van a stdout y se
   pierden. Candidato: `data/estadisticas.json`.
5. **Línea "Prueba de Prime"**: commits ajenos `679e8d3` + `0d0f3ac`
   (enlace `/prime` con el tag, solo con insignia PRIME, bajo "Ver
   oferta", con aviso de renovación automática). Aceptada sin revisar a
   fondo.
6. **Pinterest**: opción C (pin vertical 1000x1500 + texto por Telegram)
   recomendada, y opción A (API oficial) en paralelo. Sin respuesta.
7. **Link corto / tag**: `amzn.eu` está excluido del acortador; el tag
   `benatechs00-20` está atado a `"amazon."` y no atribuye en
   `amazon.ca/.co.uk`. `amazon.co.jp` ya no importa: desde el 22-nov-2026
   no se pasa a amazon.com y siempre va al interno para revisión manual
   (ver §1). Sin resolver lo de `.ca/.co.uk` y `amzn.eu`.
8. **Los 99 pendientes**: si se quieren publicar ya, hay que volver a
   pasarlos por la regla nueva (no se re-evalúan solos).

---

## 7. Riesgos aceptados al ampliar la lista negra

- `americana` bloquea "nevera americana" (y "chaqueta americana"). Si
  molesta, cambiarla por `chaqueta americana` / `traje americano`.
- `push up` (fitness), `clutch` (autos), `plataforma`, `sueter`.
- Palabras que también existen fuera de cocina/maquillaje: `plato` (plato
  de ducha), `vaso`, `pestana` (pestaña de puerta), `mantel`.
  En títulos de ofertas casi no aparecen así; si molestan, se quitan de
  `PALABRAS_NO_AUTO` sin tocar nada más.

---

## 8. Qué NO se debe tocar sin autorización

Tags de afiliado, lógica base de bloqueo de duplicados, imágenes/logo
(las **posiciones** de la imagen y el logo de Benatechs no se mueven; el
color y la letra del badge sí se pueden ajustar siguiendo el punto 10),
ritmo de Facebook (`FACEBOOK_SEGUNDOS_ENTRE_POSTS`), auto-publicación,
Oferta Radar, selección de ofertas, `MAX_OFERTAS_POR_CORRIDA`,
`CUOTA_POR_CANAL`, Supabase, `concurrency` y la frecuencia del cron (salvo
la recomendación del punto 5).

Los secrets `CREATORS_CREDENTIAL_ID` / `CREATORS_CREDENTIAL_SECRET`
**funcionan**: la Creators API sí responde, no borrarlos.

---

## 8.1 Bridge a Oferta Radar (Amazon y MercadoLibre)

`oferta_radar.py` envía la oferta a `POST /api/offers/import` **después** de
publicarla en Telegram/Facebook. Con `USAR_BRIDGE_OFERTA_RADAR = False`, la web
se crea en paralelo y el link que ve la gente sigue siendo el de la tienda.

- **Amazon**: se limpia la URL, se extrae el ASIN y se mantiene el tag de
  afiliado (`AMAZON_TAG`).
- **MercadoLibre**: se envía `tienda: "mercadolibre"`, `marketplaceId`/`externalId`
  con el `MCO…` (de `/p/MCO…`, `/MCO-…` o `item_id=`), `amazonUrl` vacío,
  `currency: "COP"` y el enlace de afiliado **tal cual** (no se toca
  `matt_tool`). No se envía Prime.
- Si el mensaje de MercadoLibre viene en otra moneda, se descarta sin encolar.
- Si falla la red o el sitio responde 5xx, la oferta se guarda en
  `data/oferta_radar_pendientes.json` y se reintenta en la siguiente corrida.

Pruebas (sin red ni claves):

```bash
python -m unittest test_oferta_radar.py
```

---

## 9. Cómo comprobar que no se rompió

Los scripts de prueba viven **fuera del repo**, en
`C:\Users\CUENTA\AppData\Local\Temp\opencode\`:

- `pruebas_seco.py` — 30 pruebas en seco (deben ser 30/30).
- `verif_negra.py` — evalúa los pendientes reales contra las listas.
- `spot_negra.py` — 30 títulos de control (pasar / bloquear).
- `chk_md.py` — confirma que el bloque Python de
  `LISTA_BLANCA_HISTORICA.md` es idéntico a
  `config.PALABRAS_AUTO_PERMITIDAS`.
- `gen_whitelist_md.py` — regenera el `.md` desde `config.py`.

Para importar `revisar_canales` en un script hace falta stubear `requests`
en `sys.modules` y definir `TELEGRAM_API_ID=1`, `TELEGRAM_API_HASH=x`,
`TELEGRAM_SESSION=x`, `TELEGRAM_BOT_TOKEN=x`.

---

## 10. Imagen publicada: diseño y fuentes (21-nov-2026)

Todo vive en `procesar_oferta.py`. El bloque de dibujo va desde
`_COLORES_TIENDA` hasta `_dibujar_redes_sociales` (justo antes de
`aplicar_logo_a_bytes`) y se pinta sobre la imagen ya normalizada a
`TAMANO_ESTANDAR = 1100`.

**Posiciones (no se cambian sin pedirlo)**

| Zona | Qué va |
|---|---|
| arriba izquierda | badge del precio |
| arriba derecha | logo de la tienda en una pastilla |
| abajo izquierda | líneas de redes (`REDES_SOCIALES_LINEAS`) |
| abajo derecha | logo de Benatechs (`LOGO_PATH`) |

**Color del badge según el precio** (`_precio_en_cop` + `_colores_precio`)

| Precio | Relleno | Borde |
|---|---|---|
| menos de $30.000 | verde hoja `(22,128,61)` | `(134,239,172)` |
| menos de $50.000 | verde esmeralda `(6,120,86)` | `(52,211,153)` |
| menos de $100.000 | naranja `(194,65,12)` | `(251,191,36)` |
| menos de $200.000 | vino `(139,30,30)` | `(248,113,113)` |
| $200.000 o más | índigo `(49,46,129)` | dorado `(250,204,21)` |
| el texto no dice "COP" | negro `(15,15,15)` | naranja `(255,176,32)` |

Son **5 tramos** desde el 22-nov-2026 (antes eran 3). Los cinco rellenos
dan al menos 5:1 de contraste con la letra blanca, así que el precio se lee
sobre cualquier foto.

`_precio_en_cop` devuelve `None` cuando el texto no trae "COP": ahí queda
el color neutro, **nunca se inventa un rango**. Entiende `$45.900 COP`,
`$45,900 COP` y `~$45.900 COP`.

**Anillo de la tienda** (`_COLORES_TIENDA`): Amazon naranja
`(255,153,0)`; MercadoLibre azul `(52,131,250)`.

**Letras**: `assets/fuentes/ArchivoBlack-Regular.ttf` para el precio y
`assets/fuentes/Poppins-SemiBold.ttf` para las redes (también está
`Poppins-Bold.ttf`). Las elige `_cargar_fuente(tamano, estilo="precio"` o
`"redes")`, con respaldo a DejaVu/Liberation y, de última, a la letra por
defecto de Pillow: si falta el `.ttf`, la imagen sale igual.

**Helpers nuevos, reutilizables**: `_oscurecer`, `_degradado_vertical`,
`_pastilla` (pastilla con degradado, borde y esquinas redondeadas) y
`_pegar_con_sombra` (sombra difusa detrás). El precio usa Archivo Black a
`0.062 × ancho`; las redes, Poppins a `0.030 × ancho` con contorno negro y
sombra suave (antes eran 8 copias del texto para simular el borde).

**Cómo ver la imagen sin publicar nada**: `probar_imagen.py`, fuera del
repo en `C:\Users\CUENTA\AppData\Local\Temp\opencode\`; genera 6 muestras
(una por cada tramo de precio + sin COP) en `...\opencode\muestras\` y
verifica los cortes y el contraste con la letra blanca. Hay que stubear
`requests` antes de importar `procesar_oferta` (en este equipo no está
instalado).
