"""Mejoras surgidas de una prueba real con gemma3:4b: copia de ejemplos de la skill, mandar al usuario a ejecutar tools
y respuestas que repiten el tipo de la pregunta anterior."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import SK, T, V, agente_con  # noqa: E402

COPIADO = V("19649180-5", "falta_informacion", ["Certificado de afiliación vigente o regularización previsional"], ["R2_PREVISION_ACTIVA", "R5_REGISTRO_COMPLETO"],
            "La previsión del paciente figura inactiva. Solicite un certificado de afiliación vigente.")
CORRECTO = V("19649180-5", "falta_informacion", ["Registro del paciente en el sistema (RUT no encontrado o mal digitado)"], ["R1_RUT_VALIDO", "R5_REGISTRO_COMPLETO"],
             "No existe un registro para este RUT. Verifique que esté bien digitado.")


def test_antecedentes_copiados_de_un_ejemplo_de_la_skill_se_rechazan():
    ag, llm = agente_con([T("evaluar_reglas", rut="19649180-5"), SK, COPIADO, CORRECTO])
    r = ag.turno("dime si el paciente 19649180-5 es apto")
    assert r["antecedentes_faltantes"] == CORRECTO["antecedentes_faltantes"]
    assert r["auditoria"] == "ok_tras_1_correcciones"
    assert "no corresponden a la evidencia" in llm.llamadas[3][-1]["content"]
    assert "Registro del paciente en el sistema" in llm.llamadas[3][-1]["content"]


def test_si_el_modelo_insiste_en_copiar_se_entrega_el_resultado_de_las_reglas():
    ag, _ = agente_con([T("evaluar_reglas", rut="19649180-5"), SK, COPIADO, COPIADO, COPIADO])
    r = ag.turno("dime si el paciente 19649180-5 es apto")
    assert r["auditoria"] == "corregido_por_auditor"
    assert "Registro del paciente" in r["antecedentes_faltantes"][0]


def test_paráfrasis_razonable_de_los_antecedentes_se_acepta():
    ag, _ = agente_con([T("evaluar_reglas", rut="22222222-2"), SK,
                        V("22222222-2", "no_califica", ["Regularizar la previsión: certificado de afiliación vigente"], ["R2_PREVISION_ACTIVA"])])
    assert ag.turno("verifica 22222222-2")["auditoria"] == "ok"


def test_fuera_de_alcance_que_manda_al_usuario_a_ejecutar_una_tool_se_rechaza():
    mal = {"tipo": "fuera_de_alcance", "texto": "Debe consultar la herramienta consultar_registro con el RUT.", "limite": "fuera de función"}
    ag, llm = agente_con([mal, T("consultar_registro", rut="11111111-1"),
                          {"tipo": "respuesta", "base": "herramienta", "texto": "La previsión del paciente 11111111-1 es Fonasa A."}])
    ag.mem.ruts.add("11111111-1")
    r = ag.turno("dime su previsión")
    assert r["tipo"] == "respuesta" and r["tools_usadas"] == ["consultar_registro"]
    assert "las ejecutas tú" in llm.llamadas[1][-1]["content"]


def test_tras_cada_resultado_de_tool_se_recuerda_la_pregunta_actual():
    ag, llm = agente_con([T("consultar_registro", rut="11111111-1"),
                          {"tipo": "respuesta", "base": "herramienta", "texto": "La previsión del paciente 11111111-1 es Fonasa A."}])
    ag.turno("dime la previsión del 11111111-1")
    ultimo = llm.llamadas[1][-1]["content"]
    assert "RESULTADO_TOOL consultar_registro" in ultimo and "pregunta ACTUAL" in ultimo and "dime la previsión del 11111111-1" in ultimo
