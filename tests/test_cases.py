"""Run every fixture case in tests/cases through the deterministic pipeline.

Claims are hand-written stand-ins for agent output, so no LLM is involved.
"""

import unittest
from collections import Counter
from datetime import date

from norfigures.events import RunLog
from norfigures.ledger import load
from norfigures.pipeline import verify_claims
from norfigures.report import exit_code

from tests.helpers import TODAY, client, load_cases

CASES = load_cases()


class FixtureCasesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.series = load()

    def test_case_count_and_categories(self):
        self.assertGreaterEqual(len(CASES), 15)
        self.assertLessEqual(len(CASES), 20)
        cats = Counter(c["category"] for _, c in CASES)
        for cat in ("correct", "wrong", "ambiguous", "forecast", "mapping_trap", "no_figure"):
            self.assertGreaterEqual(cats[cat], 2, cat)

    def test_cases(self):
        for name, case in CASES:
            with self.subTest(case=name):
                published = date.fromisoformat(case["published"]) if case["published"] else None
                outcome = verify_claims(case["claims"], client(), self.series,
                                        published=published, today=TODAY, log=RunLog())
                got = {r.claim.id: r for r in outcome.results}
                for cid, exp in case["expected"]["claims"].items():
                    res = got[cid]
                    detail = f"{name}/{cid}: labels={res.labels} notes={res.notes}"
                    self.assertEqual(res.verdict, exp["verdict"], detail)
                    for label in exp["labels_include"]:
                        self.assertIn(label, res.labels, detail)
                self.assertEqual(exit_code(outcome.results), case["expected"]["exit_code"], name)

    def test_every_claim_in_every_case_is_reported(self):
        for name, case in CASES:
            with self.subTest(case=name):
                published = date.fromisoformat(case["published"]) if case["published"] else None
                outcome = verify_claims(case["claims"], client(), self.series,
                                        published=published, today=TODAY)
                self.assertEqual([r.claim.id for r in outcome.results],
                                 [c["id"] for c in case["claims"]])


if __name__ == "__main__":
    unittest.main()
