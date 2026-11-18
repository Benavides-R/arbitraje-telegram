# Lista blanca histórica (PALABRAS_AUTO_PERMITIDAS)

Guardada el **2026-11-18**, cuando el bot pasó de *lista blanca* a *lista negra*.

## Qué era

Antes, una oferta **solo se publicaba sola** si el título contenía alguna de estas
palabras (y además tenía imagen, título, precio, no estaba en la lista negra, no
requería casillero y la tienda no estaba pausada). Todo lo demás se iba a revisión
manual.

Era el cuello de botella #1: de 99 ofertas pendientes, **63 ya tenían foto, título y
precio** y solo se frenaban por no traer la palabra exacta.

## Qué hay ahora

Modelo de **lista negra**: todo lo que llega completo se publica solo, salvo que caiga
en `PALABRAS_NO_AUTO` o en las excepciones de siempre (tiendas pausadas, tiendas de
revisión manual, requiere casillero).

## Cómo revertir a la lista blanca

1. Abrir `config.py`.
2. Poner `USAR_LISTA_BLANCA = True` (está justo encima de la lista).
3. Listo. `PALABRAS_AUTO_PERMITIDAS` **sigue intacta en `config.py`**: no se borró ni
   se editó.

Si la lista de `config.py` se perdiera o se cambiara, aquí está la copia exacta de las
211 palabras tal como estaban ese día: se puede pegar de vuelta.

## Las 211 palabras (copia exacta, lista para pegar en `config.py`)

```python
PALABRAS_AUTO_PERMITIDAS = [
    "camara", "camara de seguridad", "seguridad", "alarma", "cerradura", "sensor",
    "timbre inteligente", "rastreador", "localizador", "gps", "tablet", "inflador",
    "compresor", "drone", "dron", "audifono", "auricular", "smartwatch",
    "reloj inteligente", "laptop", "monitor", "disco duro", "ssd", "router",
    "proyector", "impresora", "cable", "cargador", "cargador rapido", "power bank",
    "altavoz", "soundbar", "teclado", "mouse", "webcam", "audifonos inalambricos",
    "audifonos gamer", "diadema", "camara deportiva", "lupa", "termometro",
    "balanza", "ventilador", "purificador de aire", "bombillo", "lampara", "led",
    "aspiradora", "freidora de aire", "foco", "mochila", "reloj", "gafas de sol",
    "guantes", "herramienta", "taladro", "bateria", "memoria", "portatil",
    "telefono", "bluetooth", "inalambrico", "recargable", "karaoke", "juego",
    "pieza", "paquete", "acero", "sarten", "cuchillo", "toalla", "edredon",
    "manta", "organizador", "facial", "cabello", "cepillo", "serum", "nike",
    "adidas", "puma", "reebok", "balance", "garmin", "columbia", "under armour",
    "saucony", "fila", "champion", "jordan", "asics", "sudadera", "tenis",
    "capucha", "sueter", "zapatillas", "camiseta", "chaqueta", "camisa",
    "pantalones", "polo", "calzado", "ninos", "cuero", "collar", "aretes",
    "pulsera", "anillo", "joyeria", "hanes", "skechers", "nautica", "tommy", "rtx",
    "geforce", "grafica", "escritorio", "billetera", "rfid", "usb", "molinillo",
    "controlador", "microscopio", "tv", "smart tv", "fire tv", "televisor",
    "hisense", "tcl", "roku", "samsung", "philips", "sony", "zapatos", "converse",
    "vans", "medicube", "cerave", "dove", "johnson", "listerine", "colgate",
    "gillette", "nivea", "palmolive", "pantene", "schick", "eucerin", "neutrogena",
    "cetaphil", "vaseline", "oral-b", "oral b", "sensodyne", "chapstick", "crema",
    "shampoo", "champu", "acondicionador", "jabon", "desodorante", "locion",
    "balsamo", "pasta dental", "enjuague", "protector solar", "hidratante",
    "limpiador", "suero", "antitranspirante", "bolso", "parlante", "bocina",
    "celular", "computador", "consola", "playstation", "xbox", "nintendo",
    "control", "silla gamer", "aire acondicionado", "colchon", "cafetera",
    "licuadora", "olla", "vajilla", "secador", "afeitadora", "cortadora",
    "multimetro", "destornillador", "extensor", "regulador", "videoportero",
    "videopuerto", "grabadora", "tripode", "raton", "alexa", "echo dot", "rgb",
    "luces permanentes", "luces exteriores", "cadena de luces", "razer",
    "logitech", "corsair", "anker", "jbl", "redragon"
]
```

## Las mismas 211 palabras, en columnas

| Palabra | Palabra | Palabra |
|---|---|---|
| camara | camara de seguridad | seguridad |
| alarma | cerradura | sensor |
| timbre inteligente | rastreador | localizador |
| gps | tablet | inflador |
| compresor | drone | dron |
| audifono | auricular | smartwatch |
| reloj inteligente | laptop | monitor |
| disco duro | ssd | router |
| proyector | impresora | cable |
| cargador | cargador rapido | power bank |
| altavoz | soundbar | teclado |
| mouse | webcam | audifonos inalambricos |
| audifonos gamer | diadema | camara deportiva |
| lupa | termometro | balanza |
| ventilador | purificador de aire | bombillo |
| lampara | led | aspiradora |
| freidora de aire | foco | mochila |
| reloj | gafas de sol | guantes |
| herramienta | taladro | bateria |
| memoria | portatil | telefono |
| bluetooth | inalambrico | recargable |
| karaoke | juego | pieza |
| paquete | acero | sarten |
| cuchillo | toalla | edredon |
| manta | organizador | facial |
| cabello | cepillo | serum |
| nike | adidas | puma |
| reebok | balance | garmin |
| columbia | under armour | saucony |
| fila | champion | jordan |
| asics | sudadera | tenis |
| capucha | sueter | zapatillas |
| camiseta | chaqueta | camisa |
| pantalones | polo | calzado |
| ninos | cuero | collar |
| aretes | pulsera | anillo |
| joyeria | hanes | skechers |
| nautica | tommy | rtx |
| geforce | grafica | escritorio |
| billetera | rfid | usb |
| molinillo | controlador | microscopio |
| tv | smart tv | fire tv |
| televisor | hisense | tcl |
| roku | samsung | philips |
| sony | zapatos | converse |
| vans | medicube | cerave |
| dove | johnson | listerine |
| colgate | gillette | nivea |
| palmolive | pantene | schick |
| eucerin | neutrogena | cetaphil |
| vaseline | oral-b | oral b |
| sensodyne | chapstick | crema |
| shampoo | champu | acondicionador |
| jabon | desodorante | locion |
| balsamo | pasta dental | enjuague |
| protector solar | hidratante | limpiador |
| suero | antitranspirante | bolso |
| parlante | bocina | celular |
| computador | consola | playstation |
| xbox | nintendo | control |
| silla gamer | aire acondicionado | colchon |
| cafetera | licuadora | olla |
| vajilla | secador | afeitadora |
| cortadora | multimetro | destornillador |
| extensor | regulador | videoportero |
| videopuerto | grabadora | tripode |
| raton | alexa | echo dot |
| rgb | luces permanentes | luces exteriores |
| cadena de luces | razer | logitech |
| corsair | anker | jbl |
| redragon |  |  |
