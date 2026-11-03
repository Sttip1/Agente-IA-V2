"""Utilidades puras: texto, RUT chileno, extracción de JSON."""
import json
import re
import unicodedata


def norm(s):
    """minúsculas y sin tildes, para comparar texto."""
    s = unicodedata.normalize("NFD", str(s))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


RUT_RE = re.compile(r"(?<![\d.])(\d{1,2}(?:\.?\d{3}){2})\s?-\s?([\dkK])(?![\w])")


def normalizar_rut(s):
    return str(s).strip().replace(".", "").replace(" ", "").upper()


def dv_rut(numero):
    suma, f = 0, 2
    for d in reversed(numero):
        suma += int(d) * f
        f = 2 if f == 7 else f + 1
    r = 11 - suma % 11
    return "0" if r == 11 else "K" if r == 10 else str(r)


def rut_valido(rut):
    m = re.fullmatch(r"(\d{7,8})-([\dK])", normalizar_rut(rut))
    return bool(m) and dv_rut(m.group(1)) == m.group(2)


def extraer_ruts(texto):
    """RUTs del texto del usuario, normalizados (acepta puntos y espacios)."""
    return [normalizar_rut(a + "-" + b) for a, b in RUT_RE.findall(texto or "")]


_REFERENCIA_PACIENTE = re.compile(
    r"\b(su|sus|le|les|ella|paciente|pacientes|caso|casos|ese|esa|mismo|misma|apto|apta|califica|calificar|verifica\w*|evalua\w*|"
    r"revisa\w*|falta\w*|antecedentes?|cumple|acoge\w*|tramit\w*|reglas?|nuevamente|denuevo)\b|de nuevo")


def refiere_a_paciente(texto):
    """True si el mensaje alude a un paciente/caso (RUT, "su previsión", "¿qué le falta?", "verifica..."),
    es decir, si tiene sentido usar el RUT del contexto de la sesión. Heurística deliberadamente simple."""
    t = norm(texto)
    return bool(extraer_ruts(texto)) or bool(_REFERENCIA_PACIENTE.search(t))


def ocultar_ruts(texto):
    """Enmascara RUTs para los logs (11111111-1 -> 11.***.***-1)."""
    return RUT_RE.sub(lambda m: f"{m.group(1).replace('.', '')[:2]}.***.***-{m.group(2)}", texto)


def extraer_json(texto):
    """Primer objeto JSON de la respuesta del LLM (tolera ```json ...``` y texto extra)."""
    if not isinstance(texto, str):
        return None
    t = texto.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        v = json.loads(t)
        return v if isinstance(v, dict) else None
    except json.JSONDecodeError:
        pass
    dec = json.JSONDecoder()
    for i, c in enumerate(t):
        if c == "{":
            try:
                v, _ = dec.raw_decode(t[i:])
                if isinstance(v, dict):
                    return v
            except json.JSONDecodeError:
                continue
    return None
