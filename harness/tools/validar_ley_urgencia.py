import json
import os

def validar_ley_urgencia(rut):
    """
    Valida el cumplimiento de la Ley de Urgencia para un paciente según sus antecedentes.
    Evalúa previsión activa, revisión de triage por clínico y documentos presentados.
    Devuelve estado, reglas aplicadas y antecedentes faltantes.
    Imprime traza [TRAZA TOOL] y [TRAZA VALIDADOR].
    """
    print(f"[TRAZA TOOL] Ejecutando validar_ley_urgencia con rut={rut}")
    ruta_datos = os.path.join(os.path.dirname(__file__), "..", "..", "data", "pacientes_simulados.json")
    
    if not os.path.exists(ruta_datos):
        return {"error": "Archivo de pacientes simulados no encontrado.", "rut": rut}
    
    try:
        with open(ruta_datos, "r", encoding="utf-8") as f:
            pacientes = json.load(f)
    except Exception as e:
        return {"error": f"Error al leer datos: {str(e)}", "rut": rut}
        
    if rut not in pacientes:
        return {
            "estado": "falta_informacion",
            "explicacion": "El RUT no está registrado. Verifique que esté bien digitado.",
            "antecedentes_faltantes": ["RUT registrado en el sistema"],
            "reglas_aplicadas": ["Ley de Urgencia Art. 3 - Verificación de Identidad"]
        }
        
    p = pacientes[rut]
    reglas_aplicadas = [
        "Ley de Urgencia Art. 1 - Condición de Urgencia Vital",
        "Ley de Urgencia Art. 3 - Verificación Previsional y Triage"
    ]
    antecedentes_faltantes = []
    
    # Validaciones
    prevision_activa = p.get("prevision_activa", False)
    triage_revisado = p.get("triage_revisado_por_clinico", False)
    documentos = p.get("documentos_presentados", [])
    
    print(f"[TRAZA VALIDADOR] Evaluando paciente {rut}: prevision_activa={prevision_activa}, triage_revisado={triage_revisado}, docs={len(documentos)}")
    
    if not prevision_activa:
        return {
            "estado": "no_califica",
            "explicacion": f"El paciente {p['nombre']} presenta previsión inactiva ({p['prevision']}). No califica para cobertura automática de urgencia estándar sin regularización.",
            "antecedentes_faltantes": ["Certificado de afiliación vigente o regularización previsional"],
            "reglas_aplicadas": reglas_aplicadas
        }
        
    if not triage_revisado:
        return {
            "estado": "no_califica",
            "explicacion": f"El paciente {p['nombre']} no cuenta con validación de triage por personal clínico de urgencia.",
            "antecedentes_faltantes": ["Validación de Triage por médico o enfermera de urgencia"],
            "reglas_aplicadas": reglas_aplicadas
        }
        
    # Verificar documentos mínimos (ej. cédula)
    tiene_identidad = any("cedula" in d.lower() or "pasaporte" in d.lower() for d in documentos)
    if not tiene_identidad:
        antecedentes_faltantes.append("Cédula de identidad o documento oficial de identificación")
        return {
            "estado": "falta_informacion",
            "explicacion": f"Faltan documentos de identificación (cédula o pasaporte) para el paciente {p['nombre']}.",
            "antecedentes_faltantes": antecedentes_faltantes,
            "reglas_aplicadas": reglas_aplicadas
        }
        
    return {
        "estado": "califica",
        "explicacion": f"El paciente {p['nombre']} cumple con previsión activa ({p['prevision']}), triage validado y documentos mínimos presentados bajo la Ley de Urgencia.",
        "antecedentes_faltantes": [],
        "reglas_aplicadas": reglas_aplicadas
    }
