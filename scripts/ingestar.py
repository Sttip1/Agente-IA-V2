"""Ingesta del RAG: carga data/documentos/, los divide en fragmentos, calcula los embeddings y los guarda en el almacén vectorial
(.cache_rag/, un JSON por combinación documentos+modelo). Es reproducible: mismos documentos y modelo => mismo almacén.

Uso:  python -m scripts.ingestar [--sin-embeddings] [--consulta "texto"]
  --sin-embeddings   solo muestra el chunking (no necesita Ollama)
  --consulta         después de ingerir, ejecuta una búsqueda de prueba y muestra los fragmentos y puntajes"""
import argparse
import json
import sys

from harness.config import CACHE_RAG_DIR, EMBED_MODEL, RAG_UMBRAL
from harness.datos import cargar_documentos
from harness.errores import LLMNoDisponible
from harness.llm_client import OllamaClient
from harness.rag import RAG, chunkear


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ingesta de documentos para el RAG")
    ap.add_argument("--sin-embeddings", action="store_true")
    ap.add_argument("--consulta")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    docs = cargar_documentos()
    if not docs:
        print("No hay documentos en data/documentos/.")
        return 1
    chunks = chunkear(docs)
    print(f"Documentos: {len(docs)} | fragmentos: {len(chunks)} (uno por sección '## ')")
    for c in chunks:
        print(f"  - {c['fuente']} | {c['titulo']} | {len(c['texto'])} caracteres")
    largos = [len(c["texto"]) for c in chunks]
    print(f"Tamaño de fragmento: mín {min(largos)}, máx {max(largos)}, promedio {sum(largos) // len(largos)} caracteres")
    if a.sin_embeddings:
        return 0
    rag = RAG(docs, OllamaClient(), cache_dir=CACHE_RAG_DIR)
    try:
        ok = rag.preparar()
    except LLMNoDisponible as e:
        print(f"No se pudo ingerir: {e}")
        return 1
    print(f"Embeddings ({EMBED_MODEL}): {'listos en ' + CACHE_RAG_DIR if ok else 'NO disponibles; el RAG usará búsqueda léxica'}")
    if a.consulta:
        print(f"Consulta de prueba (umbral {RAG_UMBRAL}):")
        print(json.dumps(rag.buscar(a.consulta), ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
