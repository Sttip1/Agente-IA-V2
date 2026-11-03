"""Servidor MCP (JSON-RPC 2.0 sobre stdio) de convenios institucionales.
Se ejecuta como proceso aparte:  python -m harness.mcp_server"""
import json
import re
import sys

from harness.utilidades import norm

CONVENIOS = {  # DATOS SIMULADOS
    "isapre banmedica": {"convenio_vigente": True, "cobertura_urgencia": "80%", "observacion": "Convenio de urgencia vital activo."},
    "isapre colmena": {"convenio_vigente": True, "cobertura_urgencia": "85%", "observacion": "Convenio preferencial urgencias."},
    "fonasa a": {"convenio_vigente": True, "cobertura_urgencia": "100%", "observacion": "Cobertura institucional Ley de Urgencia (Tramo A)."},
    "fonasa b": {"convenio_vigente": True, "cobertura_urgencia": "100%", "observacion": "Cobertura institucional Ley de Urgencia (Tramo B)."},
    "fonasa c": {"convenio_vigente": True, "cobertura_urgencia": "90%", "observacion": "Cobertura institucional Ley de Urgencia (Tramo C)."},
    "fonasa d": {"convenio_vigente": True, "cobertura_urgencia": "80%", "observacion": "Cobertura institucional Ley de Urgencia (Tramo D)."},
    "particular": {"convenio_vigente": False, "cobertura_urgencia": "0%", "observacion": "Pago directo o evaluación de asistencia social."},
}
ALIAS_CONVENIOS = {"banmedica": "isapre banmedica", "colmena": "isapre colmena"}


def consultar_convenio(prevision):
    k = norm(re.sub(r"\(.*?\)", "", prevision))  # ignora "(Morosidad)" y similares
    k = re.sub(r"\s+", " ", ALIAS_CONVENIOS.get(k, k))
    if k in CONVENIOS:
        return {"prevision": prevision, "resultado": "encontrado", "simulado": True, **CONVENIOS[k]}
    if k == "fonasa":
        return {"prevision": prevision, "resultado": "ambiguo", "mensaje": "Fonasa requiere indicar el tramo.",
                "opciones": ["Fonasa A", "Fonasa B", "Fonasa C", "Fonasa D"]}
    return {"prevision": prevision, "resultado": "no_encontrado", "convenio_vigente": None,
            "observacion": "No hay convenio registrado para esta previsión; no se puede afirmar vigencia."}


def servidor_mcp():
    """Servidor MCP mínimo (initialize, tools/list, tools/call, ping)."""
    for s in (sys.stdin, sys.stdout):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    def responder(rid, result=None, error=None):
        msg = {"jsonrpc": "2.0", "id": rid}
        msg.update({"error": error} if error else {"result": result})
        sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    for linea in sys.stdin:
        linea = linea.strip()
        if not linea:
            continue
        try:
            req = json.loads(linea)
        except json.JSONDecodeError as e:
            responder(None, error={"code": -32700, "message": f"Parse error: {e}"})
            continue
        if not isinstance(req, dict) or req.get("id") is None:
            continue  # notificaciones (p. ej. notifications/initialized): sin respuesta
        rid, metodo, params = req["id"], req.get("method"), req.get("params") or {}
        if metodo == "initialize":
            responder(rid, {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                            "serverInfo": {"name": "servidor_convenios", "version": "1.0.0"}})
        elif metodo == "ping":
            responder(rid, {})
        elif metodo == "tools/list":
            responder(rid, {"tools": [{
                "name": "consultar_convenio",
                "description": "Consulta el convenio institucional y la cobertura de urgencia de una previsión (ej: 'Isapre Colmena', 'Fonasa C').",
                "inputSchema": {"type": "object", "properties": {"prevision": {"type": "string"}}, "required": ["prevision"]},
            }]})
        elif metodo == "tools/call":
            if params.get("name") != "consultar_convenio":
                responder(rid, error={"code": -32601, "message": f"Tool no encontrada: {params.get('name')}"})
                continue
            prev = (params.get("arguments") or {}).get("prevision")
            if not isinstance(prev, str) or not prev.strip():
                responder(rid, {"isError": True, "content": [{"type": "text", "text": "Falta el argumento 'prevision' (string)."}]})
            else:
                responder(rid, {"content": [{"type": "text", "text": json.dumps(consultar_convenio(prev), ensure_ascii=False)}]})
        else:
            responder(rid, error={"code": -32601, "message": f"Method not found: {metodo}"})


if __name__ == "__main__":
    servidor_mcp()
