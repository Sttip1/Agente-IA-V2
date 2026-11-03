---
name: responder-consulta-normativa
description: Úsala cuando la pregunta sea sobre el reglamento, el protocolo de admisión o convenios, para responder solo con lo recuperado y citar la fuente.
---
# Skill: responder-consulta-normativa

## Cuándo usarla
Preguntas del tipo "¿qué dice el reglamento sobre...?", "¿qué documentos se exigen?", "¿hay convenio con...?".

## Pasos
1. Llama a buscar_reglamento (normativa y protocolos) o a consultar_convenio (convenios y cobertura), según corresponda.
2. Si el resultado es no_encontrado, ambiguo o trae un error, dilo con claridad. No completes con conocimiento propio.
3. Responde en 2 o 3 líneas, solo con lo que devolvió la herramienta.
4. Cita la fuente: nombre del archivo y artículo o sección para normativa; "servidor de convenios (datos simulados)" para convenios.
5. Si la pregunta pide una decisión (autorizar, aprobar, ingresar), no la tomes: usa tipo fuera_de_alcance.

## Ejemplo
Pregunta: "¿Qué documentos se exigen para pacientes extranjeros?"
Respuesta: "El protocolo exige cédula u otro documento oficial; para extranjeros se acepta pasaporte (protocolo_admision.md, sección 3)."
