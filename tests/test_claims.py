import unittest
from decimal import Decimal as D

from norfigures.claims import SchemaError, parse_json, to_decimal, validate
from norfigures.ledger import load

GOOD = {"id": "c1", "source_text": "KPI var 3,6 %", "status": "checkable", "indicator": "kpi",
        "measure": "12_month_change", "period": "2026-10", "unit": "percent",
        "stated_value": "3,6", "mappings": [{"series_id": "kpi_12m"}]}


class ClaimSchemaTest(unittest.TestCase):
    def setUp(self):
        self.series = load()

    def test_valid_claim(self):
        (c,) = validate([GOOD], self.series)
        self.assertEqual(c.stated_value, D("3.6"))
        self.assertEqual(c.mappings, ("kpi_12m",))

    def test_wrapped_form_is_accepted(self):
        self.assertEqual(len(validate({"claims": [GOOD]}, self.series)), 1)

    def test_decimals_survive_json(self):
        data = parse_json('[{"v": 4.0}]')
        self.assertEqual(str(data[0]["v"]), "4.0")
        self.assertEqual(str(to_decimal("4,00")), "4.00")

    def test_rejects_non_numbers(self):
        for bad in ("abc", True, "NaN", "inf", None, [1]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                to_decimal(bad)

    def test_all_problems_are_reported_together(self):
        bad = dict(GOOD, id="c2", status="maybe", stated_value="x",
                   mappings=[{"series_id": "made_up"}])
        with self.assertRaises(SchemaError) as cm:
            validate([GOOD, bad, "not an object"], self.series)
        text = "\n".join(cm.exception.problems)
        for fragment in ("status", "stated_value", "made_up", "must be an object"):
            self.assertIn(fragment, text)

    def test_never_repaired_silently(self):
        cases = [
            dict(GOOD, mappings=[]),                       # checkable without mapping
            dict(GOOD, stated_value=None),                 # checkable without number
            dict(GOOD, period="October"),                  # bad period
            dict(GOOD, extra_field=1),                     # unknown field
            dict(GOOD, mappings=[{"series_id": "kpi_12m", "source": "norges_bank"}]),
            dict(GOOD, status="out_of_scope", indicator=None),
        ]
        for c in cases:
            with self.subTest(claim=c), self.assertRaises(SchemaError):
                validate([c], self.series)

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(SchemaError):
            validate([GOOD, GOOD], self.series)

    def test_top_level_must_be_a_list(self):
        with self.assertRaises(SchemaError):
            validate("text", self.series)


if __name__ == "__main__":
    unittest.main()
