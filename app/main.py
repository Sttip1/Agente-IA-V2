"""API FastAPI del Agente P02.

    uvicorn app.main:app --host 127.0.0.1 --port 8000

    GET  /health      estado del servicio (?profundo=true comprueba también Ollama)
    GET  /metadata    qué es el agente: versión, modelo, tools, skills, límites, parámetros
    POST /run         {"mensaje": "...", "session_id": "opcional"} -> resultado + run_id
    GET  /logs        ?run_id=... reconstruye una ejecución; sin run_id devuelve los últimos eventos

Toda la lógica está en app/servicio.py; aquí solo se traduce HTTP."""
from typing import Optional

from fastapi import Body, FastAPI, Query
from fastapi.responses import JSONResponse

from app.servicio import Servicio

CUERPO = Body(...)   # singleton a nivel de módulo (recomendación de ruff B008)


def crear_app(servicio=None):
    estado = {"servicio": servicio}

    def svc():
        if estado["servicio"] is None:      # perezoso: importar el módulo no arranca Ollama ni el servidor MCP
            estado["servicio"] = Servicio()
        return estado["servicio"]

    app = FastAPI(title="Agente P02 - Verificación administrativa de urgencia (Clínica X)", version="2.0.0")

    @app.get("/health")
    def health(profundo: bool = False):
        return svc().salud(profundo)

    @app.get("/metadata")
    def metadata():
        return svc().metadata()

    @app.post("/run")
    def run(cuerpo: dict = CUERPO):
        codigo, respuesta = svc().ejecutar(cuerpo)
        return JSONResponse(respuesta, status_code=codigo)

    @app.get("/logs")
    def logs(run_id: Optional[str] = Query(None), limite: int = Query(100, ge=1, le=1000)):
        codigo, respuesta = svc().logs(run_id, limite)
        return JSONResponse(respuesta, status_code=codigo)

    return app


app = crear_app()
