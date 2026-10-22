import json
import os

class ValidacionError(Exception):
    """Excepción propia para errores de validación de esquemas."""
    pass

def cargar_schema(nombre_schema):
    """Carga un esquema JSON desde la carpeta agent/."""
    ruta = os.path.join(os.path.dirname(__file__), "..", "agent", f"{nombre_schema}.schema.json")
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)

def validar_datos(datos, schema_nombre):
    """
    Valida un diccionario de datos contra un esquema JSON propio (input o output)
    verificando tipos, campos requeridos y enums básicos.
    Lanza ValidacionError si hay incumplimientos.
    """
    schema = cargar_schema(schema_nombre)
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    # Verificar campos requeridos
    for campo in required:
        if campo not in datos:
            raise ValidacionError(f"Falta el campo requerido: '{campo}' según {schema_nombre}.schema.json")

    # Verificar tipos y propiedades
    for campo, valor in datos.items():
        if campo in properties:
            prop_def = properties[campo]
            esperado = prop_def.get("type")
            
            # Validación de tipos en Python
            if esperado == "string" and not isinstance(valor, str):
                raise ValidacionError(f"El campo '{campo}' debe ser de tipo string, recibido {type(valor).__name__}")
            elif esperado == "string" and isinstance(valor, str) and prop_def.get("minLength", 0) > 0 and len(valor.strip()) < prop_def["minLength"]:
                raise ValidacionError(f"El campo '{campo}' no puede estar vacío (minLength={prop_def['minLength']})")
            elif esperado == "boolean" and not isinstance(valor, bool):
                raise ValidacionError(f"El campo '{campo}' debe ser de tipo boolean, recibido {type(valor).__name__}")
            elif esperado == "array" and not isinstance(valor, list):
                raise ValidacionError(f"El campo '{campo}' debe ser de tipo array (lista), recibido {type(valor).__name__}")
            
            # Validación de enum
            if "enum" in prop_def and valor not in prop_def["enum"]:
                raise ValidacionError(f"El valor '{valor}' para el campo '{campo}' no es válido. Opciones permitidas: {prop_def['enum']}")

    return True
