"""
Conteo simple de publicaciones por canal, para el reporte semanal que se
manda por Telegram los domingos (ver verificar_y_enviar_reporte, llamada
una vez por corrida desde main() -- se manda solo la primera vez que el
cron corre en domingo, gracias al chequeo de "ultimo_reporte").
"""

import json
from pathlib import Path
from datetime import datetime, timezone

ARCHIVO = Path(__file__).parent / "data" / "estadisticas.json"


def _cargar():
    if ARCHIVO.exists():
        return json.loads(ARCHIVO.read_text())
    return {"conteo_por_canal": {}, "ultimo_reporte": None}


def _guardar(datos):
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVO.write_text(json.dumps(datos, indent=2, ensure_ascii=False))


def registrar_publicacion(canal):
    datos = _cargar()
    datos["conteo_por_canal"][canal] = datos["conteo_por_canal"].get(canal, 0) + 1
    _guardar(datos)


def verificar_y_enviar_reporte(enviar_mensaje_func):
    """Si hoy es domingo y todavía no se mandó el reporte de esta semana,
    arma un resumen simple y lo envía -- luego resetea el conteo."""
    ahora = datetime.now(timezone.utc)
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
