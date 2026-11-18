"""Real headlines from the February and March 2025 KPI releases.

Two runs over the same headlines:
- hand-extracted claims -> phrase tables -> mapper -> verifier (no model, always runs)
- recorded Haiku extraction -> the same (runs once `norfigures record-agents` has recorded them)

Official values for 2025 come from the closed SSB tables that hold the rates
as published (B24). Headlines are quoted with a link to the outlet.
"""

import unittest
from datetime import date
from pathlib import Path

from norfigures.agents.extractor import recording_path
from norfigures.claims import parse_json
from norfigures.events import RunLog
from norfigures.ledger import load
from norfigures.pipeline import check_text, prepare, verify_claims
from norfigures.report import exit_code

from tests.helpers import client

DIR = Path(__file__).parent / "headlines"
TODAY = date(2026, 11, 18)


def load_headlines():
    return [(p.stem, parse_json(p.read_text(encoding="utf-8"))) for p in sorted(DIR.glob("*.json"))]


class HeadlinesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.series = load()
        cls.headlines = load_headlines()

    def test_set_is_present(self):
        self.assertGreaterEqual(len(self.headlines), 8)

    def test_hand_extracted_claims(self):
        for name, h in self.headlines:
            with self.subTest(headline=name):
                log = RunLog()
                claims = prepare([dict(c) for c in h["claims"]], self.series, log)
                out = verify_claims(claims, client(), self.series,
                                    published=date.fromisoformat(h["published"]), today=TODAY, log=log)
                self.assertEqual([r.verdict for r in out.results], h["expected"]["verdicts"],
                                 f"{name}: {[(r.labels, r.notes) for r in out.results]}")
                self.assertEqual(exit_code(out.results), h["expected"]["exit_code"], name)

    def test_recorded_extraction(self):
        missing = [n for n, h in self.headlines if not recording_path(h["text"], h["published"]).exists()]
        if missing:
            self.skipTest(f"no recorded extractor output for {len(missing)} headlines; "
                          "run `norfigures record-agents`")
        for name, h in self.headlines:
            with self.subTest(headline=name):
                out = check_text(h["text"], client(), self.series, "replay",
                                 published=date.fromisoformat(h["published"]), today=TODAY, log=RunLog())
                checked = [r.verdict for r in out.results]
                # A no-figure headline may yield no claim at all; the exit code is what matters.
                if h["expected"]["exit_code"] == 0:
                    self.assertEqual(checked, h["expected"]["verdicts"], name)
                else:
                    self.assertNotIn("mismatched", checked, f"{name}: false alarm")
                self.assertEqual(exit_code(out.results), h["expected"]["exit_code"], name)


if __name__ == "__main__":
    unittest.main()
