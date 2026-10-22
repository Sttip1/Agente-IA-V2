# Bitácora de Desarrollo - Grupo 6 (CINF110)

## Proyecto: Agente P02 - Verificación administrativa de casos de urgencia (Clínica X)

### Bitácora de Sesiones y Fases

- **Fase 1:** Definición declarativa (`agent.md`, `manifest.yaml`, esquemas JSON, `SKILL.md`), datos simulados (`pacientes_simulados.json`, documentos institucionales) y validadores propios. Pruebas unitarias iniciales implementadas con `unittest`.
- **Fase 2:** Implementación del cliente LLM nativo (`llm_client.py`) con `urllib`, gestión de memoria conversacional y arnés ejecutable (`runtime.py`) con loop de herramientas, validación de salida y registro en `logs/ejecucion.jsonl`. Incorporación de `FakeLLM` para pruebas sin Ollama.
- **Fase 3:** Desarrollo del pipeline RAG (`rag_pipeline.py`) con chunking, embeddings, almacenamiento vectorial y similitud coseno con umbrales de confianza, conectado a la herramienta `buscar_reglamento`.
- **Fase 4:** Implementación del servidor y cliente MCP (`mcp_server/servidor_convenios.py` y `mcp_client.py`) mediante JSON-RPC sobre `stdio`, integración de la tool `consultar_convenio` y activación del skill.
- **Fase 5:** Documentación completa de arquitectura, README institucional y registro de sesión en evidencias.
