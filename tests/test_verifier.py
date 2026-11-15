import unittest
from datetime import date
from decimal import Decimal as D

from norfigures.claims import validate
from norfigures.ledger import load
from norfigures.report import AccountingError, exit_code, summarize
from norfigures.sources.base import Observation
from norfigures.verifier import (CANNOT_VERIFY, MATCHED, MISMATCHED, ClaimResult,
                                 ProvenanceError, Reading, Run, check_provenance,
                                 compare_point, compare_range, round_like, verify_claim)
from norfigures import periods

from tests.helpers import TODAY, client


class RoundingTest(unittest.TestCase):
    """D8 rounding and D10 hedged tolerance."""

    def test_round_half_up_to_stated_decimals(self):
        self.assertEqual(round_like(D("3.56"), D("3.6")), D("3.6"))
        self.assertEqual(round_like(D("3.55"), D("3.6")), D("3.6"))   # half up, not banker's
        self.assertEqual(round_like(D("3.54"), D("3.6")), D("3.5"))
        self.assertEqual(round_like(D("4"), D("4.00")), D("4.00"))   # Norges Bank sends "4"

    def test_point_comparison(self):
        self.assertTrue(compare_point(D("3.6"), D("3.56"), hedged=False))
        self.assertFalse(compare_point(D("3.6"), D("3.54"), hedged=False))
        self.assertTrue(compare_point(D("4.0"), D("4"), hedged=False))
        self.assertFalse(compare_point(D("4.25"), D("4.5"), hedged=False))

    def test_hedged_allows_one_unit_in_last_digit(self):
        self.assertTrue(compare_point(D("3"), D("2.0"), hedged=True))
        self.assertTrue(compare_point(D("3"), D("3.6"), hedged=True))   # 3.6 -> 4, |4-3| = 1
        self.assertFalse(compare_point(D("3"), D("4.6"), hedged=True))  # 4.6 -> 5
        self.assertFalse(compare_point(D("3"), D("3.6"), hedged=False))

    def test_range_comparison(self):
        self.assertTrue(compare_range(D("10.50"), D("10.312"), D("10.875"), hedged=False))
        self.assertTrue(compare_range(D("10.31"), D("10.312"), D("10.875"), hedged=False))
        self.assertFalse(compare_range(D("11.20"), D("10.312"), D("10.875"), hedged=False))


class PeriodsTest(unittest.TestCase):
    def test_infer_monthly(self):
        self.assertEqual(periods.infer_monthly(date(2026, 11, 20)), ["2026-10"])
        self.assertEqual(periods.infer_monthly(date(2026, 11, 5)), ["2026-10", "2026-09"])
        self.assertEqual(periods.infer_monthly(date(2026, 1, 3)), ["2025-12", "2025-11"])

    def test_month_arithmetic(self):
        self.assertEqual(periods.add_months("2026-01", -1), "2025-12")
        self.assertEqual(periods.month_bounds("2024-02")[1], date(2024, 2, 29))


def _claims(*dicts):
    return validate(list(dicts), load())


class GuardrailTest(unittest.TestCase):
    def setUp(self):
        self.series = load()
        self.run = Run(client(), self.series)

    def test_provenance_rejects_value_not_fetched_in_this_run(self):
        (c,) = _claims({"id": "c1", "source_text": "x", "status": "checkable", "indicator": "kpi",
                        "measure": "12_month_change", "period": "2026-10", "unit": "percent",
                        "stated_value": "3.6", "mappings": [{"series_id": "kpi_12m"}]})
        res = verify_claim(c, self.run, None, TODAY)
        check_provenance([res], self.run)  # genuine result passes

        forged = Observation("ssb", "kpi_12m", "2026-10", D("3.6"), "https://data.ssb.no/x", "t")
        res.readings[0].observations = [forged]
        with self.assertRaises(ProvenanceError):
            check_provenance([res], self.run)

    def test_provenance_rejects_tampered_value(self):
        (c,) = _claims({"id": "c1", "source_text": "x", "status": "checkable", "indicator": "kpi",
                        "measure": "12_month_change", "period": "2026-10", "unit": "percent",
                        "stated_value": "3.6", "mappings": [{"series_id": "kpi_12m"}]})
        res = verify_claim(c, self.run, None, TODAY)
        res.readings[0].official_value = D("9.9")
        with self.assertRaises(ProvenanceError):
            check_provenance([res], self.run)

    def test_no_claims_is_never_a_pass(self):
        self.assertEqual(exit_code([]), 2)

    def test_mismatch_outranks_unverifiable(self):
        (c,) = _claims({"id": "c1", "source_text": "x", "status": "no_figure"})
        r1 = ClaimResult(c, MISMATCHED)
        r2 = ClaimResult(c, CANNOT_VERIFY)
        r3 = ClaimResult(c, MATCHED)
        self.assertEqual(exit_code([r2, r1, r3]), 1)
        self.assertEqual(exit_code([r2, r3]), 2)
        self.assertEqual(exit_code([r3]), 0)

    def test_accounting_must_add_up(self):
        (c,) = _claims({"id": "c1", "source_text": "x", "status": "no_figure"})
        self.assertEqual(summarize([ClaimResult(c, MATCHED)])["claims_found"], 1)
        with self.assertRaises(AccountingError):
            summarize([ClaimResult(c, "something_else")])


if __name__ == "__main__":
    unittest.main()
