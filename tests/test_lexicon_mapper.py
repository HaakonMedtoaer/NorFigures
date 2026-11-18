"""Phrase tables and the deterministic mapper."""

import unittest

from norfigures.ledger import load
from norfigures.lexicon import found, hints, load as load_phrases, review
from norfigures.mapper import map_claim

from tests.helpers import load_cases


def claim(text, **kw):
    base = {"id": "c1", "source_text": text, "status": "checkable", "indicator": "kpi",
            "measure": "12_month_change", "period": "2026-10", "unit": "percent",
            "stated_value": "3.6", "hedged": False, "labels": []}
    base.update(kw)
    return base


class PhraseTablesTest(unittest.TestCase):
    def test_tables_load_and_have_no_duplicates(self):
        data = load_phrases()
        flat = list(data["hedges"]) + list(data["forecast_markers"]) + list(data["change_verbs"])
        for v in data["measures"].values():
            flat += v
        for v in data["indicators"].values():
            flat += v
        self.assertEqual(len(flat), len(set(flat)), "a phrase appears twice")

    def test_whole_word_matching(self):
        self.assertEqual(found("Renten vil ligge på 4 %", ["vil"]), ["vil"])
        self.assertEqual(found("Han ville det", ["vil"]), [])
        self.assertEqual(found("Inflasjonen var som ventet", ["venter", "ventes"]), [])
        self.assertEqual(found("ca. 3 prosent", ["ca."]), ["ca."])
        self.assertEqual(found("KPI-JAE steg", ["kpi"]), [])

    def test_measure_phrases(self):
        self.assertEqual(hints("KPI steg 3,6 % siste tolv måneder").measure, "12_month_change")
        self.assertEqual(hints("Fra september til oktober steg KPI 0,3 %").measure, "monthly_change")
        self.assertIsNone(hints("Prisene steg 0,3 % i oktober").measure)


class ReviewTest(unittest.TestCase):
    def test_hedge_word_sets_hedged(self):
        c = review(claim("kjerneinflasjonen er rundt 3 prosent", indicator="kpi_jae"))
        self.assertTrue(c["hedged"])
        self.assertIn("lexicon_override", c["labels"])

    def test_forecast_marker_turns_checkable_into_forecast(self):
        c = review(claim("Inflasjonen ventes å bli 3 % i desember"))
        self.assertEqual(c["status"], "forecast")

    def test_explicit_measure_phrase_wins(self):
        c = review(claim("Fra september til oktober steg KPI med 0,3 prosent", measure="12_month_change"))
        self.assertEqual(c["measure"], "monthly_change")
        self.assertIn("Phrase tables", c["notes"])

    def test_change_verb_on_policy_rate(self):
        c = review(claim("Norges Bank økte renten med 0,25 prosent", indicator="policy_rate", measure="level"))
        self.assertEqual(c["measure"], "change")

    def test_out_of_scope_words(self):
        c = review(claim("Arbeidsledigheten var 4,5 prosent", indicator="kpi"))
        self.assertEqual((c["status"], c["indicator"]), ("out_of_scope", "unemployment"))

    def test_agreement_changes_nothing(self):
        c = claim("KPI steg 3,6 prosent siste tolv måneder")
        self.assertEqual(review(c)["labels"], [])


class MapperTest(unittest.TestCase):
    def setUp(self):
        self.series = load()

    def m(self, text, **kw):
        return map_claim(review(claim(text, **kw)), self.series)[0]

    def test_rules(self):
        self.assertEqual(self.m("KPI steg 3,6 prosent siste tolv måneder"), ["kpi_12m"])
        self.assertEqual(self.m("Inflasjonen var 3,1 %"), ["kpi_12m", "kpi_jae_12m"])
        self.assertEqual(self.m("Prisene steg 0,3 %"), ["kpi_12m", "kpi_monthly"])
        self.assertEqual(self.m("KPI-veksten er 3,6 %"), ["kpi_12m"])
        self.assertEqual(self.m("Kjerneinflasjonen var 3,0 %", indicator="kpi_jae"), ["kpi_jae_12m"])
        self.assertEqual(self.m("Styringsrenten er 4,5 %", indicator="policy_rate", measure="level"),
                         ["policy_rate"])

    def test_unmapped_is_explained(self):
        ids, note = map_claim(review(claim("KPI-JAE steg 0,2 prosent fra forrige måned",
                                           indicator="kpi_jae")), self.series)
        self.assertEqual(ids, [])
        self.assertIn("Not in the ledger", note)

    def test_mapper_reproduces_fixture_mappings(self):
        # Case 14 holds a deliberately wrong hand mapping; the code maps it correctly.
        for name, case in load_cases():
            if name.startswith("14_"):
                continue
            for c in case["claims"]:
                if c["status"] != "checkable":
                    continue
                with self.subTest(case=name, claim=c["id"]):
                    got, _ = map_claim(review(c), self.series)
                    self.assertEqual(got, [m["series_id"] for m in c["mappings"]])


class PrepareTest(unittest.TestCase):
    """The text pipeline's mapping step, without any model or recording."""

    def test_prepare_maps_and_logs_each_claim(self):
        from norfigures.events import RunLog
        from norfigures.pipeline import prepare
        log = RunLog()
        extracted = [
            claim("Inflasjonen var 3,1 % i oktober"),
            claim("KPI-JAE steg 0,2 prosent fra forrige måned", indicator="kpi_jae"),
            claim("Arbeidsledigheten var 4,5 prosent", indicator="other"),
        ]
        out = prepare(extracted, load(), log)
        self.assertEqual([m["series_id"] for m in out[0]["mappings"]], ["kpi_12m", "kpi_jae_12m"])
        self.assertEqual((out[1]["status"], out[1]["mappings"]), ("ambiguous", []))
        self.assertIn("unmapped", out[1]["labels"])
        self.assertEqual(out[2]["status"], "out_of_scope")
        maps = [e for e in log.events if e["stage"] == "map"]
        self.assertEqual([e["claim_id"] for e in maps], ["c1", "c1", "c1"])
        self.assertEqual(maps[0]["detail"]["claim_status"], "checkable")


if __name__ == "__main__":
    unittest.main()
