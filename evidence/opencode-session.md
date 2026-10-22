# Evidencia de Sesión - Agente P02 (Grupo 6)

## Prompts Usados y Flujo de Desarrollo
1. *Fase 1:* Creación de estructura declarativa en `agent/`, datos simulados en `data/`, validadores de esquemas y tests unitarios.
2. *Fase 2:* Desarrollo de `llm_client.py` con `urllib`, arnés en `runtime.py`, loop de tools y validación contra `output.schema.json`.
3. *Fase 3:* Implementación del pipeline RAG con similitud coseno para búsqueda en reglamentos y protocolos.
4. *Fase 4:* Arquitectura MCP por stdio (`servidor_convenios.py` y `mcp_client.py`) para consulta de convenios.
5. *Fase 5:* Elaboración de documentación, README y pruebas finales.

## Decisiones Aceptadas
- Uso exclusivo de la biblioteca estándar de Python (sin frameworks externos como LangChain ni SDKs de OpenAI).
- Implementación de un arnés propio (`harness/`) para parser de salida, validación de esquemas y loop de herramientas con un máximo de 5 iteraciones.
- Servidor MCP minimalista por JSON-RPC sobre `stdio` para mantener portabilidad y simplicidad.

## Alternativas Rechazadas
- Uso de bibliotecas de terceros (`jsonschema`, `numpy`, `scipy`) para evitar dependencias externas fuera de la biblioteca estándar de Python.
- Modelos cerrados o APIs pagadas (se priorizó Ollama con modelos locales como `gemma3:4b`).

## Qué Funciona Correctamente
- Carga de agentes declarativos y validación estricta de esquemas de entrada y salida.
- Invocación de herramientas (consultar antecedentes, validar ley de urgencia, RAG documental y MCP de convenios).
- Trazas completas en terminal (`[TRAZA LLM]`, `[TRAZA TOOL]`, `[TRAZA MCP]`, `[TRAZA RAG]`, `[TRAZA SKILL]`, `[TRAZA VALIDADOR]`).
- 21 pruebas unitarias ejecutadas exitosamente con `unittest`.

## Dificultades y Soluciones
- *Dificultad:* Importación directa de `chat` que dificultaba el monkeypatching en pruebas con `FakeLLM`.
  *Solución:* Cambio a importación de módulo `import harness.llm_client` y llamada mediante `harness.llm_client.chat`.
- *Dificultad:* Codificación de caracteres en Windows al comunicar procesos por `stdio` en MCP.
  *Solución:* Configuración explícita de `encoding="utf-8", errors="replace"` en los procesos secundarios.
