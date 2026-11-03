"""Cliente MCP persistente por stdio: arranca el servidor una vez, lee con timeout
(hilo + cola; funciona en Windows) y se reinicia solo si el servidor muere."""
import contextlib
import json
import os
import queue
import subprocess
import sys
import threading
import time

from harness.config import BASE_DIR, MCP_TIMEOUT
from harness.errores import ToolError


class MCPClient:
    def __init__(self, comando=None, timeout=MCP_TIMEOUT):
        self.comando = comando or [sys.executable, "-m", "harness.mcp_server"]
        self.timeout, self.proc, self.q, self._id = timeout, None, None, 0
        self.lock = threading.Lock()

    @staticmethod
    def _leer(proc, q):
        try:
            for linea in proc.stdout:
                q.put(linea)
        except (OSError, ValueError):
            pass
        finally:
            q.put(None)
            try:
                proc.stdout.close()   # lo cierra el propio hilo lector: evita fugas de descriptores
            except (OSError, ValueError):
                pass

    def _enviar(self, obj):
        try:
            self.proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        except (OSError, ValueError) as e:
            self.cerrar()
            raise ToolError(f"No se pudo escribir al servidor MCP: {e}") from e

    def _rpc(self, metodo, params=None):
        self._id += 1
        rid = self._id
        self._enviar({"jsonrpc": "2.0", "id": rid, "method": metodo, **({"params": params} if params is not None else {})})
        limite = time.time() + self.timeout
        while True:
            try:
                linea = self.q.get(timeout=max(0.01, limite - time.time()))
            except queue.Empty as e:
                self.cerrar()
                raise ToolError(f"Timeout ({self.timeout}s) esperando al servidor MCP en '{metodo}'") from e
            if linea is None:
                self.cerrar()
                raise ToolError("El servidor MCP terminó inesperadamente")
            try:
                msg = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if msg.get("id") != rid:
                continue
            if "error" in msg:
                raise ToolError(f"MCP error: {msg['error'].get('message', msg['error'])}")
            return msg.get("result", {})

    def _asegurar(self):
        if self.proc and self.proc.poll() is None:
            return
        if self.proc:        # el servidor murió: libera sus pipes antes de relanzarlo
            self.cerrar()
        env = dict(os.environ, PYTHONIOENCODING="utf-8",
                   PYTHONPATH=BASE_DIR + os.pathsep + os.environ.get("PYTHONPATH", ""))
        # comando fijo (sys.executable -m harness.mcp_server) o inyectado por código; nunca viene del usuario
        self.proc = subprocess.Popen(  # noqa: S603  # nosec B603
            self.comando, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            encoding="utf-8", errors="replace", bufsize=1, env=env, cwd=BASE_DIR)
        self.q = queue.Queue()
        threading.Thread(target=self._leer, args=(self.proc, self.q), daemon=True).start()
        self._rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                 "clientInfo": {"name": "agente_p02", "version": "1.0.0"}})
        self._enviar({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def listar_tools(self):
        with self.lock:
            self._asegurar()
            return self._rpc("tools/list").get("tools", [])

    def llamar(self, nombre, argumentos):
        with self.lock:
            self._asegurar()
            res = self._rpc("tools/call", {"name": nombre, "arguments": argumentos})
        texto = (res.get("content") or [{}])[0].get("text", "")
        if res.get("isError"):
            raise ToolError(texto or "Error MCP")
        try:
            return json.loads(texto)
        except json.JSONDecodeError:
            return {"resultado": texto}

    def cerrar(self):
        p, self.proc = self.proc, None
        if p:
            try:
                p.stdin.close()
            except (OSError, ValueError):
                pass
            with contextlib.suppress(Exception):   # cierre best-effort: el proceso puede estar ya muerto
                p.terminate()
                p.wait(timeout=2)
