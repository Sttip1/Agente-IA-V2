"""Auditor: el harness NO decide el veredicto, lo verifica. Devuelve un mensaje de error
para que el LLM corrija, o None si la respuesta es aceptable."""
import re

from harness.reglas import REGLAS
from harness.utilidades import extraer_ruts, norm, normalizar_rut

FRASES_PROHIBIDAS = re.compile(
    r"\b(autorizo|apruebo|se autoriza|queda autorizad[oa]|queda aprobad[oa]|ingreso (autorizado|aprobado)|"
    r"se recomienda (el )?ingres|debe ingresar a (uci|hospitalizacion)|reclasific[oa] (el )?triage a)\b")


_STOP_RAICES = {"para", "como", "este", "esta", "sobre", "desde", "entre", "hasta", "cual", "donde", "ausente"}


def _raices(texto):
    """Raíces (6 letras) de las palabras significativas, para comparar antecedentes parafraseados."""
    return {w[:6] for w in re.findall(r"[a-z0-9]+", norm(texto)) if len(w) >= 4 and w not in _STOP_RAICES}


NARRACION = re.compile(r"\b(ejecutando|ejecutare|ejecuto|llamando|llamare|procedo a|voy a (usar|utilizar|consultar|llamar|ejecutar))\b")


def narra_una_tool(texto, nombres_tools):
    """True si el texto anuncia que va a usar/ejecutar una tool ("Ejecutando evaluar_reglas...")."""
    t = norm(texto)
    return bool(NARRACION.search(t)) and any(n in t for n in nombres_tools)


def auditar(msg, texto_usuario, ejecuto_tool, evaluaciones, nombres_tools=(), tools_usadas=(), hay_contexto=True, limites=()):
    """msg ya cumple el esquema. evaluaciones: {rut: resultado del motor} del turno actual.
    tools_usadas: tools ejecutadas en el turno; hay_contexto: la sesión tiene RUTs/casos previos; limites: valores válidos de 'limite'."""
    tipo = msg["tipo"]
    if tipo == "respuesta":
        base = msg["base"]
        if base == "herramienta" and not any(t != "cargar_skill" for t in tools_usadas):
            return ("AUDITORÍA: declaraste base='herramienta' pero no consultaste ninguna herramienta de información en este turno. "
                    "Si la consulta es de admisión de urgencias, llama la herramienta adecuada; si es ambigua, pregunta con base='aclaracion'; "
                    "si no tiene relación con admisión de urgencias, usa tipo 'fuera_de_alcance'. No respondas con datos que no vienen de una herramienta. "
                    "Para llamar una herramienta tu mensaje debe ser SOLO el JSON de la llamada, por ejemplo "
                    '{"tool": "consultar_registro", "args": {"rut": "<RUT del contexto>"}} para datos del paciente '
                    "o consultar_convenio para convenios y coberturas.")
        if base == "memoria" and not hay_contexto:
            return "AUDITORÍA: declaraste base='memoria' pero la sesión no tiene casos ni RUTs previos. Pide al usuario el dato (base='aclaracion')."
    if tipo == "fuera_de_alcance":
        citadas = [n for n in nombres_tools if n != "cargar_skill" and n in norm(msg["texto"])]
        if citadas:
            return ("AUDITORÍA: no le indiques al usuario que ejecute herramientas (" + ", ".join(citadas) + "): las ejecutas tú. "
                    "Si la consulta es de admisión de urgencias, tu mensaje debe ser SOLO el JSON de la llamada a la herramienta; "
                    "si de verdad no es de tu función, usa fuera_de_alcance sin mencionar herramientas.")
    if tipo == "fuera_de_alcance" and limites and norm(msg["limite"]) not in [norm(x) for x in limites]:
        return f"AUDITORÍA: 'limite' debe ser exactamente uno de: {list(limites)}."
    textos = " ".join(str(msg.get(c, "")) for c in ("texto", "explicacion"))
    if tipo == "respuesta" and ejecuto_tool and narra_una_tool(msg["texto"], nombres_tools):
        return ("AUDITORÍA: ya tienes los resultados de las herramientas. No describas acciones ('Ejecutando...'): "
                "entrega ahora la respuesta final con los datos obtenidos (veredicto si te pidieron verificar un caso).")
    if tipo != "fuera_de_alcance" and FRASES_PROHIBIDAS.search(norm(textos)):
        return ("AUDITORÍA: tu texto autoriza/aprueba/recomienda ingresos o cobros, lo que excede tus límites. "
                "Reescribe describiendo solo la verificación administrativa.")
    if tipo == "respuesta" and extraer_ruts(texto_usuario) and not ejecuto_tool:
        return "AUDITORÍA: el usuario mencionó un RUT; consulta las herramientas antes de responder sobre ese paciente."
    if tipo != "veredicto":
        return None
    rut = normalizar_rut(msg["rut"])
    ref = evaluaciones.get(rut)
    if ref is None:
        return (f"AUDITORÍA: diste un veredicto para {rut} sin haber llamado a evaluar_reglas con ese RUT en este turno. "
                "Llama a la herramienta y basa tu veredicto en su evidencia.")
    if msg["estado"] != ref["estado"]:
        return (f"AUDITORÍA: tu estado '{msg['estado']}' contradice la evidencia de las reglas, que según la política de estados "
                f"corresponde a '{ref['estado']}'. Corrige estado, antecedentes_faltantes y explicación.")
    if msg["estado"] == "califica" and msg["antecedentes_faltantes"]:
        return "AUDITORÍA: un caso que califica no puede tener antecedentes_faltantes."
    if msg["estado"] != "califica" and not msg["antecedentes_faltantes"]:
        return f"AUDITORÍA: el estado es {msg['estado']}; debes listar antecedentes_faltantes. Según las reglas: {ref['antecedentes_faltantes']}."
    if msg["estado"] != "califica" and ref["antecedentes_faltantes"]:
        ref_raices = set().union(*(_raices(a) for a in ref["antecedentes_faltantes"]))
        ajenos = [a for a in msg["antecedentes_faltantes"] if not (_raices(a) & ref_raices)]
        sin_cubrir = [a for a in ref["antecedentes_faltantes"] if not any(_raices(a) & _raices(m) for m in msg["antecedentes_faltantes"])]
        if ajenos or sin_cubrir:
            return ("AUDITORÍA: los antecedentes_faltantes no corresponden a la evidencia de las reglas de ESTE caso"
                    + (f" (no respaldados: {ajenos})" if ajenos else "") + (f" (sin mencionar: {sin_cubrir})" if sin_cubrir else "")
                    + f". Según evaluar_reglas deben ser: {ref['antecedentes_faltantes']}. No copies frases de los ejemplos de la skill; "
                    "redacta la explicación con la evidencia real.")
    desconocidas = [r for r in msg["reglas_aplicadas"] if r not in REGLAS]
    if desconocidas:
        return f"AUDITORÍA: reglas_aplicadas contiene IDs inexistentes {desconocidas}. IDs válidos: {list(REGLAS)}."
    return None


def tool_pendiente(msg, texto_usuario, ejecuto_tool, nombres_tools):
    """Detecta una 'respuesta' que en realidad era una llamada a tool NARRADA ("Ejecutando evaluar_reglas...")
    o que contesta sobre un RUT sin haber consultado nada. Devuelve la llamada que el modelo debió emitir
    ({"tool", "args"}; args puede ir vacío si no se pueden deducir) o None."""
    if msg["tipo"] != "respuesta" or ejecuto_tool:
        return None
    ruts = extraer_ruts(texto_usuario)
    if ruts and "evaluar_reglas" in nombres_tools:
        en_texto = [r for r in extraer_ruts(msg["texto"]) if r in ruts]
        return {"tool": "evaluar_reglas", "args": {"rut": (en_texto or ruts)[0]}}
    t = norm(msg["texto"])
    if "buscar_reglamento" in nombres_tools and "buscar_reglamento" in t:
        return {"tool": "buscar_reglamento", "args": {"consulta": texto_usuario}}
    otras = [n for n in nombres_tools if n in t and n != "cargar_skill"]
    return {"tool": otras[0], "args": {}} if otras else None


def forzar_desde_reglas(evaluaciones, rut):
    """Veredicto construido solo con el motor de reglas (último recurso si el LLM sigue contradiciéndolas)."""
    ref = evaluaciones[normalizar_rut(rut)]
    ev = "; ".join(f"{i}: {v[1]}" for i, v in ref["detalle"].items())
    return {"tipo": "veredicto", "rut": ref["rut"], "estado": ref["estado"],
            "explicacion": f"Resultado según las reglas de negocio. Evidencia: {ev}.",
            "antecedentes_faltantes": ref["antecedentes_faltantes"],
            "reglas_aplicadas": list(ref["detalle"]), "auditoria": "corregido_por_auditor"}
