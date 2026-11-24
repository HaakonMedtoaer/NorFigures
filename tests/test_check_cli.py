import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from norfigures.cli import main

from tests.helpers import CASES_DIR

BAD = CASES_DIR / "bad_input"


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def claims_file(case: str) -> str:
    data = json.loads((CASES_DIR / f"{case}.json").read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp()) / "claims.json"
    tmp.write_text(json.dumps(data["claims"], ensure_ascii=False), encoding="utf-8")
    return str(tmp)


class BadInputTest(unittest.TestCase):
    def test_empty_file_exits_3(self):
        code, _, err = run("check", "--claims", str(BAD / "empty.json"), "--offline", "--log", "none")
        self.assertEqual(code, 3)
        self.assertIn("empty", err)

    def test_binary_file_exits_3(self):
        code, _, err = run("check", "--claims", str(BAD / "binary.json"), "--offline", "--log", "none")
        self.assertEqual(code, 3)
        self.assertIn("binary", err)

    def test_schema_invalid_is_failed_extraction(self):
        code, _, err = run("check", "--claims", str(BAD / "schema_invalid.json"), "--offline", "--log", "none")
        self.assertEqual(code, 3)
        self.assertIn("failed extraction", err)

    def test_missing_file_exits_3(self):
        code, _, _ = run("check", "--claims", "/nonexistent/claims.json", "--offline", "--log", "none")
        self.assertEqual(code, 3)

    def test_needs_exactly_one_input(self):
        code, _, err = run("check")
        self.assertEqual(code, 3)
        self.assertIn("either a text FILE", err)

    def test_offline_text_without_recording_exits_3(self):
        tmp = Path(tempfile.mkdtemp()) / "t.txt"
        tmp.write_text("En tekst som aldri er tatt opp: KPI var 9,9 % i mars.", encoding="utf-8")
        code, _, err = run("check", str(tmp), "--offline", "--log", "none")
        self.assertEqual(code, 3)
        self.assertIn("no recorded extractor output", err)

    def test_bad_published_date(self):
        code, _, err = run("check", "--claims", claims_file("01_correct_kpi"), "--published",
                           "15.11.2026", "--offline", "--log", "none")
        self.assertEqual(code, 3)

    def test_empty_claim_list_exits_2(self):
        tmp = Path(tempfile.mkdtemp()) / "c.json"
        tmp.write_text("[]", encoding="utf-8")
        code, out, _ = run("check", "--claims", str(tmp), "--offline", "--log", "none")
        self.assertEqual(code, 2)
        self.assertIn("not a pass", out)


class OutputTest(unittest.TestCase):
    def test_table_worked_example(self):
        code, out, _ = run("check", "--claims", claims_file("20_spec_worked_example"),
                           "--published", "2026-11-15", "--offline", "--log", "none")
        self.assertEqual(code, 1)
        self.assertIn("MISMATCHED", out)
        self.assertIn("Claims found: 3 | matched: 0 | mismatched: 2 | could not verify: 1", out)

    def test_readme_example_file(self):
        # examples/memo.txt is the README's quick start; it must stay the worked example.
        memo = CASES_DIR.parents[1] / "examples" / "memo.txt"
        case = json.loads((CASES_DIR / "20_spec_worked_example.json").read_text(encoding="utf-8"))
        self.assertEqual(memo.read_text(encoding="utf-8").strip(), case["text"])
        code, out, _ = run("check", str(memo), "--published", "2026-11-15", "--offline", "--log", "none")
        self.assertEqual(code, 1)
        self.assertIn("Claims found: 3 | matched: 0 | mismatched: 2 | could not verify: 1", out)

    def test_json_output_keeps_precision_and_adds_up(self):
        code, out, _ = run("check", "--claims", claims_file("20_spec_worked_example"),
                           "--published", "2026-11-15", "--offline", "--format", "json", "--log", "none")
        data = json.loads(out)
        self.assertEqual(code, data["exit_code"])
        s = data["summary"]
        self.assertEqual(s["matched"] + s["mismatched"] + s["cannot_verify"], s["claims_found"])
        c2 = data["claims"][1]
        self.assertEqual(c2["stated_value"], "4.0")
        self.assertTrue(c2["readings"][0]["url"].startswith("https://data.norges-bank.no/"))

    def test_event_log_written(self):
        log = Path(tempfile.mkdtemp()) / "run.jsonl"
        run("check", "--claims", claims_file("20_spec_worked_example"), "--published",
            "2026-11-15", "--offline", "--log", str(log))
        events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        stages = [e["stage"] for e in events]
        for stage in ("load", "validate", "fetch", "compare", "report"):
            self.assertIn(stage, stages)
        self.assertEqual(len({e["run_id"] for e in events}), 1)
        compares = [e for e in events if e["stage"] == "compare"]
        self.assertEqual([e["claim_id"] for e in compares], ["c1", "c2", "c3"])
        for key in ("run_id", "claim_id", "stage", "status", "detail", "ts"):
            self.assertIn(key, events[0])
        # What the flow map and README animation show (spec section 14).
        self.assertEqual(compares[0]["detail"]["stated"], "3.1")
        self.assertEqual(compares[0]["detail"]["readings"][0]["official"], "3.6")
        fetches = {e["detail"]["series_id"]: e["detail"] for e in events if e["stage"] == "fetch"}
        self.assertEqual(fetches["kpi_12m"]["ref"], "table 14706")
        self.assertEqual(fetches["policy_rate"]["ref"], "IR/B.KPRA.SD.R")
        prov = [e for e in events if e["stage"] == "provenance"]
        self.assertEqual([e["status"] for e in prov], ["ok"])
        self.assertEqual(stages[-1], "report")

    def test_blocked_host_is_logged_as_a_guardrail(self):
        from norfigures.events import RunLog
        from norfigures.ledger import load
        from norfigures.net import HostNotAllowed
        from norfigures.verifier import Run

        class Blocked:
            def get(self, *a, **k):
                raise HostNotAllowed("host 'example.com' is not on the allowlist")
            get_json = get_text = get

        log = RunLog()
        series = load()
        with self.assertRaises(HostNotAllowed):
            Run(Blocked(), series, log).fetch(series["policy_rate"], "2026-11-01", "2026-11-15", "c1")
        self.assertEqual(log.events[-1]["status"], "failed")
        self.assertEqual(log.events[-1]["detail"]["guardrail"], "host_not_allowed")


if __name__ == "__main__":
    unittest.main()
