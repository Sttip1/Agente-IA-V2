"""Registro de tools (cargado desde agent/tools.yaml). Las tools entregan HECHOS (registro, evidencia por regla, normativa,
convenios, instrucciones de skills); el veredicto lo redacta el LLM y lo audita el harness.

agent/tools.yaml declara cada tool (schemas, permisos); agent/manifest.yaml actúa como lista blanca:
solo las tools allí permitidas se exponen al LLM."""
from harness.declarativo import cargar_declaracion
from harness.errores import ToolError
from harness.reglas import REGLAS, motor_reglas
from harness.schema_validator import errores
from harness.utilidades import normalizar_rut, rut_valido


class Herramientas:
    """Registro de herramientas construido desde agent/tools.yaml.

    - Cada tool declarada se enlaza a su implementación: 'local' -> método de esta clase indicado en 'handler';
      'mcp' -> llamada al servidor MCP (la tool debe aparecer en tools/list del servidor).
    - El manifest actúa como lista blanca: solo lo permitido se expone al LLM.
    - Los argumentos se validan contra el input_schema declarado ANTES de ejecutar."""

    def __init__(self, pacientes, rag, mcp=None, skills=None, permitidas=None, especificaciones=None):
        self.pacientes, self.rag, self.mcp = pacientes, rag, mcp
        self.skills = skills or {}
        self.specs = especificaciones if especificaciones is not None else cargar_declaracion().tools
        self.evaluaciones = {}        # rut -> resultado del motor (referencia del auditor; se limpia por turno)
        self.skills_cargadas = set()  # skills cargadas en el turno actual
        self.avisos = []
        self.registro = {}
        self._publicadas_mcp = self._descubrir_mcp()
        for nombre, spec in self.specs.items():
            self._registrar(nombre, spec)
        if permitidas is not None:
            for t in permitidas:
                if t not in self.registro:
                    self.avisos.append(f"El manifest declara la tool '{t}' pero no está disponible en esta sesión.")
            self.registro = {t: self.registro[t] for t in permitidas if t in self.registro}
        if "evaluar_reglas" not in self.registro:
            self.avisos.append("evaluar_reglas no está habilitada: el agente no podrá emitir veredictos.")

    def _descubrir_mcp(self):
        """tools/list real del servidor MCP: {nombre: tool}. Vacío si no hay servidor o falla."""
        if not self.mcp or not any(s["origin"] == "mcp" for s in self.specs.values()):
            return {}
        try:
            return {t["name"]: t for t in self.mcp.listar_tools()}
        except ToolError as e:
            self.avisos.append(f"MCP no disponible, se omite: {e}")
            return {}

    def _registrar(self, nombre, spec):
        descripcion = spec["description"]
        if spec["origin"] == "local":
            if nombre == "cargar_skill":
                if not self.skills:
                    return
                descripcion += " Skills disponibles: " + ", ".join(self.skills) + "."
            fn = getattr(self, spec["handler"], None)
            if fn is None:
                self.avisos.append(f"tools.yaml: la tool '{nombre}' apunta al handler inexistente '{spec['handler']}'.")
                return
        else:
            if nombre not in self._publicadas_mcp:
                if self.mcp and not any("MCP no disponible" in a for a in self.avisos):
                    self.avisos.append(f"El servidor MCP no publica la tool declarada '{nombre}'.")
                return
            requeridos = set((self._publicadas_mcp[nombre].get("inputSchema") or {}).get("required", []))
            if requeridos != set(spec["input_schema"].get("required", [])):
                self.avisos.append(f"La tool MCP '{nombre}' publica argumentos requeridos {sorted(requeridos)} distintos a tools.yaml.")
            descripcion += " (vía MCP)"
            fn = (lambda n: lambda **kw: self.mcp.llamar(n, kw))(nombre)
        props = spec["input_schema"].get("properties", {})
        self.registro[nombre] = {
            "descripcion": descripcion,
            "params": {k: f"{v.get('type', 'string')}, {v.get('description', '')}".strip(", ") for k, v in props.items()},
            "fn": fn, "origen": spec["origin"], "spec": spec}

    def nuevo_turno(self):
        self.evaluaciones.clear()
        self.skills_cargadas.clear()

    def requiere_rut_del_usuario(self, nombre):
        return bool(self.registro[nombre]["spec"].get("permissions", {}).get("rut_must_come_from_user"))

    def validar_args(self, nombre, args):
        """None si los argumentos cumplen el input_schema declarado; si no, el motivo (se devuelve al LLM)."""
        if not isinstance(args, dict):
            return "'args' debe ser un objeto JSON."
        errs = errores(args, self.registro[nombre]["spec"]["input_schema"])
        for k, v in args.items():
            if isinstance(v, str) and not v.strip() and not any(f"'{k}'" in e or f".{k}:" in e for e in errs):
                errs.append(f"$.{k}: no puede estar vacío")
        if errs:
            esperados = list(self.registro[nombre]["params"])
            return f"Argumentos inválidos para {nombre}: " + "; ".join(errs) + f". Argumentos esperados: {esperados}."
        return None

    def descripcion_para_prompt(self):
        return "\n".join(f"- {n}({', '.join(i['params'])}): {i['descripcion']}" for n, i in self.registro.items())

    # --- tools locales ---
    def consultar_registro(self, rut):
        rut = normalizar_rut(rut)
        if rut not in self.pacientes:
            return {"estado": "no_encontrado", "rut": rut, "rut_valido": rut_valido(rut)}
        reg = {k: v for k, v in self.pacientes[rut].items() if k != "esperado"}  # 'esperado' es solo para tests
        return {"estado": "encontrado", "rut_valido": rut_valido(rut), "registro": reg}

    def evaluar_reglas(self, rut):
        rut = normalizar_rut(rut)
        res = motor_reglas(rut, self.pacientes.get(rut))
        self.evaluaciones[rut] = res   # referencia para el auditor; el LLM NO recibe 'estado'
        return {"rut": rut, "reglas": [
            {"id": i, "descripcion": REGLAS[i], "cumple": v[0], "evidencia": v[1]} for i, v in res["detalle"].items()]}

    def buscar_reglamento(self, consulta):
        return self.rag.buscar(consulta)

    def cargar_skill(self, nombre):
        nombre = nombre.strip()
        if nombre not in self.skills:
            return {"error": f"La skill '{nombre}' no existe. Disponibles: {list(self.skills)}"}
        self.skills_cargadas.add(nombre)
        return {"skill": nombre, "instrucciones": self.skills[nombre]["body"]}
