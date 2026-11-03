"""Casos reales observados con gemma3:4b: confundir 'tool' con 'tipo' y reutilizar el RUT de la sesión en una pregunta ajena."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import SK, T, V, agente_con  # noqa: E402

from harness.utilidades import refiere_a_paciente  # noqa: E402

FUERA = {"tipo": "fuera_de_alcance", "limite": "fuera de función", "texto": "Eso no es parte de la admisión de urgencias."}


class TestReferenciaAPaciente(unittest.TestCase):
    def test_mensajes_que_aluden_a_un_paciente(self):
        for t in ("dime su previsión", "¿y qué le falta?", "verifica el caso", "revisa 11111111-1", "¿es apto?", "hazlo de nuevo"):
            self.assertTrue(refiere_a_paciente(t), t)

    def test_mensajes_ajenos(self):
        for t in ("dime la hora de colacion", "que puedes hacer", "cuál es el clima hoy", "dame una receta de pastel"):
            self.assertFalse(refiere_a_paciente(t), t)


class TestDerivaDelModelo(unittest.TestCase):
    def _sesion(self, tercer_turno):
        ag, llm = agente_con([T("evaluar_reglas", rut="11111111-1"), SK, V("11111111-1", "califica")] + tercer_turno)
        ag.turno("revisa 11111111-1")
        return ag, llm

    def test_tool_que_en_realidad_es_un_tipo_recibe_el_formato_correcto(self):
        ag, llm = self._sesion([{"tool": "fuera_de_alcance", "texto": "No puedo."}, FUERA])
        r = ag.turno("dime la hora de colacion")
        self.assertEqual(r["tipo"], "fuera_de_alcance")
        self.assertIn('usa "tipo"', llm.llamadas[-1][-1]["content"])

    def test_no_reusa_el_rut_de_la_sesion_en_una_pregunta_ajena(self):
        ag, llm = self._sesion([T("consultar_registro", rut="11111111-1"), FUERA])
        r = ag.turno("dime la hora de colacion")
        self.assertEqual(r["tipo"], "fuera_de_alcance")
        self.assertNotIn("consultar_registro", [e.get("tool") for e in ag.log.eventos if e["evento"] == "tool"])
        self.assertIn("no se refiere a ningún paciente", llm.llamadas[-1][-1]["content"])

    def test_si_insiste_el_arnes_deriva_sin_veredicto(self):
        ag, _ = self._sesion([T("consultar_registro", rut="11111111-1")] * 3)
        r = ag.turno("dime la hora de colacion")
        self.assertEqual((r["tipo"], r["origen"]), ("fuera_de_alcance", "harness"))

    def test_seguimiento_legitimo_si_usa_el_rut_de_la_sesion(self):
        ag, _ = self._sesion([T("consultar_registro", rut="11111111-1"),
                              {"tipo": "respuesta", "base": "herramienta", "texto": "La previsión del paciente 11111111-1 es Fonasa A (activa)."}])
        r = ag.turno("dime su previsión")
        self.assertEqual(r["tipo"], "respuesta")

    def test_que_puedes_hacer_se_acepta_como_saludo(self):
        ag, _ = agente_con([{"tipo": "respuesta", "base": "saludo", "texto": "Puedo verificar si un caso califica y responder sobre normativa."}])
        r = ag.turno("que puedes hacer")
        self.assertEqual((r["tipo"], r["base"]), ("respuesta", "saludo"))


if __name__ == "__main__":
    unittest.main()
