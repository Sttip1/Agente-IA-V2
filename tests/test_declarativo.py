import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakes import RAIZ, SKILL_FALTANTES, agente_con  # noqa: E402

from harness.config import AGENT_DIR  # noqa: E402
from harness.datos import cargar_pacientes  # noqa: E402
from harness.declarativo import cargar_declaracion, parsear_yaml, separar_frontmatter  # noqa: E402
from harness.errores import ConfiguracionError  # noqa: E402
from harness.reglas import REGLAS  # noqa: E402
from harness.schema_validator import validar_schema  # noqa: E402


def _leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def _escribir(ruta, txt):
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(txt)


class TestParsers(unittest.TestCase):
    def test_yaml(self):
        d = parsear_yaml('# c\nid: P02\nn: 8\nok: true\nlista:\n  - "a: b"\n  - c\nversion: 1.0.0\n')
        self.assertEqual(d, {"id": "P02", "n": 8, "ok": True, "lista": ["a: b", "c"], "version": "1.0.0"})

    def test_yaml_invalido(self):
        with self.assertRaises(ConfiguracionError):
            parsear_yaml("a: [sin cerrar")

    def test_frontmatter(self):
        meta, cuerpo = separar_frontmatter("---\nname: x\ndescription: algo largo\n---\n# Titulo\ntexto")
        self.assertEqual(meta, {"name": "x", "description": "algo largo"})
        self.assertTrue(cuerpo.startswith("# Titulo"))
        self.assertEqual(separar_frontmatter("sin frontmatter"), ({}, "sin frontmatter"))
        with self.assertRaises(ConfiguracionError):
            separar_frontmatter("---\nname: x\nsin cierre")


class TestDeclaracion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decl = cargar_declaracion()

    def copia(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        destino = os.path.join(d, "agent")
        shutil.copytree(AGENT_DIR, destino)
        return destino

    def test_carga_real(self):
        self.assertEqual(self.decl.manifest["id"], "P02")
        self.assertEqual(self.decl.version, "2.0.0")
        self.assertEqual(set(self.decl.tools), {"consultar_registro", "evaluar_reglas", "buscar_reglamento", "consultar_convenio", "cargar_skill"})
        self.assertEqual(set(self.decl.skills), {"clasificar-antecedente-faltante", "responder-consulta-normativa"})
        self.assertEqual(set(self.decl.schema_salida), {"veredicto", "respuesta", "fuera_de_alcance"})
        self.assertEqual(self.decl.ejecucion["max_pasos"], 8)

    def test_agent_md_es_consistente_con_el_codigo(self):
        md = self.decl.agent_md
        for regla in REGLAS:
            self.assertIn(regla, md, f"agent.md debe mencionar {regla}")
        for tipo in self.decl.schema_salida:
            self.assertIn(f'"{tipo}"', md, f"agent.md debe mostrar el formato de {tipo}")
        for tool in self.decl.manifest["tools"]:
            self.assertIn(tool, md, f"agent.md debe mencionar la tool {tool}")
        for skill in self.decl.skills:
            self.assertIn(skill, md, f"agent.md debe mencionar la skill {skill}")
        for estado in self.decl.manifest["estados"]:
            self.assertIn(estado, md)

    def test_registros_de_prueba_cumplen_el_esquema_de_entrada(self):
        import json
        with open(os.path.join(RAIZ, "data", "paciente.schema.json"), encoding="utf-8") as f:
            props = json.load(f)["properties"]
        for rut, p in cargar_pacientes().items():
            for campo, valor in p.items():
                if campo in props and valor is not None:
                    self.assertIsNone(validar_schema(valor, props[campo]), f"{rut}.{campo}")

    def test_falta_carpeta(self):
        with self.assertRaises(ConfiguracionError):
            cargar_declaracion("/ruta/que/no/existe")

    def test_manifest_permite_una_tool_no_declarada_en_tools_yaml(self):
        d = self.copia()
        ruta = os.path.join(d, "manifest.yaml")
        _escribir(ruta, _leer(ruta).replace("  - cargar_skill", "  - cargar_skill\n  - tool_no_declarada", 1))
        with self.assertRaises(ConfiguracionError) as cm:
            cargar_declaracion(d)
        self.assertIn("tools.yaml no declara", str(cm.exception))

    def test_tool_sin_input_schema(self):
        d = self.copia()
        ruta = os.path.join(d, "tools.yaml")
        _escribir(ruta, "tools:\n  - name: x\n    description: algo\n    origin: local\n    handler: x\n")
        with self.assertRaises(ConfiguracionError) as cm:
            cargar_declaracion(d)
        self.assertIn("input_schema", str(cm.exception))

    def test_salidas_del_manifest_deben_coincidir_con_el_schema(self):
        d = self.copia()
        ruta = os.path.join(d, "manifest.yaml")
        _escribir(ruta, _leer(ruta).replace("  - fuera_de_alcance\n", "  - otra_cosa\n", 1))
        with self.assertRaises(ConfiguracionError):
            cargar_declaracion(d)

    def test_manifest_sin_claves(self):
        d = self.copia()
        _escribir(os.path.join(d, "manifest.yaml"), "id: P02\n")
        with self.assertRaises(ConfiguracionError) as cm:
            cargar_declaracion(d)
        self.assertIn("faltan las claves", str(cm.exception))

    def test_skill_con_nombre_que_no_coincide(self):
        d = self.copia()
        ruta = os.path.join(d, "skills", SKILL_FALTANTES, "SKILL.md")
        _escribir(ruta, _leer(ruta).replace(f"name: {SKILL_FALTANTES}", "name: otro", 1))
        with self.assertRaises(ConfiguracionError):
            cargar_declaracion(d)

    def test_skill_inexistente_en_manifest(self):
        d = self.copia()
        ruta = os.path.join(d, "manifest.yaml")
        _escribir(ruta, _leer(ruta).replace("  - responder-consulta-normativa", "  - fantasma"))
        with self.assertRaises(ConfiguracionError):
            cargar_declaracion(d)

    def test_parametro_de_ejecucion_invalido(self):
        d = self.copia()
        ruta = os.path.join(d, "manifest.yaml")
        _escribir(ruta, _leer(ruta).replace("max_pasos: 8", "max_pasos: muchos"))
        with self.assertRaises(ConfiguracionError):
            cargar_declaracion(d)


class TestManifestComoListaBlanca(unittest.TestCase):
    def test_solo_se_exponen_las_tools_del_manifest(self):
        ag, _ = agente_con([], permitidas=["evaluar_reglas"])
        self.assertEqual(list(ag.herr.registro), ["evaluar_reglas"])
        # agent.md es prosa y puede nombrar otras tools; lo que cuenta es la sección generada de herramientas.
        sistema = ag.mem.ventana()[0]["content"]
        seccion = sistema.split("## Herramientas disponibles")[1].split("\n## ")[0]
        self.assertIn("evaluar_reglas", seccion)
        self.assertNotIn("buscar_reglamento", seccion)
        self.assertNotIn("cargar_skill", seccion)

    def test_tool_declarada_pero_inexistente_genera_aviso(self):
        ag, _ = agente_con([], permitidas=["evaluar_reglas", "tool_fantasma"])
        self.assertTrue(any("tool_fantasma" in a for a in ag.herr.avisos))

    def test_sin_evaluar_reglas_hay_aviso(self):
        ag, _ = agente_con([], permitidas=["buscar_reglamento"])
        self.assertTrue(any("evaluar_reglas" in a for a in ag.herr.avisos))

    def test_prompt_contiene_agent_md_tools_skills_y_valores(self):
        ag, _ = agente_con([])
        sistema = ag.mem.ventana()[0]["content"]
        self.assertIn("Agente P02", sistema)                       # agent.md
        self.assertIn("- evaluar_reglas(rut)", sistema)            # tools habilitadas
        self.assertIn(f"- {SKILL_FALTANTES}:", sistema)           # catálogo (solo name + description)
        self.assertNotIn("Cuándo usarla", sistema)                 # el cuerpo de la skill NO está cargado
        self.assertIn("NO diagnostica | NO reclasifica triage", sistema)
        self.assertIn("RUTs mencionados por el usuario en esta sesión: ninguno", sistema)

    def test_cargar_skill_devuelve_el_cuerpo_y_rechaza_inventadas(self):
        ag, _ = agente_con([])
        ok = ag.herr.registro["cargar_skill"]["fn"](nombre=SKILL_FALTANTES)
        self.assertIn("Cuándo usarla", ok["instrucciones"])
        self.assertIn(SKILL_FALTANTES, ag.herr.skills_cargadas)
        self.assertIn("error", ag.herr.registro["cargar_skill"]["fn"](nombre="inventada"))


if __name__ == "__main__":
    unittest.main()
