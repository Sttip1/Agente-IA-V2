"""Reglas de negocio R1..R5 (definidas por el grupo) y su motor determinista.
La tool evaluar_reglas entrega esta evidencia al LLM y el auditor la usa como referencia."""
from harness.utilidades import norm, normalizar_rut, rut_valido

REGLAS = {
    "R1_RUT_VALIDO": "El RUT tiene formato y dígito verificador válidos.",
    "R2_PREVISION_ACTIVA": "La previsión del paciente está activa/vigente.",
    "R3_TRIAGE_CLINICO": "El triage fue revisado y validado por personal clínico.",
    "R4_DOC_IDENTIDAD": "Se presentó cédula o pasaporte (certificado de nacimiento solo si es menor de edad).",
    "R5_REGISTRO_COMPLETO": "El registro existe y trae motivo, previsión activa, triage y documentos.",
}
CAMPOS_REQUERIDOS = ("motivo_consulta", "prevision_activa", "triage_revisado_por_clinico", "documentos_presentados")


def _doc_identidad_ok(documentos, es_menor):
    for d in documentos:
        n = norm(d)
        if any(k in n for k in ("cedula", "carnet", "pasaporte")):
            return True
        if es_menor and "certificado de nacimiento" in n:
            return True
    return False


def motor_reglas(rut, registro):
    """Evalúa las reglas. Función pura y determinista.
    cumple: True / False / None (dato ausente = no se puede afirmar)."""
    rut = normalizar_rut(rut)
    r = {}
    r["R1_RUT_VALIDO"] = (rut_valido(rut), f"RUT {rut}: " + ("dígito verificador correcto" if rut_valido(rut) else "formato o dígito verificador inválido"))
    if registro is None:
        r["R5_REGISTRO_COMPLETO"] = (False, "No existe registro para este RUT en el sistema")
        return {
            "rut": rut, "estado": "falta_informacion", "detalle": r,
            "antecedentes_faltantes": ["Registro del paciente en el sistema (RUT no encontrado o mal digitado)"],
        }
    act, tri, docs = (registro.get(k) for k in ("prevision_activa", "triage_revisado_por_clinico", "documentos_presentados"))
    act = act if isinstance(act, bool) else None
    tri = tri if isinstance(tri, bool) else None
    prev = registro.get("prevision") or "no informada"
    r["R2_PREVISION_ACTIVA"] = (act, f"Previsión '{prev}': " + {True: "activa", False: "INACTIVA", None: "dato ausente"}[act])
    r["R3_TRIAGE_CLINICO"] = (tri, "Triage " + {True: "revisado por clínico", False: "NO revisado por clínico", None: "dato ausente"}[tri])
    if isinstance(docs, list):
        ok = _doc_identidad_ok(docs, bool(registro.get("es_menor")))
        r["R4_DOC_IDENTIDAD"] = (ok, f"Documentos presentados: {docs or 'ninguno'}" + ("" if ok else " (falta documento de identidad aceptable)"))
    else:
        r["R4_DOC_IDENTIDAD"] = (None, "Documentos presentados: dato ausente")
    faltan = [c for c in CAMPOS_REQUERIDOS if registro.get(c) is None]
    r["R5_REGISTRO_COMPLETO"] = (not faltan, "Registro completo" if not faltan else f"Campos ausentes: {faltan}")

    faltantes = []
    if r["R1_RUT_VALIDO"][0] is False:
        faltantes.append("RUT con formato y dígito verificador válidos")
    if act is False:
        faltantes.append("Certificado de afiliación vigente o regularización previsional")
    elif act is None:
        faltantes.append("Estado de la previsión del paciente (dato ausente en el registro)")
    if tri is False:
        faltantes.append("Validación de triage por personal clínico")
    elif tri is None:
        faltantes.append("Estado de revisión de triage (dato ausente en el registro)")
    if r["R4_DOC_IDENTIDAD"][0] is False:
        faltantes.append("Cédula de identidad o documento oficial de identificación")
    elif r["R4_DOC_IDENTIDAD"][0] is None:
        faltantes.append("Documentos presentados (dato ausente en el registro)")
    extra = [c for c in faltan if c not in ("prevision_activa", "triage_revisado_por_clinico", "documentos_presentados")]
    if extra:
        faltantes.append("Datos ausentes en el registro: " + ", ".join(extra))

    if act is False or tri is False:
        estado = "no_califica"
    elif any(v[0] is not True for v in r.values()):
        estado = "falta_informacion"
    else:
        estado = "califica"
    return {"rut": rut, "estado": estado, "detalle": r, "antecedentes_faltantes": faltantes}
