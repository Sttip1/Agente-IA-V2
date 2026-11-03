# Ejemplos de contratos

Cada archivo es `{"schema": ..., "descripcion": ..., "dato": ...}`.

- `valid/`: el dato **debe** cumplir el schema (`input`, `veredicto`, `respuesta` o `fuera_de_alcance`).
- `invalid/`: el dato **debe ser rechazado**; la descripción dice qué regla incumple.

Se ejecutan automáticamente en `tests/test_contratos.py` (y por lo tanto en CI), usando `harness/schema_validator.py`.
