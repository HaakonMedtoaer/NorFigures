import tempfile
import unittest
from pathlib import Path

from norfigures import net
from norfigures.ledger import LedgerError, load

FIVE = {"kpi_12m", "kpi_monthly", "kpi_jae_12m", "policy_rate", "eurnok"}


class LedgerTest(unittest.TestCase):
    def test_the_five_mvp_series_are_present_and_confirmed(self):
        series = load()
        self.assertEqual(set(series), FIVE)
        for s in series.values():
            with self.subTest(series=s.id):
                self.assertRegex(s.confirmed, r"^\d{4}-\d{2}-\d{2}$")

    def test_history_segments(self):
        s = load()["kpi_12m"]
        self.assertEqual(s.segments("2025-11", "2026-02"), [
            ("2025-11", "2025-12", "03013", s.history[0]["selection"]),
            ("2026-01", "2026-02", "14706", s.selection)])
        self.assertEqual([seg[2] for seg in s.segments("2025-02", "2025-02")], ["03013"])
        self.assertEqual([seg[2] for seg in s.segments("2026-10", "2026-10")], ["14706"])

    def test_published_2025_rates_come_from_closed_tables(self):
        from norfigures.fetch import fetch_series
        from norfigures.net import Client
        series = load()
        kpi = fetch_series(Client("replay"), series["kpi_12m"], start="2025-02", end="2025-02")
        jae = fetch_series(Client("replay"), series["kpi_jae_12m"], start="2025-02", end="2025-02")
        self.assertEqual((str(kpi[0].value), kpi[0].dims["_table"]), ("3.6", "03013"))
        self.assertEqual((str(jae[0].value), jae[0].dims["_table"]), ("3.4", "05327"))

    def test_every_source_maps_to_an_allowlisted_host(self):
        from norfigures.sources import norges_bank, ssb
        for base in (ssb.BASE, norges_bank.BASE):
            net.check_url(base)

    def _write(self, text):
        p = Path(tempfile.mkdtemp()) / "ledger.md"
        p.write_text(text, encoding="utf-8")
        return p

    def test_missing_block_is_an_error(self):
        with self.assertRaises(LedgerError):
            load(self._write("# no series here\n"))

    def test_incomplete_series_is_an_error(self):
        bad = '```json series\n{"x": {"source": "ssb", "table": "1"}}\n```\n'
        with self.assertRaises(LedgerError):
            load(self._write(bad))

    def test_unknown_source_is_an_error(self):
        bad = '```json series\n{"x": {"source": "wikipedia"}}\n```\n'
        with self.assertRaises(LedgerError):
            load(self._write(bad))


if __name__ == "__main__":
    unittest.main()
