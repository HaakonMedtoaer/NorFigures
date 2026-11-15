import asyncio
import os
import unittest
from unittest import mock

from norfigures import mcp_server


@mock.patch.dict(os.environ, {"NORFIGURES_OFFLINE": "1"})
class McpToolsTest(unittest.TestCase):
    def test_fetch_values_from_ledger_series(self):
        out = mcp_server.fetch_values("kpi_jae_12m", "2026-01", "2026-03")
        self.assertEqual([o["period"] for o in out["observations"]], ["2026-01", "2026-02", "2026-03"])
        self.assertTrue(out["url"].startswith("https://data.ssb.no/"))
        self.assertIsInstance(out["observations"][0]["value"], str)

    def test_unknown_series_refused(self):
        with self.assertRaises(ValueError):
            mcp_server.fetch_values("made_up", "2026-01", "2026-02")

    def test_norges_bank_search_uses_ledger(self):
        ids = [r["series_id"] for r in mcp_server.search_series("norges_bank", "exchange")]
        self.assertEqual(ids, ["eurnok"])

    def test_bad_source_refused(self):
        with self.assertRaises(ValueError):
            mcp_server.search_series("wikipedia", "kpi")


class McpServerTest(unittest.TestCase):
    def test_three_read_only_tools(self):
        try:
            server = mcp_server.build_server()
        except ImportError:
            self.skipTest("mcp package not installed (pip install 'norfigures[agents]')")
        tools = asyncio.run(server.list_tools())
        self.assertEqual(sorted(t.name for t in tools),
                         ["describe_series", "fetch_values", "search_series"])
        for t in tools:
            self.assertTrue(t.annotations.read_only_hint, t.name)
            self.assertFalse(t.annotations.destructive_hint, t.name)


if __name__ == "__main__":
    unittest.main()
