"""Chat interactivo por consola."""
import argparse
import json
import sys

from harness.arranque import crear_agente
from harness.config import MODEL
from harness.errores import ConfiguracionError
from harness.llm_client import OllamaClient
from harness.presentacion import render


def chat(args):
    try:
        agente = crear_agente(OllamaClient(modelo=args.model or MODEL), verbose=not args.quiet)
    except ConfiguracionError as e:
        print(f"Error de configuración: {e}")
        return 2
    print("=" * 66)
    print(" Agente P02 - Verificación administrativa de urgencia (Clínica X)")
    print(f" Modelo: {args.model or MODEL} | tools: {', '.join(agente.herr.registro)}")
    print(f" Skills: {', '.join(agente.decl.skills) or 'ninguna'}")
    print(" Comandos: 'salir' · '/reset' (borra la memoria)   RUTs de prueba: 11111111-1 ... 77777777-7")
    print("=" * 66)
    while True:
        try:
            entrada = input("\nUsuario: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if entrada.lower() in ("salir", "exit", "quit"):
            break
        if entrada == "/reset":
            agente.mem.reiniciar()
            print("Memoria reiniciada.")
            continue
        if not entrada:
            continue
        r = agente.turno(entrada)
        print("\nAgente:", render(r))
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Agente P02 - Verificación administrativa de urgencias (Clínica X)")
    ap.add_argument("--quiet", action="store_true", help="oculta las trazas")
    ap.add_argument("--json", action="store_true", help="imprime también el JSON final")
    ap.add_argument("--model", help="modelo de Ollama (por defecto OLLAMA_MODEL o gemma3:4b)")
    sys.exit(chat(ap.parse_args(argv)))
