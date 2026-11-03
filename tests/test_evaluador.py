"""El evaluador automático: ejecuta evals/cases.jsonl, detecta incumplimientos y genera el reporte."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from evals import evaluator  # noqa: E402
from harness.mcp_client import MCPClient  # noqa: E402


@pytest.fixture(scope="module")
def mcp():
    c = MCPClient()
    yield c
    c.cerrar()


def test_los_casos_de_evaluacion_tienen_criterios_explicitos():
    casos = evaluator.cargar_casos(evaluator.CASOS_POR_DEFECTO)
    assert len(casos) >= 15
    ids = [c["id"] for c in casos]
    assert len(ids) == len(set(ids))
    for c in casos:
        assert c["criterios"] and c["descripcion"] and c["mock"], c["id"]
    assert {c["categoria"] for c in casos} >= {"veredicto", "auditoria", "rag", "mcp", "limites", "aclaracion", "memoria"}


def test_todos_los_casos_pasan_en_modo_mock_y_se_genera_el_reporte(tmp_path):
    codigo = evaluator.main(["--modo", "mock", "--salida", str(tmp_path)])
    assert codigo == 0
    datos = json.loads((tmp_path / "eval_report.json").read_text(encoding="utf-8"))
    assert datos["metricas"]["tasa_aprobacion"] == 1.0 and datos["metricas"]["casos"] >= 15
    md = (tmp_path / "eval_report.md").read_text(encoding="utf-8")
    assert "## Métricas" in md and "## Casos que fallan" in md and "Ninguno." in md


def test_el_evaluador_detecta_un_caso_que_falla(mcp):
    caso = next(c for c in evaluator.cargar_casos(evaluator.CASOS_POR_DEFECTO) if c["id"] == "E01")
    caso["criterios"]["estado"] = "no_califica"                  # criterio imposible a propósito
    caso["criterios"]["tools_excluye"] = ["evaluar_reglas"]
    r = evaluator.ejecutar_caso(caso, "mock", "x", mcp)
    assert len(r["fallas"]) == 2
    assert any("estado" in f for f in r["fallas"]) and any("prohibida" in f for f in r["fallas"])


def test_el_codigo_de_salida_es_1_si_no_se_alcanza_el_minimo(tmp_path):
    casos = tmp_path / "casos.jsonl"
    caso = {"id": "X1", "categoria": "veredicto", "descripcion": "debe fallar", "entrada": "hola",
            "criterios": {"tipo": "veredicto"}, "mock": [{"tipo": "respuesta", "base": "saludo", "texto": "Hola"}]}
    casos.write_text(json.dumps(caso) + "\n", encoding="utf-8")
    assert evaluator.main(["--casos", str(casos), "--salida", str(tmp_path / "r")]) == 1
    assert "X1" in (tmp_path / "r" / "eval_report.md").read_text(encoding="utf-8")


def test_jsonl_invalido_se_informa_con_la_linea(tmp_path):
    ruta = tmp_path / "malo.jsonl"
    ruta.write_text('{"id": "A"}\n{no es json}\n', encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        evaluator.cargar_casos(str(ruta))
    assert ":2:" in str(e.value)
