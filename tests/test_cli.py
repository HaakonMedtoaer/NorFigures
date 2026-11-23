import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from norfigures.cli import main


class CliTest(unittest.TestCase):
    def test_latest_offline_prints_all_series(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["latest", "--offline"])
        self.assertEqual(code, 0)
        for sid in ("kpi_12m", "kpi_monthly", "kpi_jae_12m", "aku_trend", "aku_3mma", "policy_rate", "eurnok"):
            self.assertIn(sid, out.getvalue())
        self.assertIn("offline", out.getvalue())

    def test_unknown_command_exits_nonzero(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            main(["frobnicate"])
        self.assertNotEqual(cm.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
