# Arquitectura del Agente P02

## Flujo de un turno

```text
Usuario ──► Agente.turno(texto)
              │  guarda RUTs mencionados · añade a memoria · limpia estado del turno
              ▼
        ┌──► LLM (Ollama /api/chat, format=json) ◄── prompt = agent.md + tools habilitadas
        │         │                                        + catálogo de skills + contexto de sesión
        │         ▼
        │   ¿qué devolvió?
        │    ├─ JSON inválido ─────────► feedback de formato (máx. max_formato)
        │    ├─ {"tool": ...} ─► valida nombre (lista blanca del manifest) y argumentos
        │    │                    · bloquea RUTs que el usuario no escribió
        │    │                    · no re-ejecuta llamadas repetidas
        │    │                    · ejecuta (local / RAG / MCP / cargar_skill) y captura errores
        │    │                    └► RESULTADO_TOOL ──────────────────────────────┐
        │    └─ respuesta final ─► valida contra output.schema.json                 │
        │                          └► AUDITOR                                       │
        │                               ├─ rechaza ─► feedback "AUDITORÍA: ..." ────┤
        │                               │            (máx. max_correcciones; luego  │
        │                               │             se fuerza el resultado de     │
        │                               │             las reglas)                   │
        │                               ├─ veredicto no_califica/falta_informacion  │
        │                               │   sin skill cargada ─► 1 recordatorio ────┤
        │                               └─ acepta ─► registra y devuelve            │
        └───────────────────────────────────────────────────────────────────────────┘
```
Cada ejecución recibe un `run_id`; cada paso queda en `logs/ejecucion.jsonl` y en `GET /logs?run_id=...` (eventos `inicio`, `prompt`, `llm`, `tool`, `skill`, `validacion`, `auditoria`, `final`, `fin`) con los RUTs enmascarados.

## Capas de la aplicación

```text
Cliente ──HTTP──► app/main.py (FastAPI: /health /metadata /run /logs)
                      │  valida entrada (input.schema.json) · traduce errores a códigos HTTP
                      ▼
                  app/servicio.py ──► una sesión (memoria) por session_id
                      ▼
                  harness/runtime.py  (bucle del agente, run_id)
                      ├─ prompt_builder.py ◄── agent/agent.md + manifest + tools.yaml + skills
                      ├─ llm_client.py ──► Ollama
                      ├─ schema_validator.py ──► valida salida del LLM y argumentos de tools
                      ├─ tool_registry.py ◄── agent/tools.yaml ──► tools locales / RAG / MCP
                      ├─ auditor.py
                      └─ tracing.py ──► logs/ejecucion.jsonl y /logs
```

## Dos capas

| Capa | Dónde | Qué contiene | Quién la edita |
|---|---|---|---|
| Declarativa | `agent/` | prompt, política, límites, manifest, tools.yaml, skills, esquemas, ejemplos | cualquiera del grupo, sin tocar Python |
| Ejecutable | `harness/` | bucle, tools, RAG, MCP, auditor, memoria, logs | quien programa |

`harness/declarativo.py` valida la capa declarativa al iniciar y falla con un mensaje claro (`ConfiguracionError`) si algo está mal: manifest incompleto, skill con nombre distinto a su carpeta, parámetro no numérico, etc.

## Quién decide qué

| Decisión | Responsable |
|---|---|
| Qué tool llamar, en qué orden, cuándo basta | LLM |
| Estado del caso (`califica` / `no_califica` / `falta_informacion`) y su explicación | LLM, a partir de la evidencia de `evaluar_reglas` |
| Si una petición excede los límites (diagnóstico, triage, cobros, ingreso) | LLM (`fuera_de_alcance`), con segunda red en el auditor para frases que autorizan |
| Evidencia de cada regla R1..R5 | `harness/reglas.py` (determinista) |
| Que el veredicto tenga evidencia, sea coherente con las reglas y use solo RUTs del usuario | Auditor |
| Qué tools existen (tools.yaml) y cuáles ve el LLM (manifest.yaml) | declaración en `agent/` |

## Componentes

- **Reglas (`reglas.py`)**: `R1_RUT_VALIDO`, `R2_PREVISION_ACTIVA`, `R3_TRIAGE_CLINICO`, `R4_DOC_IDENTIDAD`, `R5_REGISTRO_COMPLETO`. Cada una devuelve `True`, `False` o `None` (dato ausente: no se puede afirmar). Política: R2 o R3 en `False` → `no_califica`; si no, cualquier regla distinta de `True` → `falta_informacion`; si no, `califica`.
- **RAG (`rag.py`)**: un fragmento por artículo/sección; embeddings `nomic-embed-text` con prefijos `search_document:` / `search_query:`; caché en `.cache_rag/` cuya clave incluye el contenido de los documentos y el modelo; si Ollama no entrega embeddings se usa una búsqueda léxica de respaldo. Umbral mínimo para no inventar respuestas.
- **MCP (`mcp_server.py` / `mcp_client.py`)**: JSON-RPC 2.0 por stdio. El cliente es persistente, descubre las tools con `tools/list`, lee con timeout (hilo + cola, portable a Windows) y relanza el servidor si muere.
- **Skills**: *progressive disclosure*. El prompt solo incluye nombre y descripción; el procedimiento completo entra al contexto cuando el LLM llama `cargar_skill`.
- **Memoria (`memoria.py`)**: ventana de mensajes acotada más un resumen estructurado (RUTs mencionados y casos ya verificados) que se inyecta en el prompt, para que los seguimientos funcionen aunque el historial se recorte.

## Modelos que "narran" las herramientas
Modelos pequeños (p. ej. gemma3:4b) a veces escriben "Ejecutando evaluar_reglas..." como respuesta en vez de emitir el JSON de la llamada.
El harness lo detecta (`auditor.tool_pendiente`): 1.º le indica el JSON exacto a emitir; si insiste y los argumentos son deducibles, ejecuta la tool por él
(`tool_asistida`, campo `tools_asistidas` en la salida). Si sigue narrando, tras `max_correcciones` entrega el resultado de las reglas (`corregido_por_auditor`).

## Honestidad de las respuestas (`base`)
Toda `respuesta` declara de dónde sale su contenido (`herramienta|memoria|aclaracion|saludo`). El LLM decide; el auditor solo verifica que lo declarado sea cierto
(p. ej. `herramienta` exige haber consultado una tool en el turno) y que `fuera_de_alcance` use un `limite` válido del manifest.
