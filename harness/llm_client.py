import json, os, urllib.error, urllib.request
BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/")
API_KEY = os.getenv("OLLAMA_API_KEY", "").strip()
MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")
TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

from harness.errores import LLMNoDisponible

def chat(mensajes):
    """
    Envía una lista de mensajes al LLM de Ollama vía chat/completions usando urllib.
    Maneja errores con mensajes claros (Ollama apagado, modelo no descargado, timeout).
    Imprime traza [TRAZA LLM].
    """
    url = f"{BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json"
    }
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
        
    payload = {
        "model": MODEL,
        "messages": mensajes,
        "temperature": 0.1
    }
    
    print(f"[TRAZA LLM] Llamando a Ollama model={MODEL} url={url}")
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            resultado_json = json.loads(response.read().decode("utf-8"))
            content = resultado_json["choices"][0]["message"]["content"]
            return content
    except urllib.error.URLError as e:
        mensaje_err = str(e.reason) if hasattr(e, "reason") else str(e)
        if "Connection refused" in mensaje_err or "getaddrinfo failed" in mensaje_err:
            raise LLMNoDisponible(f"Ollama está apagado o no accesible en {BASE_URL}. Asegúrate de iniciar Ollama.")
        raise LLMNoDisponible(f"Error de conexión con Ollama: {mensaje_err}")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        if e.code == 404 or "model" in error_body.lower():
            raise LLMNoDisponible(f"El modelo '{MODEL}' no está descargado en Ollama. Descárgalo con 'ollama pull {MODEL}'. Detalle: {error_body}")
        raise LLMNoDisponible(f"Error HTTP {e.code} de Ollama: {error_body}")
    except TimeoutError:
        raise LLMNoDisponible(f"Timeout al conectar con Ollama ({TIMEOUT_SECONDS}s). El modelo tardó demasiado en responder.")
    except Exception as e:
        raise LLMNoDisponible(f"Error inesperado al comunicarse con Ollama: {str(e)}")

def embed(textos):
    """
    Obtiene los embeddings para una lista de textos usando el endpoint nativo /api/embeddings de Ollama.
    """
    base_host = BASE_URL.replace("/v1", "") if BASE_URL.endswith("/v1") else BASE_URL
    url = f"{base_host}/api/embeddings"
    headers = {
        "Content-Type": "application/json"
    }
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
        
    embeddings_resultado = []
    for texto in textos:
        if not texto or not isinstance(texto, str) or not texto.strip():
            continue
            
        payload = {
            "model": EMBED_MODEL,
            "prompt": texto.strip()
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
                res_json = json.loads(response.read().decode("utf-8"))
                emb = res_json.get("embedding", [])
                embeddings_resultado.append(emb)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="ignore")
            raise LLMNoDisponible(f"Error HTTP {e.code} en embeddings con modelo {EMBED_MODEL}: {error_body}")
        except urllib.error.URLError as e:
            mensaje_err = str(e.reason) if hasattr(e, "reason") else str(e)
            raise LLMNoDisponible(f"Error de conexión en embeddings con Ollama: {mensaje_err}")
        except Exception as e:
            raise LLMNoDisponible(f"Error al obtener embeddings con modelo {EMBED_MODEL}: {str(e)}")
            
    return embeddings_resultado
