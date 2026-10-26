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
        return json.loads(ARCHIVO.read_text(encoding="utf-8"))
    return {"conteo_por_canal": {}, "ultimo_reporte": None}


def _guardar(datos):
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVO.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")


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
        registros = json.loads(APROBADAS_FILE.read_text(encoding="utf-8"))
    registros.append(registro)
    APROBADAS_FILE.parent.mkdir(parents=True, exist_ok=True)
    APROBADAS_FILE.write_text(json.dumps(registros, indent=2, ensure_ascii=False), encoding="utf-8")


def registrar_imagen_origen(origen):
    """Conteo de dónde terminó saliendo la foto del producto:
    "html" (requests simple), "navegador" (Playwright), "navegador_tras_captcha"
    (el navegador ganó DESPUÉS de que el HTML ligero ya dio captcha -- el dato
    que decide si vale la pena saltárselo), "captcha" (Amazon respondió con su
    desafío de robot -- bloqueo por IP) o "fallo" -- para monitorear la
    variación diaria de la extracción (históricamente iba de 0% a 94% según
    el día)."""
    datos = _cargar()
    imagenes = datos.get("imagenes_origen", {})
    imagenes[origen] = imagenes.get(origen, 0) + 1
    datos["imagenes_origen"] = imagenes
    _guardar(datos)


def registrar_auto_publicacion(canal):
    """Publicación AUTOMÁTICA (completa, sin tu aprobación) -- contador
    SEPARADO de conteo_por_canal (que son solo aprobaciones manuales tuyas),
    para poder medir de verdad cuánto genera el bot solo. Se resetea junto
    con el reporte semanal. Nunca lanza error: no debe tumbar una
    publicación."""
    try:
        datos = _cargar()
        autos = datos.get("auto_publicadas", {})
        autos[canal] = autos.get(canal, 0) + 1
        datos["auto_publicadas"] = autos
        _guardar(datos)
    except Exception as e:
        print(f"[WARN] No se registró la publicación automática: {e}")


def registrar_tiempo_navegador(segundos):
    """Acumula cuántos segundos de corrida se van en intentos de navegador
    (Playwright) y cuántos intentos hubo -- para decidir con números si
    compensa saltarlo cuando el HTML ya dio captcha. Nunca lanza error."""
    try:
        datos = _cargar()
        tiempo = datos.get("tiempo_navegador", {"segundos": 0.0, "intentos": 0})
        tiempo["segundos"] = round(tiempo.get("segundos", 0.0) + segundos, 1)
        tiempo["intentos"] = tiempo.get("intentos", 0) + 1
        datos["tiempo_navegador"] = tiempo
        _guardar(datos)
    except Exception as e:
        print(f"[WARN] No se registró el tiempo de navegador: {e}")


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
    autos = datos.get("auto_publicadas", {})
    total = sum(conteo.values())
    total_auto = sum(autos.values())
    if total == 0 and total_auto == 0:
        texto = "📊 Reporte semanal: no se publicó ninguna oferta esta semana."
    else:
        lineas = [f"📊 Reporte semanal -- {total + total_auto} ofertas "
                  f"({total} manuales + {total_auto} automáticas):"]
        for canal, cantidad in sorted(conteo.items(), key=lambda x: -x[1]):
            lineas.append(f"• {canal}: {cantidad} manuales"
                          + (f" + {autos.get(canal, 0)} automáticas" if autos.get(canal) else ""))
        for canal, cantidad in sorted(autos.items(), key=lambda x: -x[1]):
            if canal not in conteo:
                lineas.append(f"• {canal}: {cantidad} automáticas")
        texto = "\n".join(lineas)

    enviar_mensaje_func(texto)

    datos["conteo_por_canal"] = {}
    datos["auto_publicadas"] = {}
    datos["ultimo_reporte"] = hoy
    _guardar(datos)
