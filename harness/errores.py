"""Excepciones propias del arnés."""


class LLMNoDisponible(Exception):
    """Ollama apagado, sin el modelo descargado o con timeout."""


class ToolError(Exception):
    """Error al ejecutar una tool (incluye fallas del servidor MCP)."""


class ConfiguracionError(Exception):
    """Archivo declarativo o de datos ausente o mal formado (agent/, data/)."""
