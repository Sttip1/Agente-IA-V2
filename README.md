# Grupo 6 - CINF110 (Agentes de IA)
## Agente P02: Verificación administrativa de casos de urgencia (Clínica X)

Este repositorio contiene la implementación del agente **P02**, diseñado bajo un enfoque mixto **declarativo-ejecutable** para asistir al personal administrativo de urgencias de la **Clínica X** en la validación preliminar de casos bajo la Ley de Urgencia.

---

## 🛠️ Requisitos
- **Python 3.10+** (solo biblioteca estándar de Python: sin LangChain, sin SDK de OpenAI, sin `pip install`).
- **Ollama** instalado y ejecutándose localmente (`http://localhost:11434`).
- Modelos requeridos en Ollama:
  - `ollama pull gemma3:4b` (Modelo LLM principal; configurable mediante variable de entorno `OLLAMA_MODEL`).
  - `ollama pull nomic-embed-text` (Modelo de embeddings para el pipeline RAG; configurable mediante `OLLAMA_EMBED_MODEL`).

---

## 📁 Mapa de Carpetas y Estructura

El proyecto está organizado en las siguientes carpetas y archivos:

```text
evaluacion_2_agente_ia/
│
├── agent/                      # Definición declarativa del agente
│   ├── agent.md                # Propósito, responsabilidades, alcance y límites
│   ├── manifest.yaml           # Metadatos, entradas, salidas, tools, skill y límites
│   ├── input.schema.json       # Esquema JSON de entradas
│   ├── output.schema.json      # Esquema JSON de salidas
│   └── SKILL.md                # Skill: clasificar-antecedente-faltante
│
├── harness/                    # ⚙️ ARNÉS EJECUTABLE DEL AGENTE
│   ├── config.py               # Configuración de rutas y variables de entorno
│   ├── errores.py              # Excepciones propias (LLMNoDisponible, ToolError, ValidacionError)
│   ├── memoria.py              # Historial conversacional
│   ├── output_parser.py        # Extracción y parsing de JSON desde la respuesta del LLM
│   ├── schema_validator.py     # Validador de esquemas JSON (input/output)
│   ├── llm_client.py           # Cliente HTTP nativo (urllib) para Ollama (/chat/completions y /embeddings)
│   ├── runtime.py              # Bucle interactivo de chat, loop de tools y validación de esquemas
│   ├── rag_pipeline.py         # Pipeline RAG documental (chunking, embeddings, similitud coseno)
│   ├── mcp_client.py           # Cliente MCP por stdio (JSON-RPC)
│   ├── mcp_server/
│   │   └── servidor_convenios.py # Servidor MCP en Python puro (consultar_convenio)
│   └── tools/
│       ├── __init__.py         # Registro central de herramientas (tools)
│       ├── consultar_antecedentes.py # Tool: buscar_paciente(rut)
│       ├── validar_ley_urgencia.py   # Tool: validar_ley_urgencia(rut)
│       └── buscar_reglamento.py      # Tool: búsqueda en RAG institucional
│
├── data/                       # Datos simulados y documentación base
│   ├── pacientes_simulados.json# 4 pacientes de prueba (califica, sin previsión, falta doc, sin triage)
│   └── documentos/
│       ├── reglamento_urgencia.md  # Reglamento institucional Ley de Urgencia
│       └── protocolo_admision.md   # Protocolo interno de admisión en urgencias
│
├── tests/                      # Suite de pruebas unitarias (ejecutables con unittest)
│   ├── test_tools.py
│   ├── test_validator.py
│   ├── test_parser.py
│   ├── test_rag.py
│   └── test_mcp.py
│
├── docs/                       # Documentación del proyecto
│   ├── arquitectura/
│   │   └── flujo-del-agente.md # Diagrama y descripción del flujo de ejecución
│   └── bitacora/
│       └── README.md           # Bitácora de desarrollo del Grupo 6
│
├── evidence/                   # Evidencia de sesión y prompts
│   └── opencode-session.md
│
├── opencode.json               # Configuración de permisos de entorno
└── README.md                   # Este archivo
```

---

## 🚀 Cómo Ejecutar

Para iniciar el chat interactivo del Agente P02:

```powershell
python evaluacion_2_agente_ia/harness/runtime.py
```

### Cambiar de Modelo LLM
Puedes cambiar el modelo utilizado por Ollama configurando la variable de entorno antes de ejecutar:
```powershell
$env:OLLAMA_MODEL = "gemma3:4b"
python evaluacion_2_agente_ia/harness/runtime.py
```

---

## 🧪 Cómo Ejecutar las Pruebas Unitarias

Para ejecutar todas las pruebas unitarias del arnés y tools con `unittest`:

```powershell
python -m unittest discover -s evaluacion_2_agente_ia/tests -p "test_*.py"
```

---

## 🎬 Demos por Tema (Guía para el Video)

1. **Tools:**
   - *Comando:* `"Revisa el paciente 11111111-1"`
   - *Comportamiento:* El LLM solicita la ejecución de `consultar_antecedentes` y luego `validar_ley_urgencia`. Se aprecian las trazas `[TRAZA TOOL]` y `[TRAZA VALIDADOR]` en terminal. La salida final cumple estrictamente con `output.schema.json`.

2. **MCP (Model Context Protocol):**
   - *Comando:* `"¿Hay convenio para Isapre Banmedica?"`
   - *Comportamiento:* El arnés se comunica mediante JSON-RPC por `stdio` con el servidor `servidor_convenios.py`, mostrando la traza `[TRAZA MCP]` con los detalles del convenio de urgencia.

3. **Skill:**
   - *Comando:* Caso de paciente con documentos faltantes (`33333333-3`).
   - *Comportamiento:* Se activa la skill `clasificar-antecedente-faltante` (registrando `[TRAZA SKILL]`), guiando al administrativo en la redacción formal de la solicitud del documento ausente.

4. **RAG (Retrieval-Augmented Generation):**
   - *Comando:* `"¿Qué dice el reglamento sobre la urgencia vital?"`
   - *Comportamiento:* El pipeline RAG (`rag_pipeline.py`) recupera fragmentos de `reglamento_urgencia.md` mediante similitud coseno, imprimiendo las fuentes y scores con la traza `[TRAZA RAG]`. Si se pregunta algo fuera de los documentos, indica que no se encontró en ellos.

5. **Límites Estrictos:**
   - *Comando:* `"¿Qué diagnóstico médico tiene el paciente y debe ingresar a UCI?"`
   - *Comportamiento:* El agente se niega formalmente citando sus límites declarados (`NO diagnostica`, `NO decide el ingreso final`).
