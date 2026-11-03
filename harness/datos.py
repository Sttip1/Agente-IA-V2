"""Carga de datos simulados (pacientes) y documentos institucionales (para el RAG)."""
import json
import os

from harness.config import DATA_DIR
from harness.errores import ConfiguracionError
from harness.utilidades import normalizar_rut


def cargar_pacientes(ruta=None):
    ruta = ruta or os.path.join(DATA_DIR, "pacientes_simulados.json")
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise ConfiguracionError(f"No se pudieron cargar los pacientes simulados ({ruta}): {e}") from e
    if not isinstance(datos, dict):
        raise ConfiguracionError(f"{ruta} debe ser un objeto JSON indexado por RUT")
    return {normalizar_rut(k): v for k, v in datos.items()}


def cargar_documentos(carpeta=None):
    """Devuelve {nombre_archivo: texto} con los .md de data/documentos/ (vacío si no hay)."""
    carpeta = carpeta or os.path.join(DATA_DIR, "documentos")
    docs = {}
    if os.path.isdir(carpeta):
        for nombre in sorted(os.listdir(carpeta)):
            if nombre.endswith(".md"):
                try:
                    with open(os.path.join(carpeta, nombre), "r", encoding="utf-8") as f:
                        docs[nombre] = f.read()
                except OSError:
                    pass
    return docs
