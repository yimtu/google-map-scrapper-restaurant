import unittest
from pathlib import Path


class GeminiContractTests(unittest.TestCase):
    def test_gemini_context_imports_canonical_agent_contract(self):
        root = Path(__file__).parents[1]
        gemini = (root / "GEMINI.md").read_text(encoding="utf-8")
        agents = (root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("@./AGENTS.md", gemini)
        self.assertIn("/memory show", gemini)
        self.assertIn("not the product's decision engine", gemini)
        for invariant in (
            "REQUESTED", "ADDITIONAL", "UNCLASSIFIED",
            "Uber Eats", "Rappi", "DiDi Food",
            "3 o más locales", "un solo PDF",
        ):
            self.assertIn(invariant, agents)


if __name__ == "__main__":
    unittest.main()
