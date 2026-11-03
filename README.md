# Agente P02 - Verificación administrativa de casos de urgencia (Clínica X)

CINF110 - Agentes de IA · Iniciativa 2: Admisión, urgencias y reglas de negocio.

Un agente de IA que apoya al personal administrativo de urgencias a revisar si un caso, ya evaluado por personal clínico, tiene los antecedentes administrativos suficientes para tramitarse bajo la Ley de Urgencia. Entrega `califica`, `no_califica` o `falta_informacion`, con una explicación y lo que falta. Usa datos **simulados**.

El **LLM decide** (qué herramienta usar, qué estado dar, cómo explicarlo); el **arnés** valida, ejecuta las herramientas, audita y deja trazabilidad. Detalle en [`docs/arquitectura.md`](docs/arquitectura.md) y [`docs/decisiones.md`](docs/decisiones.md).

## 1. Instalación desde cero

Requisitos: **Python 3.10+**, **Git** y [**Ollama**](https://ollama.com).

```bash
git clone https://github.com/Sttip1/Agente-IA-V2.git
cd Agente-IA-V2

python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\Activate.ps1        Linux/macOS:  source .venv/bin/activate
pip install -r requirements.txt

ollama pull gemma3:4b            # modelo de chat
ollama pull nomic-embed-text     # modelo de embeddings (RAG)
```

Configuración (opcional): copia `.env.example` a `.env` y ajusta los valores. **No hay claves ni credenciales**: todo corre en local. El `.env` no se versiona.

## 2. Ejecutar

Ollama debe estar en ejecución (`ollama serve` si no arranca solo).

| Qué | Comando |
|---|---|
| Chat por consola | `python main.py` (`--quiet`, `--json`, `--model gemma3:12b`) |
| API HTTP | `uvicorn app.main:app --host 127.0.0.1 --port 8000` y abre http://127.0.0.1:8000/docs |
| Ingesta del RAG (chunking + embeddings) | `python -m scripts.ingestar` (`--sin-embeddings`, `--consulta "urgencia vital"`) |
| Pruebas | `pytest` |
| Evaluación automática (sin Ollama) | `python -m evals.evaluator --modo mock` |
| Evaluación con el modelo real | `python -m evals.evaluator --modo live --model gemma3:4b` |
| Lint y seguridad | `ruff check .` · `bandit -r harness app evals -c pyproject.toml` |

Comandos dentro del chat: `salir` y `/reset` (borra la memoria).
RUTs de prueba: `11111111-1` (califica) · `22222222-2` (previsión inactiva) · `33333333-3` (falta cédula) · `44444444-4` (sin triage) · `55555555-5` (menor con certificado) · `66666666-6` (extranjero con pasaporte) · `77777777-7` (registro incompleto) · `99999999-9` (no existe).

### API

```bash
curl http://127.0.0.1:8000/health                      # ?profundo=true comprueba también Ollama
curl http://127.0.0.1:8000/metadata                    # versión, modelo, tools, skills, límites
curl -X POST http://127.0.0.1:8000/run -H "Content-Type: application/json" \
     -d '{"mensaje": "Dime si el paciente 11111111-1 es apto", "session_id": "mesa-1"}'
curl "http://127.0.0.1:8000/logs?run_id=<run_id devuelto por /run>"
```

| Código | Cuándo |
|---|---|
| 200 | respuesta del agente (veredicto, respuesta o fuera_de_alcance) |
| 422 | entrada inválida según `agent/input.schema.json` |
| 404 | `/logs` con un `run_id` desconocido |
| 502 | el LLM no produjo una salida válida tras los reintentos |
| 503 | Ollama apagado, sin el modelo o con timeout |
| 504 | el agente no concluyó dentro de `max_pasos` |

## 3. Estructura del repositorio

```
agente_p02/
├── agent/                      DEFINICIÓN DECLARATIVA (el código la lee al iniciar)
│   ├── agent.md                propósito, responsabilidades, rol, límites, criterios de éxito, política de estados
│   ├── manifest.yaml           id, versión, tools permitidas (lista blanca), skills, límites, parámetros
│   ├── tools.yaml              herramientas: descripción, schema de entrada/salida, permisos
│   ├── input.schema.json       contrato de entrada de /run
│   ├── output.schema.json      contrato de salida: veredicto | respuesta | fuera_de_alcance (con reglas condicionales)
│   ├── examples/valid|invalid  ejemplos que se ejecutan en los tests
│   └── skills/<nombre>/SKILL.md
├── harness/                    ARNÉS
│   ├── runtime.py              bucle LLM <-> tools, validación, auditoría, run_id
│   ├── prompt_builder.py       arma el prompt desde agent/
│   ├── llm_client.py           cliente de Ollama (configurable por entorno)
│   ├── schema_validator.py     validación JSON Schema (entrada, salida, args de tools)
│   ├── tool_registry.py        carga tools.yaml, valida args y ejecuta (local o MCP)
│   ├── tracing.py              logs estructurados JSONL con run_id
│   ├── auditor.py · reglas.py · rag.py · memoria.py · declarativo.py
│   └── mcp_server.py · mcp_client.py     servidor y cliente MCP (stdio, JSON-RPC)
├── app/                        API FastAPI (main.py) y su lógica (servicio.py)
├── data/                       pacientes simulados + documentos para el RAG
├── scripts/ingestar.py         ingesta reproducible del RAG
├── tests/                      pytest (contratos, arnés, tools, API, trazabilidad, RAG, MCP, evaluador)
├── evals/                      cases.jsonl + evaluator.py
├── reports/                    evidencia: pruebas, evaluación, calidad y seguridad
├── docs/                       arquitectura, decisiones, guía de defensa
└── .github/workflows/ci.yml    Ruff + Bandit + pytest + evaluación en cada push/PR
```

## 4. Quién decide qué

- **El LLM decide** qué tool llamar y en qué orden, cuándo tiene evidencia suficiente, qué estado asigna y cómo lo explica. Los límites (no diagnostica, no reclasifica triage, no aprueba cobros, no decide ingreso) también los aplica el LLM mediante `fuera_de_alcance`.
- **Las tools entregan hechos**: registro del paciente, evidencia regla por regla, fragmentos de normativa, convenios. No entregan el veredicto.
- **El arnés valida y audita**: valida entrada y salida con JSON Schema, valida los argumentos de cada tool, rechaza veredictos sin evidencia o contradictorios con las reglas, y le devuelve el motivo al LLM para que se corrija. Si tras `max_correcciones` sigue contradiciendo las reglas, entrega el resultado de las reglas marcado `corregido_por_auditor`.

## 5. Cómo extenderlo

- **Cambiar comportamiento o límites**: editar `agent/agent.md` (sin tocar Python).
- **Agregar una skill**: carpeta `agent/skills/<nombre>/SKILL.md` con frontmatter y añadirla a `skills:` en `manifest.yaml`.
- **Agregar una tool**: declararla en `agent/tools.yaml` (schemas y permisos), implementar su `handler` en `harness/tool_registry.py` (o publicarla en un servidor MCP) y permitirla en `manifest.yaml`.
- **Agregar un campo opcional a la salida**: `agent/output.schema.json` + un ejemplo en `agent/examples/` (los tests lo ejecutan).
- **Agregar un caso de evaluación**: una línea en `evals/cases.jsonl`.
- **Cambiar una regla de negocio**: `harness/reglas.py`; si cambia la política de estados, actualizar `agent.md`.

## 6. Calidad y evidencia

Cada push ejecuta `.github/workflows/ci.yml`: Ruff, Bandit, pytest y el evaluador; los reportes quedan como artefacto y en [`reports/`](reports/). Si una etapa falla, el workflow queda en rojo y no se debe integrar el cambio.

## 7. Datos y alcance

Todos los datos son simulados. El agente es una ayuda administrativa: **no diagnostica, no clasifica clínicamente, no autoriza cobros ni decide el ingreso**.
