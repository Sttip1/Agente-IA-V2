class MemoriaConversacional:
    """Gestiona el historial de mensajes para la interacción con el LLM."""
    
    def __init__(self, system_prompt=None):
        self.mensajes = []
        if system_prompt:
            self.mensajes.append({
                "role": "system",
                "content": system_prompt
            })
            
    def agregar_usuario(self, contenido):
        self.mensajes.append({
            "role": "user",
            "content": contenido
        })
        
    def agregar_asistente(self, contenido):
        self.mensajes.append({
            "role": "assistant",
            "content": contenido
        })
        
    def agregar_tool(self, nombre_tool, resultado):
        self.mensajes.append({
            "role": "tool",
            "name": nombre_tool,
            "content": str(resultado)
        })
        
    def obtener_historial(self):
        return self.mensajes
        
    def limpiar(self, system_prompt=None):
        self.mensajes = []
        if system_prompt:
            self.mensajes.append({
                "role": "system",
                "content": system_prompt
            })
