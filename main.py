#!/usr/bin/env python3
"""Punto de entrada del Agente P02 (chat por consola).
Uso:  python main.py [--quiet] [--json] [--model gemma3:4b]
Para la API HTTP:  uvicorn app.main:app --host 127.0.0.1 --port 8000"""
import importlib
import sys

for _modulo in ("yaml", "jsonschema"):
    try:
        importlib.import_module(_modulo)
    except ImportError:
        sys.exit(f"Falta la dependencia '{_modulo}'. Instálala con:  pip install -r requirements.txt")

from harness.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
