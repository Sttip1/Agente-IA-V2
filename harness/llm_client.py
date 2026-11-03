"""Cliente de Ollama (/api/chat y /api/embed) usando solo urllib."""
import json
import urllib.error
import urllib.request

from harness.config import EMBED_MODEL, MODEL, OLLAMA_HOST, TIMEOUT
from harness.errores import ConfiguracionError, LLMNoDisponible


class OllamaClient:
    def __init__(self, host=OLLAMA_HOST, modelo=MODEL, modelo_embed=EMBED_MODEL, timeout=TIMEOUT):
        if not str(host).startswith(("http://", "https://")):
            raise ConfiguracionError(f"OLLAMA_HOST debe empezar con http:// o https:// (recibido: {host!r})")
        self.host, self.modelo, self.modelo_embed, self.timeout = host, modelo, modelo_embed, timeout

    def _post(self, ruta, payload, reintentos=1):
        req = urllib.request.Request(self.host + ruta, data=json.dumps(payload).encode("utf-8"),  # noqa: S310  # nosec B310
                                     headers={"Content-Type": "application/json"}, method="POST")
        for intento in range(reintentos + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310  # nosec B310 (host http/https validado en __init__)
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                cuerpo = e.read().decode("utf-8", errors="ignore")
                # Modelo faltante: {"error": "model \"x\" not found, try pulling it first"}.
                # Endpoint inexistente (Ollama antiguo): "404 page not found" -> NO menciona 'model'.
                if e.code == 404 and "model" in cuerpo.lower():
                    raise LLMNoDisponible(f"Modelo no descargado en Ollama. Ejecuta: ollama pull {payload.get('model')}") from e
                raise LLMNoDisponible(f"HTTP {e.code} desde Ollama ({ruta}): {cuerpo[:200]}") from e
            except (TimeoutError, urllib.error.URLError, ConnectionError, OSError) as e:
                es_timeout = isinstance(e, TimeoutError) or "timed out" in str(e)
                if es_timeout and intento < reintentos:
                    continue
                if es_timeout:
                    raise LLMNoDisponible(f"Timeout ({self.timeout}s) esperando a Ollama; el modelo es lento o está cargando.") from e
                raise LLMNoDisponible(f"No se pudo conectar con Ollama en {self.host}. ¿Está en ejecución (ollama serve)? Detalle: {e}") from e
            except json.JSONDecodeError as e:
                raise LLMNoDisponible(f"Respuesta no válida de Ollama: {e}") from e

    def disponible(self, timeout=3.0):
        """(ok, detalle): comprueba que Ollama responda y tenga el modelo de chat descargado."""
        try:
            with urllib.request.urlopen(self.host + "/api/tags", timeout=timeout) as resp:  # noqa: S310  # nosec B310 (host http/https validado en __init__)
                modelos = [m.get("name", "") for m in json.loads(resp.read().decode("utf-8")).get("models", [])]
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            return False, f"Ollama no responde en {self.host}: {e}"
        if not any(m == self.modelo or m.split(":")[0] == self.modelo.split(":")[0] and ":" not in self.modelo for m in modelos):
            return False, f"Ollama responde pero falta el modelo '{self.modelo}' (ollama pull {self.modelo})"
        return True, f"modelo {self.modelo} disponible"

    def chat(self, mensajes):
        data = self._post("/api/chat", {
            "model": self.modelo, "messages": mensajes, "stream": False, "format": "json",
            "options": {"temperature": 0, "num_ctx": 8192},
        })
        try:
            return data["message"]["content"]
        except (KeyError, TypeError) as e:
            raise LLMNoDisponible(f"Respuesta inesperada de Ollama: {str(data)[:200]}") from e

    def embed(self, textos):
        try:
            data = self._post("/api/embed", {"model": self.modelo_embed, "input": textos})
            return data["embeddings"]
        except LLMNoDisponible as e:
            if "HTTP 404" not in str(e):
                raise
        salida = []  # Ollama antiguo: endpoint /api/embeddings, un texto por llamada
        for t in textos:
            salida.append(self._post("/api/embeddings", {"model": self.modelo_embed, "prompt": t})["embedding"])
        return salida
