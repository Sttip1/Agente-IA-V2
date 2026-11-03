"""Contratos de entrada/salida: schemas válidos, ejemplos válidos e inválidos (agent/examples/) y reparación de salida mal formada."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import RAIZ, V, agente_con  # noqa: E402

from harness.declarativo import cargar_declaracion  # noqa: E402
from harness.schema_validator import cargar_json, errores, schema_es_valido, validar_ejemplos  # noqa: E402

DECL = cargar_declaracion()
SCHEMAS = {"input": DECL.schema_entrada, **DECL.schema_salida}
EJEMPLOS = validar_ejemplos(os.path.join(RAIZ, "agent", "examples"), SCHEMAS)


@pytest.mark.parametrize("nombre", sorted(SCHEMAS))
def test_cada_schema_es_json_schema_valido(nombre):
    schema_es_valido(SCHEMAS[nombre])


def test_hay_ejemplos_validos_e_invalidos():
    assert sum(1 for _, esperado, _, _ in EJEMPLOS if esperado) >= 5
    assert sum(1 for _, esperado, _, _ in EJEMPLOS if not esperado) >= 5


@pytest.mark.parametrize("archivo,esperado,ok,detalle", EJEMPLOS, ids=[e[0] for e in EJEMPLOS])
def test_ejemplo_se_comporta_como_declara(archivo, esperado, ok, detalle):
    assert ok, f"{archivo}: se esperaba {'válido' if esperado else 'inválido'} pero el resultado fue: {detalle}"


def test_los_errores_son_claros_y_en_espanol():
    errs = errores({"tipo": "veredicto", "estado": "quizas"}, DECL.schema_salida["veredicto"])
    assert any("falta el campo requerido 'rut'" in e for e in errs)
    assert any("$.estado" in e and "no permitido" in e for e in errs)


def test_regla_condicional_califica_exige_faltantes_vacios():
    v = DECL.schema_salida["veredicto"]
    assert errores(V("11111111-1", "califica"), v) == []
    assert errores(V("11111111-1", "califica", ["algo"]), v)
    assert errores(V("11111111-1", "no_califica"), v)
    assert errores(V("11111111-1", "no_califica", ["Cédula"]), v) == []


def test_entrada_valida_e_invalida():
    ent = DECL.schema_entrada
    assert errores({"mensaje": "hola"}, ent) == []
    assert errores({"mensaje": "x" * 1001}, ent)
    assert errores({"mensaje": 5}, ent)
    assert errores({}, ent)


# --- el arnés ante salidas mal formadas del LLM -------------------------------------------------
def test_salida_mal_formada_se_repara_con_reintento_controlado():
    ag, llm = agente_con(["esto no es json", {"tipo": "respuesta", "base": "saludo", "texto": "Hola, ¿en qué ayudo?"}])
    r = ag.turno("hola")
    assert r["tipo"] == "respuesta"
    assert "FORMATO" in llm.llamadas[1][-1]["content"]          # el LLM recibe el motivo para corregirse


def test_salida_que_viola_el_schema_se_devuelve_al_llm_con_el_error():
    ag, llm = agente_con([{"tipo": "veredicto", "rut": "11111111-1"}, {"tipo": "respuesta", "base": "aclaracion", "texto": "¿De qué caso?"}])
    ag.turno("hola")
    assert "ERROR DE ESQUEMA" in llm.llamadas[1][-1]["content"]
    assert "falta el campo requerido" in llm.llamadas[1][-1]["content"]


def test_salida_invalida_persistente_termina_en_error_controlado():
    ag, _ = agente_con(["basura"] * 4)
    r = ag.turno("hola")
    assert (r["tipo"], r["codigo"]) == ("error", "formato_invalido")
    assert r["run_id"]


def test_entrada_demasiado_larga_se_rechaza_antes_de_llamar_al_llm():
    ag, llm = agente_con([])                                     # un guion vacío falla si el arnés llamara al LLM
    r = ag.turno("a" * 1500)
    assert (r["tipo"], r["codigo"]) == ("error", "entrada_invalida")
    assert llm.llamadas == []


def test_ejemplos_validos_de_salida_pasan_el_schema_real():
    for nombre in ("veredicto_califica", "veredicto_falta_informacion"):
        ej = cargar_json(os.path.join(RAIZ, "agent", "examples", "valid", nombre + ".json"))
        assert errores(ej["dato"], DECL.schema_salida["veredicto"]) == []
