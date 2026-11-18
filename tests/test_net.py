import tempfile
import unittest
from pathlib import Path
from unittest import mock

from norfigures import net
from norfigures.net import Client, HostNotAllowed, RecordingMissing, check_url


class AllowlistTest(unittest.TestCase):
    def test_allowed_hosts_are_exactly_the_two_official_apis(self):
        self.assertEqual(net.ALLOWED_HOSTS, {"data.ssb.no", "data.norges-bank.no"})

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
            with mock.patch("urllib.request.urlopen") as urlopen, \
                    self.subTest(mode=mode), self.assertRaises(HostNotAllowed):
                client.get("https://example.com/x")
            urlopen.assert_not_called()


class ReadOnlyTest(unittest.TestCase):
    def test_client_exposes_get_only(self):
        public = {n for n in dir(Client) if not n.startswith("_")}
        self.assertEqual(public, {"get", "from_env"})

    def test_live_request_uses_get(self):
        client = Client("live")
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = OSError("stop here")
            with self.assertRaises(net.FetchError):
                client.get("https://data.ssb.no/x")
        self.assertEqual(urlopen.call_args[0][0].get_method(), "GET")

    def test_redirect_off_the_allowlist_is_refused(self):
        client = Client("live")
        fake = mock.MagicMock()
        fake.__enter__.return_value.geturl.return_value = "https://evil.example.com/x"
        with mock.patch("urllib.request.urlopen", return_value=fake), \
                self.assertRaises(HostNotAllowed):
            client.get("https://data.ssb.no/x")

    def test_no_other_module_imports_network_libraries(self):
        src = Path(net.__file__).parent
        for path in src.rglob("*.py"):
            if path.name == "net.py":
                continue
            text = path.read_text(encoding="utf-8")
            for lib in ("urllib.request", "http.client", "socket", "requests"):
                with self.subTest(file=path.name, lib=lib):
                    self.assertNotIn(f"import {lib}", text)


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
