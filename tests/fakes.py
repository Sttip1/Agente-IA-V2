"""Utilidades compartidas por los tests: LLM simulado, servidor Ollama falso y fábrica de agentes."""
import http.server
import json
import os
import sys
import threading

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from harness.datos import cargar_documentos, cargar_pacientes  # noqa: E402
from harness.declarativo import cargar_declaracion  # noqa: E402
from harness.errores import LLMNoDisponible  # noqa: E402
from harness.rag import RAG  # noqa: E402
from harness.reglas import REGLAS  # noqa: E402
from harness.runtime import Agente  # noqa: E402
from harness.tool_registry import Herramientas  # noqa: E402
from harness.tracing import Log  # noqa: E402

SKILL_FALTANTES = "clasificar-antecedente-faltante"


class LLMFalso:
    """Devuelve respuestas de un guion y registra los mensajes que recibió en cada llamada."""

    def __init__(self, guion):
        self.guion, self.llamadas = list(guion), []

    def chat(self, mensajes):
        self.llamadas.append(mensajes)
        if not self.guion:
            raise AssertionError("El agente pidió más respuestas del LLM de las previstas en el guion")
        x = self.guion.pop(0)
        if isinstance(x, Exception):
            raise x
        return x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)

    def embed(self, textos):
        raise LLMNoDisponible("sin embeddings en test")


def T(_tool, **a):
    """Llamada a tool (el primer parámetro no se llama 'nombre' porque cargar_skill usa ese argumento)."""
    return {"tool": _tool, "args": a}


SK = T("cargar_skill", nombre=SKILL_FALTANTES)


def V(rut, estado, faltantes=(), reglas=None, expl="Explicación de prueba con evidencia suficiente."):
    """Veredicto final."""
    return {"tipo": "veredicto", "rut": rut, "estado": estado, "explicacion": expl,
            "antecedentes_faltantes": list(faltantes), "reglas_aplicadas": reglas or list(REGLAS)}


def agente_con(guion, mcp=None, permitidas="manifest", log=None):
    """Agente real (agent/ + data/ reales) con LLM simulado y sin caché RAG en disco."""
    decl = cargar_declaracion()
    llm = LLMFalso(guion)
    perm = decl.manifest["tools"] if permitidas == "manifest" else permitidas
    herr = Herramientas(cargar_pacientes(), RAG(cargar_documentos(), llm, cache_dir=None), mcp,
                        skills=decl.skills, permitidas=perm, especificaciones=decl.tools)
    return Agente(llm, herr, decl, log or Log(None, verbose=False)), llm


class OllamaFalso:
    """Servidor HTTP local que imita a Ollama. rutas: {path: (codigo, objeto|texto, retardo_seg)}"""

    def __init__(self, rutas):
        self.capturas = []
        capturas, tabla = self.capturas, rutas

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                capturas.append((self.path, body))
                codigo, obj, retardo = tabla.get(self.path, (404, "404 page not found", 0))
                if retardo:
                    import time
                    time.sleep(retardo)
                datos = (obj if isinstance(obj, str) else json.dumps(obj)).encode()
                try:
                    self.send_response(codigo)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(datos)))
                    self.end_headers()
                    self.wfile.write(datos)
                except OSError:
                    pass

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def cerrar(self):
        self.srv.shutdown()
        self.srv.server_close()
