from harness.tools.consultar_antecedentes import buscar_paciente
from harness.tools.validar_ley_urgencia import validar_ley_urgencia
from harness.tools.buscar_reglamento import buscar_reglamento
from harness.mcp_client import consultar_convenio_mcp

def wrapper_consultar_convenio(prevision):
    """Wrapper para consultar convenio vía MCP con traza [TRAZA MCP]."""
    print(f"[TRAZA MCP] Iniciando consulta de convenio para prevision='{prevision}'")
    return consultar_convenio_mcp(prevision)

# Registro central de tools de la Clínica X
REGISTRO_TOOLS = {
    "consultar_antecedentes": {
        "funcion": buscar_paciente,
        "descripcion": "Busca los antecedentes administrativos y datos de un paciente usando su RUT.",
        "parametros": {
            "rut": "string (ej: 11111111-1)"
        }
    },
    "validar_ley_urgencia": {
        "funcion": validar_ley_urgencia,
        "descripcion": "Valida si un paciente cumple con la Ley de Urgencia (previsión, triage y documentos).",
        "parametros": {
            "rut": "string (ej: 11111111-1)"
        }
    },
    "buscar_reglamento": {
        "funcion": buscar_reglamento,
        "descripcion": "Busca en el reglamento de urgencia y protocolos de admisión de la Clínica X.",
        "parametros": {
            "consulta": "string (texto o concepto a buscar)"
        }
    },
    "consultar_convenio": {
        "funcion": wrapper_consultar_convenio,
        "descripcion": "Consulta el convenio institucional y cobertura de urgencia para una previsión dada vía MCP.",
        "parametros": {
            "prevision": "string (ej: Isapre Banmedica, Fonasa A)"
        }
    }
}

def ejecutar_tool(nombre_tool, args):
    """Ejecuta una tool registrada a partir de su nombre y argumentos."""
    if nombre_tool not in REGISTRO_TOOLS:
        return {"error": f"Tool desconocida: '{nombre_tool}'. Herramientas disponibles: {list(REGISTRO_TOOLS.keys())}."}
    
    func = REGISTRO_TOOLS[nombre_tool]["funcion"]
    # Si args es dict o string
    if isinstance(args, dict):
        return func(**args)
    elif isinstance(args, str):
        return func(args)
    else:
        return func(args)
