"""Carga la definición declarativa del agente desde agent/:

    agent.md                       prompt, política, límites y criterios de éxito (prosa)
    manifest.yaml                  identidad, versión, tools permitidas, skills, límites, parámetros de ejecución
    tools.yaml                     herramientas: nombre, descripción, schemas de entrada/salida y permisos
    skills/<nombre>/SKILL.md       procedimientos con frontmatter (name, description)
    input.schema.json / output.schema.json   contratos de entrada y salida

El arnés no tiene valores del agente escritos en el código: todo sale de estos archivos y se valida al cargar."""
import os

import yaml

from harness.config import AGENT_DIR, EJECUCION_DEFECTO
from harness.errores import ConfiguracionError
from harness.schema_validator import cargar_json, schema_es_valido

CLAVES_MANIFEST = ("id", "nombre", "version", "tools", "skills", "limites", "estados", "salidas")
ORIGENES_TOOL = ("local", "mcp")


def parsear_yaml(texto, origen="YAML"):
    try:
        datos = yaml.safe_load(texto)
    except yaml.YAMLError as e:
        raise ConfiguracionError(f"{origen}: YAML inválido: {e}") from e
    return {} if datos is None else datos


def separar_frontmatter(texto):
    """Devuelve (meta, cuerpo). Si no hay bloque '---', meta es {}."""
    lineas = texto.lstrip("﻿").splitlines()
    if lineas and lineas[0].strip() == "---":
        for i in range(1, len(lineas)):
            if lineas[i].strip() == "---":
                meta = parsear_yaml("\n".join(lineas[1:i]), "frontmatter")
                if not isinstance(meta, dict):
                    raise ConfiguracionError("Frontmatter debe ser un mapa clave: valor")
                return meta, "\n".join(lineas[i + 1:]).strip()
        raise ConfiguracionError("Frontmatter sin cierre '---'")
    return {}, texto.strip()


def _leer(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        raise ConfiguracionError(f"No se pudo leer {ruta}: {e}") from e


def _leer_yaml(ruta):
    datos = parsear_yaml(_leer(ruta), ruta)
    if not isinstance(datos, dict):
        raise ConfiguracionError(f"{ruta}: debe ser un mapa clave: valor")
    return datos


class Declaracion:
    """Definición declarativa del agente ya cargada y validada."""

    def __init__(self, agent_md, manifest, skills, schema_salida, schema_entrada, ejecucion, tools):
        self.agent_md, self.manifest, self.skills = agent_md, manifest, skills
        self.schema_salida, self.schema_entrada, self.ejecucion, self.tools = schema_salida, schema_entrada, ejecucion, tools

    @property
    def version(self):
        return str(self.manifest["version"])


def _cargar_tools(ruta):
    datos = _leer_yaml(ruta)
    lista = datos.get("tools")
    if not isinstance(lista, list) or not lista:
        raise ConfiguracionError(f"{ruta}: 'tools' debe ser una lista no vacía")
    tools = {}
    for t in lista:
        if not isinstance(t, dict) or not t.get("name"):
            raise ConfiguracionError(f"{ruta}: cada tool necesita 'name'")
        n = t["name"]
        for campo in ("description", "origin", "input_schema"):
            if not t.get(campo):
                raise ConfiguracionError(f"{ruta}: la tool '{n}' no declara '{campo}'")
        if t["origin"] not in ORIGENES_TOOL:
            raise ConfiguracionError(f"{ruta}: la tool '{n}' tiene origin '{t['origin']}'; use {ORIGENES_TOOL}")
        if t["origin"] == "local" and not t.get("handler"):
            raise ConfiguracionError(f"{ruta}: la tool local '{n}' necesita 'handler'")
        if n in tools:
            raise ConfiguracionError(f"{ruta}: la tool '{n}' está duplicada")
        schema_es_valido(t["input_schema"])
        if t.get("output_schema"):
            schema_es_valido(t["output_schema"])
        t.setdefault("permissions", {})
        tools[n] = t
    return tools


def cargar_declaracion(agent_dir=None):
    agent_dir = agent_dir or AGENT_DIR
    if not os.path.isdir(agent_dir):
        raise ConfiguracionError(f"No existe la carpeta declarativa del agente: {agent_dir}")

    agent_md = _leer(os.path.join(agent_dir, "agent.md")).strip()
    if not agent_md:
        raise ConfiguracionError("agent/agent.md está vacío")

    manifest = _leer_yaml(os.path.join(agent_dir, "manifest.yaml"))
    faltan = [k for k in CLAVES_MANIFEST if k not in manifest]
    if faltan:
        raise ConfiguracionError(f"manifest.yaml: faltan las claves {faltan}")
    for k in ("tools", "skills", "limites", "estados", "salidas"):
        if not isinstance(manifest[k], list):
            raise ConfiguracionError(f"manifest.yaml: '{k}' debe ser una lista")

    tools = _cargar_tools(os.path.join(agent_dir, "tools.yaml"))
    sin_declarar = [t for t in manifest["tools"] if t not in tools]
    if sin_declarar:
        raise ConfiguracionError(f"manifest.yaml permite tools que tools.yaml no declara: {sin_declarar}")

    skills = {}
    for nombre in manifest["skills"]:
        ruta = os.path.join(agent_dir, "skills", str(nombre), "SKILL.md")
        meta, cuerpo = separar_frontmatter(_leer(ruta))
        if meta.get("name") != nombre:
            raise ConfiguracionError(f"{ruta}: el frontmatter 'name' debe ser '{nombre}'")
        if not meta.get("description"):
            raise ConfiguracionError(f"{ruta}: falta 'description' en el frontmatter")
        if not cuerpo:
            raise ConfiguracionError(f"{ruta}: la skill no tiene contenido")
        skills[nombre] = {"description": str(meta["description"]), "body": cuerpo}
    sk = manifest.get("skill_para_faltantes")
    if sk and sk not in skills:
        raise ConfiguracionError(f"manifest.yaml: skill_para_faltantes '{sk}' no está en 'skills'")

    esquema = cargar_json(os.path.join(agent_dir, "output.schema.json"))
    schema_salida = esquema.get("$defs")
    if not isinstance(schema_salida, dict) or not schema_salida:
        raise ConfiguracionError("output.schema.json debe definir los tipos de salida en '$defs'")
    if set(manifest["salidas"]) != set(schema_salida):
        raise ConfiguracionError(f"manifest.yaml 'salidas' {sorted(manifest['salidas'])} no coincide con output.schema.json {sorted(schema_salida)}")
    for sch in schema_salida.values():
        schema_es_valido(sch)
    schema_entrada = cargar_json(os.path.join(agent_dir, "input.schema.json"))
    schema_es_valido(schema_entrada)

    ejecucion = {}
    for k, defecto in EJECUCION_DEFECTO.items():
        v = manifest.get(k, defecto)
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            raise ConfiguracionError(f"manifest.yaml: '{k}' debe ser un entero positivo")
        ejecucion[k] = v
    return Declaracion(agent_md, manifest, skills, schema_salida, schema_entrada, ejecucion, tools)
