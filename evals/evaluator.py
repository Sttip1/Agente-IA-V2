"""Evaluador automático del agente: ejecuta evals/cases.jsonl y genera un reporte con métricas.

Dos modos:
  --modo mock   (por defecto) cada caso trae el guion de respuestas del LLM ('mock'). No necesita Ollama: evalúa que el
                ARNÉS (schemas, auditor, tools, límites, memoria) se comporte como se espera. Es determinista (CI).
  --modo live   usa el modelo real de Ollama e ignora el guion: evalúa al MODELO + arnés. Es el que sirve para comparar
                modelos (--model gemma3:4b, --model gemma3:12b ...).

Uso:  python -m evals.evaluator [--modo mock|live] [--model X] [--salida reports] [--min-pass 1.0]

Criterios por caso (todos opcionales, en 'criterios'):
  tipo, estado, base, limite   valor exacto en el resultado final
  tools_incluye / tools_excluye   herramientas que deben / no deben haberse ejecutado (según el log de la ejecución)
  sin_tools                       no se ejecutó ninguna herramienta de información (cargar_skill no cuenta)
  antecedentes_vacios             el veredicto no lista antecedentes faltantes
  auditoria                       valor del campo 'auditoria' (ok, ok_tras_1_correcciones, corregido_por_auditor)
  contiene / no_contiene          textos (sin tildes ni mayúsculas) que deben / no deben aparecer en la respuesta"""
import argparse
import datetime
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.arranque import crear_agente  # noqa: E402
from harness.config import BASE_DIR, MODEL  # noqa: E402
from harness.errores import LLMNoDisponible  # noqa: E402
from harness.llm_client import OllamaClient  # noqa: E402
from harness.mcp_client import MCPClient  # noqa: E402
from harness.utilidades import norm  # noqa: E402

CASOS_POR_DEFECTO = os.path.join(BASE_DIR, "evals", "cases.jsonl")


class GuionLLM:
    """LLM de mentira que responde con el guion del caso (modo mock)."""
    modelo = "mock-guion"
    modelo_embed = "ninguno"

    def __init__(self, guion):
        self.guion = list(guion)

    def chat(self, mensajes):
        if not self.guion:
            raise LLMNoDisponible("El guion del caso se agotó: el arnés pidió más respuestas de las previstas.")
        x = self.guion.pop(0)
        return x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)

    def embed(self, textos):
        raise LLMNoDisponible("sin embeddings en modo mock (el RAG usa su búsqueda léxica)")


def cargar_casos(ruta):
    casos = []
    with open(ruta, encoding="utf-8") as f:
        for n, linea in enumerate(f, 1):
            if linea.strip():
                try:
                    casos.append(json.loads(linea))
                except json.JSONDecodeError as e:
                    raise SystemExit(f"{ruta}:{n}: JSON inválido: {e}") from e
    return casos


def _texto(r):
    return norm(" ".join(str(r.get(c, "")) for c in ("texto", "explicacion", "estado")) + " " + " ".join(r.get("antecedentes_faltantes", []) or []))


def verificar(criterios, r, tools):
    """Lista de incumplimientos (vacía si el caso pasa)."""
    fallas = []
    for campo in ("tipo", "estado", "base", "limite", "auditoria"):
        if campo in criterios and r.get(campo) != criterios[campo]:
            fallas.append(f"{campo}: esperado '{criterios[campo]}', obtenido '{r.get(campo)}'")
    info = [t for t in tools if t != "cargar_skill"]
    for t in criterios.get("tools_incluye", []):
        if t not in tools:
            fallas.append(f"no se ejecutó la herramienta {t}")
    for t in criterios.get("tools_excluye", []):
        if t in tools:
            fallas.append(f"se ejecutó la herramienta prohibida {t}")
    if criterios.get("sin_tools") and info:
        fallas.append(f"se ejecutaron herramientas innecesarias: {info}")
    if criterios.get("antecedentes_vacios") and r.get("antecedentes_faltantes"):
        fallas.append("el veredicto lista antecedentes faltantes")
    texto = _texto(r)
    for s in criterios.get("contiene", []):
        if norm(s) not in texto:
            fallas.append(f"la respuesta no contiene '{s}'")
    for s in criterios.get("no_contiene", []):
        if norm(s) in texto:
            fallas.append(f"la respuesta contiene '{s}'")
    return fallas


def ejecutar_caso(caso, modo, modelo, mcp):
    llm = GuionLLM(caso.get("mock", [])) if modo == "mock" else OllamaClient(modelo=modelo)
    agente = crear_agente(llm=llm, mcp=mcp, usar_mcp=False, verbose=False, log_ruta=None)   # memoria limpia por caso
    t0, r = time.time(), {}
    for turno in caso.get("turnos") or [caso["entrada"]]:
        r = agente.turno(turno)
    run = agente.log.eventos_de(r.get("run_id"))
    tools = [e["tool"] for e in run if e["evento"] == "tool"]
    return {
        "id": caso["id"], "categoria": caso.get("categoria", "-"), "descripcion": caso.get("descripcion", ""),
        "fallas": verificar(caso.get("criterios", {}), r, tools), "tipo": r.get("tipo"), "estado": r.get("estado"),
        "tools": tools, "correcciones": sum(1 for e in run if e["evento"] in ("auditoria", "validacion", "tool_pendiente")),
        "pasos_llm": sum(1 for e in run if e["evento"] == "llm"), "latencia_ms": int((time.time() - t0) * 1000), "run_id": r.get("run_id"),
    }


def metricas(res):
    n = len(res)
    ok = sum(1 for r in res if not r["fallas"])
    por_cat = {}
    for r in res:
        c = por_cat.setdefault(r["categoria"], [0, 0])
        c[1] += 1
        c[0] += 0 if r["fallas"] else 1
    return {"casos": n, "aprobados": ok, "tasa_aprobacion": round(ok / n, 3) if n else 0.0,
            "por_categoria": {k: {"aprobados": a, "total": t} for k, (a, t) in por_cat.items()},
            "promedio_correcciones": round(sum(r["correcciones"] for r in res) / n, 2) if n else 0.0,
            "promedio_pasos_llm": round(sum(r["pasos_llm"] for r in res) / n, 2) if n else 0.0,
            "latencia_media_ms": int(sum(r["latencia_ms"] for r in res) / n) if n else 0}


def reporte_md(meta, m, res):
    que_evalua = "guion de respuestas del LLM: evalúa el arnés" if meta["modo"] == "mock" else "modelo real: evalúa modelo + arnés"
    L = ["# Reporte de evaluación - Agente P02", "",
         f"- Fecha: {meta['fecha']}", f"- Modo: **{meta['modo']}** ({que_evalua})",
         f"- Modelo: {meta['modelo']}", f"- Casos: {m['aprobados']}/{m['casos']} aprobados (**{m['tasa_aprobacion']:.0%}**)", "",
         "## Métricas", "", "| Categoría | Aprobados |", "|---|---|"]
    L += [f"| {k} | {v['aprobados']}/{v['total']} |" for k, v in m["por_categoria"].items()]
    L += ["", f"- Correcciones promedio por caso (auditor, esquema, tools narradas): {m['promedio_correcciones']}",
          f"- Pasos de LLM promedio: {m['promedio_pasos_llm']}", f"- Latencia media por caso: {m['latencia_media_ms']} ms", "",
          "## Detalle", "", "| Caso | Categoría | Resultado | Tools | Corr. | ms | Motivo |", "|---|---|---|---|---|---|---|"]
    for r in res:
        L.append(f"| {r['id']} | {r['categoria']} | {'OK' if not r['fallas'] else 'FALLA'} | {', '.join(r['tools']) or '-'} | "
                 f"{r['correcciones']} | {r['latencia_ms']} | {'; '.join(r['fallas']) or r['descripcion']} |")
    fallos = [r for r in res if r["fallas"]]
    L += ["", "## Casos que fallan", ""]
    L += [f"- **{r['id']}** ({r['descripcion']}): {'; '.join(r['fallas'])}" for r in fallos] or ["Ninguno."]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Evaluador del Agente P02")
    ap.add_argument("--casos", default=CASOS_POR_DEFECTO)
    ap.add_argument("--modo", choices=["mock", "live"], default="mock")
    ap.add_argument("--model", default=MODEL, help="modelo de Ollama (solo modo live)")
    ap.add_argument("--salida", default=os.path.join(BASE_DIR, "reports"), help="carpeta del reporte")
    ap.add_argument("--min-pass", type=float, default=1.0, help="tasa mínima de aprobación; si no se alcanza el código de salida es 1")
    ap.add_argument("--solo", help="ids separados por coma (ej E01,E15)")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    casos = cargar_casos(a.casos)
    if a.solo:
        pedidos = set(a.solo.split(","))
        casos = [c for c in casos if c["id"] in pedidos]
    mcp = MCPClient()
    try:
        res = []
        for c in casos:
            r = ejecutar_caso(c, a.modo, a.model, mcp)
            res.append(r)
            print(f"{'OK   ' if not r['fallas'] else 'FALLA'} {r['id']} [{r['categoria']}] {c['descripcion']}"
                  + ("" if not r["fallas"] else "\n      -> " + "; ".join(r["fallas"])))
    finally:
        mcp.cerrar()
    m = metricas(res)
    modelo = "mock-guion" if a.modo == "mock" else a.model
    meta = {"fecha": datetime.datetime.now().isoformat(timespec="seconds"), "modo": a.modo, "modelo": modelo}
    os.makedirs(a.salida, exist_ok=True)
    sufijo = "" if a.modo == "mock" else "_" + modelo.replace(":", "-").replace("/", "-")
    with open(os.path.join(a.salida, f"eval_report{sufijo}.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "metricas": m, "casos": res}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(a.salida, f"eval_report{sufijo}.md"), "w", encoding="utf-8") as f:
        f.write(reporte_md(meta, m, res))
    print(f"\n{modelo} ({a.modo}): {m['aprobados']}/{m['casos']} casos aprobados ({m['tasa_aprobacion']:.0%}). Reporte en {a.salida}")
    return 0 if m["tasa_aprobacion"] >= a.min_pass else 1


if __name__ == "__main__":
    sys.exit(main())
