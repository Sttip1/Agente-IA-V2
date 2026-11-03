"""RAG sobre data/documentos/: chunking por artículo, embeddings con caché y respaldo léxico."""
import hashlib
import json
import math
import os
import re

from harness.config import CACHE_RAG_DIR, EMBED_MODEL, RAG_UMBRAL, RAG_UMBRAL_LEXICO
from harness.errores import LLMNoDisponible
from harness.utilidades import norm

STOPWORDS = set("""que dice dicen segun indica sobre del las los una unos unas con por para como esta este esto estan
son del al de la el en y o a se su sus lo le les es hay cual cuales cuando donde quien tiene tienen puede pueden
debe deben ser mas muy reglamento documento documentos""".split())


def _tokens(texto):
    out = set()
    for w in re.findall(r"[a-z0-9]+", norm(texto)):
        if len(w) >= 3 and w not in STOPWORDS:
            out.add(w[:6])  # "raíz" aproximada: urgencia/urgencias -> urgenc
    return out


def chunkear(docs):
    """Un fragmento por sección '## ...' (con el título del documento como contexto)."""
    chunks = []
    for nombre, texto in docs.items():
        titulo_doc, titulo, buf = "", None, []

        def volcar():
            cuerpo = "\n".join(buf).strip()
            if cuerpo:
                chunks.append({"fuente": nombre, "titulo": titulo or titulo_doc,
                               "texto": f"{titulo_doc} | {titulo or ''}\n{cuerpo}".strip()})

        for linea in texto.splitlines():
            if linea.startswith("## "):
                volcar()
                titulo, buf = linea[3:].strip(), []
            elif linea.startswith("# "):
                titulo_doc = linea[2:].strip()
            else:
                buf.append(linea)
        volcar()
    return chunks


def coseno(a, b):
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return 0.0 if na == 0 or nb == 0 else sum(x * y for x, y in zip(a, b, strict=False)) / (na * nb)


class RAG:
    """cache_dir=None desactiva la caché en disco (así lo usan los tests: nunca tocan la real)."""

    def __init__(self, docs, llm, cache_dir=CACHE_RAG_DIR):
        self.docs, self.llm, self.cache_dir = docs, llm, cache_dir
        self.chunks = chunkear(docs)
        self._vectores, self._intentado = None, False

    def _ruta_cache(self):
        if not self.cache_dir:
            return None
        h = hashlib.sha256(json.dumps(self.docs, sort_keys=True).encode() + EMBED_MODEL.encode()).hexdigest()[:16]
        return os.path.join(self.cache_dir, f"rag_{h}.json")   # cambia si cambian los documentos o el modelo

    def preparar(self):
        """Ingesta: calcula (o carga de la caché) los embeddings de todos los fragmentos. True si quedaron disponibles."""
        self._preparar()
        return bool(self._vectores) and len(self._vectores) == len(self.chunks)

    def _preparar(self):
        if self._intentado:
            return
        self._intentado = True
        ruta = self._ruta_cache()
        if ruta:
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    self._vectores = json.load(f)
                    return
            except (OSError, json.JSONDecodeError):
                pass
        try:
            self._vectores = self.llm.embed(["search_document: " + c["texto"] for c in self.chunks])
        except LLMNoDisponible:
            self._vectores = None  # sin embeddings -> búsqueda léxica
            return
        if ruta:
            try:
                os.makedirs(self.cache_dir, exist_ok=True)
                with open(ruta, "w", encoding="utf-8") as f:
                    json.dump(self._vectores, f)
            except OSError:
                pass

    def buscar(self, consulta, k=3):
        if not self.chunks:
            return {"estado": "no_encontrado", "metodo": "ninguno", "mensaje": "No hay documentos institucionales cargados."}
        self._preparar()
        puntajes, metodo, umbral = None, "lexico", RAG_UMBRAL_LEXICO
        if self._vectores and len(self._vectores) == len(self.chunks):
            try:
                q = self.llm.embed(["search_query: " + consulta])[0]
                puntajes = [coseno(q, v) for v in self._vectores]
                metodo, umbral = "embeddings", RAG_UMBRAL
            except LLMNoDisponible:
                puntajes = None
        if puntajes is None:
            tq = _tokens(consulta)
            puntajes = [(len(tq & _tokens(c["texto"])) / len(tq)) if tq else 0.0 for c in self.chunks]
        orden = sorted(range(len(self.chunks)), key=lambda i: puntajes[i], reverse=True)[:k]
        if not orden or puntajes[orden[0]] < umbral:
            return {"estado": "no_encontrado", "metodo": metodo,
                    "mensaje": "No se encontró información relevante en los documentos institucionales."}
        return {"estado": "encontrado", "metodo": metodo, "resultados": [
            {"fuente": self.chunks[i]["fuente"], "titulo": self.chunks[i]["titulo"],
             "fragmento": self.chunks[i]["texto"], "score": round(puntajes[i], 3)}
            for i in orden if puntajes[i] >= umbral]}
