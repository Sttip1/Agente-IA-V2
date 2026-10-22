import os
import json
import datetime
from harness.config import AGENT_DIR, LOGS_DIR
from harness.memoria import MemoriaConversacional
import harness.llm_client
from harness.output_parser import extraer_json_respuesta
from harness.schema_validator import validar_datos, ValidacionError
from harness.tools import REGISTRO_TOOLS, ejecutar_tool

def cargar_prompt_sistema():
    """Carga agent.md y añade instrucciones operativas sobre tools, flujo obligatorio y esquemas de salida."""
    ruta_agent = os.path.join(AGENT_DIR, "agent.md")
    ruta_skill = os.path.join(AGENT_DIR, "SKILL.md")
    
    contenido_agent = ""
    if os.path.exists(ruta_agent):
        with open(ruta_agent, "r", encoding="utf-8") as f:
            contenido_agent = f.read()
            
    contenido_skill = ""
    if os.path.exists(ruta_skill):
        with open(ruta_skill, "r", encoding="utf-8") as f:
            contenido_skill = f.read()

    tools_desc = "\n".join([f"- {nombre}: {info['descripcion']} (Parámetros: {info['parametros']})" for nombre, info in REGISTRO_TOOLS.items()])

    prompt = f"""{contenido_agent}

## Herramientas Disponibles (Tools)
Tienes acceso a las siguientes herramientas que puedes invocar cuando necesites consultar información:
{tools_desc}

## Flujo Obligatorio de Trabajo
Cuando te pidan revisar un caso o paciente, debes seguir estrictamente este orden:
1. Primero, invocar la herramienta `consultar_antecedentes` con el RUT del paciente.
2. Segundo, invocar la herramienta `validar_ley_urgencia` con el RUT del paciente.
3. Tercero, entregar la respuesta final en formato JSON cumpliendo estrictamente con el esquema output.schema.json.
NO respondas con texto conversacional ni inventes datos sin haber consultado las herramientas.

## Protocolo de Invocación de Herramientas
Cuando necesites usar una herramienta, responde ÚNICAMENTE con un objeto JSON en este formato estricto (sin texto adicional ni explicaciones previas):
{{"tool": "<nombre_tool>", "args": {{"param": "valor"}}}}

## Protocolo de Respuesta Final
Cuando tengas la respuesta completa, tu respuesta final debe cumplir estrictamente con el esquema output.schema.json, entregando un JSON con los campos:
- "estado": "califica" | "no_califica" | "falta_informacion"
- "explicacion": string detallada y NO VACÍA
- "antecedentes_faltantes": lista de strings (vacía si no falta nada)
- "reglas_aplicadas": lista de strings

## Skill de Apoyo
{contenido_skill}

## Regla Estricta sobre Preguntas Generales y RUTs
- Si la pregunta del usuario es general (ej. sobre horarios, casino, servicios generales, etc.) y NO menciona ningún paciente ni RUT, NO invoques bajo ninguna circunstancia `consultar_antecedentes` ni `validar_ley_urgencia`. Si la información no está en los reglamentos o protocolos de la Clínica X, responde directamente que no se encuentra en los documentos institucionales.
"""
    return prompt

def registrar_ejecucion(log_data):
    """Registra cada ejecución en logs/ejecucion.jsonl."""
    ruta_log = os.path.join(LOGS_DIR, "ejecucion.jsonl")
    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        **log_data
    }
    with open(ruta_log, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

def ejecutar_turno(prompt_usuario, memoria):
    """
    Gestiona un turno conversacional completo, incluyendo guardas de límites deterministas,
    validación de entrada (RUT, basura), loop de herramientas, y skill con validación anti-alucinación.
    """
    import re
    prompt_limpio = prompt_usuario.strip()
    if not prompt_limpio or prompt_limpio in ["^V", "^C", ""] or not any(c.isalnum() for c in prompt_limpio):
        return "No he entendido su consulta o texto ingresado. Por favor, escriba una consulta válida sobre urgencias, convenios, reglamentos o indique un RUT de paciente (ej: 11111111-1)."

    # REQUISITO 1: Guardas de límites deterministas ANTES de llamar al RAG o a tools
    lower_prompt = prompt_limpio.lower()

    if any(k in lower_prompt for k in ["diagnóst", "diagnost", "qué tiene", "que tiene", "enfermedad", "tratamiento"]):
        print("[TRAZA LIMITE] Límite aplicado: Diagnóstico / Tratamiento / Enfermedad prohibido.")
        return "Solo puedo verificar antecedentes administrativos (previsión, triage revisado por clínico y documentos). No diagnostico, no reclasifico triage, no apruebo cobros ni decido el ingreso del paciente."
    
    if "triage" in lower_prompt and any(w in lower_prompt for w in ["reclasif", "cambia", "subir", "bajar", "modific"]):
        print("[TRAZA LIMITE] Límite aplicado: Reclasificación de triage prohibida.")
        return "Solo puedo verificar antecedentes administrativos (previsión, triage revisado por clínico y documentos). No diagnostico, no reclasifico triage, no apruebo cobros ni decido el ingreso del paciente."

    if any(k in lower_prompt for k in ["cobro", "cobrar", "pago", "pagar", "presupuesto"]):
        print("[TRAZA LIMITE] Límite aplicado: Aprobación de cobros / pagos prohibida.")
        return "Solo puedo verificar antecedentes administrativos (previsión, triage revisado por clínico y documentos). No diagnostico, no reclasifico triage, no apruebo cobros ni decido el ingreso del paciente."

    if any(k in lower_prompt for k in ["ingreso", "ingresar", "autoriz", "aprobar"]):
        match_rut_limite = re.search(r'\d{7,8}-[\dkK]', prompt_usuario)
        if match_rut_limite:
            print("[TRAZA LIMITE] Límite aplicado: Aprobación/decisión de ingreso con RUT detectado.")
            return "Solo puedo verificar antecedentes administrativos (previsión, triage revisado por clínico y documentos). No decido el ingreso final del paciente (aunque para el RUT detectado puedo realizar la verificación administrativa si lo requiere)."
        else:
            print("[TRAZA LIMITE] Límite aplicado: Decisión / aprobación de ingreso prohibida.")
            return "Solo puedo verificar antecedentes administrativos (previsión, triage revisado por clínico y documentos). No diagnostico, no reclasifico triage, no apruebo cobros ni decido el ingreso del paciente."

    es_consulta_paciente = any(palabra in prompt_limpio.lower() for palabra in ["paciente", "revisa", "revisar", "urgencia", "rut", "caso"])
    match_rut = re.search(r'\d{7,8}-[\dkK]', prompt_limpio)
    if es_consulta_paciente and not match_rut:
        return "Para revisar un caso de paciente, debe proporcionar un RUT válido (ej: 11111111-1). Por favor, indíquelo."

    # REQUISITO 1: Si el mensaje NO contiene un RUT, el arnés llama SIEMPRE a buscar_reglamento o consultar_convenio
    if not match_rut:
        lower_prompt = prompt_limpio.lower()
        if any(w in lower_prompt for w in ["convenio", "isapre", "fonasa", "particular"]):
            prevision = "Isapre Banmedica"
            if "fonasa" in lower_prompt:
                prevision = "Fonasa A" if "a" in lower_prompt else "Fonasa C"
            elif "colmena" in lower_prompt:
                prevision = "Isapre Colmena"
            elif "banmedica" in lower_prompt or "isapre" in lower_prompt:
                prevision = "Isapre Banmedica"
            
            print(f"[TRAZA TOOL] Ejecutando automáticamente consultar_convenio para prevision='{prevision}'")
            res_conv = ejecutar_tool("consultar_convenio", {"prevision": prevision})
            prev = res_conv.get("prevision", prevision)
            vigente = res_conv.get("convenio_vigente", False)
            cob = res_conv.get("cobertura_urgencia", "N/A")
            obs = res_conv.get("observacion", "Sin observaciones.")
            return f"Según el Servidor de Convenios (Fuente: servidor_convenios.py):\n- Previsión: {prev}\n- Convenio vigente: {vigente}\n- Cobertura de urgencia: {cob}\n- Observación: {obs}"
        else:
            print(f"[TRAZA TOOL] Ejecutando automáticamente buscar_reglamento con consulta='{prompt_limpio}'")
            res_rag = ejecutar_tool("buscar_reglamento", {"consulta": prompt_limpio})
            if not isinstance(res_rag, dict) or res_rag.get("estado") != "encontrado":
                return "No encontré información sobre eso en los documentos de la clínica."
            
            resultados = res_rag.get("resultados", [])
            fuentes = ", ".join(set(r.get("fuente", "documento") for r in resultados))
            
            prompt_resumen = (
                f"Basándote ÚNICAMENTE en los siguientes fragmentos recuperados de los documentos institucionales, "
                f"redacta una respuesta breve de 2 o 3 líneas citando la fuente ({fuentes}):\n\n" +
                "\n\n".join([f"Fuente: {r['fuente']}\n{r['fragmento']}" for r in resultados])
            )
            try:
                redaccion_llm = harness.llm_client.chat([{"role": "user", "content": prompt_resumen}])
            except Exception:
                redaccion_llm = f"Según los documentos institucionales ({fuentes}), se contemplan directrices normativas de urgencia."

            texto_final = f"{redaccion_llm.strip()}\n\n---\nFragmentos de respaldo y scores RAG:"
            for r in resultados:
                texto_final += f"\n- Fuente: {r.get('fuente')} | Score: {r.get('score')}\n  {r.get('fragmento')}"
            return texto_final

    memoria.agregar_usuario(prompt_usuario)
    max_vueltas = 8
    vueltas = 0
    reintentos_formato = 0
    tools_ejecutadas = set()
    respuesta_final = None

    while vueltas < max_vueltas:
        vueltas += 1
        historial = memoria.obtener_historial()
        
        try:
            respuesta_bruta = harness.llm_client.chat(historial)
        except Exception as e:
            print(f"[ERROR LLM] {str(e)}")
            return {"error": str(e)}

        print(f"\n[TRAZA LLM] Respuesta cruda recibida (vuelta {vueltas}):\n{respuesta_bruta}")
        
        # Intentar extraer tool call JSON o salida JSON
        json_parsed = extraer_json_respuesta(respuesta_bruta)
        
        if json_parsed and isinstance(json_parsed, dict) and "tool" in json_parsed:
            nombre_tool = json_parsed["tool"]
            args = json_parsed.get("args", {})
            
            # Verificar si es llamada duplicada a tool con mismos argumentos en este turno
            tool_signature = (nombre_tool, json.dumps(args, sort_keys=True))
            if tool_signature in tools_ejecutadas:
                reintentos_formato += 1
                print(f"[TRAZA TOOL] Tool duplicada detectada: {nombre_tool} con args {args}. No se vuelve a ejecutar.")
                memoria.agregar_asistente(respuesta_bruta)
                memoria.agregar_usuario(f"Ya consultaste esta herramienta ({nombre_tool}) con estos argumentos en este turno. No la repitas; el siguiente paso es validar_ley_urgencia (si no lo has hecho) o entregar la respuesta final.")
                continue

            tools_ejecutadas.add(tool_signature)
            print(f"[TRAZA TOOL] El LLM solicita ejecutar tool: {nombre_tool} con args: {args}")

            # REQUISITO 7: No permitir usar un RUT que el usuario no escribió en su mensaje ni usar tools de paciente sin RUT
            if nombre_tool in ["consultar_antecedentes", "validar_ley_urgencia"]:
                match_rut_prompt = re.search(r'\d{7,8}-[\dkK]', prompt_usuario)
                if not match_rut_prompt:
                    print(f"[TRAZA TOOL] Bloqueado: el LLM intentó usar herramientas de paciente sin un RUT proporcionado por el usuario.")
                    memoria.agregar_asistente(respuesta_bruta)
                    memoria.agregar_usuario("El usuario no proporcionó ningún RUT válido en su mensaje. No puede usar herramientas de paciente. Responda directamente indicando que la información no está disponible o que requiere un RUT.")
                    continue

                rut_arg = args.get("rut", "")
                if rut_arg not in prompt_usuario:
                    print(f"[TRAZA TOOL] Bloqueado: el LLM intentó usar un RUT ({rut_arg}) no proporcionado por el usuario en su mensaje.")
                    memoria.agregar_asistente(respuesta_bruta)
                    memoria.agregar_usuario(f"No puede consultar el RUT {rut_arg} porque el usuario no lo escribió en su mensaje. Pida al usuario un RUT válido (ej: 11111111-1).")
                    continue
                
            try:
                resultado_tool = ejecutar_tool(nombre_tool, args)
            except Exception as e:
                resultado_tool = {"error": str(e)}
                
            print(f"[TRAZA TOOL] Resultado de {nombre_tool}:\n{json.dumps(resultado_tool, ensure_ascii=False)}")
            
            if isinstance(resultado_tool, dict) and "error" in resultado_tool and "Tool desconocida" in str(resultado_tool["error"]):
                print(f"[TRAZA TOOL] Tool desconocida interceptada. Guiando al LLM...")
                memoria.agregar_asistente(respuesta_bruta)
                memoria.agregar_usuario("La herramienta solicitada no existe. Si es una consulta sobre reglamentos, protocolos o información general, usa 'buscar_reglamento'. Si la información no está en los documentos institucionales, respóndele al usuario indicando que no se encuentra en ellos.")
                continue
            
            # REQUISITO 6: Manejo directo para buscar_reglamento y consultar_convenio (Texto plano citando fuente)
            if nombre_tool == "buscar_reglamento":
                if isinstance(resultado_tool, dict) and resultado_tool.get("estado") == "encontrado":
                    resultados = resultado_tool.get("resultados", [])
                    fuentes = ", ".join(set(r.get("fuente", "documento") for r in resultados))
                    texto_resp = f"Según los documentos institucionales (Fuente: {fuentes}):\n\n"
                    for r in resultados:
                        texto_resp += f"- [{r.get('fuente')} | Score: {r.get('score')}]: {r.get('fragmento')}\n\n"
                    return texto_resp.strip()
                else:
                    return "No encontrado en los documentos institucionales de la Clínica X."

            if nombre_tool == "consultar_convenio":
                if isinstance(resultado_tool, dict):
                    prev = resultado_tool.get("prevision", "Desconocida")
                    vigente = resultado_tool.get("convenio_vigente", False)
                    cob = resultado_tool.get("cobertura_urgencia", "N/A")
                    obs = resultado_tool.get("observacion", "Sin observaciones.")
                    return f"Según el Servidor de Convenios (Fuente: servidor_convenios.py):\n- Previsión: {prev}\n- Convenio vigente: {vigente}\n- Cobertura de urgencia: {cob}\n- Observación: {obs}"
            
            # Si la tool es validar_ley_urgencia, evaluar si activa skill por antecedentes faltantes
            if nombre_tool == "validar_ley_urgencia" and isinstance(resultado_tool, dict) and "estado" in resultado_tool:
                faltantes = resultado_tool.get("antecedentes_faltantes", [])
                if faltantes:
                    print(f"[TRAZA SKILL] Activando skill clasificar-antecedente-faltante")
                    ruta_skill = os.path.join(AGENT_DIR, "SKILL.md")
                    contenido_skill = ""
                    if os.path.exists(ruta_skill):
                        with open(ruta_skill, "r", encoding="utf-8") as f:
                            contenido_skill = f.read()

                    # Cargar datos reales del paciente para la skill
                    nombre_paciente = "Paciente"
                    motivo_consulta = "Consulta de urgencia"
                    prevision_paciente = "Desconocida"
                    triage_revisado_paciente = False
                    documentos_paciente = []
                    try:
                        ruta_pacientes = os.path.join(AGENT_DIR, "..", "data", "pacientes_simulados.json")
                        with open(ruta_pacientes, "r", encoding="utf-8") as f:
                            pdata = json.load(f)
                            if args.get("rut") in pdata:
                                p_info = pdata[args["rut"]]
                                nombre_paciente = p_info.get("nombre", "Paciente")
                                motivo_consulta = p_info.get("motivo_consulta", "Consulta de urgencia")
                                prevision_paciente = p_info.get("prevision", "Desconocida")
                                triage_revisado_paciente = p_info.get("triage_revisado_por_clinico", False)
                                documentos_paciente = p_info.get("documentos_presentados", [])
                    except Exception:
                        pass

                    # Mensajes nuevos y aislados para la skill
                    mensajes_skill = [
                        {
                            "role": "system",
                            "content": f"{contenido_skill}\n\nInstrucción estricta: Escribe UNA o DOS frases dirigidas al administrativo, pidiendo SOLO los antecedentes de la lista. No menciones previsiones, requisitos ni pasos que no estén en el contexto. Responde SOLO con texto plano en español. NO uses tools ni JSON."
                        },
                        {
                            "role": "user",
                            "content": f"Datos reales del paciente:\n- Nombre: {nombre_paciente}\n- Previsión: {prevision_paciente}\n- Triage revisado por clínico: {triage_revisado_paciente}\n- Documentos presentados: {documentos_paciente}\n- Antecedentes faltantes: {faltantes}\n\nRedacta la solicitud al administrativo."
                        }
                    ]

                    # Llamar al LLM con mensajes aislados para que redacte la explicación basada en la skill (con hasta 2 reintentos)
                    skill_exito = False
                    explicacion_skill = ""
                    for intento_skill in range(2):
                        try:
                            print(f"[TRAZA LLM] Reintento skill generación explicación ({intento_skill+1}/2)")
                            resp_skill = harness.llm_client.chat(mensajes_skill)
                            if resp_skill and len(resp_skill.strip()) > 0:
                                parsed_skill = extraer_json_respuesta(resp_skill)
                                if parsed_skill and isinstance(parsed_skill, dict) and "tool" in parsed_skill:
                                    print(f"[TRAZA SKILL] LLM intentó invocar tool durante skill. Ignorando...")
                                    continue
                                
                                clean_resp = resp_skill.strip()
                                if clean_resp.startswith("```"):
                                    clean_resp = clean_resp.split("\n", 1)[1] if "\n" in clean_resp else clean_resp
                                    if clean_resp.endswith("```"):
                                        clean_resp = clean_resp[:-3].strip()

                                # Validación anti-alucinación
                                lower_clean = clean_resp.lower()
                                alucino_prevision = False
                                if "isapre" in lower_clean and "fonasa" in prevision_paciente.lower() or "fonasa" in lower_clean and "isapre" in prevision_paciente.lower():
                                    alucino_prevision = True
                                
                                alucino_triage = False
                                if triage_revisado_paciente and ("revisar" in lower_clean or "validar triage" in lower_clean or "falta triage" in lower_clean):
                                    alucino_triage = True

                                if alucino_prevision or alucino_triage:
                                    print(f"[TRAZA SKILL] Texto generado alucinó previsiones o triage ya revisado. Descartado, usando plantilla.")
                                    skill_exito = False
                                    break

                                explicacion_skill = clean_resp
                                skill_exito = True
                                break
                        except Exception:
                            pass

                    if skill_exito:
                        resultado_tool["explicacion"] = explicacion_skill
                        memoria.agregar_asistente(respuesta_bruta)
                        memoria.agregar_tool(nombre_tool, resultado_tool)
                    else:
                        print(f"[TRAZA SKILL] Usando plantilla fija de skill.")
                        resultado_tool["explicacion"] = f"Solicite al paciente {nombre_paciente} los siguientes documentos ausentes: {', '.join(faltantes)} para continuar con el proceso de admisión de urgencia."
                        memoria.agregar_asistente(respuesta_bruta)
                        memoria.agregar_tool(nombre_tool, resultado_tool)

                try:
                    validar_datos(resultado_tool, "output")
                    print(f"[TRAZA VALIDADOR] Salida validada correctamente contra output.schema.json.")
                    respuesta_final = resultado_tool
                    break
                except ValidacionError as ve:
                    print(f"[TRAZA VALIDADOR] Error de validación: {str(ve)}")
                    # Si falla validación de tool, agregar error al historial
                    memoria.agregar_asistente(respuesta_bruta)
                    memoria.agregar_tool(nombre_tool, resultado_tool)
                    continue

            # Agregar al historial la llamada y el resultado para otras tools
            memoria.agregar_asistente(respuesta_bruta)
            memoria.agregar_tool(nombre_tool, resultado_tool)
            continue
            
        elif json_parsed and isinstance(json_parsed, dict) and "estado" in json_parsed:
            # Es un candidato a respuesta final (JSON con estado)
            try:
                validar_datos(json_parsed, "output")
                print(f"[TRAZA VALIDADOR] Salida validada correctamente contra output.schema.json.")
                respuesta_final = json_parsed
                memoria.agregar_asistente(respuesta_bruta)
                break
            except ValidacionError as ve:
                print(f"[TRAZA VALIDADOR] Error de validación de esquema: {str(ve)}. Reintentando corrección...")
                memoria.agregar_asistente(respuesta_bruta)
                memoria.agregar_usuario(f"Error de validación: {str(ve)}. Asegúrate de que 'explicacion' no esté vacía y que cumpla estrictamente con output.schema.json.")
                continue
        else:
            # Respuesta vacía, texto conversacional o JSON inválido
            reintentos_formato += 1
            if reintentos_formato <= 2:
                print(f"[TRAZA LLM] reintento {reintentos_formato}: respuesta vacía o formato incorrecto.")
                memoria.agregar_asistente(respuesta_bruta)
                recordatorio = (
                    "Tu respuesta estuvo vacía o no tiene el formato esperado. "
                    "Recuerda el flujo obligatorio: "
                    "1) Si aún falta consultar antecedentes, responde solo {\"tool\": \"consultar_antecedentes\", \"args\": {\"rut\": \"...\"}}. "
                    "2) Si ya consultaste antecedentes y falta validar, responde solo {\"tool\": \"validar_ley_urgencia\", \"args\": {\"rut\": \"...\"}}. "
                    "3) Si ya tienes todos los datos y validaciones, responde el JSON final con estado, explicacion (no vacía), antecedentes_faltantes y reglas_aplicadas."
                )
                memoria.agregar_usuario(recordatorio)
                continue
            else:
                print(f"[ERROR] El LLM no entregó una respuesta válida ni invocó herramientas tras {reintentos_formato} reintentos de formato.")
                return {
                    "error": "El modelo no entregó una respuesta válida ni invocó herramientas correctamente.",
                    "ultima_respuesta_bruta": respuesta_bruta
                }

    if not respuesta_final:
        return {
            "error": "Se superó el límite de vueltas sin una respuesta final concluyente.",
            "estado": "falta_informacion"
        }

    # Registrar en ejecucion.jsonl
    registrar_ejecucion({
        "prompt_usuario": prompt_usuario,
        "respuesta_final": respuesta_final,
        "vueltas": vueltas
    })

    return respuesta_final

def iniciar_chat_interactivo():
    """Inicia el bucle interactivo de chat por consola."""
    print("=" * 60)
    print(" Agente P02 - Verificación Administrativa de Urgencia (Clínica X)")
    print(" Grupo 6 - CINF110 (Agentes de IA)")
    print(" Escribe 'salir' para terminar la sesión.")
    print("=" * 60)
    
    system_prompt = cargar_prompt_sistema()
    memoria = MemoriaConversacional(system_prompt=system_prompt)
    
    while True:
        try:
            usuario_input = input("\nUsuario: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSaliendo...")
            break
            
        if not usuario_input:
            continue
            
        if usuario_input.lower() in ["salir", "exit", "quit"]:
            print("Saliendo de la sesión del Agente P02. ¡Hasta luego!")
            break
            
        resultado = ejecutar_turno(usuario_input, memoria)
        print("\n--- Respuesta del Agente P02 ---")
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
        print("-" * 34)

if __name__ == "__main__":
    iniciar_chat_interactivo()
