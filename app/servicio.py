"""Capa de servicio de la API: toda la lógica de /health, /metadata, /run y /logs, sin depender de FastAPI.
(app/main.py solo traduce HTTP <-> estas funciones; así se prueba sin levantar un servidor.)"""
import atexit
import json
import os
import threading
import time
import uuid

from harness.arranque import crear_agente
from harness.config import API_MAX_SESIONES, EMBED_MODEL, LOGS_DIR, MODEL
from harness.declarativo import cargar_declaracion
from harness.llm_client import OllamaClient
from harness.mcp_client import MCPClient
from harness.schema_validator import errores
from harness.tracing import Log
from harness.utilidades import ocultar_ruts

# Código HTTP según el 'codigo' de error que devuelve el runtime.
HTTP_POR_CODIGO = {
    "llm_no_disponible": 503,   # Ollama apagado, sin modelo o timeout
    "formato_invalido": 502,    # el LLM no produjo JSON utilizable tras los reintentos
    "salida_invalida": 502,     # el JSON no cumple output.schema.json tras los reintentos
    "tool_invalida": 502,
    "argumentos_invalidos": 502,
    "limite_pasos": 504,        # el agente no concluyó en max_pasos
    "entrada_invalida": 422,
    "error_interno": 500,
}


class Servicio:
    def __init__(self, llm=None, usar_mcp=True, log_ruta="auto", agent_dir=None):
        self.decl = cargar_declaracion(agent_dir)
        ruta = os.path.join(LOGS_DIR, "ejecucion.jsonl") if log_ruta == "auto" else log_ruta
        self.log = Log(ruta, verbose=False, version_agente=self.decl.version)
        self.llm = llm or OllamaClient()
        self.mcp = MCPClient() if usar_mcp else None
        if self.mcp:
            atexit.register(self.mcp.cerrar)
        self.agent_dir = agent_dir
        self.sesiones = {}                 # session_id -> Agente (memoria propia por sesión)
        self.lock = threading.Lock()       # un solo run a la vez: Ollama local atiende en serie
        self.inicio = time.time()

    # ---- /health
    def salud(self, profundo=False):
        info = {"status": "ok", "agente": self.decl.manifest["id"], "version": self.decl.version,
                "uptime_s": int(time.time() - self.inicio)}
        if profundo:
            ok, detalle = self.llm.disponible() if hasattr(self.llm, "disponible") else (True, "LLM sin chequeo de salud")
            info["llm"] = {"disponible": ok, "detalle": detalle}
            if not ok:
                info["status"] = "degraded"
        return info

    # ---- /metadata
    def metadata(self):
        m = self.decl.manifest
        return {
            "id": m["id"], "nombre": m["nombre"], "version": self.decl.version, "grupo": m.get("grupo"),
            "institucion": m.get("institucion"), "usuario_objetivo": m.get("usuario_objetivo"), "rol": m.get("rol"),
            "modelo": getattr(self.llm, "modelo", MODEL), "modelo_embeddings": getattr(self.llm, "modelo_embed", EMBED_MODEL),
            "entradas": m.get("entradas", []), "salidas": m["salidas"], "estados": m["estados"], "limites": m["limites"],
            "tools": [{"name": n, "description": t["description"], "origin": t["origin"], "permissions": t["permissions"],
                       "habilitada": n in m["tools"]} for n, t in self.decl.tools.items()],
            "skills": {n: s["description"] for n, s in self.decl.skills.items()},
            "ejecucion": self.decl.ejecucion,
            "endpoints": ["GET /health", "GET /metadata", "POST /run", "GET /logs"],
        }

    # ---- /run
    def _agente(self, session_id):
        ag = self.sesiones.get(session_id)
        if ag is None:
            if len(self.sesiones) >= API_MAX_SESIONES:
                self.sesiones.pop(next(iter(self.sesiones)))      # descarta la sesión más antigua
            ag = crear_agente(llm=self.llm, mcp=self.mcp, usar_mcp=False, verbose=False, log=self.log,
                              agent_dir=self.agent_dir)
            self.sesiones[session_id] = ag
        return ag

    def ejecutar(self, cuerpo):
        """Devuelve (codigo_http, json). Valida la entrada con input.schema.json antes de tocar el LLM."""
        t0 = time.time()
        errs = errores(cuerpo, self.decl.schema_entrada)
        if errs:
            return 422, {"error": "entrada_invalida", "detalles": errs}
        session_id = cuerpo.get("session_id") or uuid.uuid4().hex[:12]
        with self.lock:
            resultado = self._agente(session_id).turno(cuerpo["mensaje"], session_id=session_id)
        codigo = HTTP_POR_CODIGO.get(resultado.get("codigo"), 500) if resultado.get("tipo") == "error" else 200
        return codigo, {"run_id": resultado.get("run_id"), "session_id": session_id,
                        "latencia_ms": int((time.time() - t0) * 1000), "resultado": resultado}

    # ---- /logs
    def logs(self, run_id=None, limite=100):
        limite = max(1, min(int(limite), 1000))
        if run_id:
            eventos = self.log.eventos_de(run_id)
            if not eventos:
                return 404, {"error": "run_id_no_encontrado", "run_id": run_id}
        else:
            eventos = self.log.ultimos(limite)
        # Los RUTs se enmascaran también al servir los logs por la API.
        seguros = json.loads(ocultar_ruts(json.dumps(eventos, ensure_ascii=False, default=str)))
        return 200, {"run_id": run_id, "total": len(seguros), "eventos": seguros}
