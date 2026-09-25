import unittest
from pathlib import Path


class AgentPlatformContractTests(unittest.TestCase):
    def test_pending_queue_requires_active_integrated_browser_research(self):
        contract = (Path(__file__).parents[1] / "AGENTS.md").read_text(encoding="utf-8")
        required = [
            "DEBE resolverlos activamente utilizando las capacidades web disponibles en su entorno",
            "el agente realiza la investigación con el navegador o herramienta web disponible",
            "Un snippet o la memoria del modelo no son evidencia",
            "Que el nombre aparezca en un buscador no basta",
            "Abre el resultado",
            "foodscan verify-platforms",
            "conserva `PENDING`",
        ]
        for phrase in required:
            self.assertIn(phrase, contract)


if __name__ == "__main__":
    unittest.main()
