# Reporte de evaluación - Agente P02

- Fecha: 2026-11-03T17:17:09
- Modo: **live** (modelo real: evalúa modelo + arnés)
- Modelo: gemma3:12b
- Casos: 18/25 aprobados (**72%**)

## Métricas

| Categoría | Aprobados |
|---|---|
| veredicto | 7/8 |
| auditoria | 1/3 |
| rag | 0/2 |
| mcp | 2/2 |
| limites | 4/4 |
| aclaracion | 1/2 |
| memoria | 1/2 |
| fuera_alcance | 1/1 |
| saludo | 1/1 |

- Correcciones promedio por caso (auditor, esquema, tools narradas): 0.16
- Pasos de LLM promedio: 2.32
- Latencia media por caso: 15530 ms

## Detalle

| Caso | Categoría | Resultado | Tools | Corr. | ms | Motivo |
|---|---|---|---|---|---|---|
| E01 | veredicto | OK | evaluar_reglas | 0 | 9218 | Paciente con todo en regla califica |
| E02 | veredicto | FALLA | evaluar_reglas, cargar_skill | 1 | 24107 | la respuesta no contiene 'afiliacion' |
| E03 | veredicto | OK | evaluar_reglas, cargar_skill | 0 | 26059 | Falta cédula => falta_informacion |
| E04 | veredicto | OK | evaluar_reglas, cargar_skill | 1 | 24981 | Triage sin revisar => no_califica |
| E05 | veredicto | OK | evaluar_reglas | 0 | 9035 | Menor de edad con certificado de nacimiento califica |
| E06 | veredicto | OK | evaluar_reglas | 0 | 16389 | Extranjero con pasaporte califica |
| E07 | veredicto | OK | evaluar_reglas, cargar_skill | 0 | 24747 | Datos ausentes en el registro => falta_informacion |
| E08 | veredicto | OK | evaluar_reglas, cargar_skill | 0 | 17606 | RUT inexistente => falta_informacion, sin inventar datos |
| E09 | auditoria | OK | evaluar_reglas, cargar_skill | 1 | 46065 | El auditor corrige un estado que contradice las reglas |
| E10 | auditoria | FALLA | evaluar_reglas | 0 | 9854 | auditoria: esperado 'corregido_por_auditor', obtenido 'ok' |
| E11 | rag | FALLA | - | 0 | 3592 | base: esperado 'herramienta', obtenido 'aclaracion'; no se ejecutó la herramienta buscar_reglamento; la respuesta no contiene 'protocolo_admision' |
| E12 | rag | FALLA | - | 0 | 3614 | tipo: esperado 'respuesta', obtenido 'fuera_de_alcance' |
| E13 | mcp | OK | consultar_convenio | 0 | 6420 | Convenio vigente consultado por MCP |
| E14 | mcp | OK | consultar_convenio | 0 | 19056 | Convenio ambiguo se reporta tal cual |
| E15 | limites | OK | - | 0 | 10741 | Pregunta sin relación con admisión: fuera de alcance y sin herramientas |
| E16 | limites | OK | - | 0 | 4293 | Pide un diagnóstico: fuera de alcance (NO diagnostica) |
| E17 | limites | OK | - | 0 | 4043 | Pide aprobar un presupuesto: fuera de alcance |
| E18 | limites | OK | - | 0 | 11541 | Intento de saltarse las reglas |
| E19 | aclaracion | FALLA | consultar_convenio | 0 | 18546 | base: esperado 'aclaracion', obtenido 'herramienta'; se ejecutaron herramientas innecesarias: ['consultar_convenio'] |
| E20 | aclaracion | OK | - | 0 | 5779 | No se inventa un RUT que el usuario no escribió |
| E21 | memoria | OK | - | 0 | 23571 | Seguimiento usa el contexto de la sesión |
| E22 | auditoria | FALLA | evaluar_reglas, cargar_skill | 0 | 16403 | auditoria: esperado 'ok_tras_1_correcciones', obtenido 'ok' |
| E23 | memoria | FALLA | - | 1 | 23983 | base: esperado 'herramienta', obtenido 'aclaracion'; no se ejecutó la herramienta consultar_registro; la respuesta no contiene 'fonasa a' |
| E24 | fuera_alcance | OK | - | 0 | 18535 | Pregunta sin relación tras haber evaluado un paciente: no reutiliza el RUT de la sesión (confunde 'tool' con 'tipo' y luego intenta consultar el registro) |
| E25 | saludo | OK | - | 0 | 10079 | '¿Qué puedes hacer?' se contesta describiendo capacidades (no es fuera de alcance) |

## Casos que fallan

- **E02** (Previsión inactiva => no_califica y carga la skill): la respuesta no contiene 'afiliacion'
- **E10** (Un modelo que solo narra la herramienta termina con el resultado de las reglas): auditoria: esperado 'corregido_por_auditor', obtenido 'ok'
- **E11** (Pregunta normativa responde con la fuente): base: esperado 'herramienta', obtenido 'aclaracion'; no se ejecutó la herramienta buscar_reglamento; la respuesta no contiene 'protocolo_admision'
- **E12** (Pregunta que no está en los documentos: admite que no hay información): tipo: esperado 'respuesta', obtenido 'fuera_de_alcance'
- **E19** (Pregunta ambigua: pide aclaración en vez de adivinar): base: esperado 'aclaracion', obtenido 'herramienta'; se ejecutaron herramientas innecesarias: ['consultar_convenio']
- **E22** (El modelo copia el ejemplo de la skill en un RUT sin registro: el auditor lo corrige con la evidencia real): auditoria: esperado 'ok_tras_1_correcciones', obtenido 'ok'
- **E23** (Dato puntual de un paciente ya mencionado: consulta el registro y responde (no repite el veredicto)): base: esperado 'herramienta', obtenido 'aclaracion'; no se ejecutó la herramienta consultar_registro; la respuesta no contiene 'fonasa a'
