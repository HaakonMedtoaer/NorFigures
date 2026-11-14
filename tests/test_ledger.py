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
