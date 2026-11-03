"""Runtime del arnés: bucle del agente (LLM <-> tools) con validación de esquema, auditoría y trazabilidad.

    usuario -> [LLM decide] -> tool? -> resultado -> [LLM decide] -> ... -> respuesta final
                                                         |
                                       esquema (agent/output.schema.json) + auditor
"""
import json
import time
import uuid

from harness.auditor import auditar, forzar_desde_reglas, tool_pendiente
from harness.errores import LLMNoDisponible, ToolError
from harness.memoria import Memoria
from harness.prompt_builder import construir_prompt
from harness.schema_validator import validar_schema
from harness.tracing import Log
from harness.utilidades import extraer_json, extraer_ruts, normalizar_rut, refiere_a_paciente


class Agente:
    def __init__(self, llm, herramientas, declaracion, log=None):
        self.llm, self.herr, self.decl = llm, herramientas, declaracion
        self.cfg = declaracion.ejecucion
        self.log = log or Log(None, verbose=False)
        self.log.version_agente = self.log.version_agente or declaracion.version
        self.mem = Memoria(construir_prompt(declaracion, herramientas), self.cfg["ventana_mensajes"])
        self.skill_faltantes = declaracion.manifest.get("skill_para_faltantes")

    def _feedback(self, raw, texto):
        self.mem.add("assistant", raw)
        self.mem.add("user", texto)

    @staticmethod
    def _recordatorio(texto):
        """Tras cada resultado de tool se recuerda la pregunta ACTUAL: los modelos chicos tienden a repetir el tipo de la respuesta anterior."""
        return (f"Recuerda: responde a la pregunta ACTUAL del usuario («{texto[:200]}»). Si pidió verificar un caso, entrega un veredicto; "
                "si preguntó un dato puntual (previsión, convenio, cobertura, normativa), entrega una respuesta con base 'herramienta' usando este resultado.")

    def _ejecutar(self, nombre, args, llamadas, tools_usadas, asistida=False):
        """Ejecuta una tool capturando cualquier error, la registra y devuelve su resultado como texto."""
        t0 = time.time()
        try:
            resultado = self.herr.registro[nombre]["fn"](**args)
        except (LLMNoDisponible, ToolError) as e:
            resultado = {"error": str(e)}
        except Exception as e:  # una tool nunca debe tumbar el agente
            resultado = {"error": f"Fallo interno de la tool: {type(e).__name__}: {e}"}
        rtxt = json.dumps(resultado, ensure_ascii=False)
        llamadas[(nombre, json.dumps(args, sort_keys=True))] = rtxt
        tools_usadas.append(nombre)
        self.log.ev("tool", traza=f"{nombre}({args}) -> {rtxt[:200]}", tool=nombre, args=args,
                    ms=int((time.time() - t0) * 1000), resultado=resultado, asistida=asistida)
        if nombre == "cargar_skill" and "error" not in resultado:
            self.log.ev("skill", traza=f"skill cargada: {resultado['skill']}", skill=resultado["skill"])
        return rtxt

    def turno(self, texto, session_id=None):
        """Ejecuta una consulta completa. Devuelve el resultado con su 'run_id' (clave para reconstruirla en /logs)."""
        run_id = uuid.uuid4().hex[:12]
        self.log.turno += 1
        self.log.iniciar_ejecucion(run_id, session_id)
        t0 = time.time()
        self.log.ev("inicio", entrada=texto, agente=self.decl.manifest["id"], version_agente=self.decl.version,
                    modelo=getattr(self.llm, "modelo", "desconocido"), parametros=self.cfg,
                    tools=list(self.herr.registro))
        try:
            resultado = self._turno(texto)
        except Exception as e:  # el servicio nunca debe caer por un error inesperado del arnés
            self.log.ev("error_interno", traza=f"{type(e).__name__}: {e}", error=f"{type(e).__name__}: {e}")
            resultado = {"tipo": "error", "codigo": "error_interno", "texto": "Error interno del agente. Revise los logs con el run_id."}
        resultado["run_id"] = run_id
        self.log.ev("fin", tipo_resultado=resultado.get("tipo"), estado=resultado.get("estado"), codigo=resultado.get("codigo"),
                    auditoria=resultado.get("auditoria"), latencia_ms=int((time.time() - t0) * 1000))
        return resultado

    def _fuera_de_funcion(self):
        """Salida del arnés cuando el modelo insiste en consultar datos de un paciente que el mensaje no menciona."""
        self.log.ev("fuera_de_funcion", traza="el modelo insistió en consultar un paciente que el mensaje no menciona")
        return {"tipo": "fuera_de_alcance", "limite": "fuera de función", "origen": "harness",
                "texto": "Esa consulta no parece de admisión de urgencias. Puedo verificar si un caso califica (indíqueme el RUT), "
                         "explicar qué antecedentes faltan y responder sobre la normativa interna y los convenios."}

    def _turno(self, texto):
        cfg = self.cfg
        texto = (texto or "").strip()
        if sum(c.isalnum() for c in texto) < 2:   # vacío, "^V", "???", un solo carácter...
            return {"tipo": "respuesta", "origen": "harness",
                    "texto": "No entendí su consulta. Escriba una pregunta o el RUT de un paciente (ej: 11111111-1)."}
        err_entrada = validar_schema({"mensaje": texto}, self.decl.schema_entrada)
        if err_entrada:
            self.log.ev("validacion_entrada", traza=err_entrada, error=err_entrada)
            return {"tipo": "error", "codigo": "entrada_invalida", "texto": f"Consulta inválida: {err_entrada}"}
        self.mem.ruts.update(extraer_ruts(texto))
        self.mem.add("user", texto)
        self.herr.nuevo_turno()
        self.log.ev("usuario", mensaje=texto)
        ejecuto_tool, fallos, correcciones, llamadas, tools_usadas = False, 0, 0, {}, []
        skill_recordada, pendientes, asistidas, bloqueos = False, 0, [], 0

        for paso in range(1, cfg["max_pasos"] + 1):
            t0 = time.time()
            try:
                mensajes = self.mem.ventana()
                if paso == 1:
                    self.log.ev("prompt", prompt_efectivo=mensajes, n_mensajes=len(mensajes))
                raw = self.llm.chat(mensajes)
            except LLMNoDisponible as e:
                self.log.ev("error_llm", traza=str(e), error=str(e))
                return {"tipo": "error", "codigo": "llm_no_disponible", "texto": f"No pude consultar el modelo de lenguaje: {e}"}
            self.log.ev("llm", traza=f"paso {paso}: {raw.strip()[:160]}", paso=paso, ms=int((time.time() - t0) * 1000), respuesta=raw)

            msg = extraer_json(raw)
            if msg is None:
                fallos += 1
                self.log.ev("formato", traza="respuesta sin JSON válido", intento=fallos)
                if fallos > cfg["max_formato"]:
                    return {"tipo": "error", "codigo": "formato_invalido", "texto": "El modelo no produjo una respuesta con formato válido. Intente reformular la consulta."}
                self._feedback(raw, 'FORMATO: responde SOLO con un objeto JSON: una llamada {"tool":...,"args":{...}} o una respuesta final con "tipo".')
                continue

            # ---------------- llamada a tool ----------------
            if "tool" in msg:
                nombre, args = msg.get("tool"), msg.get("args") if msg.get("args") is not None else {}
                if nombre not in self.herr.registro:
                    fallos += 1
                    self.log.ev("tool_invalida", traza=f"tool inexistente o no habilitada: {nombre}", tool=str(nombre))
                    if fallos > cfg["max_formato"]:
                        return {"tipo": "error", "codigo": "tool_invalida", "texto": "El modelo solicitó herramientas inexistentes repetidamente."}
                    if nombre in self.decl.schema_salida:   # confundió un TIPO de respuesta final con una herramienta
                        self._feedback(raw, f"FORMATO: '{nombre}' no es una herramienta, es un tipo de respuesta final. No uses la clave "
                                            f'"tool": usa "tipo". Ejemplo: {{"tipo": "fuera_de_alcance", "limite": "fuera de función", '
                                            f'"texto": "..."}}. Las herramientas son: {list(self.herr.registro)}.')
                    else:
                        self._feedback(raw, f"La herramienta '{nombre}' no existe. Disponibles: {list(self.herr.registro)}.")
                    continue
                err = self.herr.validar_args(nombre, args)
                if err:
                    fallos += 1
                    self.log.ev("tool_invalida", traza=err, tool=nombre)
                    if fallos > cfg["max_formato"]:
                        return {"tipo": "error", "codigo": "argumentos_invalidos", "texto": "El modelo no logró invocar las herramientas con argumentos válidos."}
                    self._feedback(raw, "ERROR DE ARGUMENTOS: " + err)
                    continue
                if self.herr.requiere_rut_del_usuario(nombre) and normalizar_rut(args.get("rut", "")) not in self.mem.ruts:
                    self.log.ev("rut_bloqueado", traza=f"RUT no proporcionado por el usuario: {args['rut']}", tool=nombre)
                    bloqueos += 1
                    if bloqueos > 2:
                        return self._fuera_de_funcion()
                    self._feedback(raw, f"BLOQUEADO: el usuario no ha escrito el RUT {args['rut']}. No inventes RUTs. "
                                        f"Pídele al usuario un RUT válido (ej: 11111111-1) con tipo 'respuesta'.")
                    continue
                if self.herr.requiere_rut_del_usuario(nombre) and not refiere_a_paciente(texto):
                    # El RUT está en la sesión, pero este mensaje no habla de ningún paciente (p. ej. "¿a qué hora es la colación?").
                    self.log.ev("rut_bloqueado", traza="el mensaje no se refiere a ningún paciente; no se usa el RUT del contexto", tool=nombre)
                    bloqueos += 1
                    if bloqueos > 2:
                        return self._fuera_de_funcion()
                    self._feedback(raw, "BLOQUEADO: el mensaje del usuario no se refiere a ningún paciente, así que no corresponde consultar datos de uno. "
                                        'Si la consulta no es de admisión de urgencias, responde SOLO {"tipo": "fuera_de_alcance", '
                                        '"limite": "fuera de función", "texto": "..."}.')
                    continue
                firma = (nombre, json.dumps(args, sort_keys=True))
                if firma in llamadas:
                    self._feedback(raw, f"Ya ejecutaste {nombre} con esos argumentos. Resultado previo: {llamadas[firma]}. "
                                        "No la repitas: entrega la respuesta final.")
                    continue
                rtxt = self._ejecutar(nombre, args, llamadas, tools_usadas)
                ejecuto_tool = True
                self._feedback(raw, f"RESULTADO_TOOL {nombre}: {rtxt}\n" + self._recordatorio(texto))
                continue

            # ---------------- respuesta final ----------------
            tipo = msg.get("tipo")
            if tipo not in self.decl.schema_salida:
                fallos += 1
                if fallos > cfg["max_formato"]:
                    return {"tipo": "error", "codigo": "formato_invalido", "texto": "El modelo no entregó una respuesta final con formato válido."}
                self._feedback(raw, f"FORMATO: 'tipo' debe ser uno de {list(self.decl.schema_salida)} (o llamar una tool).")
                continue
            err = validar_schema(msg, self.decl.schema_salida[tipo])
            if err:
                fallos += 1
                self.log.ev("validacion", traza=f"esquema inválido: {err}", error=err)
                if fallos > cfg["max_formato"]:
                    return {"tipo": "error", "codigo": "salida_invalida", "texto": "El modelo no logró producir una salida válida según el esquema."}
                self._feedback(raw, f"ERROR DE ESQUEMA ({tipo}): {err}")
                continue

            # El modelo "narró" una tool (p. ej. "Ejecutando evaluar_reglas...") en vez de llamarla.
            # 1.º aviso con el JSON exacto que debe emitir; si insiste y la llamada es deducible, la ejecuta el
            # harness por él (queda registrado como tool_asistida y en msg["tools_asistidas"]).
            sug = tool_pendiente(msg, texto, ejecuto_tool, list(self.herr.registro))
            if sug:
                pendientes += 1
                asistible = not self.herr.validar_args(sug["tool"], sug["args"])
                self.log.ev("tool_pendiente", traza=f"el modelo describió la tool {sug['tool']} en vez de llamarla (intento {pendientes})",
                            n=pendientes, tool=sug["tool"])
                if not asistible:
                    sug = {"tool": sug["tool"], "args": {p: "<valor>" for p in self.herr.registro[sug["tool"]]["params"]}}
                if pendientes == 1:
                    self._feedback(raw, "AUDITORÍA: escribir que vas a usar una herramienta NO la ejecuta. Para ejecutarla tu mensaje "
                                        "debe ser SOLO este JSON, sin más texto: " + json.dumps(sug, ensure_ascii=False))
                    continue
                if asistible:
                    rtxt = self._ejecutar(sug["tool"], sug["args"], llamadas, tools_usadas, asistida=True)
                    ejecuto_tool = True
                    asistidas.append(sug["tool"])
                    self.log.ev("tool_asistida", traza=f"el harness ejecutó {sug['tool']} en lugar del modelo")
                    self._feedback(raw, f"RESULTADO_TOOL {sug['tool']}: {rtxt}\n{self._recordatorio(texto)}\nNOTA: el sistema ejecutó la herramienta por ti porque "
                                        "no emitiste la llamada. Con este resultado, entrega ahora la respuesta final.")
                    continue
                correcciones += 1
                if correcciones > cfg["max_correcciones"]:
                    return {"tipo": "fuera_de_alcance", "limite": "auditoría", "origen": "harness",
                            "texto": "No pude consultar la herramienta necesaria para responder. Un funcionario debe revisar esta consulta."}
                self._feedback(raw, "AUDITORÍA: no emitiste la llamada. Tu mensaje debe ser SOLO este JSON, completando los valores: "
                                    + json.dumps(sug, ensure_ascii=False))
                continue

            msg_aud = auditar(msg, texto, ejecuto_tool, self.herr.evaluaciones, list(self.herr.registro), tools_usadas,
                              bool(self.mem.casos or len(self.mem.ruts) > len(extraer_ruts(texto))),
                              self.decl.manifest["limites"])
            if msg_aud:
                correcciones += 1
                self.log.ev("auditoria", traza=msg_aud, n=correcciones)
                if correcciones > cfg["max_correcciones"]:
                    # Último recurso: si ya hay evidencia de reglas para un RUT del turno, se entrega el resultado de las reglas.
                    candidatos = ([normalizar_rut(msg["rut"])] if tipo == "veredicto" else []) + extraer_ruts(texto)
                    rut_ref = next((r for r in candidatos if r in self.herr.evaluaciones), None)
                    if rut_ref:
                        final = forzar_desde_reglas(self.herr.evaluaciones, rut_ref)
                        final["tools_asistidas"], final["tools_usadas"] = asistidas, tools_usadas
                        self.log.ev("auditoria_forzada", traza="se entrega el resultado de las reglas", final=final)
                        self.mem.add("assistant", json.dumps(final, ensure_ascii=False))
                        self.mem.casos[final["rut"]] = final["estado"]
                        return final
                    return {"tipo": "fuera_de_alcance", "limite": "auditoría", "origen": "harness",
                            "texto": "No pude dar una respuesta que cumpla las reglas de verificación. Un funcionario debe revisar este caso."}
                self._feedback(raw, msg_aud)
                continue

            # Skill declarada en el manifest: se exige (con un solo recordatorio) en veredictos con faltantes.
            if (tipo == "veredicto" and msg["estado"] != "califica" and self.skill_faltantes
                    and "cargar_skill" in self.herr.registro and self.skill_faltantes not in self.herr.skills_cargadas):
                if not skill_recordada:
                    skill_recordada = True
                    self.log.ev("skill_pendiente", traza=f"falta cargar la skill {self.skill_faltantes}")
                    self._feedback(raw, f"SKILL: antes de dar este veredicto carga la skill '{self.skill_faltantes}' con cargar_skill "
                                        "y úsala para redactar la explicación y los antecedentes faltantes.")
                    continue
                self.log.ev("skill_omitida", traza=f"el modelo no cargó la skill {self.skill_faltantes}; se acepta el veredicto")

            self.mem.add("assistant", raw)
            if tipo == "veredicto":
                self.mem.casos[normalizar_rut(msg["rut"])] = msg["estado"]
            msg["auditoria"] = "ok" if correcciones == 0 else f"ok_tras_{correcciones}_correcciones"
            msg["tools_usadas"] = tools_usadas
            msg["tools_asistidas"] = asistidas
            msg["skills_usadas"] = sorted(self.herr.skills_cargadas)
            self.log.ev("final", traza=f"{tipo} {msg.get('estado', '')}".strip(), pasos=paso, final=msg)
            return msg

        self.log.ev("limite_pasos", traza="se superó el máximo de pasos")
        return {"tipo": "error", "codigo": "limite_pasos", "texto": "No logré concluir la consulta en el número máximo de pasos. Intente de nuevo o reformule."}
