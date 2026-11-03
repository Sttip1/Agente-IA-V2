import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import (
    RAIZ,  # noqa: F401,E402  (prepara sys.path)
    V,  # noqa: E402
)

from harness.declarativo import cargar_declaracion  # noqa: E402
from harness.memoria import Memoria  # noqa: E402
from harness.schema_validator import validar_schema  # noqa: E402
from harness.tracing import Log  # noqa: E402
from harness.utilidades import extraer_json, extraer_ruts, norm, normalizar_rut, ocultar_ruts, rut_valido  # noqa: E402


class TestUtilidades(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(norm("  Cédula DE Identidad "), "cedula de identidad")

    def test_rut_dv(self):
        self.assertTrue(rut_valido("11111111-1"))
        self.assertTrue(rut_valido("11.111.111-1"))
        self.assertFalse(rut_valido("11111111-2"))
        self.assertFalse(rut_valido("abc"))
        self.assertEqual(normalizar_rut(" 11.111.111-k "), "11111111-K")

    def test_extraer_ruts_con_puntos_y_texto(self):
        self.assertEqual(extraer_ruts("revisa 11.111.111-1 y 22222222-2, gracias"), ["11111111-1", "22222222-2"])
        self.assertEqual(extraer_ruts("llamar al 56912345678"), [])

    def test_ocultar_ruts(self):
        self.assertNotIn("11111111", ocultar_ruts("rut 11111111-1 y 11.111.111-1"))

    def test_extraer_json_tolerante(self):
        self.assertEqual(extraer_json('texto previo ```json\n{"a": 1}\n``` fin'), {"a": 1})
        self.assertEqual(extraer_json('Claro: {"a": {"b": 2}} listo'), {"a": {"b": 2}})
        self.assertIsNone(extraer_json("sin json"))
        self.assertIsNone(extraer_json("[1, 2]"))

    def test_validar_schema_con_el_esquema_real(self):
        sv = cargar_declaracion().schema_salida["veredicto"]
        self.assertIsNone(validar_schema(V("11111111-1", "califica"), sv))
        self.assertIsNotNone(validar_schema({"tipo": "veredicto"}, sv))
        self.assertIsNotNone(validar_schema(V("1-1", "quizas"), sv))
        self.assertIsNotNone(validar_schema(V("11111111-1", "califica", expl="corto"), sv))
        self.assertIsNotNone(validar_schema({**V("11111111-1", "califica"), "tipo": "otro"}, sv))

    def test_ventana_de_memoria_acotada(self):
        m = Memoria("sys", ventana=30)
        for i in range(100):
            m.add("user" if i % 2 == 0 else "assistant", str(i))
        v = m.ventana()
        self.assertLessEqual(len(v), 31)
        self.assertEqual(v[1]["role"], "user")

    def test_log_enmascara_ruts_en_disco(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "l.jsonl")
            Log(ruta, verbose=False).ev("usuario", mensaje="revisa 11111111-1")
            with open(ruta, encoding="utf-8") as f:
                self.assertNotIn("11111111", f.read())


if __name__ == "__main__":
    unittest.main()
