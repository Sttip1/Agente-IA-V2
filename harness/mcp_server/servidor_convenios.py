import sys
import json

CONVENIOS_SIMULADOS = {
    "isapre banmedica": {
        "convenio_vigente": True,
        "cobertura_urgencia": "80%",
        "observacion": "Convenio GES de urgencia vital activo."
    },
    "isapre colmena": {
        "convenio_vigente": True,
        "cobertura_urgencia": "85%",
        "observacion": "Convenio preferencial urgencias."
    },
    "fonasa a": {
        "convenio_vigente": True,
        "cobertura_urgencia": "100%",
        "observacion": "Cobertura institucional Ley de Urgencia (Tramo A)."
    },
    "fonasa c": {
        "convenio_vigente": True,
        "cobertura_urgencia": "90%",
        "observacion": "Cobertura institucional Ley de Urgencia (Tramo C)."
    },
    "particular": {
        "convenio_vigente": False,
        "cobertura_urgencia": "0%",
        "observacion": "Pago directo o evaluación de asistencia social."
    }
}

def consultar_convenio(prevision):
    """Consulta el convenio institucional para una previsión dada."""
    clave = prevision.lower().strip()
    # Buscar coincidencia parcial
    for k, v in CONVENIOS_SIMULADOS.items():
        if k in clave or clave in k:
            return {
                "prevision": prevision,
                "resultado": "encontrado",
                **v
            }
    return {
        "prevision": prevision,
        "resultado": "no_encontrado",
        "convenio_vigente": False,
        "observacion": "No se registra convenio específico preestablecido. Se aplica Ley de Urgencia estándar."
    }

def main():
    sys.stderr.write("[MCP SERVER] Servidor de convenios iniciado por stdio.\n")
    sys.stderr.flush()

    while True:
        linea = sys.stdin.readline()
        if not linea:
            break
        linea = linea.strip()
        if not linea:
            continue

        try:
            req = json.loads(linea)
        except json.JSONDecodeError as e:
            res = {
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": f"Parse error: {str(e)}"},
                "id": None
            }
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()
            continue

        method = req.get("method")
        req_id = req.get("id")

        if method == "initialize":
            res = {
                "jsonrpc": "2.0",
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "serverInfo": {
                        "name": "servidor_convenios",
                        "version": "0.1.0"
                    }
                },
                "id": req_id
            }
        elif method == "tools/list":
            res = {
                "jsonrpc": "2.0",
                "result": {
                    "tools": [
                        {
                            "name": "consultar_convenio",
                            "description": "Consulta el estado de convenios institucionales para una previsión de salud en la Clínica X.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "prevision": {"type": "string"}
                                },
                                "required": ["prevision"]
                            }
                        }
                    ]
                },
                "id": req_id
            }
        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            arguments = params.get("arguments", {})
            
            if name == "consultar_convenio":
                prevision = arguments.get("prevision", "")
                sys.stderr.write(f"[MCP SERVER] Ejecutando consultar_convenio para prevision={prevision}\n")
                sys.stderr.flush()
                tool_res = consultar_convenio(prevision)
                res = {
                    "jsonrpc": "2.0",
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(tool_res, ensure_ascii=False)
                            }
                        ]
                    },
                    "id": req_id
                }
            else:
                res = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Method/Tool not found: {name}"},
                    "id": req_id
                }
        else:
            res = {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Method not found: {method}"},
                "id": req_id
            }

        sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
