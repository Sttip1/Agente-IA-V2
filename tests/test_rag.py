import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.rag_pipeline import buscar_en_rag, similitud_coseno
from harness.tools.buscar_reglamento import buscar_reglamento
import harness.llm_client

class FakeEmbeddingClient:
    def embed(self, textos):
        # Retorna vectores falsos deterministas basados en longitud de texto
        return [[float(len(t) % 10)] * 768 for t in textos]

class TestRAGPipeline(unittest.TestCase):
    
    def setUp(self):
        # Mock de llm_client.embed para evitar llamadas reales a Ollama en tests
        self.original_embed = harness.llm_client.embed
        harness.llm_client.embed = FakeEmbeddingClient().embed

    def tearDown(self):
        harness.llm_client.embed = self.original_embed

    def test_similitud_coseno(self):
        v1 = [1.0, 0.0, 0.0]
        v2 = [1.0, 0.0, 0.0]
        score = similitud_coseno(v1, v2)
        self.assertEqual(score, 1.0)

    def test_buscar_en_rag(self):
        res = buscar_en_rag("Ley de Urgencia")
        self.assertIn("estado", res)
        # Con el fake embed o documentos existentes, debe retornar formato correcto
        if res["estado"] == "encontrado":
            self.assertTrue(len(res["resultados"]) > 0)

    def test_buscar_reglamento_tool(self):
        res = buscar_reglamento("atención médica inmediata")
        self.assertIn("estado", res)

if __name__ == "__main__":
    unittest.main()
