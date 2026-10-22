import subprocess
import json
import os
import sys

class MCPClientStdio:
    """Cliente MCP mínimo por stdio que se comunica con el servidor de convenios."""
    
    def __init__(self):
        script_servidor = os.path.join(os.path.dirname(__file__), "mcp_server", "servidor_convenios.py")
        self.proc = subprocess.Popen(
            [sys.executable, script_servidor],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        self.request_id = 1
        self._inicializar()

    def _enviar_req(self, method, params=None):
        req = {
            "jsonrpc": "2.0",
            "method": method,
            "id": self.request_id
        }
        if params is not None:
            req["params"] = params
        self.request_id += 1

        linea = json.dumps(req, ensure_ascii=False) + "\n"
        self.proc.stdin.write(linea)
        self.proc.stdin.flush()

        respuesta_linea = self.proc.stdout.readline()
        if not respuesta_linea:
            return None
        return json.loads(respuesta_linea.strip())

    def _inicializar(self):
        res = self._enviar_req("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "runtime_mcp_client", "version": "0.1.0"}
        })
        return res

    def listar_tools(self):
        res = self._enviar_req("tools/list")
        if res and "result" in res:
            return res["result"].get("tools", [])
        return []

    def llamar_tool(self, nombre_tool, argumentos):
        print(f"[TRAZA MCP] Llamando tool MCP '{nombre_tool}' con argumentos: {argumentos}")
        res = self._enviar_req("tools/call", {
            "name": nombre_tool,
            "arguments": argumentos
        })
        if res and "result" in res:
            content = res["result"].get("content", [])
            if content and len(content) > 0:
                texto_resp = content[0].get("text", "{}")
                try:
                    return json.loads(texto_resp)
                except Exception:
                    return {"resultado": texto_resp}
        if res and "error" in res:
            return {"error": res["error"].get("message", "Error MCP desconocido")}
        return {"error": "Respuesta vacía del servidor MCP"}

    def cerrar(self):
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.terminate()
            self.proc.wait(timeout=2)
        except Exception:
            pass

def consultar_convenio_mcp(prevision):
    """Función de conveniencia para invocar la tool de convenio vía cliente MCP."""
    cliente = MCPClientStdio()
    try:
        resultado = cliente.llamar_tool("consultar_convenio", {"prevision": prevision})
        return resultado
    finally:
        cliente.cerrar()
