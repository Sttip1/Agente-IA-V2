class LLMNoDisponible(Exception):
    """Excepción lanzada cuando Ollama no responde, da timeout o el modelo no está disponible."""
    pass

class ToolError(Exception):
    """Excepción lanzada cuando ocurre un error ejecutando una herramienta (tool)."""
    pass

class ValidacionError(Exception):
    """Excepción lanzada cuando un dato o salida no cumple con los esquemas JSON definidos."""
    pass
