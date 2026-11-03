import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import RAIZ  # noqa: F401,E402

from harness.datos import cargar_pacientes  # noqa: E402
from harness.reglas import motor_reglas  # noqa: E402
from harness.utilidades import rut_valido  # noqa: E402


class TestReglas(unittest.TestCase):
    def test_todos_los_pacientes_coinciden_con_esperado(self):
        pacientes = cargar_pacientes()
        self.assertGreaterEqual(len(pacientes), 7)
        for rut, p in pacientes.items():
            self.assertEqual(motor_reglas(rut, p)["estado"], p["esperado"], rut)

    def test_todos_los_ruts_de_prueba_son_validos(self):
        self.assertTrue(all(rut_valido(r) for r in cargar_pacientes()))

    def test_rut_inexistente(self):
        r = motor_reglas("99999999-9", None)
        self.assertEqual(r["estado"], "falta_informacion")
        self.assertTrue(r["antecedentes_faltantes"])

    def test_previsional_inactiva_y_triage_son_duros(self):
        p = cargar_pacientes()
        self.assertEqual(motor_reglas("22222222-2", p["22222222-2"])["estado"], "no_califica")
        self.assertEqual(motor_reglas("44444444-4", p["44444444-4"])["estado"], "no_califica")

    def test_menor_acepta_certificado_de_nacimiento_pero_adulto_no(self):
        reg = dict(cargar_pacientes()["55555555-5"])
        self.assertEqual(motor_reglas("55555555-5", reg)["estado"], "califica")
        reg["es_menor"] = False
        self.assertEqual(motor_reglas("55555555-5", reg)["estado"], "falta_informacion")

    def test_dato_ausente_no_se_trata_como_false(self):
        r = motor_reglas("77777777-7", cargar_pacientes()["77777777-7"])
        self.assertIsNone(r["detalle"]["R2_PREVISION_ACTIVA"][0])
        self.assertEqual(r["estado"], "falta_informacion")

    def test_dos_fallas_a_la_vez_se_listan_ambas(self):
        reg = dict(cargar_pacientes()["22222222-2"])
        reg["documentos_presentados"] = []
        r = motor_reglas("22222222-2", reg)
        self.assertEqual(r["estado"], "no_califica")
        self.assertEqual(len(r["antecedentes_faltantes"]), 2)


if __name__ == "__main__":
    unittest.main()
