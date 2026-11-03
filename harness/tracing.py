"""Trazabilidad: registro estructurado (JSONL) de cada evento, con identificador de ejecución (run_id).

Cada evento incluye: ts, run_id, sesion, session_id, turno, evento, version del agente y los datos propios del evento
(usuario, inicio, llm, tool, skill, validacion, auditoria, final, fin, errores...). Una ejecución completa se reconstruye
filtrando por run_id, tanto en el archivo logs/ejecucion.jsonl como en el endpoint GET /logs?run_id=...

Los RUTs se enmascaran en disco (11.***.***-1); en pantalla se muestran trazas cortas si verbose=True.
No se registran credenciales: el arnés no maneja ninguna."""
import datetime
import json
import os
import threading
import uuid

from harness.utilidades import ocultar_ruts

MAX_EVENTOS_EN_MEMORIA = 5000


class Log:
    def __init__(self, ruta=None, verbose=True, version_agente=None):
        self.ruta, self.verbose, self.sesion, self.turno = ruta, verbose, uuid.uuid4().hex[:8], 0
        self.version_agente = version_agente
        self.run_id, self.session_id = None, None
        self.eventos, self._aviso = [], False
        self._lock = threading.Lock()
        if ruta:
            try:
                os.makedirs(os.path.dirname(ruta), exist_ok=True)
            except OSError:
                self.ruta = None

    def iniciar_ejecucion(self, run_id, session_id=None):
        self.run_id, self.session_id = run_id, session_id

    def ev(self, tipo, traza=None, **datos):
        e = {"ts": datetime.datetime.now().isoformat(timespec="milliseconds"), "run_id": self.run_id,
             "sesion": self.sesion, "session_id": self.session_id, "turno": self.turno,
             "version_agente": self.version_agente, "evento": tipo, **datos}
        with self._lock:
            self.eventos.append(e)
            if len(self.eventos) > MAX_EVENTOS_EN_MEMORIA:
                del self.eventos[: len(self.eventos) - MAX_EVENTOS_EN_MEMORIA]
        if self.verbose and traza:
            print(f"  [{tipo.upper()}] {traza}")
        if self.ruta:
            try:
                with self._lock, open(self.ruta, "a", encoding="utf-8") as f:
                    f.write(ocultar_ruts(json.dumps(e, ensure_ascii=False, default=str)) + "\n")
            except OSError:
                if not self._aviso:
                    self._aviso = True
                    print("  [AVISO] No se pudo escribir el log en disco.")

    def eventos_de(self, run_id):
        with self._lock:
            return [e for e in self.eventos if e.get("run_id") == run_id]

    def ultimos(self, n=100):
        with self._lock:
            return list(self.eventos[-n:])
