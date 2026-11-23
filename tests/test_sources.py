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
        short = jsonstat(["2026M01", "2026M02"])
        short["value"] = [1.5]   # fewer values than cells: a SourceError, not an IndexError
        with self.assertRaises(SourceError):
            ssb.parse_jsonstat(short, "s", "u", "t")
        sdmx = {"data": {"dataSets": [{"series": {"0": {"observations": {"5": ["4.0"]}}}}],
                         "structure": {"dimensions": {"series": [{"id": "X", "values": [{"id": "a"}]}],
                                                      "observation": [{"values": [{"id": "2026-11-01"}]}]}}}}
        with self.assertRaises(SourceError):   # observation index past the time list
            parse_sdmx(sdmx, "s", "u", "t")
        with self.assertRaises(SourceError):
            parse_sdmx({"nope": 1}, "s", "u", "t")


def jsonstat(codes, start=3.0):
    """A one-dimension json-stat2 answer, one value per time code."""
    return {"id": ["Tid"], "size": [len(codes)], "value": [start + i / 10 for i in range(len(codes))],
            "role": {"time": ["Tid"]},
            "dimension": {"Tid": {"category": {"index": {c: i for i, c in enumerate(codes)}}}}}


class SsbStub(Client):
    """Answers like SSB: 400 "Non-existent value" if any period asked for is after `newest`."""

    def __init__(self, newest, always_400=False):
        super().__init__("replay")
        self.newest, self.always_400 = newest, always_400

    def get(self, base, params=None):
        import json
        from norfigures.net import FetchError, Response, build_url
        url = build_url(base, params)
        tid = (params or {}).get("valueCodes[Tid]", "")
        if tid.startswith("top("):
            return Response(url, 200, json.dumps(jsonstat([self.newest])), "t", False)
        codes = tid.split(",")
        if self.always_400 or any(c > self.newest for c in codes):
            raise FetchError("HTTP 400", 400, '{"title":"Non-existent value","status":400}')
        return Response(url, 200, json.dumps(jsonstat(codes)), "t", False)


class NotPublishedYetTest(unittest.TestCase):
    """SSB answers 400 for a period it does not hold yet and for a wrong code (D21)."""

    def test_a_year_after_the_newest_is_no_data(self):
        from norfigures.sources import ssb
        sel = {"KPIavledetSerie": "KPI", "ContentsCode": "Aarsendring"}
        self.assertEqual(ssb.fetch(Client("replay"), "kpi_annual", "14707", sel, start="2026", end="2026"), [])

    def test_a_range_whose_end_is_not_out_yet_returns_what_is_published(self):
        # "Fra september til oktober" before October's release: SSB answers 400 for
        # the whole range. September must come back, not a fetch error (audit 2026-11-23).
        stub = SsbStub(newest="2026M09")
        obs = ssb.fetch(stub, "kpi_12m", "03013", {"x": "y"}, start="2026-09", end="2026-10")
        self.assertEqual([o.period for o in obs], ["2026-09"])
        self.assertEqual(ssb.fetch(stub, "kpi_12m", "03013", {"x": "y"}, start="2026-10", end="2026-11"), [])
        years = SsbStub(newest="2025")
        self.assertEqual([o.period for o in ssb.fetch(years, "a", "14707", {}, start="2025", end="2026")],
                         ["2025"])

    def test_a_range_inside_the_published_data_still_fails_on_a_400(self):
        from norfigures.net import FetchError
        stub = SsbStub(newest="2026M10", always_400=True)
        with self.assertRaises(FetchError):
            ssb.fetch(stub, "kpi_12m", "03013", {"x": "y"}, start="2026-09", end="2026-10")

    def test_a_wrong_code_still_fails(self):
        from norfigures.net import FetchError
        from norfigures.sources import ssb
        sel = {"KPIavledetSerie": "NO-SUCH-SERIES", "ContentsCode": "Aarsendring"}
        with self.assertRaises(FetchError):
            ssb.fetch(Client("replay"), "x", "14707", sel, start="2025", end="2025")


if __name__ == "__main__":
    unittest.main()
