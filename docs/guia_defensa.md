# Guía de repaso y defensa - Agente P02

Para estudiar antes de la demostración. Está pensada para que **cada integrante** pueda explicar **cualquier parte** (el docente elige a quién le pregunta qué) y mostrar la respuesta en el código o en la ejecución.

Orden: 1) conceptos · 2) mapa de archivos · 3) flujo de una consulta · 4) las preguntas de la rúbrica con respuesta lista · 5) cambios en vivo · 6) demo paso a paso · 7) uso de IA y contribución · 8) lo que aún falta.

---

## 1. Conceptos (qué es y qué hace en ESTE proyecto)

### LLM (modelo de lenguaje)
**Qué es:** un modelo que, dado un texto, genera el texto más probable que sigue. No tiene acceso a nada fuera de lo que se le escribe; no ejecuta código ni consulta bases de datos.
**Aquí:** `gemma3:4b` corriendo local con **Ollama** (`harness/llm_client.py`, `temperature: 0` para que sea lo más determinista posible, `format: json` para pedirle JSON). Es el que **decide**: qué herramienta usar, qué estado dar y cómo explicarlo.

### Agente
**Qué es:** un LLM metido en un **bucle**: piensa → pide una acción (herramienta) → recibe el resultado → decide el siguiente paso, hasta tener una respuesta final. Lo que lo diferencia de un chatbot es que **actúa** y **decide el camino**.
**Aquí:** `harness/runtime.py`, método `_turno`: el bucle `for paso in range(1, max_pasos + 1)`.

### Harness / arnés
**Qué es:** todo el código **alrededor** del LLM: arma el prompt, llama al modelo, ejecuta las herramientas que el modelo pide, valida lo que devuelve, guarda logs, maneja errores. El LLM piensa; el arnés ejecuta y protege.
**Aquí:** la carpeta `harness/` (y `app/` para exponerlo por HTTP). Regla para explicarlo: *«el LLM propone, el arnés dispone»*.

### Prompt (y prompt del sistema)
**Qué es:** el texto que recibe el LLM. El **prompt del sistema** son las instrucciones permanentes (quién eres, qué puedes y no puedes hacer).
**Aquí:** lo arma `harness/prompt_builder.py` juntando: `agent/agent.md` + herramientas habilitadas (de `tools.yaml`, filtradas por `manifest.yaml`) + catálogo de skills (solo nombre y descripción) + valores válidos + contexto de sesión (RUTs y casos ya vistos). Se ve completo en el evento `prompt` de los logs.

### Definición declarativa (`agent/`)
**Qué es:** describir el agente con **archivos de configuración** en vez de escribirlo en Python. Cambiar el comportamiento = editar un archivo, no programar.
- `agent.md`: propósito, responsabilidades, rol en el ecosistema, límites, criterios de éxito, política de estados.
- `manifest.yaml`: id, versión, **lista blanca** de tools, skills, límites, parámetros (`max_pasos`, `max_formato`, `max_correcciones`, `ventana_mensajes`).
- `tools.yaml`: cada herramienta con su descripción, schema de entrada/salida y permisos.
- `input.schema.json` / `output.schema.json`: contratos.
**Cómo se carga:** `harness/declarativo.py` (`cargar_declaracion`) lee todo al iniciar y **falla con un mensaje claro** si algo está mal o es incoherente (por ejemplo, una tool permitida en el manifest pero no declarada en `tools.yaml`).

### JSON Schema (contratos)
**Qué es:** un estándar para describir la forma que debe tener un JSON: tipos, campos obligatorios (`required`), valores permitidos (`enum`), largos, patrones, reglas condicionales (`if/then/else`).
**Aquí:** `input.schema.json` valida lo que **entra**; `output.schema.json` valida lo que el LLM **responde**; cada tool tiene su `input_schema` para sus argumentos. Un solo validador: `harness/schema_validator.py` (librería `jsonschema`, mensajes de error en español).
**Regla condicional del proyecto:** si `estado` es `califica`, `antecedentes_faltantes` debe ir vacío; si no, debe traer al menos uno.
**Diferencia clave (pregunta típica):** el *schema* valida la **forma** (tipos, campos, valores). El *código* (auditor) valida el **sentido** (que el estado coincida con la evidencia de las reglas, que no se invente un RUT).

### Tool (herramienta)
**Qué es:** una función que el LLM puede pedir ejecutar. El LLM **no la ejecuta**: escribe un JSON `{"tool": "...", "args": {...}}` y el arnés la corre y le devuelve el resultado.
**Aquí:** `consultar_registro`, `evaluar_reglas`, `buscar_reglamento`, `consultar_convenio` (MCP), `cargar_skill`. Registro: `harness/tool_registry.py`. Gemma3 no tiene "function calling" nativo en Ollama, por eso el protocolo es un JSON escrito por el modelo.
**Importante:** las tools entregan **hechos**, no el veredicto. `evaluar_reglas` devuelve la evidencia de R1 a R5; el estado lo decide el LLM y lo verifica el auditor.

### Skill
**Qué es:** un procedimiento por escrito ("cómo hacer X paso a paso") que se carga **solo cuando hace falta**, para no gastar contexto. Se llama *progressive disclosure*: el prompt solo trae nombre y descripción; el contenido completo entra cuando el LLM llama `cargar_skill`.
**Aquí:** `agent/skills/*/SKILL.md` (con frontmatter `name` y `description`). La skill `clasificar-antecedente-faltante` explica cómo traducir una regla fallida a un antecedente concreto. El manifest exige cargarla antes de un veredicto no-califica (`skill_para_faltantes`), con un solo recordatorio.

### MCP (Model Context Protocol)
**Qué es:** un protocolo estándar para que un agente use herramientas **servidas por otro programa** (JSON-RPC 2.0, aquí por stdio). Es como un "USB" de herramientas: cualquier agente que hable MCP puede usar cualquier servidor MCP.
**Aquí:** `harness/mcp_server.py` (servidor de convenios, proceso aparte) y `harness/mcp_client.py` (el arnés). Mensajes: `initialize` → `tools/list` (descubre qué tools hay) → `tools/call` (ejecuta). El cliente tiene timeout y se reinicia si el servidor muere. En `tools.yaml`, `consultar_convenio` tiene `origin: mcp`.
**Diferencia con una tool local:** la local es una función dentro del mismo programa; la MCP vive en otro proceso (aislamiento y reutilización, a cambio de latencia y de gestionar su ciclo de vida).

### RAG (Retrieval-Augmented Generation)
**Qué es:** en vez de que el LLM responda de memoria (e invente), primero **se buscan fragmentos relevantes** en tus documentos y se le entregan para que responda **con base en ellos**.
**Pasos y dónde están:**
1. **Carga** de documentos: `harness/datos.py` → `data/documentos/*.md`.
2. **Chunking** (partir en fragmentos): `rag.chunkear`, un fragmento por sección `##` (8 fragmentos de 279 a 423 caracteres).
3. **Embeddings**: cada fragmento se convierte en un vector de números que representa su significado (`nomic-embed-text` vía Ollama).
4. **Almacenamiento**: JSON en `.cache_rag/` (la clave incluye el contenido de los documentos y el modelo, así que se regenera sola).
5. **Recuperación**: la pregunta también se convierte en vector; se compara con **similitud coseno** y se toman los **top-k = 3** mejores.
6. **Umbral** (0.60): si el mejor puntaje es menor, devuelve `no_encontrado` y el agente **admite que no sabe**.
7. **Respaldo léxico**: si no hay embeddings, busca por palabras.
**Script de ingesta:** `python -m scripts.ingestar` (muestra el chunking y calcula los embeddings; `--consulta "..."` prueba una búsqueda con sus puntajes).

### Memoria
**Aquí:** `harness/memoria.py`. Ventana de los últimos 30 mensajes + un resumen estructurado (RUTs mencionados y casos verificados) que se reinyecta en el prompt, para que "¿y qué le falta?" funcione aunque el historial se recorte. En la API hay una memoria por `session_id`.

### Auditor
**Qué es:** código que **verifica** (no decide) lo que el LLM respondió y, si algo no cuadra, le devuelve el motivo para que corrija. Reglas principales (`harness/auditor.py`): el veredicto exige haber llamado a `evaluar_reglas` con ese RUT; el estado debe coincidir con la política aplicada a la evidencia; "califica" no puede traer faltantes; las reglas citadas deben existir; no se pueden autorizar ingresos ni cobros; una `respuesta` que dice `base: herramienta` debe haber usado una herramienta; un `fuera_de_alcance` debe usar un límite válido. Si tras `max_correcciones` (2) el LLM sigue contradiciendo, entrega el resultado de las reglas marcado `corregido_por_auditor`.
**Evidencia, no frases copiadas:** si el estado no es "califica", los `antecedentes_faltantes` deben corresponder a los que devolvió `evaluar_reglas` (se comparan por palabras clave, así que una paráfrasis razonable pasa). Esto se agregó porque en una prueba real gemma3:4b copió el ejemplo de la skill ("previsión inactiva") para un RUT que ni existía.
**Tool narrada:** modelos pequeños a veces escriben "Ejecutando evaluar_reglas..." en vez de emitir el JSON. El arnés lo detecta (`tool_pendiente`), le dice el JSON exacto que debe enviar y, si insiste, ejecuta la tool por él (queda marcado como `tool_asistida`).

### Trazabilidad
**Aquí:** `harness/tracing.py`. Cada ejecución tiene un **`run_id`** y todos sus eventos lo llevan. `GET /logs?run_id=...` o `logs/ejecucion.jsonl` permiten reconstruir qué pasó, paso a paso. Los RUTs se enmascaran.

### API (FastAPI)
**Qué es:** el arnés publicado por HTTP. `app/main.py` solo traduce HTTP ↔ `app/servicio.py`. Endpoints: `/health`, `/metadata`, `/run`, `/logs`. Códigos: 200 / 422 (entrada inválida) / 404 / 502 (LLM no produjo salida válida) / 503 (Ollama caído) / 504 (agotó los pasos).

### Pruebas, evaluación y calidad
- **pytest** (`tests/`): verifica que el **código** funcione (contratos, arnés, tools, API, trazabilidad, RAG, MCP). Son rápidas y no necesitan Ollama (usan un LLM simulado).
- **Evaluación** (`evals/`): mide qué tan bien se **comporta el agente** ante preguntas realistas, con criterios explícitos por caso. En modo `mock` evalúa el arnés (determinista, para CI); en modo `live` evalúa el modelo real. Diferencia con pytest: pytest dice "el código hace lo que programé"; la evaluación dice "el agente responde bien a lo que un usuario preguntaría".
- **Ruff**: revisa estilo y errores probables (y reglas de seguridad `S`). **Bandit**: busca patrones inseguros en Python. **GitHub Actions** (`.github/workflows/ci.yml`): ejecuta todo eso en cada push y deja los reportes.

---

## 2. Mapa: qué hay en cada archivo

| Quiero explicar... | Archivos |
|---|---|
| Qué es el agente y sus límites | `agent/agent.md`, `agent/manifest.yaml` |
| Qué herramientas hay y sus permisos | `agent/tools.yaml`, `harness/tool_registry.py` |
| Contratos | `agent/input.schema.json`, `agent/output.schema.json`, `agent/examples/`, `harness/schema_validator.py` |
| Cómo se arma el prompt | `harness/prompt_builder.py` |
| El bucle del agente | `harness/runtime.py` (`turno` → `_turno`) |
| Hablar con el modelo | `harness/llm_client.py` |
| Verificar al LLM | `harness/auditor.py` |
| Reglas de negocio | `harness/reglas.py` (R1–R5) |
| RAG | `harness/rag.py`, `scripts/ingestar.py`, `data/documentos/` |
| MCP | `harness/mcp_server.py`, `harness/mcp_client.py` |
| Skills | `agent/skills/*/SKILL.md`, `tool_registry.cargar_skill` |
| Logs | `harness/tracing.py`, `logs/ejecucion.jsonl` |
| API | `app/main.py`, `app/servicio.py` |
| Pruebas | `tests/`, `evals/cases.jsonl`, `evals/evaluator.py` |
| Calidad y CI | `pyproject.toml`, `.github/workflows/ci.yml`, `reports/` |
| Decisiones | `docs/decisiones.md`, `docs/arquitectura.md` |

---

## 3. Qué pasa cuando llega una consulta (con `run_id`)

Ejemplo: `POST /run {"mensaje": "Dime si el paciente 11111111-1 es apto"}`

1. `app/main.py` recibe el JSON → `Servicio.ejecutar` lo valida con `input.schema.json` (si falla: **422**, el LLM ni se entera).
2. Se busca o crea el agente de esa sesión (memoria propia).
3. `runtime.turno` crea el **`run_id`** y registra `inicio` (entrada, versión del agente, modelo, parámetros).
4. `_turno` guarda el RUT mencionado, arma los mensajes (prompt del sistema + historial) y registra `prompt`.
5. **LLM** (paso 1) → `{"tool":"evaluar_reglas","args":{"rut":"11111111-1"}}`.
6. **Arnés**: ¿la tool existe y está permitida? ¿los argumentos cumplen su `input_schema`? ¿el RUT lo escribió el usuario? Si todo bien, la ejecuta (`evento tool`) y le devuelve `RESULTADO_TOOL ...` con la evidencia R1–R5.
7. **LLM** (paso 2) → pide `cargar_skill` (si el estado no es "califica").
8. **LLM** (paso 3) → responde un `veredicto` JSON.
9. **Arnés**: valida contra `output.schema.json` (si falla, devuelve `ERROR DE ESQUEMA` y reintenta) → pasa por el **auditor** (si no cuadra, devuelve `AUDITORÍA: ...`) → acepta.
10. Se registra `final` y `fin` (latencia) y se devuelve el resultado con `run_id`. `GET /logs?run_id=...` muestra los eventos.

**Quién hace qué:** *LLM* → elegir herramienta, orden, estado, explicación, rechazar lo fuera de alcance. *Arnés* → prompt, ejecutar tools, validar schemas, auditar, memoria, logs, límites de pasos y errores. *Reglas (`reglas.py`)* → la evidencia de cada R1–R5, determinista.

---

## 4. Las preguntas de la rúbrica, con respuesta lista

> Siempre: responde corto, y **muéstralo** (archivo o comando). Si no sabes algo, dilo y explica cómo lo averiguarías.

**1. Si cambias una regla en `agent.md`, ¿qué cambia sin tocar Python? ¿Dónde se lee?**
`agent.md` es el prompt del sistema. `cargar_declaracion` lo lee al iniciar; `prompt_builder.construir_prompt` lo pone al inicio del mensaje de sistema que ve el LLM. Si cambio, por ejemplo, un límite, al reiniciar el agente se comporta distinto, sin tocar Python.
*Matiz honesto:* las **reglas de negocio R1–R5** y la política de estados viven también en `reglas.py` y el auditor las hace cumplir. Si cambiara solo el texto de la política en `agent.md`, el LLM lo intentaría, pero el auditor lo corregiría según `reglas.py`. Cambiar de verdad una regla requiere `reglas.py` **y** `agent.md`; hay un test que avisa si quedan desalineados.
*Mostrar:* editar un límite en `agent.md`, reiniciar `python main.py` y probarlo.

**2. Muéstrame un caso inválido: ¿dónde falla y qué recibe el usuario?**
Entrada inválida: `POST /run` con `{}` falla en `input.schema.json` (falta `mensaje`) y responde **422** con `{"error":"entrada_invalida","detalles":["$: falta el campo requerido 'mensaje'"]}`; el LLM nunca se llama. Ejemplos: `agent/examples/invalid/`.
*Mostrar:* `curl -X POST http://127.0.0.1:8000/run -H "Content-Type: application/json" -d "{}"` y `pytest tests/test_contratos.py -v`.

**3. Si el LLM responde un JSON que no cumple el schema de salida, ¿qué hace el arnés?**
No cae. `schema_validator.validar_schema` detecta el error y el arnés se lo devuelve al LLM (`ERROR DE ESQUEMA ($.campo: motivo)`) para que se corrija; reintenta hasta `max_formato` (3). Si agota los reintentos, devuelve un error controlado (`salida_invalida` o `formato_invalido`, HTTP 502) con su `run_id`. Si ni siquiera es JSON, mismo mecanismo (`FORMATO: responde SOLO con un objeto JSON...`).
*Mostrar:* `runtime.py` (busca `ERROR DE ESQUEMA`) y `tests/test_contratos.py::test_salida_que_viola_el_schema_se_devuelve_al_llm_con_el_error`.

**4. ¿Qué información entra al prompt y qué decide el LLM frente a lo que decide el código?**
Entra: `agent.md`, herramientas habilitadas, catálogo de skills (solo nombre y descripción), valores válidos, contexto de sesión y el historial reciente. El LLM decide: qué tool y en qué orden, el estado, la explicación y si algo es fuera de alcance. El código decide: la evidencia de cada regla, qué tools existen, que los argumentos y la salida cumplan el schema, que el veredicto sea coherente con la evidencia, los límites de pasos y la trazabilidad.
*Mostrar:* el evento `prompt` en `/logs?run_id=...`.

**5. Toma un identificador de ejecución y muéstrame su recorrido en los logs.**
Hago una consulta en `/run`, copio el `run_id` y abro `/logs?run_id=<id>`: se ve `inicio` → `usuario` → `prompt` → `llm` → `tool` (`evaluar_reglas`) → `llm` → `tool` (`cargar_skill`) → `skill` → `llm` → `final` → `fin`, cada uno con tiempos. En consola: `Select-String -Path logs\ejecucion.jsonl -Pattern "<run_id>"`.
*Tratamiento de errores:* timeouts de Ollama → un reintento y luego 503; JSON inválido → reintentos y 502; error de una tool → vuelve al agente como `{"error":...}` y el servicio sigue.

**6. ¿Cómo decide el agente usar la herramienta y qué pasa si los argumentos no cumplen su schema?**
El LLM lee en el prompt la lista de tools con sus parámetros y decide emitir `{"tool":..., "args":...}`. El arnés comprueba: que la tool exista y esté permitida, que `args` cumpla su `input_schema` de `tools.yaml` (`tool_registry.validar_args`) y, si la tool lo pide (`rut_must_come_from_user`), que el RUT lo haya escrito el usuario. Si no cumple, no se ejecuta: el motivo vuelve al LLM (`ERROR DE ARGUMENTOS`) y reintenta hasta 3 veces.
*Mostrar:* `tests/test_tool_registry.py::test_args_invalidos_vuelven_al_llm_y_este_se_corrige`.

**7. ¿Qué cambiaría si esta herramienta fuera un servidor MCP?**
Casi nada para el agente: en `tools.yaml` pasaría de `origin: local` a `origin: mcp`; el arnés la descubriría con `tools/list` y la llamaría con `tools/call`. La validación de argumentos, los permisos y el manejo de errores serían los mismos. Cambia que corre en otro proceso (aislamiento, reutilizable por otros agentes) y que hay que manejar timeout, reinicio y fallas de conexión. **Ya tenemos un caso real:** `consultar_convenio` (`mcp_server.py` / `mcp_client.py`).

**8. ¿Por qué ese tamaño de chunk y ese modelo de embeddings? ¿Qué responde el agente si la pregunta no está en los documentos?**
Chunk = una sección: cada sección es una norma completa (279–423 caracteres); partir por tamaño fijo cortaría artículos. `nomic-embed-text`: abierto, liviano, corre local con Ollama, funciona con español; usa prefijos `search_document:` / `search_query:`. top-k = 3 porque hay 8 fragmentos y un 4B tiene contexto limitado. Si la pregunta no está en los documentos, el puntaje queda bajo el umbral (0.60), `buscar_reglamento` devuelve `no_encontrado` y el agente lo dice en vez de inventar (caso E12). *Limitación honesta:* el umbral es un valor inicial sin calibrar con muchas preguntas; calibrarlo es la mejora. Con más documentos usaríamos PostgreSQL + pgvector.
*Mostrar:* `python -m scripts.ingestar --consulta "¿cuál es el menú del casino?"`.

**9. ¿Qué caso de evaluación falla hoy o fallaría primero, y por qué?**
En modo `mock` pasan los 25 casos (eso mide el arnés). Con el modelo real hay que correr `python -m evals.evaluator --modo live`. Los candidatos a fallar primero son los que exigen **criterio** a un modelo de 4B: E19 (pregunta ambigua: debe pedir aclaración en vez de adivinar), E20 (no inventar un RUT) y E12 (admitir que no hay información). **Responde con el resultado real de tu corrida**, no con esta hipótesis, y explica por qué (p. ej. "el modelo respondió con el RUT de la sesión en vez de aclarar").

**10. ¿Qué detectó Ruff, Semgrep o Bandit y qué corrigieron o aceptaron? ¿Qué corre en cada push?**
Ruff detectó (entre otros): `B904` (re-lanzar excepciones sin `from e`, corregido), `S310` (`urlopen`: aceptado con motivo, porque se valida que el host sea http/https en el constructor), `S603` (`subprocess`: aceptado, el comando es fijo), `S110` (`try/except/pass`: corregido con `contextlib.suppress`), `B008` (corregido con un singleton), `I001` (orden de imports, corregido). **Para Bandit: ejecútenlo y anoten aquí sus hallazgos reales** (`bandit -r harness app evals -c pyproject.toml`). En cada push, GitHub Actions corre Ruff → Bandit → pytest → evaluador y sube los reportes; si algo falla, queda en rojo y se corrige antes de integrar.

**11. Agrega un campo opcional al schema de salida: ¿qué archivos tocas y qué prueba se ve afectada?** → ver sección 5.

**12. Si una parte la generó un asistente, ¿cómo verificaste que es correcta?** → ver sección 7.

**13. Muestra un commit o ticket tuyo y explica una decisión técnica que tomaste.** → ver sección 7.

---

## 5. Cambios en vivo (para practicar)

### A. Agregar un campo opcional al schema de salida (ej. `nivel_certeza` en el veredicto)
1. `agent/output.schema.json`: en `veredicto.properties` agregar `"nivel_certeza": {"type": "string", "enum": ["alta", "media", "baja"]}` **sin** ponerlo en `required` (por eso es opcional).
2. `agent/examples/valid/`: un ejemplo con el campo y en `invalid/` uno con un valor fuera del enum.
3. `agent/agent.md`: mencionar el campo en el formato del veredicto, para que el LLM sepa que puede emitirlo.
4. (Opcional) `harness/presentacion.py` para mostrarlo en consola.
**Qué prueba se ve afectada:** `tests/test_contratos.py` recoge los ejemplos nuevos automáticamente. Si en cambio lo hiciera **obligatorio**, fallarían los ejemplos válidos existentes, los guiones de `evals/cases.jsonl` y el helper `V()` de `tests/fakes.py`, porque ninguno trae el campo. Verifico con `pytest`.

### B. Endurecer una restricción (ej. `mensaje` máximo 500 caracteres)
`agent/input.schema.json` (`maxLength`) → se aplica en `/run` y en el chat. Afecta `tests/test_contratos.py::test_entrada_valida_e_invalida` y `test_entrada_demasiado_larga...` (cambiar el largo de prueba).

### C. Sumar un caso de evaluación
Una línea en `evals/cases.jsonl` (`id`, `categoria`, `descripcion`, `entrada`, `criterios`, `mock`). Se ejecuta con `python -m evals.evaluator --solo E22`. Afecta el reporte y el mínimo de casos de `tests/test_evaluador.py`.

### D. Ajustar el chunking
`harness/rag.py::chunkear` (por ejemplo, partir por párrafos). Verificar con `python -m scripts.ingestar --sin-embeddings`. Afecta `tests/test_rag.py` y obliga a regenerar embeddings (la caché cambia sola).

### E. Agregar una herramienta
`agent/tools.yaml` (declarar con schemas y permisos) → handler en `tool_registry.py` → permitirla en `manifest.yaml` → mencionarla en `agent.md` (hay un test que lo exige) → un test en `tests/test_tool_registry.py`.

---

## 6. Demo paso a paso (guion sugerido, 8–10 minutos)

Antes: Ollama activo, `.venv` activado, `uvicorn app.main:app --port 8000` corriendo.

1. **Estructura** (1 min): mostrar el árbol del repo y `agent/` (agent.md, manifest, tools.yaml, schemas).
2. `GET /health` y `GET /metadata`: muestran versión, modelo, tools y skills **leídos de los archivos**.
3. **Caso feliz**: `/run` con `Dime si el paciente 11111111-1 es apto` → `califica`.
4. **Caso con faltantes**: `Verifica el 33333333-3` → `falta_informacion` + se cargó la skill. Mostrar el `run_id` y `/logs?run_id=...`.
5. **Herramienta MCP**: `¿Hay convenio con Isapre Colmena?`.
6. **RAG**: `¿Qué documentos exige el protocolo de admisión?` y `¿cuál es el menú del casino?` (no está → lo admite).
7. **Límites**: `¿Qué diagnóstico tiene el paciente 11111111-1?` → fuera de alcance, sin herramientas.
8. **Fallos provocados** (muy valorado en C6): 
   - Ollama apagado: detener `ollama` (o `$env:OLLAMA_HOST="http://localhost:9"`) y llamar `/run` → **503** con mensaje claro, el servicio sigue vivo.
   - Entrada inválida: `/run` con `{}` → **422**.
   - `run_id` inexistente: `/logs?run_id=zzz` → **404**.
   - Salida inválida / tool que falla: mostrar el test correspondiente (`pytest tests/test_contratos.py tests/test_tool_registry.py -v`).
9. **Calidad**: `pytest`, `ruff check .`, la evaluación (`python -m evals.evaluator`) y la pestaña **Actions** del repo en verde.

**Si algo falla en vivo:** no improvisen; digan qué debería pasar, muestren el log (`run_id`) y el test que cubre ese caso.

---

## 7. Uso responsable de IA y contribución (I7 e I8)

### Uso de IA (I7) — sean honestos
Este proyecto se desarrolló **con ayuda de un asistente de IA** (Claude). La política del curso permite usar IA, pero exige **justificar las decisiones y defender el comportamiento**; presentar como propio lo que no se entiende o no se desarrolló puede penalizarse con nota mínima. Por eso:
- **Declaren** qué generó la IA (código del arnés, tests, documentación) y qué diseñaron/decidieron ustedes.
- **Lean el código** que van a defender y ejecútenlo: cada integrante debe poder explicar su área sin mirar.
- **Cómo se verificó** (respuestas verdaderas para este repo): se ejecutaron las pruebas (`pytest`), se probó el agente real con gemma3:4b en consola (se vieron fallas reales: el modelo "narraba" la herramienta, respondía fuera de tema y elegía mal el estado, y por eso se agregaron el auditor, `base` y las correcciones), se leyó el código crítico y se revisaron los logs de ejecuciones reales.
- **Alternativas que se descartaron y por qué** (decisiones propias que pueden defender): que el código calculara el estado y el LLM solo lo redactara (dejaría de ser un agente); filtrar palabras prohibidas con listas (frágil; mejor schema + límites en el prompt + auditor); una base vectorial (innecesaria con 8 fragmentos); un framework tipo LangChain (se prefirió entender y controlar cada pieza).

### Contribución (I8)
La nota individual mira **commits, PRs y tickets de Jira de cada uno**. Recomendación:
- Repartir por área (y cada uno estudia especialmente la suya, pero conoce las demás): **A** definición y contratos (`agent/`, schemas, ejemplos) · **B** arnés, API y trazabilidad (`runtime`, `app/`, `tracing`) · **C** herramientas y MCP · **D** RAG · **E** pruebas, evaluación y CI.
- Un ticket de Jira por tarea (ej. `P02-14 Validar argumentos de tools con JSON Schema`), una rama por ticket (`feature/P02-14-validar-args`), commits pequeños con el id del ticket (`P02-14: valida args contra input_schema`), y **Pull Request** revisado por otro integrante.
- **No concentrar todo al final**: la rúbrica castiga los aportes de la última semana.
- Cada uno debe poder abrir **un commit o ticket suyo** y explicar la decisión técnica que tomó.

---

## 8. Lo que aún falta (para no sorprenderse)

- **API FastAPI**: escrita y su lógica probada con tests, pero no pude ejecutar el servidor real en el entorno donde se construyó. Corran `pip install -r requirements.txt` y `pytest` (`tests/test_api.py` pasa a ejecutarse) y `uvicorn app.main:app`. Si algo falla, avisen con el mensaje de error.
- **Bandit/Semgrep**: configurado en el CI pero **no ejecutado todavía**; hay que correrlo, anotar los hallazgos en `reports/README.md` y corregirlos o justificarlos.
- **GitHub Actions**: el workflow está escrito, pero hasta que no se haga el primer push no se sabe si queda verde. Revisar la pestaña Actions y corregir lo que salga.
- **Evaluación con el modelo real**: ejecutar `python -m evals.evaluator --modo live` y subir el reporte a `reports/`.
- **Umbral del RAG (0.60)**: sin calibrar con datos reales.
- **Jira y commits individuales**: dependen del grupo.
- **pgvector**: no se usa (almacén JSON justificado en `docs/decisiones.md`); si el curso lo exige, es el siguiente paso.

## Caso real: el modelo se desvía en una pregunta ajena (E24)

Observado con gemma3:4b: tras evaluar a un paciente, el usuario escribió "dime la hora de colacion". El modelo (1) devolvió `{"tool": "fuera_de_alcance"}` confundiendo el **tipo** de mensaje con una herramienta, y (2) al ser corregido, consultó el registro del paciente anterior y terminó dando un veredicto que nadie pidió.

Qué hace el arnés ahora (`harness/runtime.py`, `harness/utilidades.py::refiere_a_paciente`):
- Si el nombre de la "tool" es en realidad un tipo de respuesta final, el feedback le muestra el formato correcto (`"tipo"`, no `"tool"`).
- Si pide una tool que requiere RUT pero el mensaje actual no habla de ningún paciente, la ejecución se **bloquea** aunque el RUT esté en la sesión; si insiste, el arnés responde `fuera_de_alcance` (origen `harness`).
- "¿Qué puedes hacer?" se contesta como `respuesta` con `base: saludo` (no es fuera de alcance).

Cómo explicarlo: el LLM decide, pero el arnés pone **barreras determinísticas** donde un modelo pequeño se equivoca; todo queda en el log (`rut_bloqueado`, `tool_invalida`, `fuera_de_funcion`). Cubierto por `tests/test_deriva.py` y los casos E24/E25.
