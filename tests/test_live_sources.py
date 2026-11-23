"""Live check of every source: runs only with NORFIGURES_LIVE=1.

The offline tests replay recorded responses, so they cannot see a source
change. This module asks the real sources, through the same allowlisted client
and parsers, and fails if a series no longer answers in the shape we expect.
NAV is scraped (D20) and is the most likely to break; SSB and Norges Bank are
checked too, since the cost is one request per series.

Run weekly by .github/workflows/live-sources.yml, or by hand:

    NORFIGURES_LIVE=1 python -m unittest tests.test_live_sources -v

Nothing is saved; recordings are refreshed only with NORFIGURES_RECORD=1.
"""

import os
import time
import unittest
from datetime import date

from norfigures.fetch import fetch_series, latest
from norfigures.ledger import load
from norfigures.net import Client
from norfigures.periods import add_months, month_of
from norfigures.sources import nav

LIVE = os.environ.get("NORFIGURES_LIVE") == "1"

# How old the newest observation may be before we call the source stale.
MAX_AGE_MONTHS = {"M": 3}
MAX_AGE_DAYS = {"B": 10}


@unittest.skipUnless(LIVE, "live check; set NORFIGURES_LIVE=1 to run against the real sources")
class LiveSourcesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = Client("live")
        cls.series = load()
        cls.today = date.today()

    def test_every_series_answers_with_a_recent_value(self):
        for sid, s in self.series.items():
            with self.subTest(series=sid):
                obs = latest(self.client, s)
                self.assertIsNotNone(obs, f"{sid}: no observation")
                self.assertEqual(obs.series_id, sid)
                if s.frequency == "M":
                    oldest = add_months(month_of(self.today), -MAX_AGE_MONTHS["M"])
                    self.assertGreaterEqual(obs.period, oldest, f"{sid}: newest month is {obs.period}")
                else:
                    age = (self.today - date.fromisoformat(obs.period)).days
                    self.assertLessEqual(age, MAX_AGE_DAYS["B"], f"{sid}: newest day is {obs.period}")
                if s.unit == "percent":
                    self.assertTrue(0 <= obs.value <= 100, f"{sid}: {obs.value} is not a percent")
                time.sleep(2)  # SSB allows 40 requests a minute

    def test_nav_page_and_file_have_the_shape_we_read(self):
        s = self.series["nav_registered"]
        page = self.client.get(nav.CURRENT_PAGE).body
        url, month = nav.find_table_link(page, s.table, nav.CURRENT_PAGE)
        values = nav.parse_table(self.client.get(url).content, tuple(s.selection["sheet"]),
                                 s.selection["row"], url)
        self.assertEqual(max(values), month, "the file name and its newest month disagree")
        self.assertEqual(sorted(values)[0][5:], "01", "the file should start in January")

    def test_nav_archive_for_last_year(self):
        s = self.series["nav_registered"]
        year = self.today.year - 1
        obs = fetch_series(self.client, s, start=f"{year}-01", end=f"{year}-12")
        self.assertEqual([o.period[5:] for o in obs], [f"{m:02d}" for m in range(1, 13)])


if __name__ == "__main__":
    unittest.main()
