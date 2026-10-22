import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.tools import ejecutar_tool
from harness.tools.consultar_antecedentes import buscar_paciente
from harness.tools.validar_ley_urgencia import validar_ley_urgencia
from harness.tools.buscar_reglamento import buscar_reglamento

class TestTools(unittest.TestCase):
    
    def test_buscar_paciente_existente(self):
        res = buscar_paciente("11111111-1")
        self.assertEqual(res["estado"], "encontrado")
        self.assertEqual(res["datos"]["rut"], "11111111-1")

    def test_buscar_paciente_inexistente(self):
        res = buscar_paciente("99999999-9")
        self.assertIn("error", res)

    def test_validar_ley_urgencia_califica(self):
        res = validar_ley_urgencia("11111111-1")
        self.assertEqual(res["estado"], "califica")

    def test_validar_ley_urgencia_no_califica(self):
        res = validar_ley_urgencia("22222222-2")
        self.assertEqual(res["estado"], "no_califica")

    def test_validar_ley_urgencia_falta_info(self):
        res = validar_ley_urgencia("33333333-3")
        self.assertEqual(res["estado"], "falta_informacion")

    def test_buscar_reglamento_encontrado(self):
        res = buscar_reglamento("urgencia vital")
        self.assertEqual(res["estado"], "encontrado")

    def test_ejecutar_tool_registro(self):
        res = ejecutar_tool("consultar_antecedentes", {"rut": "11111111-1"})
        self.assertEqual(res["estado"], "encontrado")

if __name__ == "__main__":
    unittest.main()
