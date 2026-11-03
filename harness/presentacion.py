"""Formato legible de la respuesta del agente para la consola."""
import json


def render(r):
    t = r.get("tipo")
    if t == "veredicto":
        s = [f"Caso {r['rut']}  ->  {r['estado'].upper().replace('_', ' ')}", r["explicacion"]]
        if r["antecedentes_faltantes"]:
            s.append("Antecedentes faltantes:\n" + "\n".join(f"  - {x}" for x in r["antecedentes_faltantes"]))
        s.append("Reglas aplicadas: " + ", ".join(r["reglas_aplicadas"]))
        if r.get("auditoria") == "corregido_por_auditor":
            s.append("(Resultado corregido por el auditor: el modelo contradijo las reglas.)")
        return "\n".join(s)
    if t == "fuera_de_alcance":
        return f"[Fuera de alcance - {r.get('limite', '')}] {r['texto']}"
    return r.get("texto", json.dumps(r, ensure_ascii=False))
