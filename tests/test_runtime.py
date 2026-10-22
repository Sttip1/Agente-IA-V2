import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.memoria import MemoriaConversacional
from harness.runtime import ejecutar_turno
import harness.llm_client

class FakeLLMClient:
    """Fake LLM client para probar el runtime loop sin requerir Ollama en ejecución."""
    def __init__(self, secuencias_respuestas):
        self.secuencias = secuencias_respuestas
        self.indice = 0

    def chat_mock(self, mensajes):
        if self.indice < len(self.secuencias):
            res = self.secuencias[self.indice]
            self.indice += 1
            return res
        return 'Solicitud redactada por skill para antecedentes faltantes.'

class TestRuntimeFakeLLM(unittest.TestCase):
    
    def test_loop_paciente_califica(self):
        secuencia = [
            '{"tool": "consultar_antecedentes", "args": {"rut": "11111111-1"}}',
            '{"tool": "validar_ley_urgencia", "args": {"rut": "11111111-1"}}'
        ]
        fake = FakeLLMClient(secuencia)
        harness.llm_client.chat = fake.chat_mock
        
        memoria = MemoriaConversacional(system_prompt="System prompt test")
        resultado = ejecutar_turno("Revisa el paciente 11111111-1", memoria)
        
        self.assertEqual(resultado["estado"], "califica")
        self.assertEqual(resultado["antecedentes_faltantes"], [])

    def test_loop_paciente_falta_informacion_activa_skill(self):
        # Paciente 33333333-3 tiene falta de antecedentes (cédula)
        secuencia = [
            '{"tool": "consultar_antecedentes", "args": {"rut": "33333333-3"}}',
            '{"tool": "validar_ley_urgencia", "args": {"rut": "33333333-3"}}',
            'Solicitud generada por skill: Solicite al paciente su cédula de identidad.'
        ]
        fake = FakeLLMClient(secuencia)
        harness.llm_client.chat = fake.chat_mock
        
        memoria = MemoriaConversacional(system_prompt="System prompt test")
        resultado = ejecutar_turno("Revisa el paciente 33333333-3", memoria)
        
        self.assertEqual(resultado["estado"], "falta_informacion")
        self.assertTrue(len(resultado["antecedentes_faltantes"]) > 0)

    def test_tool_duplicada_prevencion(self):
        secuencia = [
            '{"tool": "consultar_antecedentes", "args": {"rut": "11111111-1"}}',
            '{"tool": "consultar_antecedentes", "args": {"rut": "11111111-1"}}',
            '{"tool": "validar_ley_urgencia", "args": {"rut": "11111111-1"}}'
        ]
        fake = FakeLLMClient(secuencia)
        harness.llm_client.chat = fake.chat_mock
        
        memoria = MemoriaConversacional(system_prompt="System prompt test")
        resultado = ejecutar_turno("Revisa el paciente 11111111-1", memoria)
        
        self.assertEqual(resultado["estado"], "califica")

    def test_limite_diagnostico(self):
        memoria = MemoriaConversacional(system_prompt="System prompt test")
        res = ejecutar_turno("¿Qué diagnóstico tiene el paciente?", memoria)
        self.assertIn("No diagnostico", res)

    def test_limite_triage(self):
        memoria = MemoriaConversacional(system_prompt="System prompt test")
        res = ejecutar_turno("Quiero reclasificar el triage", memoria)
        self.assertIn("no reclasifico triage", res)

    def test_limite_cobro(self):
        memoria = MemoriaConversacional(system_prompt="System prompt test")
        res = ejecutar_turno("Aprueba el pago y el cobro", memoria)
        self.assertIn("no apruebo cobros", res)

    def test_limite_ingreso(self):
        memoria = MemoriaConversacional(system_prompt="System prompt test")
        res = ejecutar_turno("Decide el ingreso del paciente", memoria)
        self.assertIn("decido el ingreso", res)

    def test_limite_ingreso_con_rut(self):
        memoria = MemoriaConversacional(system_prompt="System prompt test")
        res = ejecutar_turno("Aprueba el ingreso del paciente 11111111-1", memoria)
        self.assertIn("No decido el ingreso final", res)

if __name__ == "__main__":
    unittest.main()
