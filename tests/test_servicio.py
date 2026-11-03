"""Capa de servicio de la API (sin servidor): /health, /metadata, /run y /logs, incluidos los códigos HTTP de error."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import SK, LLMFalso, T, V  # noqa: E402

from app.servicio import Servicio  # noqa: E402
from harness.errores import LLMNoDisponible  # noqa: E402


def servicio(guion):
    return Servicio(llm=LLMFalso(guion), usar_mcp=False, log_ruta=None)


def test_health():
    s = servicio([])
    d = s.salud()
    assert d["status"] == "ok" and d["agente"] == "P02" and d["version"] == "2.0.0"


def test_health_profundo_informa_si_el_llm_no_responde():
    s = servicio([])
    s.llm.disponible = lambda: (False, "Ollama no responde")
    d = s.salud(profundo=True)
    assert d["status"] == "degraded" and d["llm"]["disponible"] is False


def test_metadata_describe_al_agente():
    m = servicio([]).metadata()
    assert m["id"] == "P02" and m["version"] == "2.0.0"
    assert {t["name"] for t in m["tools"]} >= {"evaluar_reglas", "buscar_reglamento", "consultar_convenio"}
    assert set(m["salidas"]) == {"veredicto", "respuesta", "fuera_de_alcance"}
    assert "clasificar-antecedente-faltante" in m["skills"] and m["ejecucion"]["max_pasos"] == 8
    assert "POST /run" in m["endpoints"]


def test_run_ok_devuelve_run_id_y_resultado():
    s = servicio([T("evaluar_reglas", rut="11111111-1"), V("11111111-1", "califica")])
    codigo, cuerpo = s.ejecutar({"mensaje": "Dime si el 11111111-1 es apto"})
    assert codigo == 200
    assert cuerpo["resultado"]["estado"] == "califica" and cuerpo["run_id"] == cuerpo["resultado"]["run_id"]
    assert cuerpo["session_id"] and cuerpo["latencia_ms"] >= 0


def test_run_con_entrada_invalida_devuelve_422_sin_llamar_al_llm():
    s = servicio([])
    for malo in ({}, {"mensaje": ""}, {"mensaje": "hola", "extra": 1}, {"mensaje": "hola", "session_id": "con espacios"}):
        codigo, cuerpo = s.ejecutar(malo)
        assert codigo == 422 and cuerpo["error"] == "entrada_invalida" and cuerpo["detalles"]
    assert s.llm.llamadas == []


def test_run_mantiene_la_memoria_por_sesion():
    s = servicio([T("evaluar_reglas", rut="33333333-3"), SK, V("33333333-3", "falta_informacion", ["Cédula de identidad del paciente"]),
                  {"tipo": "respuesta", "base": "memoria", "texto": "Le falta la cédula de identidad."}])
    s.ejecutar({"mensaje": "revisa 33333333-3", "session_id": "mesa-1"})
    codigo, cuerpo = s.ejecutar({"mensaje": "¿y qué le falta?", "session_id": "mesa-1"})
    assert codigo == 200 and cuerpo["resultado"]["base"] == "memoria"
    assert cuerpo["session_id"] == "mesa-1"


def test_run_sesiones_distintas_no_comparten_memoria():
    s = servicio([T("evaluar_reglas", rut="11111111-1"), V("11111111-1", "califica"),
                  {"tipo": "respuesta", "base": "aclaracion", "texto": "¿De qué paciente habla?"}])
    s.ejecutar({"mensaje": "revisa 11111111-1", "session_id": "a"})
    codigo, cuerpo = s.ejecutar({"mensaje": "¿y qué le falta?", "session_id": "b"})
    assert codigo == 200 and cuerpo["resultado"]["base"] == "aclaracion"


@pytest.mark.parametrize("guion,codigo_http,codigo_error", [
    ([LLMNoDisponible("Ollama apagado")], 503, "llm_no_disponible"),
    (["basura"] * 4, 502, "formato_invalido"),
])
def test_run_traduce_los_errores_a_codigos_http(guion, codigo_http, codigo_error):
    s = servicio(guion)
    codigo, cuerpo = s.ejecutar({"mensaje": "hola"})
    assert codigo == codigo_http and cuerpo["resultado"]["codigo"] == codigo_error and cuerpo["run_id"]


def test_run_limite_de_pasos_es_504():
    s = servicio([T("consultar_registro", rut="11111111-1")] * 1)
    s.llm.guion = [T("buscar_reglamento", consulta=f"tema {i}") for i in range(12)]
    codigo, cuerpo = s.ejecutar({"mensaje": "hola 11111111-1"})
    assert codigo == 504 and cuerpo["resultado"]["codigo"] == "limite_pasos"


def test_logs_reconstruye_una_ejecucion_y_enmascara_ruts():
    s = servicio([T("evaluar_reglas", rut="11111111-1"), V("11111111-1", "califica")])
    _, run = s.ejecutar({"mensaje": "revisa 11111111-1"})
    codigo, cuerpo = s.logs(run["run_id"])
    assert codigo == 200 and cuerpo["total"] > 5
    assert [e["evento"] for e in cuerpo["eventos"]][0] == "inicio"
    assert "11111111-1" not in str(cuerpo)


def test_logs_run_id_desconocido_es_404_y_sin_run_id_devuelve_los_ultimos():
    s = servicio([{"tipo": "respuesta", "base": "saludo", "texto": "Hola"}])
    assert s.logs("noexiste")[0] == 404
    s.ejecutar({"mensaje": "hola"})
    codigo, cuerpo = s.logs(None, 3)
    assert codigo == 200 and cuerpo["total"] == 3
