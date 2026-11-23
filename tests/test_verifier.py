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


def _aku(text, value, period="2026-08", labels=(), measure="level", unit="percent",
         mappings=("aku_trend", "aku_3mma")):
    return {"id": "c1", "source_text": text, "status": "checkable", "indicator": "unemployment",
            "measure": measure, "period": period, "unit": unit, "stated_value": value,
            "labels": list(labels), "mappings": [{"series_id": m} for m in mappings]}


def _nav(text, value, period="2026-10", **kw):
    return _aku(text, value, period, mappings=("nav_registered",), **kw)


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

    def test_unsourced_figure_is_checked_against_aku_and_nav(self):
        # D20 replaces B43's "cannot verify": NAV's August 2026 rate is 2.1.
        three = ["aku_trend", "aku_3mma", "nav_registered"]
        res = self.verify(_aku("Ledigheten var 2,1 prosent i august", "2.1", mappings=three,
                               labels=["unemployment_source_unnamed"]))
        self.assertEqual(res.verdict, MATCHED)
        self.assertEqual(res.chosen.series_id, "nav_registered")
        res = self.verify(_aku("Ledigheten var 3,0 prosent i august", "3.0", mappings=three,
                               labels=["unemployment_source_unnamed"]))
        self.assertEqual(res.verdict, MISMATCHED)
        self.assertEqual(len(res.readings), 3)

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


class NavTest(unittest.TestCase):
    """NAV registered unemployment (D20), against the recorded page and table files."""

    def setUp(self):
        self.series = load()

    def verify(self, claim, published=date(2026, 11, 15)):
        run = Run(client(), self.series)
        return verify_claim(_claims(claim)[0], run, published, TODAY)

    def test_match_and_mismatch(self):
        res = self.verify(_nav("Den registrerte ledigheten var 2,0 prosent i oktober", "2.0"))
        self.assertEqual(res.verdict, MATCHED)
        self.assertTrue(res.chosen.observations[0].url.startswith("https://www.nav.no/_/attachment/"))
        res = self.verify(_nav("Den registrerte ledigheten var 2,1 prosent i oktober", "2.1"))
        self.assertEqual(res.verdict, MISMATCHED)

    def test_earlier_year_from_the_archive(self):
        res = self.verify(_nav("Den registrerte ledigheten var 2,1 prosent i desember 2025", "2.1",
                               period="2025-12"))
        self.assertEqual(res.verdict, MATCHED)

    def test_inferred_month_uses_nav_release_timing(self):
        # NAV publishes month M late in month M (offset 0). On 15 November only
        # October is out; on 23 November November may be meant too, but is not out.
        res = self.verify(_nav("Den registrerte ledigheten er 2,0 prosent", "2.0", period=None))
        self.assertEqual([r.period for r in res.readings], ["2026-10"])
        self.assertEqual(res.verdict, MATCHED)
        res = self.verify(_nav("Den registrerte ledigheten er 2,0 prosent", "2.0", period=None),
                          published=date(2026, 11, 23))
        self.assertEqual([r.period for r in res.readings], ["2026-11", "2026-10"])
        self.assertEqual(res.verdict, MATCHED)

    def test_level_inside_the_break_is_checked_as_published(self):
        res = self.verify(_nav("Den registrerte ledigheten var 2,0 prosent i mai 2025", "2.0",
                               period="2025-05"))
        self.assertEqual(res.verdict, MATCHED)

    def test_change_across_the_break_is_not_computed(self):
        res = self.verify(_nav("Den registrerte ledigheten falt med 0,1 prosentpoeng i april 2025", "0.1",
                               period="2025-04", measure="change", unit="percentage_points"))
        self.assertEqual(res.verdict, CANNOT_VERIFY)
        self.assertTrue(any("break" in n for n in res.notes))

    def test_change_after_the_break(self):
        res = self.verify(_nav("Den registrerte ledigheten falt med 0,1 prosentpoeng i september", "0.1",
                               period="2026-09", measure="change", unit="percentage_points"))
        self.assertEqual(res.verdict, MATCHED)
        self.assertEqual(str(res.readings[0].official_value), "-0.1")


def _year(text, indicator, value, maps, period="2025", measure="annual_change", unit="percent"):
    return {"id": "c1", "source_text": text, "status": "checkable", "indicator": indicator,
            "measure": measure, "period": period, "unit": unit, "stated_value": value,
            "labels": [], "mappings": [{"series_id": m} for m in maps]}


KPI_YEAR = ["kpi_annual", "kpi_12m"]
JAE_YEAR = ["kpi_jae_annual", "kpi_jae_12m"]
UNEMP_YEAR = ["aku_annual", "aku_annual_break_adjusted", "nav_registered_annual"]


class AnnualTest(unittest.TestCase):
    """Annual figures (D21), against recorded SSB, NAV and Norges Bank responses."""

    def setUp(self):
        self.series = load()

    def verify(self, claim):
        run = Run(client(), self.series)
        return verify_claim(_claims(claim)[0], run, date(2026, 11, 15), TODAY)

    def readings(self, res):
        return [(r.series_id, r.period, str(r.official_value)) for r in res.readings]

    def test_a_year_has_the_annual_average_and_the_december_rate(self):
        res = self.verify(_year("Inflasjonen i 2025 var 3,1 prosent", "kpi", "3.1", KPI_YEAR))
        self.assertEqual(res.verdict, MATCHED)
        self.assertEqual(self.readings(res), [("kpi_annual", "2025", "3.1"), ("kpi_12m", "2025-12", "3.2")])
        self.assertNotIn("period_ambiguous", res.labels)
        res = self.verify(_year("Inflasjonen i 2025 var 2,8 prosent", "kpi", "2.8", KPI_YEAR))
        self.assertEqual(res.verdict, MISMATCHED)

    def test_either_reading_can_match(self):
        # 2024: annual average 3.1, but December only 2.2 (D4).
        res = self.verify(_year("Inflasjonen i 2024 var 3,1 prosent", "kpi", "3.1", KPI_YEAR, period="2024"))
        self.assertEqual(res.verdict, MATCHED)
        self.assertEqual(res.chosen.series_id, "kpi_annual")

    def test_annual_kpi_up_to_2025_is_the_rate_as_published(self):
        # 14707 recalculated 2025 to 3.0; SSB published 3.1 (closed table 03014).
        res = self.verify(_year("Inflasjonen i 2025 var 3,1 prosent", "kpi", "3.1", ["kpi_annual"]))
        self.assertEqual(res.readings[0].observations[0].dims["_table"], "03014")

    def test_kpi_jae_up_to_2025_tolerates_the_rebase_by_reporting_it(self):
        res = self.verify(_year("KPI-JAE i 2025 var 3,0 prosent", "kpi_jae", "3.0", JAE_YEAR))
        self.assertEqual(res.verdict, CANNOT_VERIFY)
        self.assertIn("rebase_difference", res.labels)
        res = self.verify(_year("KPI-JAE i 2025 var 2,5 prosent", "kpi_jae", "2.5", JAE_YEAR))
        self.assertEqual(res.verdict, MISMATCHED)
        self.assertNotIn("rebase_difference", res.labels)

    def test_change_between_two_annual_rates(self):
        res = self.verify(_year("Inflasjonen i 2025 var 0,1 prosentpoeng lavere enn i 2024", "kpi", "0.1",
                                ["kpi_annual"], measure="change", unit="percentage_points"))
        self.assertEqual(self.readings(res), [("kpi_annual", "2025", "0.0")])
        self.assertEqual(res.verdict, MISMATCHED)

    def test_unemployment_year_checks_aku_and_nav(self):
        for value, verdict in (("4.5", MATCHED), ("2.2", MATCHED), ("3.3", MISMATCHED)):
            with self.subTest(value=value):
                res = self.verify(_year(f"Ledigheten i 2025 var {value} prosent", "unemployment", value,
                                        UNEMP_YEAR, measure="level"))
                self.assertEqual(res.verdict, verdict)
        self.assertEqual(self.readings(res), [("aku_annual", "2025", "4.5"),
                                              ("aku_annual_break_adjusted", "2025", "4.5"),
                                              ("nav_registered_annual", "2025", "2.2")])

    def test_policy_rate_and_eurnok_year_is_a_range(self):
        res = self.verify(_year("Styringsrenten var 4,25 prosent i 2025", "policy_rate", "4.25",
                                ["policy_rate"], measure="level"))
        self.assertEqual(res.verdict, MATCHED)
        self.assertEqual((str(res.readings[0].low), str(res.readings[0].high)), ("4", "4.5"))
        res = self.verify(_year("Styringsrenten var 3,0 prosent i 2025", "policy_rate", "3.0",
                                ["policy_rate"], measure="level"))
        self.assertEqual(res.verdict, MISMATCHED)
        res = self.verify(_year("Euroen kostet 11,7 kroner i 2025", "eurnok", "11.7", ["eurnok"],
                                measure="level", unit="nok_per_eur"))
        self.assertEqual(res.verdict, MATCHED)

    def test_a_year_not_published_yet_cannot_be_verified(self):
        res = self.verify(_year("Inflasjonen i 2026 var 3,0 prosent", "kpi", "3.0", KPI_YEAR, period="2026"))
        self.assertEqual(res.verdict, CANNOT_VERIFY)
        self.assertIn("no_data", res.labels)


class ChangeNotPublishedYetTest(unittest.TestCase):
    """A change whose later period is not out yet is "cannot verify", never a fetch
    error that stops the whole check (audit 2026-11-23)."""

    def verify(self, newest, claim, published=None):
        from tests.test_sources import SsbStub
        series = load()
        run = Run(SsbStub(newest), series)
        (c,) = validate([claim], series)
        return verify_claim(c, run, published, date(2026, 11, 23))

    def claim(self, text, period, sid):
        return {"id": "c1", "source_text": text, "status": "checkable", "indicator": "kpi",
                "measure": "change", "period": period, "unit": "percentage_points",
                "stated_value": "0.2", "mappings": [{"series_id": sid}]}

    def test_month_not_out_yet(self):
        res = self.verify("2026M10", self.claim("Inflasjonen steg 0,2 prosentpoeng i november",
                                                "2026-11", "kpi_12m"))
        self.assertEqual(res.verdict, CANNOT_VERIFY)
        self.assertIn("no_data", res.labels)

    def test_year_not_out_yet(self):
        res = self.verify("2025", self.claim("Inflasjonen i 2026 var 0,2 prosentpoeng lavere enn i 2025",
                                             "2026", "kpi_annual"))
        self.assertEqual(res.verdict, CANNOT_VERIFY)
        self.assertIn("no_data", res.labels)

    def test_inferred_month_inside_the_release_window(self):
        # Published 5 November: October or September could be meant; October is not out.
        res = self.verify("2026M09", self.claim("Inflasjonen steg med 0,2 prosentpoeng", None, "kpi_12m"),
                          published=date(2026, 11, 5))
        self.assertEqual([r.period for r in res.readings], ["2026-10", "2026-09"])
        self.assertFalse(res.readings[0].has_data)
        self.assertTrue(res.readings[1].has_data)
        self.assertEqual(res.verdict, CANNOT_VERIFY)
        self.assertIn("incomplete_data", res.labels)


if __name__ == "__main__":
    unittest.main()
