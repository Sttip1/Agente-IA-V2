import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import SK, SKILL_FALTANTES, LLMFalso, T, V, agente_con  # noqa: E402

from harness.auditor import forzar_desde_reglas  # noqa: E402
from harness.datos import cargar_documentos, cargar_pacientes  # noqa: E402
from harness.declarativo import cargar_declaracion  # noqa: E402
from harness.errores import LLMNoDisponible  # noqa: E402
from harness.presentacion import render  # noqa: E402
from harness.rag import RAG  # noqa: E402
from harness.runtime import Agente  # noqa: E402
from harness.tool_registry import Herramientas  # noqa: E402
from harness.tracing import Log  # noqa: E402

AFIL = "Certificado de afiliación vigente o regularización previsional"
TRIAGE = "Validación de triage por personal clínico"
CEDULA = "Cédula de identidad o documento oficial de identificación"


class TestFlujoBasico(unittest.TestCase):
    def test_califica_con_tools(self):
        ag, _ = agente_con([T("evaluar_reglas", rut="11111111-1"), V("11111111-1", "califica")])
        r = ag.turno("Revisa el paciente 11111111-1")
        self.assertEqual((r["tipo"], r["estado"], r["auditoria"]), ("veredicto", "califica", "ok"))
        self.assertEqual(r["tools_usadas"], ["evaluar_reglas"])
        self.assertEqual(r["skills_usadas"], [])        # un caso que califica no necesita la skill

    def test_el_llm_no_recibe_el_estado_de_las_reglas(self):
        ag, llm = agente_con([T("evaluar_reglas", rut="22222222-2"), SK, V("22222222-2", "no_califica", [AFIL])])
        ag.turno("caso 22222222-2")
        resultado = [m["content"] for m in llm.llamadas[1] if m["content"].startswith("RESULTADO_TOOL evaluar_reglas")][0]
        self.assertNotIn('"estado"', resultado)
        self.assertIn("INACTIVA", resultado)

    def test_rut_con_puntos(self):
        ag, _ = agente_con([T("evaluar_reglas", rut="11.111.111-1"), V("11111111-1", "califica")])
        self.assertEqual(ag.turno("revisa 11.111.111-1")["estado"], "califica")

    def test_rut_inexistente(self):
        ag, _ = agente_con([T("evaluar_reglas", rut="99999999-9"), SK,
                            V("99999999-9", "falta_informacion", ["Registro del paciente en el sistema"],
                              ["R1_RUT_VALIDO", "R5_REGISTRO_COMPLETO"])])
        self.assertEqual(ag.turno("revisa 99999999-9")["estado"], "falta_informacion")

    def test_menor_y_extranjero_califican(self):
        for rut in ("55555555-5", "66666666-6"):
            ag, _ = agente_con([T("evaluar_reglas", rut=rut), V(rut, "califica")])
            self.assertEqual(ag.turno(f"revisa {rut}")["estado"], "califica", rut)

    def test_memoria_de_seguimiento_sin_repetir_rut(self):
        ag, llm = agente_con([T("evaluar_reglas", rut="33333333-3"), SK, V("33333333-3", "falta_informacion", [CEDULA]),
                              {"tipo": "respuesta", "base": "memoria", "texto": "Le falta la cédula de identidad."}])
        ag.turno("revisa 33333333-3")
        r = ag.turno("¿y qué le falta?")
        self.assertEqual(r["tipo"], "respuesta")
        ultimo = llm.llamadas[-1]
        self.assertIn("33333333-3 -> falta_informacion", ultimo[0]["content"])
        self.assertTrue(any("revisa 33333333-3" in m["content"] for m in ultimo))

    def test_reset_de_memoria(self):
        ag, _ = agente_con([T("evaluar_reglas", rut="11111111-1"), V("11111111-1", "califica")])
        ag.turno("revisa 11111111-1")
        ag.mem.reiniciar()
        self.assertEqual((ag.mem.msgs, ag.mem.ruts, ag.mem.casos), ([], set(), {}))


class TestSkills(unittest.TestCase):
    def test_skill_se_exige_en_no_califica(self):
        ag, llm = agente_con([T("evaluar_reglas", rut="22222222-2"),
                              V("22222222-2", "no_califica", [AFIL]),       # sin skill -> recordatorio
                              SK,
                              V("22222222-2", "no_califica", [AFIL])])
        r = ag.turno("caso 22222222-2")
        self.assertEqual((r["estado"], r["auditoria"]), ("no_califica", "ok"))
        self.assertEqual(r["skills_usadas"], [SKILL_FALTANTES])
        self.assertTrue(any(m["content"].startswith("SKILL:") for m in llm.llamadas[2]))

    def test_skill_omitida_se_acepta_tras_un_solo_recordatorio(self):
        ag, _ = agente_con([T("evaluar_reglas", rut="22222222-2"),
                            V("22222222-2", "no_califica", [AFIL]), V("22222222-2", "no_califica", [AFIL])])
        r = ag.turno("caso 22222222-2")
        self.assertEqual(r["estado"], "no_califica")
        self.assertTrue(any(e["evento"] == "skill_omitida" for e in ag.log.eventos))

    def test_skill_no_se_exige_si_cargar_skill_no_esta_habilitada(self):
        ag, _ = agente_con([T("evaluar_reglas", rut="22222222-2"), V("22222222-2", "no_califica", [AFIL])],
                           permitidas=["evaluar_reglas"])
        self.assertEqual(ag.turno("caso 22222222-2")["estado"], "no_califica")


class TestAuditoria(unittest.TestCase):
    def test_veredicto_sin_tools_es_rechazado_y_corregido(self):
        ag, _ = agente_con([V("44444444-4", "califica"),               # alucinación
                            T("evaluar_reglas", rut="44444444-4"), SK,
                            V("44444444-4", "no_califica", [TRIAGE])])
        r = ag.turno("Revisa el paciente 44444444-4")
        self.assertEqual(r["estado"], "no_califica")
        self.assertEqual(r["auditoria"], "ok_tras_1_correcciones")

    def test_estado_contradictorio_se_corrige_con_feedback(self):
        ag, llm = agente_con([T("evaluar_reglas", rut="33333333-3"), V("33333333-3", "califica"),
                              SK, V("33333333-3", "falta_informacion", [CEDULA])])
        r = ag.turno("revisa 33333333-3")
        self.assertEqual(r["estado"], "falta_informacion")
        self.assertTrue(any("AUDITORÍA" in m["content"] for m in llm.llamadas[2]))

    def test_llm_terco_se_fuerza_el_resultado_de_las_reglas(self):
        ag, _ = agente_con([T("evaluar_reglas", rut="44444444-4")] + [V("44444444-4", "califica")] * 3)
        r = ag.turno("revisa 44444444-4")
        self.assertEqual((r["estado"], r["auditoria"]), ("no_califica", "corregido_por_auditor"))
        self.assertIn("corregido por el auditor", render(r))

    def test_estado_califica_con_faltantes_y_viceversa(self):
        ag, _ = agente_con([T("evaluar_reglas", rut="11111111-1"), V("11111111-1", "califica", ["algo"]),
                            V("11111111-1", "califica")])
        r = ag.turno("revisa 11111111-1")
        # la regla condicional del schema de salida (califica => sin faltantes) la atrapa antes que el auditor
        self.assertEqual((r["estado"], r["antecedentes_faltantes"]), ("califica", []))
        self.assertTrue(any(e["evento"] == "validacion" for e in ag.log.eventos))

    def test_reglas_inexistentes_se_rechazan(self):
        ag, _ = agente_con([T("evaluar_reglas", rut="11111111-1"), V("11111111-1", "califica", reglas=["R9_FALSA"]),
                            V("11111111-1", "califica")])
        self.assertEqual(ag.turno("revisa 11111111-1")["auditoria"], "ok_tras_1_correcciones")

    def test_rut_inventado_bloqueado(self):
        ag, _ = agente_con([T("evaluar_reglas", rut="11111111-1"),
                            {"tipo": "respuesta", "base": "aclaracion", "texto": "Necesito un RUT válido para continuar."}])
        r = ag.turno("revisa al paciente de la cama 3")
        self.assertEqual(r["tipo"], "respuesta")
        self.assertEqual(ag.herr.evaluaciones, {})
        self.assertTrue(any(e["evento"] == "rut_bloqueado" for e in ag.log.eventos))

    def test_respuesta_sobre_rut_sin_tools_es_rechazada(self):
        ag, _ = agente_con([{"tipo": "respuesta", "base": "herramienta", "texto": "Ese paciente está bien."},
                            T("evaluar_reglas", rut="11111111-1"), V("11111111-1", "califica")])
        self.assertEqual(ag.turno("¿cómo está 11111111-1?")["tipo"], "veredicto")

    def test_texto_que_autoriza_es_auditado(self):
        ag, _ = agente_con([{"tipo": "respuesta", "base": "herramienta", "texto": "Apruebo el ingreso del paciente."},
                            {"tipo": "fuera_de_alcance", "texto": "No decido el ingreso.", "limite": "NO decide el ingreso final"}])
        self.assertEqual(ag.turno("¿ingresa?")["tipo"], "fuera_de_alcance")

    def test_auditoria_agotada_sin_evidencia_deriva_a_humano(self):
        ag, _ = agente_con([V("44444444-4", "califica")] * 3)
        r = ag.turno("revisa 44444444-4")
        self.assertEqual((r["tipo"], r["origen"]), ("fuera_de_alcance", "harness"))

    def test_forzar_desde_reglas_directo(self):
        ag, _ = agente_con([T("evaluar_reglas", rut="22222222-2"), SK, V("22222222-2", "no_califica", [AFIL])])
        ag.turno("caso 22222222-2")
        f = forzar_desde_reglas(ag.herr.evaluaciones, "22222222-2")
        self.assertEqual((f["estado"], f["auditoria"]), ("no_califica", "corregido_por_auditor"))


NARRA_EVALUAR = {"tipo": "respuesta", "base": "herramienta", "texto": "Ejecutando la herramienta evaluar_reglas con el RUT 11111111-1..."}


class TestModeloQueNarraLaTool(unittest.TestCase):
    """Caso real observado con gemma3:4b: escribe 'Ejecutando la herramienta...' como respuesta en vez de emitir la llamada."""

    def test_el_aviso_incluye_el_json_exacto(self):
        ag, llm = agente_con([NARRA_EVALUAR, T("evaluar_reglas", rut="11111111-1"), V("11111111-1", "califica")])
        r = ag.turno("Dime si el 11111111-1 es apto")
        self.assertEqual(r["estado"], "califica")
        self.assertEqual(r["tools_asistidas"], [])          # corrigió solo, con el primer aviso
        aviso = llm.llamadas[1][-1]["content"]
        self.assertIn('{"tool": "evaluar_reglas", "args": {"rut": "11111111-1"}}', aviso)

    def test_si_insiste_el_harness_ejecuta_la_tool_por_el(self):
        ag, llm = agente_con([NARRA_EVALUAR, NARRA_EVALUAR, V("11111111-1", "califica")])
        r = ag.turno("Dime si el paciente 11111111-1 es apto para ley de urgencias")
        self.assertEqual((r["tipo"], r["estado"]), ("veredicto", "califica"))
        self.assertEqual(r["tools_asistidas"], ["evaluar_reglas"])
        self.assertIn("evaluar_reglas", r["tools_usadas"])
        self.assertTrue(any(e["evento"] == "tool_asistida" for e in ag.log.eventos))
        self.assertTrue(any(e["evento"] == "tool" and e["asistida"] for e in ag.log.eventos))
        self.assertIn("NOTA: el sistema ejecutó", llm.llamadas[2][-1]["content"])

    def test_la_asistencia_no_se_salta_la_auditoria_del_veredicto(self):
        # Tras la ejecución asistida el modelo sigue obligado a dar un estado coherente (y a cargar la skill).
        ag, _ = agente_con([{"tipo": "respuesta", "base": "herramienta", "texto": "Ejecutando evaluar_reglas con 22222222-2"},
                            {"tipo": "respuesta", "base": "herramienta", "texto": "Ejecutando evaluar_reglas con 22222222-2"},
                            V("22222222-2", "califica"), SK, V("22222222-2", "no_califica", [AFIL])])
        r = ag.turno("¿el 22222222-2 es apto?")
        self.assertEqual(r["estado"], "no_califica")
        self.assertEqual(r["auditoria"], "ok_tras_1_correcciones")

    def test_narra_buscar_reglamento_sin_rut(self):
        narra = {"tipo": "respuesta", "base": "herramienta", "texto": "Ejecutando buscar_reglamento sobre urgencia vital..."}
        ag, _ = agente_con([narra, narra, {"tipo": "respuesta", "base": "herramienta", "texto": "Artículo 1 (reglamento_urgencia.md): urgencia vital es ..."}])
        r = ag.turno("¿Qué dice el reglamento sobre la urgencia vital?")
        self.assertEqual(r["tools_asistidas"], ["buscar_reglamento"])

    def test_narrador_terco_termina_con_el_resultado_de_las_reglas(self):
        # Caso reproducido: el modelo narra una y otra vez, incluso después de que el harness ejecutó la tool.
        ag, _ = agente_con([NARRA_EVALUAR] * 6)
        r = ag.turno("Dime si el 11111111-1 es apto")
        self.assertEqual((r["tipo"], r["estado"], r["auditoria"]), ("veredicto", "califica", "corregido_por_auditor"))
        self.assertEqual(r["tools_asistidas"], ["evaluar_reglas"])

    def test_narracion_residual_tras_ejecutar_la_tool_se_rechaza(self):
        ag, llm = agente_con([T("evaluar_reglas", rut="11111111-1"), NARRA_EVALUAR, V("11111111-1", "califica")])
        r = ag.turno("Dime si el 11111111-1 es apto")
        self.assertEqual(r["estado"], "califica")
        self.assertIn("ya tienes los resultados", llm.llamadas[2][-1]["content"])

    def test_una_respuesta_normal_no_se_confunde_con_narracion(self):
        ag, _ = agente_con([{"tipo": "respuesta", "base": "saludo", "texto": "Hola, ¿en qué puedo ayudarle?"}])
        r = ag.turno("Hola")
        self.assertEqual((r["tipo"], r["tools_asistidas"]), ("respuesta", []))


class TestLimitesLosDecideElLLM(unittest.TestCase):
    def test_fuera_de_alcance_llega_al_llm(self):
        ag, llm = agente_con([{"tipo": "fuera_de_alcance", "texto": "No diagnostico.", "limite": "NO diagnostica"}])
        r = ag.turno("¿Qué diagnóstico tiene el paciente?")
        self.assertEqual(r["tipo"], "fuera_de_alcance")
        self.assertEqual(len(llm.llamadas), 1)   # no hubo lista de palabras bloqueadas

    def test_pregunta_legitima_con_palabra_ingreso_no_se_bloquea(self):
        ag, _ = agente_con([T("buscar_reglamento", consulta="documentos para ingreso a urgencia"),
                            {"tipo": "respuesta", "base": "herramienta", "texto": "Se requiere cédula de identidad (protocolo_admision.md)."}])
        r = ag.turno("¿Qué documentos piden para el ingreso a urgencia?")
        self.assertEqual(r["tipo"], "respuesta")
        self.assertIn("buscar_reglamento", r["tools_usadas"])

    def test_rag_real_a_traves_del_agente(self):
        ag, llm = agente_con([T("buscar_reglamento", consulta="urgencia vital"),
                              {"tipo": "respuesta", "base": "herramienta", "texto": "Artículo 1 del reglamento."}])
        ag.turno("¿Qué dice el reglamento sobre la urgencia vital?")
        resultado = [m["content"] for m in llm.llamadas[1] if m["content"].startswith("RESULTADO_TOOL buscar_reglamento")][0]
        self.assertIn("reglamento_urgencia.md", resultado)
        self.assertIn('"estado": "encontrado"', resultado)


class TestRobustez(unittest.TestCase):
    def test_json_mal_formado_reintenta(self):
        ag, _ = agente_con(["esto no es json", "tampoco", {"tipo": "respuesta", "base": "saludo", "texto": "Hola, ¿en qué ayudo?"}])
        self.assertEqual(ag.turno("hola")["tipo"], "respuesta")

    def test_json_mal_formado_agota_reintentos(self):
        ag, _ = agente_con(["x"] * 5)
        self.assertEqual(ag.turno("hola")["tipo"], "error")

    def test_tipo_desconocido_y_esquema_invalido(self):
        ag, _ = agente_con([{"tipo": "cualquiera"}, {"tipo": "respuesta"}, {"tipo": "respuesta", "base": "saludo", "texto": "ok"}])
        self.assertEqual(ag.turno("hola")["texto"], "ok")

    def test_tool_inexistente_y_argumentos_invalidos(self):
        ag, _ = agente_con([T("borrar_todo"), {"tool": "evaluar_reglas", "args": {"rut": "11111111-1", "x": 1}},
                            T("evaluar_reglas", rut="11111111-1"), V("11111111-1", "califica")])
        self.assertEqual(ag.turno("revisa 11111111-1")["estado"], "califica")

    def test_tool_repetida_no_se_reejecuta(self):
        ag, llm = agente_con([T("evaluar_reglas", rut="11111111-1"), T("evaluar_reglas", rut="11111111-1"),
                              V("11111111-1", "califica")])
        ag.turno("revisa 11111111-1")
        self.assertTrue(any("Ya ejecutaste" in m["content"] for m in llm.llamadas[2]))

    def test_llm_caido_no_tumba_el_agente(self):
        ag, _ = agente_con([LLMNoDisponible("Ollama apagado")])
        r = ag.turno("revisa 11111111-1")
        self.assertEqual(r["tipo"], "error")
        self.assertIn("Ollama apagado", r["texto"])

    def test_entrada_basura_no_llega_al_llm(self):
        ag, llm = agente_con([])
        for basura in ("", "   ", "^V ???", "?"):
            self.assertEqual(ag.turno(basura)["origen"], "harness")
        self.assertEqual(llm.llamadas, [])

    def test_limite_de_pasos(self):
        ag, _ = agente_con([T("buscar_reglamento", consulta=f"tema {i}") for i in range(8)])
        self.assertEqual(ag.turno("pregunta infinita")["tipo"], "error")

    def test_tool_que_lanza_excepcion(self):
        ag, _ = agente_con([T("evaluar_reglas", rut="11111111-1"), V("11111111-1", "califica"),
                            {"tipo": "respuesta", "base": "herramienta", "texto": "No pude evaluar el caso por un error del sistema."}])
        ag.herr.registro["evaluar_reglas"]["fn"] = lambda rut: 1 / 0
        r = ag.turno("revisa 11111111-1")
        self.assertEqual(r["tipo"], "respuesta")
        tool_ev = [e for e in ag.log.eventos if e["evento"] == "tool"][0]
        self.assertIn("Fallo interno", tool_ev["resultado"]["error"])
        self.assertTrue(any(e["evento"] == "auditoria" for e in ag.log.eventos))


class TestLogs(unittest.TestCase):
    def test_eventos_completos_y_rut_enmascarado(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "l.jsonl")
            decl, llm = cargar_declaracion(), LLMFalso([T("evaluar_reglas", rut="11111111-1"), V("11111111-1", "califica")])
            herr = Herramientas(cargar_pacientes(), RAG(cargar_documentos(), llm, cache_dir=None),
                                skills=decl.skills, permitidas=decl.manifest["tools"])
            Agente(llm, herr, decl, Log(ruta, verbose=False)).turno("revisa 11111111-1")
            with open(ruta, encoding="utf-8") as f:
                texto = f.read()
            self.assertNotIn("11111111-1", texto)
            for ev in ("usuario", "llm", "tool", "final"):
                self.assertIn(f'"evento": "{ev}"', texto)




class TestBaseDeLaRespuesta(unittest.TestCase):
    def test_respuesta_con_base_herramienta_sin_haber_consultado_es_rechazada(self):
        ag, llm = agente_con([{"tipo": "respuesta", "base": "herramienta", "texto": "La colación es a las 13:00."},
                              {"tipo": "fuera_de_alcance", "texto": "Eso no es de admisión de urgencias.", "limite": "fuera de función"}])
        r = ag.turno("dame la hora de la colacion")
        self.assertEqual(r["tipo"], "fuera_de_alcance")
        self.assertIn("base='herramienta'", llm.llamadas[1][-1]["content"])

    def test_base_memoria_sin_contexto_es_rechazada(self):
        ag, _ = agente_con([{"tipo": "respuesta", "base": "memoria", "texto": "Como dijimos antes, califica."},
                            {"tipo": "respuesta", "base": "aclaracion", "texto": "¿De qué paciente habla? Indíqueme su RUT."}])
        self.assertEqual(ag.turno("¿y qué le falta?")["base"], "aclaracion")

    def test_limite_invalido_en_fuera_de_alcance_es_rechazado(self):
        ag, llm = agente_con([{"tipo": "fuera_de_alcance", "texto": "No puedo.", "limite": "porque sí"},
                              {"tipo": "fuera_de_alcance", "texto": "No puedo.", "limite": "fuera de función"}])
        self.assertEqual(ag.turno("¿qué tiempo hará mañana?")["limite"], "fuera de función")
        self.assertIn("uno de", llm.llamadas[1][-1]["content"])

    def test_aclaracion_ante_pregunta_ambigua_se_acepta_sin_tools(self):
        ag, _ = agente_con([{"tipo": "respuesta", "base": "aclaracion", "texto": "¿Se refiere a la previsión de un paciente o a un convenio?"}])
        r = ag.turno("dime la prevision de isapre")
        self.assertEqual((r["tipo"], r["tools_usadas"]), ("respuesta", []))


if __name__ == "__main__":
    unittest.main()
