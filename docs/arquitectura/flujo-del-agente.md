# Arquitectura y Flujo del Agente P02

## Diagrama de Flujo del Runtime

```text
[ Usuario ] ---> input("Usuario: ") ---> [ harness/runtime.py ]
                                                │
                                    Carga system_prompt (agent.md)
                                                │
                                      Historial (memoria.py)
                                                │
                                      [ llm_client.py ] (Ollama /chat/completions)
                                                │
                                       Respuesta del LLM
                                                │
                       ┌────────────────────────┴────────────────────────┐
                       ▼                                                 ▼
             ¿Solicita Tool? (JSON)                              ¿Respuesta Final?
                       │                                                 │
            Ejecuta Tool correspondiente                           Valida esquema
            (Tools, RAG, MCP, Skill)                               (schema_validator.py)
                       │                                                 │
            Agrega resultado a memoria                              ┌────┴────┐
                       │                                            ▼         ▼
                       └─────────────────────────────────────> [ Válido ] [ Inválido ]
                                                                    │         │
                                                                    │      Reintenta 1 vez
                                                                    │
                                                                    ▼
                                                            Registra en ejecucion.jsonl
                                                                    │
                                                                    ▼
                                                            Muestra JSON final al Usuario
```

## Descripción de Componentes del Arnés (`harness/`)
1. **`config.py`**: Centraliza las rutas del proyecto y variables de entorno (`OLLAMA_BASE_URL`, `OLLAMA_MODEL`, etc.).
2. **`errores.py`**: Define excepciones específicas del sistema (`LLMNoDisponible`, `ToolError`, `ValidacionError`).
3. **`memoria.py`**: Mantiene la conversación y el contexto estructurado por roles (`system`, `user`, `assistant`, `tool`).
4. **`output_parser.py`**: Analiza y extrae objetos JSON de respuestas de LLM (tanto tool calls como salidas estructuradas).
5. **`schema_validator.py`**: Validador nativo de esquemas JSON contra `input.schema.json` y `output.schema.json`.
6. **`llm_client.py`**: Cliente HTTP nativo (`urllib`) para interactuar con Ollama (endpoints `/chat/completions` y `/embeddings`).
7. **`rag_pipeline.py`**: Sistema RAG documental con chunking por párrafos, generación de embeddings, almacenamiento vectorial en `vector_store.json` y búsqueda por similitud coseno.
8. **`mcp_client.py` & `mcp_server/servidor_convenios.py`**: Arquitectura cliente-servidor MCP basada en protocolo JSON-RPC sobre `stdio`.
9. **`runtime.py`**: Orquestador principal que ejecuta el ciclo interactivo, gestiona el bucle de herramientas (hasta 5 vueltas), aplica validaciones y registra trazas con prefijos estandarizados.
