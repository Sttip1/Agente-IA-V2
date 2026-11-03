# Decisiones técnicas

Cada decisión indica qué se eligió, por qué y qué alternativa se consideró. Sirve de apoyo para la defensa.

## Qué decide el LLM y qué decide el código
**Decisión:** el LLM elige herramientas, estado y explicación; el código ejecuta, valida y audita.
**Por qué:** el objetivo del curso es un *agente*, no un flujo fijo. Pero un 4B de parámetros se equivoca (lo vimos en pruebas reales: narra herramientas en vez de llamarlas, o elige mal el estado). Por eso las reglas de negocio son deterministas (`harness/reglas.py`) y el auditor verifica el veredicto contra ellas: el LLM propone, el código no deja pasar lo que contradice la evidencia.
**Alternativa descartada:** que el código calculara el estado y el LLM solo lo redactara (sería un script con adorno).

## Contratos con JSON Schema (draft-07, librería `jsonschema`)
- `input.schema.json`: `mensaje` obligatorio (2–1000 caracteres), `session_id` con patrón, `additionalProperties: false`. Se valida **antes** de llamar al LLM (en el arnés y en `/run`, que responde 422).
- `output.schema.json`: tres tipos (`veredicto`, `respuesta`, `fuera_de_alcance`). Reglas condicionales con `if/then/else`: si `estado = califica` entonces `antecedentes_faltantes` debe ir vacío; si no, debe tener al menos un elemento. `respuesta` exige `base` (`herramienta|memoria|aclaracion|saludo`) para que el modelo declare de dónde sale lo que dice.
- Salida mal formada del LLM: el arnés no falla; devuelve al LLM el motivo exacto (`ERROR DE ESQUEMA ($.rut: ...)`) y reintenta hasta `max_formato` (3). Si agota los reintentos, devuelve un error controlado (`formato_invalido` / `salida_invalida`, HTTP 502).
- Ejemplos válidos e inválidos en `agent/examples/`, ejecutados por `tests/test_contratos.py`.

## Herramientas declaradas (`agent/tools.yaml`)
Cada tool declara nombre, descripción, `input_schema`, `output_schema` y `permissions` (solo lectura, fuentes de datos, `rut_must_come_from_user`). `tool_registry.py` las carga, valida los argumentos contra el schema **antes** de ejecutar y devuelve el error al LLM (`ERROR DE ARGUMENTOS`) para que corrija. Si una tool falla al ejecutarse, el error vuelve al agente como resultado (`{"error": ...}`) y el servicio sigue funcionando.
**Valor real para el caso:** `evaluar_reglas` y `consultar_registro` leen el registro del paciente; `consultar_convenio` consulta cobertura de urgencia.
**Si fuera un servidor MCP:** ya hay una tool servida por MCP (`consultar_convenio`, `origin: mcp`). Para las otras bastaría publicarlas en un servidor MCP: en `tools.yaml` pasarían de `origin: local` a `origin: mcp`, el arnés las descubre con `tools/list` y las llama con `tools/call`; la validación, los permisos y el manejo de errores no cambian. La diferencia es que el servidor es un proceso aparte (aislamiento, reutilizable por otros agentes) a costa de latencia y de manejar su ciclo de vida (timeout, reinicio).

## RAG (`harness/rag.py`, `scripts/ingestar.py`)
| Parámetro | Valor | Justificación |
|---|---|---|
| Documentos | `data/documentos/*.md` (reglamento y protocolo, 8 secciones) | normativa interna simulada de la clínica |
| Chunking | un fragmento por sección `##` (279–423 caracteres, promedio 336) | cada sección es una norma completa; cortar por tamaño fijo partiría un artículo a la mitad. Se antepone el título del documento como contexto |
| Embeddings | `nomic-embed-text` vía Ollama, con prefijos `search_document:` / `search_query:` | modelo abierto, liviano (~270 MB), corre local junto al LLM y entiende español razonablemente; los prefijos son parte de su contrato de uso |
| Almacén vectorial | JSON en `.cache_rag/` (clave = hash de documentos + modelo) y similitud coseno en memoria | con 8 fragmentos una base vectorial es innecesaria; la caché se invalida sola si cambian los documentos |
| top-k | 3 | con 8 fragmentos, 3 cubre la sección buscada y las vecinas sin saturar el contexto de un modelo de 4B (8192 tokens) |
| Umbral | coseno ≥ 0.60 (`RAG_UMBRAL`) | bajo el umbral el agente responde que no hay información en lugar de inventar. **Es un valor inicial sin calibrar con datos reales**: debe ajustarse con preguntas dentro y fuera de los documentos (`python -m scripts.ingestar --consulta "..."` muestra los puntajes) |
| Respaldo | búsqueda léxica por raíces de palabras | si Ollama no entrega embeddings, el agente sigue funcionando |
**Fuente de cada fragmento:** el resultado de `buscar_reglamento` incluye `fuente`, `titulo`, `fragmento` y `score`; el agente debe citar la fuente.
**Si la respuesta no está en los documentos:** `buscar_reglamento` devuelve `no_encontrado` y el agente lo informa (caso E12 de la evaluación).
**Cómo mejoraría la recuperación:** más documentos y calibrar el umbral con un conjunto de preguntas etiquetadas; búsqueda híbrida (léxica + vectorial); reordenar los resultados; con volúmenes mayores, PostgreSQL + pgvector (`CREATE TABLE chunks(id, fuente, titulo, texto, embedding vector(768))` y `ORDER BY embedding <=> $1 LIMIT 3`).

## Trazabilidad
Cada ejecución recibe un `run_id` y todos sus eventos lo llevan (`harness/tracing.py`): `inicio` (entrada, versión del agente, modelo, parámetros, tools), `prompt` (prompt efectivo), `llm` (respuesta y latencia), `tool` (nombre, argumentos, resultado, ms), `skill`, `validacion` / `auditoria` / `formato` (por qué se corrigió), `final` y `fin` (tipo de resultado, código de error, latencia total). `GET /logs?run_id=...` y `logs/ejecucion.jsonl` permiten reconstruir una ejecución. Los RUTs se enmascaran (`11.***.***-1`) en disco y en `/logs`. No hay credenciales que filtrar: no se usan.

## Manejo de errores
| Falla | Qué hace el arnés | HTTP |
|---|---|---|
| Entrada inválida | rechaza antes de llamar al LLM | 422 |
| Ollama apagado / sin modelo / timeout | un reintento ante timeout; mensaje claro (`ollama serve`, `ollama pull`) | 503 |
| JSON inválido del LLM | reintenta con el motivo hasta 3 veces | 502 |
| Salida fuera del schema | reintenta con el error exacto hasta 3 veces | 502 |
| Tool inexistente / argumentos inválidos | devuelve el error al LLM, hasta 3 veces | 502 |
| Tool que falla | el error vuelve como resultado; el servicio sigue | 200 |
| Servidor MCP caído | se omite con aviso; si muere en medio, se reinicia | 200 |
| Más de `max_pasos` | corta y devuelve error controlado | 504 |
| Error inesperado | se captura, se registra y se devuelve `error_interno` | 500 |

## Calidad
Ruff (`E,F,W,I,B,S`) sin errores; Bandit en CI con severidad media o mayor. Las excepciones justificadas están en el código con `# noqa` / `# nosec` y su motivo: `urlopen` usa un host validado como http/https en el constructor, y `Popen` ejecuta un comando fijo del propio proyecto.

## Uso de IA en el desarrollo
Ver `docs/guia_defensa.md`, sección «Uso responsable de IA».
