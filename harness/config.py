"""Configuración central: rutas del proyecto y variables de entorno."""
import os
import re

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(HARNESS_DIR)


def _cargar_dotenv(ruta):
    """Carga KEY=VALUE de un .env local (solo si la variable no está ya definida). El .env NO se versiona."""
    try:
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if linea and not linea.startswith("#") and "=" in linea:
                    k, v = linea.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("\"'"))
    except OSError:
        pass


_cargar_dotenv(os.path.join(BASE_DIR, ".env"))
AGENT_DIR = os.path.join(BASE_DIR, "agent")
DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
CACHE_RAG_DIR = os.path.join(BASE_DIR, ".cache_rag")

_host = os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434"
OLLAMA_HOST = re.sub(r"/v1/?$", "", _host.rstrip("/"))
MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "120"))

RAG_UMBRAL = float(os.getenv("RAG_UMBRAL", "0.60"))   # coseno (embeddings); calibrar con tus documentos
RAG_UMBRAL_LEXICO = 0.34                              # fracción de términos de la consulta presentes
MCP_TIMEOUT = 10.0
API_MAX_SESIONES = int(os.getenv("API_MAX_SESIONES", "200"))

# Valores por defecto de ejecución; agent/manifest.yaml puede sobrescribirlos.
EJECUCION_DEFECTO = {"max_pasos": 8, "max_formato": 3, "max_correcciones": 2, "ventana_mensajes": 30}
