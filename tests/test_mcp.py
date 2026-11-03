import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import T, agente_con  # noqa: E402

from harness.errores import ToolError  # noqa: E402
from harness.mcp_client import MCPClient  # noqa: E402
from harness.mcp_server import consultar_convenio  # noqa: E402


class TestConvenios(unittest.TestCase):
    def test_logica_pura(self):
        self.assertEqual(consultar_convenio("Fonasa C")["cobertura_urgencia"], "90%")
        self.assertEqual(consultar_convenio("Isapre Banmedica (Morosidad)")["resultado"], "encontrado")
        self.assertEqual(consultar_convenio("colmena")["cobertura_urgencia"], "85%")
        self.assertEqual(consultar_convenio("Fonasa")["resultado"], "ambiguo")
        self.assertEqual(consultar_convenio("Isapre Inventada")["resultado"], "no_encontrado")
        self.assertIs(consultar_convenio("particular")["convenio_vigente"], False)


class TestMCP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mcp = MCPClient()

    @classmethod
    def tearDownClass(cls):
        cls.mcp.cerrar()

    def test_descubre_la_tool_por_tools_list(self):
        ag, _ = agente_con([], mcp=self.mcp)
        self.assertIn("consultar_convenio", ag.herr.registro)
        self.assertEqual(ag.herr.registro["consultar_convenio"]["origen"], "mcp")

    def test_llamada_real_por_stdio(self):
        r = self.mcp.llamar("consultar_convenio", {"prevision": "Fonasa A"})
        self.assertEqual(r["cobertura_urgencia"], "100%")

    def test_argumento_faltante_es_error(self):
        with self.assertRaises(ToolError):
            self.mcp.llamar("consultar_convenio", {})

    def test_tool_desconocida_es_error(self):
        with self.assertRaises(ToolError):
            self.mcp.llamar("otra_tool", {"x": "y"})

    def test_se_recupera_si_el_servidor_muere(self):
        c = MCPClient()
        try:
            self.assertEqual(c.llamar("consultar_convenio", {"prevision": "Fonasa A"})["cobertura_urgencia"], "100%")
            c.proc.kill()
            c.proc.wait()
            self.assertEqual(c.llamar("consultar_convenio", {"prevision": "Fonasa A"})["cobertura_urgencia"], "100%")
        finally:
            c.cerrar()

    def test_timeout(self):
        c = MCPClient(comando=[sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5)
        with self.assertRaises(ToolError):
            c.listar_tools()
        c.cerrar()

    def test_servidor_que_no_arranca_deja_aviso_y_el_agente_sigue(self):
        malo = MCPClient(comando=[sys.executable, "-c", "import sys; sys.exit(1)"], timeout=2)
        ag, _ = agente_con([], mcp=malo)
        self.assertTrue(any("MCP no disponible" in a for a in ag.herr.avisos))
        self.assertNotIn("consultar_convenio", ag.herr.registro)

    def test_tool_mcp_narrada_con_argumentos_no_deducibles_no_se_asiste_y_deriva(self):
        narra = {"tipo": "respuesta", "base": "herramienta", "texto": "Ejecutando consultar_convenio para la previsión..."}
        ag, llm = agente_con([narra] * 4, mcp=self.mcp)
        r = ag.turno("¿Hay convenio con Colmena?")
        self.assertEqual((r["tipo"], r["origen"]), ("fuera_de_alcance", "harness"))
        self.assertIn('"prevision": "<valor>"', llm.llamadas[2][-1]["content"])   # le pide completar los valores
        self.assertFalse(any(e["evento"] == "tool_asistida" for e in ag.log.eventos))

    def test_el_agente_consulta_convenio_via_mcp(self):
        ag, _ = agente_con([T("consultar_convenio", prevision="Isapre Colmena"),
                            {"tipo": "respuesta", "base": "herramienta", "texto": "Convenio vigente, cobertura 85% (servidor de convenios, simulado)."}],
                           mcp=self.mcp)
        r = ag.turno("¿Hay convenio con Isapre Colmena?")
        self.assertEqual(r["tools_usadas"], ["consultar_convenio"])


if __name__ == "__main__":
    unittest.main()
