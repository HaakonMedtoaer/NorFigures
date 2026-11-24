"""Flow map, its local server, and the README animation (spec section 14, B38, B39).

Offline: the example run replays recorded extractor output and API responses.
The server test talks to 127.0.0.1 only.
"""

import json
import re
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from norfigures import animation
from norfigures.animation import EXAMPLE_LOG, EXAMPLE_SVG, build, read_log, record_example, render_svg
from norfigures.flowserver import FlowServer

from tests.test_check_cli import claims_file, run


def strip_volatile(events):
    return [{k: v for k, v in e.items() if k not in ("run_id", "ts")} for e in events]


class AnimationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events = read_log(EXAMPLE_LOG)
        cls.tl = build(cls.events)

    def test_example_log_is_current(self):
        fresh = Path(tempfile.mkdtemp()) / "run.jsonl"
        record_example(fresh)
        self.assertEqual(strip_volatile(read_log(fresh)), strip_volatile(self.events),
                         "docs/example-run.jsonl is stale; run `python -m norfigures.animation`")

    def test_svg_is_current(self):
        self.assertEqual(render_svg(self.tl), EXAMPLE_SVG.read_text(encoding="utf-8"),
                         "docs/run.svg is stale; run `python -m norfigures.animation`")

    def test_captions_from_the_spec(self):
        caps = [s.caption for s in self.tl.steps]
        for want in ("Found 3 claims", "inflasjonen → KPI and KPI-JAE",
                     "Table 14706 · KPI 12-month · 2026-10", "IR/B.KPRA.SD.R · 2026-11-13",
                     "3.1 vs 3.6", "0 matched · 2 mismatched · 1 cannot verify · exit 1"):
            self.assertIn(want, caps)
        self.assertEqual([v.verdict for v in self.tl.verdicts], ["mismatched", "mismatched", "cannot_verify"])

    def test_every_number_shown_comes_from_the_log(self):
        log_text = json.dumps(self.events, ensure_ascii=False)
        logged = set(re.findall(r"\d+(?:\.\d+)?", log_text))
        for s in self.tl.steps:
            for n in re.findall(r"\d+(?:\.\d+)?", s.caption):
                self.assertIn(n, logged, f"{n!r} in caption {s.caption!r} is not in the run log")

    def test_claims_shown_one_after_another(self):
        order = [e["claim_id"] for e in animation.stage_order(self.events) if e["claim_id"]]
        self.assertEqual(order, sorted(order, key=lambda c: int(c[1:])))
        self.assertEqual(animation.stage_order(self.events)[-1]["stage"], "report")
        self.assertLess(self.tl.total, 16)   # spec: about 10 to 15 seconds

    def test_svg_has_no_script_or_external_reference(self):
        svg = EXAMPLE_SVG.read_text(encoding="utf-8")
        self.assertNotIn("<script", svg)
        self.assertNotIn("href", svg)


    def test_page_intro_quotes_the_example_text(self):
        # The intro strip on GitHub Pages quotes the memo behind example-run.jsonl.
        page = (EXAMPLE_LOG.parent / "flowmap.html").read_text(encoding="utf-8")
        memo = re.search(r'<p lang="nb" id="memo">(.*?)</p>', page).group(1)
        case = json.loads(animation.EXAMPLE_CASE.read_text(encoding="utf-8"))
        self.assertEqual(memo, case["text"])


class FlowServerTest(unittest.TestCase):
    def setUp(self):
        self.log = Path(tempfile.mkdtemp()) / "run.jsonl"
        self.server = FlowServer(self.log).start()
        self.base = f"http://127.0.0.1:{self.server.port}"

    def tearDown(self):
        self.server.stop()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as r:
            return r.status, r.read().decode("utf-8")

    def test_serves_page_and_log_only(self):
        status, page = self.get("/flowmap.html?live=1&log=/run.jsonl")
        self.assertEqual(status, 200)
        self.assertIn("NorFigures flow map", page)
        self.assertEqual(self.get("/run.jsonl"), (200, ""))     # no log yet: empty, not an error
        for path in ("/../README.md", "/docs/decisions.md", "/facts/ledger.md"):
            with self.assertRaises(urllib.error.HTTPError) as cm:
                self.get(path)
            cm.exception.close()
            self.assertEqual(cm.exception.code, 404)

    def test_another_host_name_is_refused(self):
        # DNS rebinding: a page on evil.example resolving to 127.0.0.1 sends its own Host.
        for host in ("evil.example:%d" % self.server.port, "localhost:%d" % self.server.port, "127.0.0.1"):
            req = urllib.request.Request(self.base + "/run.jsonl", headers={"Host": host})
            with self.subTest(host=host), self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req, timeout=5)
            cm.exception.close()
            self.assertEqual(cm.exception.code, 403)

    def test_get_only(self):
        req = urllib.request.Request(self.base + "/run.jsonl", data=b"x", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req, timeout=5)
        cm.exception.close()
        self.assertEqual(cm.exception.code, 501)

    def test_knows_when_the_page_has_the_finished_log(self):
        self.log.write_text(EXAMPLE_LOG.read_text(encoding="utf-8").split("\n", 1)[0] + "\n", encoding="utf-8")
        self.get("/run.jsonl")
        self.assertFalse(self.server.wait_until_read(0))
        self.log.write_text(EXAMPLE_LOG.read_text(encoding="utf-8"), encoding="utf-8")
        self.get("/run.jsonl")
        self.assertTrue(self.server.wait_until_read(0))

    def test_an_earlier_run_in_the_same_log_does_not_count(self):
        example = EXAMPLE_LOG.read_text(encoding="utf-8")
        first_line_of_next_run = example.splitlines()[0]
        self.log.write_text(example + first_line_of_next_run + "\n", encoding="utf-8")
        self.get("/run.jsonl")
        self.assertFalse(self.server.wait_until_read(0))

    def test_bound_to_loopback(self):
        self.assertEqual(self.server.httpd.server_address[0], "127.0.0.1")


class FlowCliTest(unittest.TestCase):
    def test_flow_needs_a_log(self):
        code, _, err = run("check", "--claims", claims_file("20_spec_worked_example"),
                           "--offline", "--log", "none", "--flow")
        self.assertEqual(code, 3)
        self.assertIn("--flow", err)

    def test_failed_run_still_ends_the_log(self):
        log = Path(tempfile.mkdtemp()) / "run.jsonl"
        bad = Path(tempfile.mkdtemp()) / "bad.json"
        bad.write_text('{"claims": [{"id": "c1"}]}', encoding="utf-8")
        code, _, _ = run("check", "--claims", str(bad), "--offline", "--log", str(log))
        self.assertEqual(code, 3)
        last = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual((last["stage"], last["status"]), ("report", "failed"))


if __name__ == "__main__":
    unittest.main()
