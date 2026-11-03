"""Trazabilidad: run_id por ejecución, eventos estructurados y reconstrucción de una ejecución desde los logs."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import SK, T, V, agente_con  # noqa: E402

from harness.tracing import Log  # noqa: E402

CEDULA = "Cédula de identidad del paciente"


def _eventos(ag, run_id):
    return [e["evento"] for e in ag.log.eventos_de(run_id)]


def test_cada_ejecucion_tiene_run_id_distinto_y_todos_sus_eventos_lo_llevan():
    ag, _ = agente_con([T("evaluar_reglas", rut="11111111-1"), V("11111111-1", "califica"),
                        {"tipo": "fuera_de_alcance", "texto": "No es de mi función.", "limite": "fuera de función"}])
    r1, r2 = ag.turno("revisa 11111111-1"), ag.turno("¿qué hora es la colación?")
    assert r1["run_id"] and r2["run_id"] and r1["run_id"] != r2["run_id"]
    assert all(e["run_id"] in (r1["run_id"], r2["run_id"]) for e in ag.log.eventos)


def test_una_ejecucion_se_reconstruye_desde_sus_eventos():
    ag, _ = agente_con([T("evaluar_reglas", rut="33333333-3"), SK, V("33333333-3", "falta_informacion", [CEDULA])])
    r = ag.turno("revisa 33333333-3", session_id="mesa-1")
    ev = _eventos(ag, r["run_id"])
    assert ev[0] == "inicio" and ev[-1] == "fin"
    for esperado in ("usuario", "prompt", "llm", "tool", "skill", "final"):
        assert esperado in ev, esperado
    inicio = ag.log.eventos_de(r["run_id"])[0]
    assert inicio["version_agente"] == "2.0.0" and inicio["modelo"] and inicio["entrada"] == "revisa 33333333-3"
    assert ag.log.eventos_de(r["run_id"])[0]["session_id"] == "mesa-1"


def test_el_log_registra_prompt_efectivo_llamadas_a_tools_validacion_y_latencia():
    ag, _ = agente_con([T("evaluar_reglas", rut="11111111-1"), V("11111111-1", "califica")])
    r = ag.turno("revisa 11111111-1")
    eventos = ag.log.eventos_de(r["run_id"])
    prompt = next(e for e in eventos if e["evento"] == "prompt")
    assert "Agente P02" in prompt["prompt_efectivo"][0]["content"]
    tool = next(e for e in eventos if e["evento"] == "tool")
    assert tool["tool"] == "evaluar_reglas" and tool["args"] == {"rut": "11111111-1"} and "ms" in tool
    fin = eventos[-1]
    assert fin["tipo_resultado"] == "veredicto" and fin["estado"] == "califica" and fin["latencia_ms"] >= 0


def test_los_errores_quedan_registrados_con_su_codigo():
    ag, _ = agente_con(["basura"] * 4)
    r = ag.turno("hola")
    fin = ag.log.eventos_de(r["run_id"])[-1]
    assert fin["codigo"] == "formato_invalido"
    assert [e for e in ag.log.eventos_de(r["run_id"]) if e["evento"] == "formato"]


def test_el_archivo_jsonl_es_estructurado_y_enmascara_ruts(tmp_path):
    ruta = tmp_path / "logs" / "ejecucion.jsonl"
    ag, _ = agente_con([T("evaluar_reglas", rut="11111111-1"), V("11111111-1", "califica")],
                       log=Log(str(ruta), verbose=False, version_agente="2.0.0"))
    r = ag.turno("revisa 11111111-1")
    texto = ruta.read_text(encoding="utf-8")
    assert "11111111-1" not in texto and "11.***.***-1" in texto
    lineas = [json.loads(linea) for linea in texto.splitlines()]
    assert all(linea["run_id"] == r["run_id"] for linea in lineas)


def test_error_inesperado_del_arnes_no_tumba_el_servicio():
    ag, _ = agente_con([])
    ag.mem.ventana = lambda: 1 / 0
    r = ag.turno("hola")
    assert (r["tipo"], r["codigo"]) == ("error", "error_interno")
    assert any(e["evento"] == "error_interno" for e in ag.log.eventos_de(r["run_id"]))
