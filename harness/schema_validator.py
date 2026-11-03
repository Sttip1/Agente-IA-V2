"""Validación con JSON Schema (draft-07) de las entradas, salidas del LLM y argumentos de tools.

Un solo punto de validación para todo el arnés. Los mensajes de error van en español y con la ruta del campo,
porque se le devuelven al LLM para que se corrija o se muestran al usuario/API."""
import json
import os

from jsonschema import Draft7Validator, FormatChecker

from harness.errores import ConfiguracionError

_FORMATOS = FormatChecker()


def _ruta(error):
    ruta = "$"
    for p in error.absolute_path:
        ruta += f"[{p}]" if isinstance(p, int) else f".{p}"
    return ruta


def _mensaje(error):
    ruta, v = _ruta(error), error.validator
    if v == "required":
        faltante = error.message.split("'")[1] if "'" in error.message else "?"
        return f"{ruta}: falta el campo requerido '{faltante}'"
    if v == "type":
        return f"{ruta}: debe ser {error.validator_value}, llegó {type(error.instance).__name__}"
    if v == "enum":
        return f"{ruta}: valor '{error.instance}' no permitido; opciones: {error.validator_value}"
    if v in ("minLength", "minItems"):
        return f"{ruta}: no puede estar vacío o es demasiado corto (mínimo {error.validator_value})"
    if v in ("maxLength", "maxItems"):
        return f"{ruta}: es demasiado largo (máximo {error.validator_value})"
    if v == "additionalProperties":
        return f"{ruta}: contiene campos no permitidos ({error.message})"
    if v == "pattern":
        return f"{ruta}: no cumple el formato esperado ({error.validator_value})"
    return f"{ruta}: {error.message}"


def errores(dato, schema):
    """Lista de mensajes de error (vacía si el dato cumple el schema)."""
    validador = Draft7Validator(schema, format_checker=_FORMATOS)
    return [_mensaje(e) for e in sorted(validador.iter_errors(dato), key=lambda e: list(map(str, e.absolute_path)))]


def validar_schema(dato, schema):
    """None si es válido o el primer error como texto (formato que consume el arnés)."""
    errs = errores(dato, schema)
    return errs[0] if errs else None


def schema_es_valido(schema):
    """Comprueba que el propio schema sea un JSON Schema draft-07 bien formado."""
    try:
        Draft7Validator.check_schema(schema)
    except Exception as e:  # jsonschema.SchemaError
        raise ConfiguracionError(f"JSON Schema mal formado: {e}") from e


def cargar_json(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise ConfiguracionError(f"No se pudo leer el JSON {ruta}: {e}") from e


def validar_ejemplos(carpeta_ejemplos, schemas):
    """Ejecuta los ejemplos de agent/examples/: cada archivo es {"schema": nombre, "descripcion": ..., "dato": ...}
    dentro de valid/ (debe cumplir) o invalid/ (debe fallar). Devuelve [(archivo, esperado_valido, ok, detalle)]."""
    resultados = []
    for sub, esperado in (("valid", True), ("invalid", False)):
        carpeta = os.path.join(carpeta_ejemplos, sub)
        if not os.path.isdir(carpeta):
            continue
        for nombre in sorted(os.listdir(carpeta)):
            if not nombre.endswith(".json"):
                continue
            ej = cargar_json(os.path.join(carpeta, nombre))
            schema = schemas[ej["schema"]]
            errs = errores(ej["dato"], schema)
            resultados.append((f"{sub}/{nombre}", esperado, (not errs) == esperado, errs[0] if errs else "válido"))
    return resultados
