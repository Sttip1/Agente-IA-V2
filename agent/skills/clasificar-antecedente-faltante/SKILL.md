---
name: clasificar-antecedente-faltante
description: Úsala cuando el estado de un caso sea no_califica o falta_informacion, para identificar cada antecedente que falta y redactar la solicitud al administrativo.
---
# Skill: clasificar-antecedente-faltante

## Cuándo usarla
Después de llamar a evaluar_reglas y antes de entregar un veredicto cuyo estado NO es califica.

## Pasos
1. Revisa la evidencia de evaluar_reglas e identifica las reglas con cumple=false o cumple=null.
2. Traduce cada una a un antecedente concreto y accionable, por ejemplo:
   - R2 false: "Certificado de afiliación vigente o regularización previsional".
   - R3 false: "Validación de triage por personal clínico".
   - R4 false: "Cédula de identidad o documento oficial de identificación".
   - Dato ausente (cumple=null): "<dato> (ausente en el registro)".
   - RUT inexistente: "Registro del paciente en el sistema (RUT mal digitado o no registrado)".
3. Redacta la explicación dirigida al administrativo de turno, en imperativo o tercera persona ("Solicite al paciente su cédula", "Verifique con el equipo clínico la validación del triage"). Nunca le hables al paciente en primera persona.
4. Menciona SOLO los antecedentes realmente faltantes. No agregues previsiones, requisitos ni datos que no estén en la evidencia.
5. Si el triage no está revisado, indica que debe verificarlo el equipo clínico. No lo reclasifiques ni opines sobre gravedad.
6. Completa antecedentes_faltantes con exactamente esos antecedentes y verifica que el estado respete la política de estados.

## Ejemplos (ilustrativos: otros pacientes; NUNCA copies sus frases si no coinciden con la evidencia de TU caso)
**Ejemplo 1.** Evidencia: R2 cumple=false ("Previsión 'Isapre Banmedica (Morosidad)': INACTIVA"), el resto true.
Estado: no_califica. Antecedente: "Certificado de afiliación vigente o regularización previsional".
Explicación: "La previsión del paciente figura inactiva. Solicite un certificado de afiliación vigente o la regularización previsional antes de continuar el trámite."

**Ejemplo 2.** Evidencia: R1 cumple=true; R5 cumple=false ("No existe registro para este RUT en el sistema").
Estado: falta_informacion. Antecedente: "Registro del paciente en el sistema (RUT no encontrado o mal digitado)".
Explicación: "No existe un registro para este RUT. Verifique que el RUT esté bien digitado o solicite la creación del registro del paciente."

Regla de oro: los antecedentes y la explicación salen de la evidencia que te devolvió evaluar_reglas para ESTE caso, no de estos ejemplos.
