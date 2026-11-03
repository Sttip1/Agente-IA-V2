# Evidencia de calidad

| Archivo | Qué es | Cómo se genera | Estado |
|---|---|---|---|
| `pytest.xml` | resultado de las pruebas (JUnit) | `pytest --junitxml=reports/pytest.xml` | 183 pasan, 1 omitida (`tests/test_api.py` necesita `fastapi` y `httpx`; con `pip install -r requirements-dev.txt` corre) |
| `eval_report.md` / `.json` | evaluación automática, modo mock (guion de respuestas): mide el arnés | `python -m evals.evaluator --modo mock` | 25/25 casos |
| `eval_report_<modelo>.md` | evaluación con el modelo real (Ollama): mide modelo + arnés | `python -m evals.evaluator --modo live --model gemma3:4b` | **pendiente: ejecutarla en tu PC y subir el archivo** |
| `ruff.txt` | resultado de Ruff (`E,F,W,I,B,S`) | `ruff check . --output-format concise` | sin errores |
| `bandit.txt` | análisis de seguridad con Bandit | `bandit -r harness app evals -c pyproject.toml -f txt -o reports/bandit.txt` | **pendiente: lo genera el CI o se ejecuta en tu PC** |

## Seguridad
- Ruff incluye las reglas `S` (equivalentes a un subconjunto de Bandit). Hallazgos encontrados y cómo se resolvieron:
  - `S310` (`urllib.request.urlopen`, 3 usos en `harness/llm_client.py`): el esquema de `OLLAMA_HOST` se valida en el constructor (solo `http://` o `https://`); no se aceptan `file:` ni otros. Se marcó con `# noqa: S310  # nosec B310` y su motivo.
  - `S603` (`subprocess.Popen` en `harness/mcp_client.py`): el comando es fijo (`python -m harness.mcp_server`) y no incluye texto del usuario. Marcado con `# noqa: S603  # nosec B603`.
  - `S110` (`try/except/pass`): reemplazado por `contextlib.suppress` en el cierre del proceso MCP.
- No hay claves ni credenciales en el repositorio: el agente corre contra Ollama local. `.env` está en `.gitignore` y `.env.example` solo trae valores de ejemplo.
- Los RUTs se enmascaran en los logs y en `/logs`.
- Cuando se ejecute Bandit, anotar aquí cada hallazgo y su decisión (corregido o aceptado con motivo).
