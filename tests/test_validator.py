import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.schema_validator import validar_datos, ValidacionError

class TestSchemaValidator(unittest.TestCase):
    
    def test_validar_input_valido(self):
        datos_input = {
            "rut": "11111111-1",
            "motivo_consulta": "Dolor",
            "prevision": "Fonasa A",
            "triage_revisado_por_clinico": True,
            "documentos_presentados": ["Carnet"]
        }
        resultado = validar_datos(datos_input, "input")
        self.assertTrue(resultado)

    def test_validar_input_faltante(self):
        datos_input = {
            "rut": "11111111-1",
            "motivo_consulta": "Dolor"
            # Faltan campos requeridos
        }
        with self.assertRaises(ValidacionError):
            validar_datos(datos_input, "input")

    def test_validar_output_valido(self):
        datos_output = {
            "estado": "califica",
            "explicacion": "Todo en orden",
            "antecedentes_faltantes": [],
            "reglas_aplicadas": ["Ley 1"]
        }
        resultado = validar_datos(datos_output, "output")
        self.assertTrue(resultado)

    def test_validar_output_enum_invalido(self):
        datos_output = {
            "estado": "estado_inventado",
            "explicacion": "Error",
            "antecedentes_faltantes": [],
            "reglas_aplicadas": []
        }
        with self.assertRaises(ValidacionError):
            validar_datos(datos_output, "output")

if __name__ == "__main__":
    unittest.main()
