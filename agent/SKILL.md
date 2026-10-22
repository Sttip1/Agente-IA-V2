# Skill: clasificar-antecedente-faltante

## Propósito
Guiar al agente y al personal administrativo en la identificación precisa de antecedentes, documentos o validaciones faltantes para procesar un caso de urgencia en la Clínica X, redactando una solicitud clara y profesional.

## Pasos de Ejecución
1. **Analizar los datos de entrada y el resultado de la validación:** Revisar qué requisitos de la Ley de Urgencia o protocolos internos no se cumplieron (ej. falta de carnet de identidad, previsión inactiva, ausencia de revisión de triage por clínico).
2. **Identificar antecedentes faltantes específicos:** Listar formalmente cada documento o validación ausente (ej. "Cédula de identidad del paciente", "Certificado de afiliación Fonasa actualizado", "Validación clínica de triage").
3. **Redactar la solicitud al administrativo:** Generar un mensaje claro, directo y protocolar dirigido al administrativo de turno (en tercera persona o imperativo, ej. "Solicite al paciente su cédula de identidad", "Verifique con el equipo clínico"), sin hablarle al paciente en primera persona. Menciona SOLO los antecedentes de la lista dada. No agregues datos, previsiones ni requisitos que no estén en el contexto.
4. **Formatear la salida:** Asegurar que el estado sea `falta_informacion` y que `antecedentes_faltantes` contenga la lista exacta para cumplir con el esquema de salida.
