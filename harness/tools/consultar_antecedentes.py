import json
import os

def buscar_paciente(rut):
    """
    Busca los antecedentes administrativos de un paciente por su RUT en pacientes_simulados.json.
    Imprime traza [TRAZA TOOL].
    Maneja RUT inexistente y archivo faltante de forma segura.
    """
    print(f"[TRAZA TOOL] Ejecutando buscar_paciente con rut={rut}")
    ruta_datos = os.path.join(os.path.dirname(__file__), "..", "..", "data", "pacientes_simulados.json")
    
    if not os.path.exists(ruta_datos):
        return {"error": "Archivo de pacientes simulados no encontrado.", "rut": rut}
    
    try:
        with open(ruta_datos, "r", encoding="utf-8") as f:
            pacientes = json.load(f)
    except Exception as e:
        return {"error": f"Error al leer la base de datos de pacientes: {str(e)}", "rut": rut}
    
    if rut not in pacientes:
        return {"error": "El RUT no está registrado. Verifique que esté bien digitado.", "rut": rut}
    
    paciente = pacientes[rut].copy()
    paciente.pop("esperado", None) # Ocultar campo esperado al LLM
    return {
        "estado": "encontrado",
        "datos": paciente
    }
