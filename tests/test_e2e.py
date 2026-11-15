"""Full loop on every fixture text: recorded extractor output -> phrase tables ->
mapper -> verifier. Needs recorded model outputs in tests/recorded/agents/;
create them with `norfigures record-agents` (needs an API key)."""

import unittest
from datetime import date

from norfigures.agents.extractor import recording_path
from norfigures.events import RunLog
from norfigures.ledger import load
from norfigures.pipeline import check_text
from norfigures.report import exit_code

from tests.helpers import TODAY, client, load_cases

CASES = load_cases()


class EndToEndTest(unittest.TestCase):
    def test_full_loop_on_recorded_extractions(self):
        series = load()
        missing = [n for n, c in CASES if not recording_path(c["text"], c.get("published")).exists()]
        if missing:
            self.skipTest(f"no recorded extractor output for {len(missing)} of {len(CASES)} cases; "
                          "run `norfigures record-agents` with an API key")
        for name, case in CASES:
            with self.subTest(case=name):
                exp = case.get("expected_e2e", case["expected"])
                pub = date.fromisoformat(case["published"]) if case["published"] else None
                out = check_text(case["text"], client(), series, "replay",
                                 published=pub, today=TODAY, log=RunLog())
                verdicts = [r.verdict for r in out.results]
                wanted = [c["verdict"] for c in exp["claims"].values()]
                self.assertEqual(verdicts, wanted, f"{name}: {[(r.claim.source_text, r.labels, r.notes) for r in out.results]}")
                self.assertEqual(exit_code(out.results), exp["exit_code"], name)


if __name__ == "__main__":
    unittest.main()
