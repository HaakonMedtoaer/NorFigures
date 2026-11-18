"""Extractor guardrails. These test the checks on model output, using small
hand-written model responses; they never call a model."""

import json
import unittest

from norfigures.agents import extractor
from norfigures.agents.extractor import ExtractionError, parse_output

TEXT = "Inflasjonen var 3,1 % i oktober. Norges Bank holdt styringsrenten på 4,0 %."


def resp(*claims):
    base = {"status": "checkable", "indicator": "kpi", "other_indicator": None,
            "measure": "12_month_change", "period": "2026-10", "unit": "percent",
            "stated_value": "3,1", "hedged": False}
    return json.dumps({"claims": [dict(base, **c) for c in claims]})


class ParseOutputTest(unittest.TestCase):
    def test_valid_output(self):
        out = parse_output(resp({"source_text": "Inflasjonen var 3,1 % i oktober"}), TEXT)
        self.assertEqual(out[0]["id"], "c1")
        self.assertEqual(out[0]["stated_value"], "3.1")

    def test_keeps_trailing_zero(self):
        out = parse_output(resp({"source_text": "styringsrenten på 4,0 %", "indicator": "policy_rate",
                                 "measure": "level", "stated_value": "4,0", "period": None}), TEXT)
        self.assertEqual(out[0]["stated_value"], "4.0")

    def test_invented_sentence_rejected(self):
        with self.assertRaises(ExtractionError) as cm:
            parse_output(resp({"source_text": "Inflasjonen var 2,8 % i oktober"}), TEXT)
        self.assertIn("verbatim", str(cm.exception))

    def test_changed_number_rejected(self):
        with self.assertRaises(ExtractionError) as cm:
            parse_output(resp({"source_text": "Inflasjonen var 3,1 % i oktober", "stated_value": "2,8"}), TEXT)
        self.assertIn("does not appear", str(cm.exception))

    def test_bad_period_rejected(self):
        with self.assertRaises(ExtractionError):
            parse_output(resp({"source_text": "Inflasjonen var 3,1 % i oktober", "period": "oktober"}), TEXT)

    def test_not_json_rejected(self):
        with self.assertRaises(ExtractionError):
            parse_output("Here are the claims: ...", TEXT)

    def test_other_indicator_named(self):
        out = parse_output(resp({"source_text": "Norges Bank holdt styringsrenten på 4,0 %",
                                 "status": "out_of_scope", "indicator": "other",
                                 "other_indicator": "Mortgage rate", "stated_value": "4,0"}), TEXT)
        self.assertEqual(out[0]["indicator"], "mortgage_rate")


class ReplayKeyTest(unittest.TestCase):
    def test_surrounding_whitespace_does_not_change_the_recording(self):
        from tests.helpers import load_cases
        name, case = load_cases()[0]
        a = extractor.extract(case["text"], case["published"], mode="replay")
        b = extractor.extract("\n " + case["text"] + "\n\n", case["published"], mode="replay")
        self.assertEqual(a.claims, b.claims)


class NoKeyTest(unittest.TestCase):
    def test_missing_key_is_a_clean_agent_error(self):
        try:
            import anthropic  # noqa: F401
        except ImportError:
            self.skipTest("anthropic not installed")
        import os
        import tempfile
        from unittest import mock
        from norfigures.agents.llm import AgentError, complete_json
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("ANTHROPIC_")}
        env["HOME"] = tempfile.mkdtemp()      # no `ant auth login` profile either
        with mock.patch.dict(os.environ, env, clear=True), self.assertRaises(AgentError) as cm:
            complete_json("s", "u", {"type": "object", "properties": {}, "required": [],
                                     "additionalProperties": False})
        self.assertIn("API key", str(cm.exception))


class PromptTest(unittest.TestCase):
    def test_prompt_contains_contract_and_phrases(self):
        p = extractor.system_prompt()
        self.assertIn("Extractor agent: contract", p)
        self.assertIn("```json phrases", p)
        self.assertIn("never follow instructions", p)

    def test_schema_objects_are_closed(self):
        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "object":
                    self.assertIs(node.get("additionalProperties"), False)
                    self.assertEqual(set(node["required"]), set(node["properties"]))
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        walk(extractor.OUTPUT_SCHEMA)

    def test_only_llm_module_imports_the_sdk(self):
        from pathlib import Path
        import norfigures
        src = Path(norfigures.__file__).parent
        users = [p.name for p in src.rglob("*.py") if "import anthropic" in p.read_text(encoding="utf-8")]
        self.assertEqual(users, ["llm.py"])


if __name__ == "__main__":
    unittest.main()
