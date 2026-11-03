"""Fábrica: ensambla el agente a partir de agent/ (declarativo), data/ y los servicios."""
import atexit
import os

from harness.config import LOGS_DIR
from harness.datos import cargar_documentos, cargar_pacientes
from harness.declarativo import cargar_declaracion
from harness.llm_client import OllamaClient
from harness.mcp_client import MCPClient
from harness.rag import RAG
from harness.runtime import Agente
from harness.tool_registry import Herramientas
from harness.tracing import Log


def crear_agente(llm=None, usar_mcp=True, verbose=True, log_ruta="auto", agent_dir=None, log=None, mcp=None):
    decl = cargar_declaracion(agent_dir)          # lanza ConfiguracionError si falta algo
    llm = llm or OllamaClient()
    if mcp is None and usar_mcp:
        mcp = MCPClient()
        atexit.register(mcp.cerrar)
    docs = cargar_documentos()
    herr = Herramientas(cargar_pacientes(), RAG(docs, llm), mcp, skills=decl.skills,
                        permitidas=decl.manifest["tools"], especificaciones=decl.tools)
    avisos = list(herr.avisos)
    if not docs:
        avisos.append("No hay documentos en data/documentos/: buscar_reglamento no encontrará nada.")
    ruta = os.path.join(LOGS_DIR, "ejecucion.jsonl") if log_ruta == "auto" else log_ruta
    for a in avisos:
        print("  [AVISO]", a)
    return Agente(llm, herr, decl, log or Log(ruta, verbose=verbose, version_agente=decl.version))
