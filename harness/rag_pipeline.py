import os
import json
import math
from harness.config import DATA_DIR
import harness.llm_client

VECTOR_STORE_PATH = os.path.join(DATA_DIR, "vector_store.json")

def calcular_norma(vec):
    return math.sqrt(sum(x * x for x in vec))

def similitud_coseno(vec1, vec2):
    """Calcula la similitud coseno entre dos vectores."""
    norm1 = calcular_norma(vec1)
    norm2 = calcular_norma(vec2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    producto_punto = sum(a * b for a, b in zip(vec1, vec2))
    return producto_punto / (norm1 * norm2)

def inicializar_vector_store():
    """
    Lee los documentos .md en data/documentos/, realiza chunking uniendo títulos con sus párrafos,
    antepone 'search_document: ', genera embeddings y los guarda en data/vector_store.json.
    """
    ruta_docs = os.path.join(DATA_DIR, "documentos")
    if not os.path.exists(ruta_docs):
        return []

    chunks = []
    fuentes = []

    for archivo in os.listdir(ruta_docs):
        if archivo.endswith(".md"):
            ruta_archivo = os.path.join(ruta_docs, archivo)
            try:
                with open(ruta_archivo, "r", encoding="utf-8") as f:
                    contenido = f.read()
                    parrafos_brutos = [p.strip() for p in contenido.split("\n\n") if p.strip()]
                    # Unir títulos (# o ##) con el párrafo siguiente
                    i = 0
                    while i < len(parrafos_brutos):
                        p = parrafos_brutos[i]
                        if (p.startswith("#") or p.startswith("##")) and i + 1 < len(parrafos_brutos):
                            chunks.append(f"{p}\n\n{parrafos_brutos[i+1]}")
                            fuentes.append(archivo)
                            i += 2
                        else:
                            chunks.append(p)
                            fuentes.append(archivo)
                            i += 1
            except Exception as e:
                print(f"[ERROR RAG] No se pudo leer {archivo}: {str(e)}")

    if not chunks:
        return []

    # Anteponer 'search_document: ' para nomic-embed-text
    textos_para_embed = [f"search_document: {chunk}" for chunk in chunks]

    print(f"[TRAZA RAG] Generando embeddings con prefijo 'search_document: ' para {len(chunks)} fragmentos...")
    embeddings = harness.llm_client.embed(textos_para_embed)

    vector_store = []
    for i, chunk in enumerate(chunks):
        vector_store.append({
            "fuente": fuentes[i],
            "texto": chunk,
            "embedding": embeddings[i] if i < len(embeddings) else [0.0] * 768
        })

    # Guardar vector store
    try:
        with open(VECTOR_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(vector_store, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ERROR RAG] No se pudo guardar vector_store.json: {str(e)}")

    return vector_store

def cargar_o_crear_vector_store():
    if os.path.exists(VECTOR_STORE_PATH):
        try:
            with open(VECTOR_STORE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return inicializar_vector_store()

def buscar_en_rag(consulta, top_k=3, umbral_minimo=0.65):
    """
    Busca fragmentos relevantes en el RAG utilizando similitud coseno con prefijo 'search_query: '.
    Imprime fragmentos con fuente y score ([TRAZA RAG]).
    Si el score máximo es menor que umbral_minimo, retorna no_encontrado.
    """
    print(f"[TRAZA RAG] Buscando en RAG consulta='{consulta}' (top_k={top_k})")
    vector_store = cargar_o_crear_vector_store()
    if not vector_store:
        return {
            "estado": "no_encontrado",
            "mensaje": "No encontrado en los documentos institucionales de la Clínica X."
        }

    consulta_con_prefijo = f"search_query: {consulta}"
    embedding_consulta = harness.llm_client.embed([consulta_con_prefijo])[0]

    resultados_con_score = []
    for item in vector_store:
        score = similitud_coseno(embedding_consulta, item["embedding"])
        resultados_con_score.append({
            "fuente": item["fuente"],
            "fragmento": item["texto"],
            "score": score
        })

    # Ordenar por score descendente
    resultados_con_score.sort(key=lambda x: x["score"], reverse=True)
    top_resultados = resultados_con_score[:top_k]

    # Imprimir fragmentos con fuente y score
    print("[TRAZA RAG] Resultados recuperados:")
    for res in top_resultados:
        print(f"  - Fuente: {res['fuente']} | Score: {res['score']:.4f}")
        print(f"    Fragmento: {res['fragmento'][:150]}...")

    # Verificar umbral mínimo (calibrado a 0.60 para nomic-embed-text)
    if not top_resultados or top_resultados[0]["score"] < umbral_minimo:
        print(f"[TRAZA RAG] Score máximo ({top_resultados[0]['score'] if top_resultados else 0.0:.4f}) por debajo del umbral ({umbral_minimo}).")
        return {
            "estado": "no_encontrado",
            "mensaje": "No encontrado en los documentos institucionales de la Clínica X."
        }

    return {
        "estado": "encontrado",
        "resultados": [
            {
                "fuente": r["fuente"],
                "fragmento": r["fragmento"],
                "score": round(r["score"], 4)
            } for r in top_resultados
        ]
    }
