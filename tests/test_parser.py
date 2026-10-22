import unittest
import sys
import os

# Asegurar que el path incluya evaluacion_2_agente_ia
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.output_parser import extraer_json_respuesta

class TestOutputParser(unittest.TestCase):
    
    def test_extraer_json_limpio(self,):
        texto = '{"tool": "buscar_paciente", "args": {"rut": "11111111-1"}}'
        resultado = extraer_json_respuesta(texto)
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado["tool"], "buscar_paciente")
        self.assertEqual(resultado["args"]["rut"], "11111111-1")

    def test_extraer_json_markdown(self):
        texto = 'Aquí tienes la tool:\n```json\n{"tool": "validar_ley_urgencia", "args": {"rut": "22222222-2"}}\n```'
        resultado = extraer_json_respuesta(texto)
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado["tool"], "validar_ley_urgencia")

    def test_extraer_json_invalido(self):
        texto = 'Esto es texto plano sin json'
        resultado = extraer_json_respuesta(texto)
        self.assertIsNone(resultado)

if __name__ == "__main__":
    unittest.main()
