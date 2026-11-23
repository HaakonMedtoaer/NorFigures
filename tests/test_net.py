import io
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from norfigures import net
from norfigures.net import Client, HostNotAllowed, RecordingMissing, check_url


class AllowlistTest(unittest.TestCase):
    def test_allowed_hosts_are_exactly_the_official_sources(self):
        self.assertEqual(net.ALLOWED_HOSTS, {"data.ssb.no", "data.norges-bank.no", "www.nav.no"})

    def test_nav_is_limited_to_statistics_pages_and_file_downloads(self):
        # D20: www.nav.no serves far more than data, so only two path prefixes pass.
        ok = ["https://www.nav.no/no/nav-og-samfunn/statistikk/arbeidssokere-og-stillinger-statistikk/helt-ledige",
              "https://www.nav.no/_/attachment/download/9356f88f:9736da86/202610_HL050%20Helt.xlsx"]
        for url in ok:
            with self.subTest(url=url):
                self.assertEqual(check_url(url), "www.nav.no")
        bad = ["https://www.nav.no/",
               "https://www.nav.no/minside",
               "https://www.nav.no/no/person/arbeid",
               "https://www.nav.no/no/nav-og-samfunn/statistikk/../../../minside",
               "https://www.nav.no/no/nav-og-samfunn/statistikk/%2e%2e/%2e%2e/minside",
               "https://www.nav.no/no/nav-og-samfunn/statistikk%2f..%2fminside",
               "https://www.nav.no/_/attachment/download/../../minside",
               "https://nav.no/no/nav-og-samfunn/statistikk/",
               "https://login.nav.no/no/nav-og-samfunn/statistikk/"]
        for url in bad:
            with self.subTest(url=url), self.assertRaises(HostNotAllowed):
                check_url(url)

    def test_path_rule_does_not_touch_the_api_hosts(self):
        self.assertEqual(check_url("https://data.ssb.no/anything"), "data.ssb.no")

    def test_accepts_official_hosts(self):
        self.assertEqual(check_url("https://data.ssb.no/api/pxwebapi/v2/tables"), "data.ssb.no")
        self.assertEqual(check_url("https://DATA.NORGES-BANK.NO/api/data/IR"), "data.norges-bank.no")

    def test_rejects_other_hosts_and_tricks(self):
        bad = [
            "https://example.com/",
            "https://data.ssb.no.evil.com/",
            "https://evil.com/data.ssb.no",
            "https://data.ssb.no@evil.com/",
            "https://user:pw@data.ssb.no/",
            "http://data.ssb.no/",
            "https://data.ssb.no:8443/",
            "ftp://data.ssb.no/",
            "file:///etc/passwd",
        ]
        for url in bad:
            with self.subTest(url=url), self.assertRaises(HostNotAllowed):
                check_url(url)

    def test_disallowed_host_is_refused_before_any_io_in_every_mode(self):
        for mode in net.MODES:
            client = Client(mode, recordings_dir=Path(tempfile.mkdtemp()))
            with mock.patch("norfigures.net._open") as urlopen, \
                    self.subTest(mode=mode), self.assertRaises(HostNotAllowed):
                client.get("https://example.com/x")
            urlopen.assert_not_called()


class ReadOnlyTest(unittest.TestCase):
    def test_client_exposes_get_only(self):
        public = {n for n in dir(Client) if not n.startswith("_")}
        self.assertEqual(public, {"get", "from_env"})

    def test_live_request_uses_get(self):
        client = Client("live")
        with mock.patch("norfigures.net._open") as urlopen:
            urlopen.side_effect = OSError("stop here")
            with self.assertRaises(net.FetchError):
                client.get("https://data.ssb.no/x")
        self.assertEqual(urlopen.call_args[0][0].get_method(), "GET")

    def test_redirect_off_the_allowlist_is_refused(self):
        client = Client("live")
        fake = mock.MagicMock()
        fake.__enter__.return_value.geturl.return_value = "https://evil.example.com/x"
        with mock.patch("norfigures.net._open", return_value=fake), \
                self.assertRaises(HostNotAllowed):
            client.get("https://data.ssb.no/x")

    def test_redirect_target_is_checked_before_it_is_requested(self):
        # urllib follows redirects itself; the handler must refuse before the next GET.
        handler = net._CheckedRedirects()
        req = urllib.request.Request("https://data.ssb.no/x", method="GET")
        for target in ("https://evil.example.com/x", "http://data.ssb.no/x",
                       "https://www.nav.no/minside"):
            with self.subTest(target=target), self.assertRaises(HostNotAllowed):
                handler.redirect_request(req, None, 302, "Found", {}, target)
        ok = handler.redirect_request(req, None, 302, "Found", {}, "https://data.ssb.no/y")
        self.assertEqual(ok.full_url, "https://data.ssb.no/y")

    def test_the_opener_uses_the_checked_redirect_handler(self):
        self.assertTrue(any(isinstance(h, net._CheckedRedirects) for h in net._OPENER.handlers))
        self.assertFalse(any(type(h) is urllib.request.HTTPRedirectHandler for h in net._OPENER.handlers))

    def test_a_text_body_that_is_not_utf8_is_a_fetch_error(self):
        fake = mock.MagicMock()
        r = fake.__enter__.return_value
        r.geturl.return_value = "https://data.ssb.no/x"
        r.read.return_value = b"\xff\xfe broken"
        r.status = 200
        r.headers.get_content_type.return_value = "application/json"
        with mock.patch("norfigures.net._open", return_value=fake), self.assertRaises(net.FetchError):
            Client("live").get("https://data.ssb.no/x")

    def test_no_other_module_imports_network_libraries(self):
        src = Path(net.__file__).parent
        for path in src.rglob("*.py"):
            if path.name == "net.py":
                continue
            text = path.read_text(encoding="utf-8")
            for lib in ("urllib.request", "http.client", "socket", "requests"):
                with self.subTest(file=path.name, lib=lib):
                    self.assertNotIn(f"import {lib}", text)


class BinaryBodyTest(unittest.TestCase):
    def test_binary_file_round_trips_through_a_recording(self):
        tmp = Path(tempfile.mkdtemp())
        url = "https://www.nav.no/_/attachment/download/a:b/202610_HL050.xlsx"
        blob = bytes(range(256)) * 4
        Client("record", recordings_dir=tmp)._save(
            net.Response(url, 200, "", "2026-11-23T00:00:00Z", False, content=blob))
        got = Client("replay", recordings_dir=tmp).get(url)
        self.assertEqual((got.content, got.body, got.replayed), (blob, "", True))

    def test_live_binary_and_text_bodies(self):
        for ctype, raw, want_body, want_content in [
                ("application/json", b'{"a": 1}', '{"a": 1}', None),
                ("text/html", "<p>ø</p>".encode(), "<p>ø</p>", None),
                ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"PK", "", b"PK")]:
            fake = mock.MagicMock()
            r = fake.__enter__.return_value
            r.geturl.return_value = "https://data.ssb.no/x"
            r.read.return_value = raw
            r.status = 200
            r.headers.get_content_type.return_value = ctype
            with self.subTest(ctype=ctype), mock.patch("norfigures.net._open", return_value=fake):
                got = Client("live").get("https://data.ssb.no/x")
                self.assertEqual((got.body, got.content), (want_body, want_content))

    def test_oversized_body_is_refused(self):
        fake = mock.MagicMock()
        r = fake.__enter__.return_value
        r.geturl.return_value = "https://data.ssb.no/x"
        r.read.return_value = b"x" * (net.MAX_BODY_BYTES + 1)
        with mock.patch("norfigures.net._open", return_value=fake), self.assertRaises(net.FetchError):
            Client("live").get("https://data.ssb.no/x")


class ErrorAnswerTest(unittest.TestCase):
    def test_a_400_answer_is_recorded_and_replays_as_the_same_error(self):
        tmp = Path(tempfile.mkdtemp())
        url = "https://data.ssb.no/api/x?y=1"
        err = urllib.error.HTTPError(url, 400, "Bad Request", {},
                                     io.BytesIO(b'{"title":"Non-existent value","status":400}'))
        with mock.patch("norfigures.net._open", side_effect=err), self.assertRaises(net.FetchError) as live:
            Client("record", recordings_dir=tmp).get(url)
        self.assertEqual(live.exception.status, 400)
        with self.assertRaises(net.FetchError) as replay:
            Client("replay", recordings_dir=tmp).get(url)
        self.assertEqual((replay.exception.status, replay.exception.body), (400, live.exception.body))

    def test_server_errors_and_rate_limits_are_never_recorded(self):
        tmp = Path(tempfile.mkdtemp())
        for code in (429, 503):
            err = urllib.error.HTTPError("https://data.ssb.no/x", code, "x", {}, io.BytesIO(b"busy"))
            with self.subTest(code=code), mock.patch("norfigures.net._open", side_effect=err), \
                    self.assertRaises(net.FetchError):
                Client("record", recordings_dir=tmp).get("https://data.ssb.no/x")
        self.assertEqual(list(tmp.iterdir()), [])


class ReplayTest(unittest.TestCase):
    def test_record_then_replay_round_trip(self):
        tmp = Path(tempfile.mkdtemp())
        resp = net.Response("https://data.ssb.no/x?a=1", 200, '{"ok": true}', "2026-11-14T00:00:00Z", False)
        Client("record", recordings_dir=tmp)._save(resp)
        got = Client("replay", recordings_dir=tmp).get("https://data.ssb.no/x", {"a": "1"})
        self.assertTrue(got.replayed)
        self.assertEqual(got.json(), {"ok": True})
        self.assertEqual(got.retrieved_at, "2026-11-14T00:00:00Z")

    def test_missing_recording_fails_loudly(self):
        with self.assertRaises(RecordingMissing):
            Client("replay", recordings_dir=Path(tempfile.mkdtemp())).get("https://data.ssb.no/nothing")

    def test_params_are_ordered_stably(self):
        self.assertEqual(net.build_url("https://h/p", {"b": "2", "a": "1"}),
                         net.build_url("https://h/p", {"a": "1", "b": "2"}))


if __name__ == "__main__":
    unittest.main()
