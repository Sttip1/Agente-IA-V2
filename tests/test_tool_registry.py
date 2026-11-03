"""Herramientas declaradas en agent/tools.yaml: carga, validación de argumentos, permisos, MCP y errores."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import T, V, agente_con  # noqa: E402

from harness.mcp_client import MCPClient  # noqa: E402
from harness.schema_validator import errores  # noqa: E402


@pytest.fixture(scope="module")
def mcp():
    c = MCPClient()
    yield c
    c.cerrar()


def test_el_registro_sale_de_tools_yaml():
    ag, _ = agente_con([])
    reg = ag.herr.registro
    assert set(reg) >= {"consultar_registro", "evaluar_reglas", "buscar_reglamento", "cargar_skill"}
    for nombre, info in reg.items():
        spec = ag.decl.tools[nombre]
        assert info["spec"] is spec
        assert spec["description"] in info["descripcion"]
        assert set(info["params"]) == set(spec["input_schema"]["properties"])


def test_cada_tool_declara_schemas_y_permisos():
    ag, _ = agente_con([])
    for nombre, spec in ag.decl.tools.items():
        assert spec["input_schema"]["type"] == "object", nombre
        assert spec["input_schema"].get("additionalProperties") is False, nombre
        assert spec["output_schema"], nombre
        assert "read_only" in spec["permissions"], nombre


@pytest.mark.parametrize("args,fragmento", [
    ({}, "falta el campo requerido 'rut'"),
    ({"rut": "11111111-1", "extra": "x"}, "campos no permitidos"),
    ({"rut": 123}, "debe ser string"),
    ({"rut": "   "}, "no puede estar vacío"),
])
def test_argumentos_invalidos_se_rechazan_con_motivo(args, fragmento):
    ag, _ = agente_con([])
    motivo = ag.herr.validar_args("evaluar_reglas", args)
    assert motivo and fragmento in motivo


def test_argumentos_validos_pasan():
    ag, _ = agente_con([])
    assert ag.herr.validar_args("evaluar_reglas", {"rut": "11111111-1"}) is None


def test_el_resultado_de_cada_tool_local_cumple_su_output_schema():
    ag, _ = agente_con([])
    casos = {"consultar_registro": {"rut": "11111111-1"}, "evaluar_reglas": {"rut": "11111111-1"},
             "buscar_reglamento": {"consulta": "triage"}, "cargar_skill": {"nombre": "clasificar-antecedente-faltante"}}
    for nombre, args in casos.items():
        salida = ag.herr.registro[nombre]["fn"](**args)
        assert errores(salida, ag.decl.tools[nombre]["output_schema"]) == [], (nombre, salida)


def test_args_invalidos_vuelven_al_llm_y_este_se_corrige():
    ag, llm = agente_con([T("evaluar_reglas"), T("evaluar_reglas", rut="11111111-1"), V("11111111-1", "califica")])
    r = ag.turno("revisa 11111111-1")
    assert r["estado"] == "califica"
    assert "ERROR DE ARGUMENTOS" in llm.llamadas[1][-1]["content"]
    assert "falta el campo requerido 'rut'" in llm.llamadas[1][-1]["content"]


def test_permiso_el_rut_debe_venir_del_usuario():
    ag, llm = agente_con([T("consultar_registro", rut="22222222-2"), {"tipo": "respuesta", "base": "aclaracion", "texto": "¿Qué RUT desea consultar?"}])
    r = ag.turno("dame los datos del paciente de la cama 3")
    assert r["tipo"] == "respuesta"
    assert "BLOQUEADO" in llm.llamadas[1][-1]["content"]
    assert any(e["evento"] == "rut_bloqueado" for e in ag.log.eventos)


def test_un_error_de_la_tool_se_devuelve_al_agente_sin_romper_el_servicio():
    aviso = {"tipo": "respuesta", "base": "herramienta", "texto": "No pude evaluar el caso por un error de la herramienta."}
    ag, llm = agente_con([T("evaluar_reglas", rut="11111111-1"), aviso])
    ag.herr.registro["evaluar_reglas"]["fn"] = lambda rut: 1 / 0
    r = ag.turno("revisa 11111111-1")
    assert r["tipo"] == "respuesta"
    resultado_tool = json.loads(llm.llamadas[1][-1]["content"].split("RESULTADO_TOOL evaluar_reglas: ")[1].split("\n")[0])
    assert "Fallo interno de la tool" in resultado_tool["error"]


def test_tool_mcp_declarada_se_descubre_por_tools_list(mcp):
    ag, _ = agente_con([], mcp=mcp)
    assert ag.herr.registro["consultar_convenio"]["origen"] == "mcp"
    assert not [a for a in ag.herr.avisos if "consultar_convenio" in a]


def test_tool_mcp_no_publicada_por_el_servidor_genera_aviso():
    malo = MCPClient(comando=[sys.executable, "-c", "import sys; sys.exit(1)"], timeout=2)
    ag, _ = agente_con([], mcp=malo)
    malo.cerrar()
    assert "consultar_convenio" not in ag.herr.registro
    assert any("MCP no disponible" in a for a in ag.herr.avisos)


def test_tool_mcp_se_ejecuta_y_valida_args_igual_que_una_local(mcp):
    ag, _ = agente_con([], mcp=mcp)
    assert ag.herr.validar_args("consultar_convenio", {}) is not None
    assert ag.herr.validar_args("consultar_convenio", {"prevision": "Fonasa C"}) is None
    salida = ag.herr.registro["consultar_convenio"]["fn"](prevision="Fonasa C")
    assert salida["cobertura_urgencia"] == "90%"
    assert errores(salida, ag.decl.tools["consultar_convenio"]["output_schema"]) == []
