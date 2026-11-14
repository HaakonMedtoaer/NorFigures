"""Parse recorded API responses. Offline; values are whatever was recorded."""

import unittest
from decimal import Decimal
from urllib.parse import urlsplit

from norfigures.fetch import fetch_series, latest
from norfigures.ledger import load
from norfigures.net import ALLOWED_HOSTS, Client
from norfigures.sources import ssb
from norfigures.sources.base import SourceError
from norfigures.sources.norges_bank import parse_sdmx


class RecordedFetchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = Client("replay")
        cls.series = load()

    def test_latest_for_every_ledger_series(self):
        for sid, s in self.series.items():
            with self.subTest(series=sid):
                obs = latest(self.client, s)
                self.assertIsNotNone(obs)
                self.assertEqual(obs.series_id, sid)
                self.assertEqual(obs.source, s.source)
                self.assertIsInstance(obs.value, Decimal)
                self.assertIn(urlsplit(obs.url).hostname, ALLOWED_HOSTS)
                self.assertTrue(obs.retrieved_at.endswith("Z"))

    def test_ssb_monthly_periods_are_normalised(self):
        obs = fetch_series(self.client, self.series["kpi_jae_12m"], start="2026-01", end="2026-03")
        self.assertEqual([o.period for o in obs], ["2026-01", "2026-02", "2026-03"])

    def test_ssb_keeps_published_decimals(self):
        # SSB sends 3.0 as the JSON number 3; the table metadata says 1 decimal.
        obs = fetch_series(self.client, self.series["kpi_jae_12m"], start="2026-01", end="2026-03")
        for o in obs:
            self.assertEqual(o.value.as_tuple().exponent, -1, o)

    def test_norges_bank_daily_range_skips_weekends(self):
        obs = fetch_series(self.client, self.series["eurnok"], start="2026-11-06", end="2026-11-13")
        periods = [o.period for o in obs]
        self.assertEqual(periods, sorted(periods))
        self.assertNotIn("2026-11-07", periods)  # Saturday
        self.assertNotIn("2026-11-08", periods)  # Sunday
        self.assertEqual(obs[0].dims["BASE_CUR"], "EUR")


class ParserTest(unittest.TestCase):
    def test_ssb_month_helpers(self):
        self.assertEqual(ssb.to_ssb_month("2026-10"), "2026M10")
        self.assertEqual(ssb.from_ssb_period("2026M10"), "2026-10")
        self.assertEqual(ssb._range("2025M11", "2026M02"), "2025M11,2025M12,2026M01,2026M02")
        with self.assertRaises(ValueError):
            ssb._range("2026M02", "2026M01")

    def test_jsonstat_skips_missing_values(self):
        d = {"id": ["ContentsCode", "Tid"], "size": [1, 2], "value": [None, 1.5],
             "role": {"time": ["Tid"], "metric": ["ContentsCode"]},
             "dimension": {"ContentsCode": {"category": {"index": {"X": 0}}},
                           "Tid": {"category": {"index": {"2026M01": 0, "2026M02": 1}}}}}
        obs = ssb.parse_jsonstat(d, "s", "u", "t")
        self.assertEqual([(o.period, o.value) for o in obs], [("2026-02", Decimal("1.5"))])

    def test_malformed_payloads_raise_source_error(self):
        with self.assertRaises(SourceError):
            ssb.parse_jsonstat({"nope": 1}, "s", "u", "t")
        with self.assertRaises(SourceError):
            parse_sdmx({"nope": 1}, "s", "u", "t")


if __name__ == "__main__":
    unittest.main()
