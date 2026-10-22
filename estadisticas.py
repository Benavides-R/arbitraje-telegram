"""
Conteo simple de publicaciones por canal, para el reporte semanal que se
manda por Telegram los domingos (ver verificar_y_enviar_reporte, llamada
una vez por corrida desde main() -- se manda solo la primera vez que el
cron corre en domingo, gracias al chequeo de "ultimo_reporte").
"""

import re
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

ARCHIVO = Path(__file__).parent / "data" / "estadisticas.json"
# Historial DETALLADO de cada aprobación (fecha, canal, título, precio,
# categoría, si traía foto) -- a diferencia de conteo_por_canal, este no se
# resetea: crece con el tiempo para poder analizar qué tipos de ofertas se
# aprueban de verdad (patrón de gustos, rendimiento por canal, etc.).
APROBADAS_FILE = Path(__file__).parent / "data" / "aprobadas.json"

# El servidor de GitHub Actions corre en UTC, pero "domingo" debe decidirse
# con la hora de Colombia (UTC-5, sin horario de verano) -- si no, el
# reporte puede disparar de noche del sábado (cuando en UTC ya es domingo).
ZONA_COLOMBIA = timezone(timedelta(hours=-5))


def _cargar():
    if ARCHIVO.exists():
        return json.loads(ARCHIVO.read_text())
    return {"conteo_por_canal": {}, "ultimo_reporte": None}


def _guardar(datos):
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVO.write_text(json.dumps(datos, indent=2, ensure_ascii=False))


def registrar_publicacion(canal, texto=None, con_imagen=None):
    """Suma al conteo semanal del reporte. Si se pasa `texto` (la oferta
    aprobada), además guarda el detalle en aprobadas.json para el análisis
    histórico de gustos/canales -- nunca falla la publicación por esto."""
    datos = _cargar()
    datos["conteo_por_canal"][canal] = datos["conteo_por_canal"].get(canal, 0) + 1
    _guardar(datos)

    if not texto:
        return
    try:
        _registrar_aprobacion_detalle(canal, texto, con_imagen)
    except Exception as e:
        print(f"[WARN] No se pudo guardar el detalle de la aprobación: {e}")


def _registrar_aprobacion_detalle(canal, texto, con_imagen):
    titulo = re.search(r"📦 <b>Producto:</b> (.+)", texto)
    precio = re.search(r"💸 Precio: (.+)", texto)
    categoria = re.search(r"#ad\s+(.+)$", texto, re.MULTILINE)

    registro = {
        "fecha": datetime.now(ZONA_COLOMBIA).isoformat(timespec="seconds"),
        "canal": canal,
        "titulo": re.sub(r"<[^>]+>", "", titulo.group(1)).strip() if titulo else None,
        "precio": precio.group(1).strip() if precio else None,
        "categoria": categoria.group(1).strip() if categoria else None,
        "con_imagen": bool(con_imagen),
    }
    registros = []
    if APROBADAS_FILE.exists():
        registros = json.loads(APROBADAS_FILE.read_text())
    registros.append(registro)
    APROBADAS_FILE.parent.mkdir(parents=True, exist_ok=True)
    APROBADAS_FILE.write_text(json.dumps(registros, indent=2, ensure_ascii=False))


def registrar_imagen_origen(origen):
    """Conteo de dónde terminó saliendo la foto del producto:
    "html" (requests simple), "navegador" (Playwright), "captcha" (Amazon
    respondió con su desafío de robot -- bloqueo por IP) o "fallo" -- para
    monitorear la variación diaria de la extracción (históricamente iba
    de 0% a 94% según el día)."""
    datos = _cargar()
    imagenes = datos.get("imagenes_origen", {})
    imagenes[origen] = imagenes.get(origen, 0) + 1
    datos["imagenes_origen"] = imagenes
    _guardar(datos)


def verificar_y_enviar_reporte(enviar_mensaje_func):
    """Si hoy es domingo y todavía no se mandó el reporte de esta semana,
    arma un resumen simple y lo envía -- luego resetea el conteo."""
    ahora = datetime.now(ZONA_COLOMBIA)
    hoy = ahora.strftime("%Y-%m-%d")
    if ahora.weekday() != 6:  # 6 = domingo
        return

    datos = _cargar()
    if datos.get("ultimo_reporte") == hoy:
        return  # ya se mandó hoy, no repetir en cada corrida del domingo

    conteo = datos.get("conteo_por_canal", {})
    total = sum(conteo.values())
    if total == 0:
        texto = "📊 Reporte semanal: no se publicó ninguna oferta esta semana."
    else:
        lineas = [f"📊 Reporte semanal -- {total} ofertas publicadas:"]
        for canal, cantidad in sorted(conteo.items(), key=lambda x: -x[1]):
            lineas.append(f"• {canal}: {cantidad}")
        texto = "\n".join(lineas)

    enviar_mensaje_func(texto)

    datos["conteo_por_canal"] = {}
    datos["ultimo_reporte"] = hoy
    _guardar(datos)
