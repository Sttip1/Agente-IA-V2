import json
import re

class ToolError(Exception):
    """Excepción propia para errores en la ejecución de tools."""
    pass

def extraer_json_respuesta(texto):
    """
    Extrae un objeto JSON de la respuesta del LLM, soportando bloques de código Markdown (```json ... ```)
    o texto plano que contenga un JSON. Retorna un diccionario o None si no es parseable.
    """
    if not isinstance(texto, str):
        return None

    # Limpiar espacios
    texto_limpio = texto.strip()

    # Buscar bloque de código ```json ... ``` o ``` ... ```
    patron_bloque = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", texto_limpio)
    if patron_bloque:
        contenido_bloque = patron_bloque.group(1).strip()
        try:
            return json.loads(contenido_bloque)
        except json.JSONDecodeError:
            pass

    # Intentar parsear todo el texto como JSON directamente
    try:
        return json.loads(texto_limpio)
    except json.JSONDecodeError:
        pass

    # Intentar buscar el primer '{' y el último '}'
    inicio = texto_limpio.find("{")
    fin = texto_limpio.rfind("}")
    if inicio != -1 and fin != -1 and fin > inicio:
        candidato = texto_limpio[inicio:fin+1]
        try:
            return json.loads(candidato)
        except json.JSONDecodeError:
            pass

    return None
