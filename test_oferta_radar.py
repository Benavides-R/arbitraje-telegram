"""Pruebas de la integración con Oferta Radar (sin red ni claves reales).

Se ejecutan con:
    python -m unittest test_oferta_radar.py
"""

import unittest
from unittest.mock import patch

import oferta_radar


TEXTO_ML = (
    "📦 <b>Producto:</b> Silla gamer ergonómica\n"
    "⭐️ Calificación: 4.7 (123)\n"
    "💸 Precio: $799.900 COP\n"
    "⚡ Ver oferta: https://www.mercadolibre.com.co/p/MCO1234567890?matt_tool=123\n"
    "#ad #hogar"
)

TEXTO_AMAZON = (
    "📦 <b>Producto:</b> Audífonos Sony WH-1000XM5\n"
    "⭐️ Calificación: 4.6 (2048)\n"
    "💸 Precio: $1.299.900 COP\n"
    "⚡ Ver oferta: https://www.amazon.com/dp/B0G5SF8CX4?tag=benatechs00-20\n"
    "#ad #audio"
)


class ExtraccionTest(unittest.TestCase):
    def test_mercadolibre_extrae_tienda_y_mco(self):
        datos = oferta_radar._extraer_datos_de_texto(TEXTO_ML)
        self.assertEqual(datos["tienda"], "mercadolibre")
        self.assertEqual(datos["externalId"], "MCO1234567890")
        self.assertEqual(datos["marketplaceId"], "MCO1234567890")
        self.assertIsNone(datos["amazonUrl"])
        self.assertFalse(datos["isPrime"])
        self.assertEqual(datos["price"], 799900)
        self.assertEqual(datos["currency"], "COP")

    def test_amazon_sigue_igual(self):
        datos = oferta_radar._extraer_datos_de_texto(TEXTO_AMAZON)
        self.assertEqual(datos["tienda"], "amazon")
        self.assertEqual(datos["externalId"], "B0G5SF8CX4")
        self.assertEqual(datos["amazonUrl"], "https://www.amazon.com/dp/B0G5SF8CX4")
        self.assertIsNone(datos["shipping"])

    def test_mercadolibre_descarta_prime(self):
        texto = TEXTO_ML.replace("#ad #hogar", "🚚 Envío Prime\n#ad #hogar")
        datos = oferta_radar._extraer_datos_de_texto(texto)
        self.assertIsNone(datos["shipping"])
        self.assertFalse(datos["isPrime"])

    def test_mercadolibre_item_mco(self):
        texto = TEXTO_ML.replace(
            "https://www.mercadolibre.com.co/p/MCO1234567890?matt_tool=123",
            "https://articulo.mercadolibre.com.co/MCO-987654321-silla-gamer",
        )
        datos = oferta_radar._extraer_datos_de_texto(texto)
        self.assertEqual(datos["tienda"], "mercadolibre")
        self.assertEqual(datos["externalId"], "MCO987654321")


class EnvioTest(unittest.TestCase):
    def _enviar(self, texto):
        capturado = {}

        def falso_enviar(payload):
            capturado.update(payload)
            return True

        with patch.object(oferta_radar, "OFERTA_RADAR_API_KEY", "clave"), \
             patch.object(oferta_radar, "OFERTA_RADAR_URL", "https://oferta-radar.com"), \
             patch.object(oferta_radar, "_enviar_payload", side_effect=falso_enviar), \
             patch.object(oferta_radar, "_guardar_cola") as guardar:
            resultado = oferta_radar.enviar_a_oferta_radar(texto, "https://img.test/foto.webp")
        return resultado, capturado, guardar

    def test_payload_mercadolibre(self):
        _, payload, guardar = self._enviar(TEXTO_ML)
        self.assertEqual(payload["tienda"], "mercadolibre")
        self.assertEqual(payload["marketplaceId"], "MCO1234567890")
        self.assertEqual(payload["currency"], "COP")
        self.assertFalse(payload["isPrime"])
        self.assertIsNone(payload["amazonUrl"])
        self.assertEqual(payload["affiliateUrl"], "https://www.mercadolibre.com.co/p/MCO1234567890?matt_tool=123")
        guardar.assert_not_called()

    def test_payload_amazon(self):
        _, payload, _ = self._enviar(TEXTO_AMAZON)
        self.assertEqual(payload["tienda"], "amazon")
        self.assertEqual(payload["externalId"], "B0G5SF8CX4")
        self.assertEqual(payload["amazonUrl"], "https://www.amazon.com/dp/B0G5SF8CX4")

    def test_mercadolibre_en_usd_se_descarta(self):
        texto = TEXTO_ML.replace("COP", "USD")
        with patch.object(oferta_radar, "OFERTA_RADAR_API_KEY", "clave"), \
             patch.object(oferta_radar, "OFERTA_RADAR_URL", "https://oferta-radar.com"), \
             patch.object(oferta_radar, "_enviar_payload") as enviar:
            resultado = oferta_radar.enviar_a_oferta_radar(texto, "https://img.test/foto.webp")
        self.assertIsNone(resultado)
        enviar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
