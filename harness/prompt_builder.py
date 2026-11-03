"""Construye el prompt del sistema: agent.md (declarativo) + secciones generadas desde el
estado real del agente (tools habilitadas, catálogo de skills, valores válidos)."""


def construir_prompt(decl, herramientas):
    partes = [decl.agent_md.strip()]
    partes.append("## Herramientas disponibles\n" + herramientas.descripcion_para_prompt())
    if decl.skills:
        catalogo = "\n".join(f"- {n}: {s['description']}" for n, s in decl.skills.items())
        partes.append("## Catálogo de skills (cárgalas con cargar_skill)\n" + catalogo)
    m = decl.manifest
    partes.append("## Valores válidos\n"
                  "- estado: " + " | ".join(m["estados"]) + "\n"
                  "- limite (en fuera_de_alcance): " + " | ".join(m["limites"]))
    return "\n\n".join(partes)
