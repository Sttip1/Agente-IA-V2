"""Memoria de la sesión: historial acotado + contexto estructurado (RUTs y casos ya verificados)."""
from harness.config import EJECUCION_DEFECTO


class Memoria:
    def __init__(self, system, ventana=EJECUCION_DEFECTO["ventana_mensajes"]):
        self.system, self.ventana_max = system, ventana
        self.msgs, self.ruts, self.casos = [], set(), {}

    def add(self, rol, contenido):
        self.msgs.append({"role": rol, "content": contenido})

    def ventana(self):
        m = self.msgs[-self.ventana_max:]
        while m and m[0]["role"] != "user":
            m = m[1:]
        ctx = ["", "", "## Contexto de sesión (memoria)"]
        ctx.append("- RUTs mencionados por el usuario en esta sesión: " + (", ".join(sorted(self.ruts)) or "ninguno"))
        if self.casos:
            ctx.append("- Casos ya verificados: " + "; ".join(f"{r} -> {e}" for r, e in self.casos.items()))
        return [{"role": "system", "content": self.system + "\n".join(ctx)}] + m

    def reiniciar(self):
        self.msgs, self.ruts, self.casos = [], set(), {}
