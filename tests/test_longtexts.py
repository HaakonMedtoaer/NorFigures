"""Long real texts: SSB release articles and Norges Bank press releases.

Every figure in these texts is correct, so any mismatch is a false alarm.
Three runs over the same texts:
- careful: the claims as the extractor contract asks for them -> exact verdicts
- careless: every claim forced to 'checkable' and to headline KPI or the policy
  rate, as a sloppy extractor might -> code must still raise no false alarm
- recorded: real extractor output, once `norfigures record-agents` has run
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

DIR = Path(__file__).parent / "longtexts"
TODAY = date(2026, 11, 19)


def load_texts():
    return [(p.stem, parse_json(p.read_text(encoding="utf-8"))) for p in sorted(DIR.glob("*.json"))]


def careless(claims, indicator):
    out = []
    for c in claims:
        c = dict(c, status="checkable", labels=[])
        if c["indicator"] not in ("kpi", "policy_rate", "eurnok"):
            c["indicator"] = "kpi" if c["indicator"] == "kpi_jae" else indicator
        if c["indicator"] == "kpi" and c["measure"] == "level":
            c["measure"] = "12_month_change"
        out.append(c)
    return out


class LongTextsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.series = load()
        cls.texts = load_texts()

    def _run(self, claims, published):
        log = RunLog()
        prepared = prepare([dict(c) for c in claims], self.series, log)
        return verify_claims(prepared, client(), self.series,
                             published=date.fromisoformat(published), today=TODAY, log=log)

    def test_set_and_sources(self):
        self.assertGreaterEqual(len(self.texts), 4)
        for name, t in self.texts:
            with self.subTest(text=name):
                self.assertTrue(t["url"].startswith(("https://www.ssb.no/", "https://www.norges-bank.no/")))
                self.assertTrue(t["source"] and t["licence"] and t["changes"])
                for c in t["claims"]:
                    self.assertIn(" ".join(c["source_text"].split()), " ".join(t["text"].split()))

    def test_careful_extraction(self):
        for name, t in self.texts:
            with self.subTest(text=name):
                out = self._run(t["claims"], t["published"])
                got = [r.verdict for r in out.results]
                detail = [(r.claim.id, r.verdict, r.labels, r.notes) for r in out.results
                          if r.verdict != t["expected"]["verdicts"][out.results.index(r)]]
                self.assertEqual(got, t["expected"]["verdicts"], f"{name}: {detail}")
                self.assertEqual(exit_code(out.results), t["expected"]["exit_code"], name)

    def test_careless_extraction_raises_no_false_alarm(self):
        for name, t in self.texts:
            with self.subTest(text=name):
                out = self._run(careless(t["claims"], t["careless_indicator"]), t["published"])
                alarms = [(r.claim.id, r.claim.source_text, r.labels, r.notes)
                          for r in out.results if r.verdict == "mismatched"]
                self.assertEqual(alarms, [], name)

    def test_recorded_extraction_raises_no_false_alarm(self):
        missing = [n for n, t in self.texts if not recording_path(t["text"], t["published"]).exists()]
        if missing:
            self.skipTest(f"no recorded extractor output for {len(missing)} long texts; "
                          "run `norfigures record-agents`")
        for name, t in self.texts:
            with self.subTest(text=name):
                out = check_text(t["text"], client(), self.series, "replay",
                                 published=date.fromisoformat(t["published"]), today=TODAY, log=RunLog())
                alarms = [(r.claim.source_text, r.labels, r.notes)
                          for r in out.results if r.verdict == "mismatched"]
                self.assertEqual(alarms, [], f"{name}: false alarms")
                matched = sum(r.verdict == "matched" for r in out.results)
                self.assertGreaterEqual(matched, t["expected"]["verdicts"].count("matched") - 1,
                                        f"{name}: too few figures checked")


if __name__ == "__main__":
    unittest.main()
