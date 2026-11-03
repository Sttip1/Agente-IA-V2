import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import RAIZ, LLMFalso  # noqa: F401,E402

from harness.config import CACHE_RAG_DIR  # noqa: E402
from harness.datos import cargar_documentos  # noqa: E402
from harness.rag import RAG, chunkear, coseno  # noqa: E402
from harness.utilidades import norm  # noqa: E402


class Embedder(LLMFalso):
    """Embeddings falsos deterministas que cuentan cuántas veces se les llama."""

    def __init__(self):
        super().__init__([])
        self.llamadas_embed = 0

    def embed(self, textos):
        self.llamadas_embed += 1
        return [[1.0 if "urgencia" in norm(t) else 0.0, 0.1, 0.2] for t in textos]


class TestRAG(unittest.TestCase):
    def setUp(self):
        self.docs = cargar_documentos()

    def test_chunking_por_seccion(self):
        chunks = chunkear(self.docs)
        self.assertEqual(len(chunks), 8)   # 4 artículos + 4 secciones del protocolo
        self.assertTrue(any("Artículo 1" in c["titulo"] for c in chunks))

    def test_busqueda_lexica_encuentra_y_rechaza(self):
        rag = RAG(self.docs, LLMFalso([]), cache_dir=None)
        ok = rag.buscar("¿Qué dice el reglamento sobre la urgencia vital?")
        self.assertEqual((ok["estado"], ok["metodo"]), ("encontrado", "lexico"))
        self.assertIn("Urgencia Vital", ok["resultados"][0]["titulo"])
        self.assertEqual(rag.buscar("¿Cuál es el menú del casino?")["estado"], "no_encontrado")
        self.assertIn("pasaporte", rag.buscar("¿qué documentos acepta el protocolo para extranjeros?")["resultados"][0]["fragmento"])

    def test_sin_documentos(self):
        self.assertEqual(RAG({}, LLMFalso([]), cache_dir=None).buscar("x")["estado"], "no_encontrado")

    def test_coseno(self):
        self.assertAlmostEqual(coseno([1, 0], [1, 0]), 1.0)
        self.assertEqual(coseno([0, 0], [1, 0]), 0.0)

    def test_embeddings_y_cache_en_disco(self):
        with tempfile.TemporaryDirectory() as d:
            emb = Embedder()
            r = RAG(self.docs, emb, cache_dir=d).buscar("urgencia")
            self.assertEqual(r["metodo"], "embeddings")
            self.assertEqual(len(os.listdir(d)), 1)
            primera = emb.llamadas_embed                    # 1 (documentos) + 1 (consulta)
            RAG(self.docs, emb, cache_dir=d).buscar("urgencia")
            self.assertEqual(emb.llamadas_embed, primera + 1)   # solo la consulta: los documentos salieron de la caché

    def test_la_cache_cambia_si_cambian_los_documentos(self):
        with tempfile.TemporaryDirectory() as d:
            a = RAG(self.docs, Embedder(), cache_dir=d)._ruta_cache()
            b = RAG({**self.docs, "nuevo.md": "# N\n\n## S\ntexto"}, Embedder(), cache_dir=d)._ruta_cache()
            self.assertNotEqual(a, b)

    def test_los_tests_no_tocan_la_cache_real(self):
        antes = set(os.listdir(CACHE_RAG_DIR)) if os.path.isdir(CACHE_RAG_DIR) else set()
        RAG(self.docs, Embedder(), cache_dir=None).buscar("urgencia")
        despues = set(os.listdir(CACHE_RAG_DIR)) if os.path.isdir(CACHE_RAG_DIR) else set()
        self.assertEqual(antes, despues)

    def test_cache_corrupta_se_regenera(self):
        with tempfile.TemporaryDirectory() as d:
            rag = RAG(self.docs, Embedder(), cache_dir=d)
            with open(rag._ruta_cache(), "w", encoding="utf-8") as f:
                f.write("{no es json")
            self.assertEqual(rag.buscar("urgencia")["metodo"], "embeddings")


if __name__ == "__main__":
    unittest.main()


def test_script_de_ingesta_muestra_el_chunking_sin_ollama(capsys):
    from scripts.ingestar import main
    assert main(["--sin-embeddings"]) == 0
    salida = capsys.readouterr().out
    assert "fragmentos:" in salida and "Tamaño de fragmento" in salida


def test_preparar_devuelve_false_sin_embeddings():
    from fakes import LLMFalso
    rag = RAG(cargar_documentos(), LLMFalso([]), cache_dir=None)
    assert rag.preparar() is False
