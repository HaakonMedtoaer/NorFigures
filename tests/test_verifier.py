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

    def test_infer_monthly_with_a_release_window(self):
        # AKU for month M comes out on day 21 to 26 of M+1; the ledger window is 20 to 27 (B42).
        w = (20, 27)
        self.assertEqual(periods.infer_monthly(date(2026, 10, 10), w), ["2026-08"])
        self.assertEqual(periods.infer_monthly(date(2026, 10, 22), w), ["2026-09", "2026-08"])
        self.assertEqual(periods.infer_monthly(date(2026, 10, 30), w), ["2026-09"])

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


def _aku(text, value, period="2026-08", labels=(), measure="level", unit="percent"):
    return {"id": "c1", "source_text": text, "status": "checkable", "indicator": "unemployment",
            "measure": measure, "period": period, "unit": unit, "stated_value": value,
            "labels": list(labels), "mappings": [{"series_id": "aku_trend"}, {"series_id": "aku_3mma"}]}


class UnemploymentTest(unittest.TestCase):
    """AKU (D16, B41 to B43), against recorded SSB table 13760 responses."""

    def setUp(self):
        self.series = load()

    def verify(self, claim, published=date(2026, 10, 22)):
        run = Run(client(), self.series)
        return verify_claim(_claims(claim)[0], run, published, TODAY)

    def test_both_aku_readings_shown(self):
        res = self.verify(_aku("Ledigheten var 4,5 prosent i juli ifølge AKU", "4.5", "2026-07"))
        self.assertEqual(res.verdict, MATCHED)
        self.assertEqual([(r.series_id, str(r.official_value)) for r in res.readings],
                         [("aku_trend", "4.5"), ("aku_3mma", "4.4")])
        self.assertIn("ambiguous_measure", res.labels)

    def test_wrong_figure_with_aku_named_is_a_mismatch(self):
        res = self.verify(_aku("AKU-ledigheten var 4,9 prosent i august", "4.9"))
        self.assertEqual(res.verdict, MISMATCHED)

    def test_wrong_figure_without_a_source_may_be_nav(self):
        res = self.verify(_aku("Ledigheten var 2,1 prosent i august", "2.1",
                               labels=["unemployment_source_unnamed"]))
        self.assertEqual(res.verdict, CANNOT_VERIFY)
        self.assertTrue(any("NAV" in n for n in res.notes))

    def test_latest_month_waits_for_the_three_month_average(self):
        # The 3-month average for September needs October; until then a wrong
        # September figure cannot be called a mismatch (incomplete data).
        res = self.verify(_aku("AKU-ledigheten var 4,9 prosent i september", "4.9", "2026-09"))
        self.assertEqual(res.verdict, CANNOT_VERIFY)
        self.assertIn("incomplete_data", res.labels)

    def test_inferred_period_inside_the_release_window(self):
        res = self.verify(_aku("AKU-ledigheten er 4,6 prosent", "4.6", period=None))
        self.assertEqual(res.verdict, MATCHED)
        self.assertIn("period_inferred", res.labels)
        self.assertEqual({r.period for r in res.readings}, {"2026-09", "2026-08"})

    def test_change_in_points(self):
        res = self.verify(_aku("AKU-ledigheten økte med 0,1 prosentpoeng fra juli til august", "0.1",
                               measure="change", unit="percentage_points"))
        self.assertEqual(res.verdict, MATCHED)
        self.assertEqual(str(res.readings[0].official_value), "0.1")


if __name__ == "__main__":
    unittest.main()
