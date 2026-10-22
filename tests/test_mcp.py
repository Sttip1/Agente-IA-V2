import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.mcp_client import MCPClientStdio, consultar_convenio_mcp
from harness.tools import ejecutar_tool

class TestMCP(unittest.TestCase):
    
    def test_mcp_cliente_servidor_conexion(self):
        cliente = MCPClientStdio()
        try:
            tools = cliente.listar_tools()
            self.assertTrue(len(tools) > 0)
            nombres = [t["name"] for t in tools]
            self.assertIn("consultar_convenio", nombres)
        finally:
            cliente.cerrar()

    def test_mcp_consultar_convenio_valido(self):
        res = consultar_convenio_mcp("Isapre Banmedica")
        self.assertEqual(res.get("resultado"), "encontrado")
        self.assertTrue(res.get("convenio_vigente"))

    def test_mcp_tool_ejecutar(self):
        res = ejecutar_tool("consultar_convenio", {"prevision": "Fonasa A"})
        self.assertEqual(res.get("resultado"), "encontrado")
        self.assertEqual(res.get("cobertura_urgencia"), "100%")

if __name__ == "__main__":
    unittest.main()
