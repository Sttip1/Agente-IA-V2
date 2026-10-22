from harness.rag_pipeline import buscar_en_rag

def buscar_reglamento(consulta):
    """
    Busca información en el reglamento y protocolos de la Clínica X utilizando el pipeline RAG.
    Imprime traza [TRAZA TOOL] y [TRAZA RAG].
    """
    print(f"[TRAZA TOOL] Ejecutando buscar_reglamento con consulta='{consulta}'")
    resultado_rag = buscar_en_rag(consulta)
    return resultado_rag
