"""Prueba de la API real con FastAPI TestClient (se omite si fastapi/httpx no están instalados)."""
import os
import sys

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import LLMFalso, T, V  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import crear_app  # noqa: E402
from app.servicio import Servicio  # noqa: E402


def cliente(guion):
    return TestClient(crear_app(Servicio(llm=LLMFalso(guion), usar_mcp=False, log_ruta=None)))


def test_los_cuatro_endpoints_responden():
    c = cliente([T("evaluar_reglas", rut="11111111-1"), V("11111111-1", "califica")])
    assert c.get("/health").json()["status"] == "ok"
    assert c.get("/metadata").json()["id"] == "P02"
    r = c.post("/run", json={"mensaje": "Dime si el 11111111-1 es apto"})
    assert r.status_code == 200 and r.json()["resultado"]["estado"] == "califica"
    logs = c.get("/logs", params={"run_id": r.json()["run_id"]})
    assert logs.status_code == 200 and logs.json()["eventos"][0]["evento"] == "inicio"


def test_errores_http():
    c = cliente([])
    assert c.post("/run", json={}).status_code == 422
    assert c.post("/run", json=["no", "objeto"]).status_code == 422
    assert c.get("/logs", params={"run_id": "noexiste"}).status_code == 404
    assert c.get("/logs", params={"limite": 0}).status_code == 422
