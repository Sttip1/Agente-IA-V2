"""Prueba el cliente HTTP real contra un servidor local que imita a Ollama."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import OllamaFalso  # noqa: E402

from harness.errores import LLMNoDisponible  # noqa: E402
from harness.llm_client import OllamaClient  # noqa: E402


class TestOllamaClient(unittest.TestCase):
    def servidor(self, rutas):
        s = OllamaFalso(rutas)
        self.addCleanup(s.cerrar)
        return s

    def test_chat_ok_y_payload(self):
        s = self.servidor({"/api/chat": (200, {"message": {"role": "assistant", "content": '{"a": 1}'}}, 0)})
        c = OllamaClient(host=s.url, modelo="m", timeout=5)
        self.assertEqual(c.chat([{"role": "user", "content": "hola"}]), '{"a": 1}')
        ruta, body = s.capturas[0]
        self.assertEqual((ruta, body["model"], body["format"], body["stream"]), ("/api/chat", "m", "json", False))
        self.assertEqual(body["options"]["temperature"], 0)

    def test_modelo_no_descargado(self):
        s = self.servidor({"/api/chat": (404, {"error": 'model "gemma3:4b" not found, try pulling it first'}, 0)})
        with self.assertRaises(LLMNoDisponible) as cm:
            OllamaClient(host=s.url, modelo="gemma3:4b", timeout=5).chat([{"role": "user", "content": "x"}])
        self.assertIn("ollama pull gemma3:4b", str(cm.exception))

    def test_ollama_apagado(self):
        with self.assertRaises(LLMNoDisponible) as cm:
            OllamaClient(host="http://127.0.0.1:9", timeout=2).chat([{"role": "user", "content": "x"}])
        self.assertIn("ollama serve", str(cm.exception))

    def test_timeout(self):
        s = self.servidor({"/api/chat": (200, {"message": {"content": "{}"}}, 2.0)})
        with self.assertRaises(LLMNoDisponible) as cm:
            OllamaClient(host=s.url, timeout=0.3).chat([{"role": "user", "content": "x"}])
        self.assertIn("Timeout", str(cm.exception))

    def test_respuesta_inesperada(self):
        s = self.servidor({"/api/chat": (200, {"otra": "cosa"}, 0)})
        with self.assertRaises(LLMNoDisponible):
            OllamaClient(host=s.url, timeout=5).chat([{"role": "user", "content": "x"}])

    def test_embed_endpoint_nuevo(self):
        s = self.servidor({"/api/embed": (200, {"embeddings": [[1, 2], [3, 4]]}, 0)})
        self.assertEqual(OllamaClient(host=s.url, timeout=5).embed(["a", "b"]), [[1, 2], [3, 4]])

    def test_embed_cae_al_endpoint_antiguo_si_no_existe_el_nuevo(self):
        s = self.servidor({"/api/embed": (404, "404 page not found", 0),
                           "/api/embeddings": (200, {"embedding": [9, 9]}, 0)})
        self.assertEqual(OllamaClient(host=s.url, timeout=5).embed(["a", "b"]), [[9, 9], [9, 9]])
        self.assertEqual([r for r, _ in s.capturas].count("/api/embeddings"), 2)

    def test_embed_con_modelo_faltante_no_cae_al_antiguo(self):
        s = self.servidor({"/api/embed": (404, {"error": 'model "nomic-embed-text" not found'}, 0)})
        with self.assertRaises(LLMNoDisponible) as cm:
            OllamaClient(host=s.url, modelo_embed="nomic-embed-text", timeout=5).embed(["a"])
        self.assertIn("ollama pull nomic-embed-text", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
