"""The only network code in NorFigures.

Guardrails (spec section 10):
- Host allowlist: every request goes through `get()`, which refuses any host
  other than the official sources, in live AND replay mode. SSB and Norges Bank
  are API hosts; NAV has no API, so `www.nav.no` is allowed only under the
  statistics pages and their file downloads (D20).
- Read-only by construction: this module can only issue HTTP GET. There is no
  other method, and nothing else in the package opens sockets.

Transports:
- live:    real HTTPS GET via urllib.
- replay:  read a recorded response from disk; never touches the network.
- record:  live GET, then save the response for later replay.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ALLOWED_HOSTS = frozenset({"data.ssb.no", "data.norges-bank.no", "www.nav.no"})

# Hosts that serve more than data are limited to these path prefixes (D20).
ALLOWED_PATHS = {
    "www.nav.no": ("/no/nav-og-samfunn/statistikk/", "/_/attachment/download/"),
}

# Bodies larger than this are refused: the biggest file we read is about 30 kB.
MAX_BODY_BYTES = 5_000_000

USER_AGENT = "NorFigures/0.1 (+open-source fact verifier)"
DEFAULT_TIMEOUT = 30

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECORDINGS_DIR = REPO_ROOT / "tests" / "recorded" / "http"

MODES = ("live", "replay", "record")


class NetError(Exception):
    """Base class for network-layer failures. Maps to exit code 3."""


class HostNotAllowed(NetError):
    """Raised when a URL points anywhere other than an allowlisted host."""


class FetchError(NetError):
    """Raised when the source is unreachable or answers with an error.

    `status` is the HTTP status when the source answered (400, 404, ...), else None,
    and `body` the start of its answer, so an adapter can tell a period that is not
    published yet from a real error.
    """

    def __init__(self, message: str, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


class RecordingMissing(NetError):
    """Raised in replay mode when no recording exists for a URL."""


@dataclass(frozen=True)
class Response:
    url: str
    status: int
    body: str          # text responses (JSON, HTML); "" for a binary file
    retrieved_at: str  # ISO 8601, UTC
    replayed: bool
    content: bytes | None = None  # binary responses (NAV's xlsx files), else None

    def json(self):
        return json.loads(self.body)


def build_url(base: str, params: dict[str, str] | None = None) -> str:
    """Append query parameters in a stable order, so recordings key reliably."""
    if not params:
        return base
    query = urllib.parse.urlencode(sorted(params.items()), safe="[](),:")
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}{query}"


def check_url(url: str) -> str:
    """Return the host if `url` is allowed, else raise HostNotAllowed."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https":
        raise HostNotAllowed(f"only https is allowed, got {parts.scheme!r}: {url}")
    if parts.username or parts.password:
        raise HostNotAllowed(f"credentials in URL are not allowed: {url}")
    if parts.port not in (None, 443):
        raise HostNotAllowed(f"non-standard port is not allowed: {url}")
    host = (parts.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise HostNotAllowed(f"host {host!r} is not on the allowlist {sorted(ALLOWED_HOSTS)}")
    if host in ALLOWED_PATHS:
        path = parts.path
        segments = urllib.parse.unquote(path).split("/")
        if any(s in (".", "..") for s in segments) or "%2f" in path.lower() or "\\" in path:
            raise HostNotAllowed(f"path tricks are not allowed: {url}")
        if not path.startswith(ALLOWED_PATHS[host]):
            raise HostNotAllowed(f"path {path!r} on {host} is not on the allowlist "
                                 f"{list(ALLOWED_PATHS[host])}")
    return host


def _is_text(content_type: str) -> bool:
    return content_type.startswith("text/") or content_type in (
        "application/json", "application/xml") or content_type.endswith("+json")


def recording_path(url: str, directory: Path) -> Path:
    host = urllib.parse.urlsplit(url).hostname
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return directory / f"{host}_{digest}.json"


class Client:
    """A GET-only HTTP client bound to one mode."""

    def __init__(self, mode: str = "live", recordings_dir: Path | None = None,
                 timeout: int = DEFAULT_TIMEOUT):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        self.mode = mode
        self.recordings_dir = Path(recordings_dir or DEFAULT_RECORDINGS_DIR)
        self.timeout = timeout

    @classmethod
    def from_env(cls, offline: bool = False) -> "Client":
        if offline or os.environ.get("NORFIGURES_OFFLINE") == "1":
            return cls("replay")
        mode = "record" if os.environ.get("NORFIGURES_RECORD") == "1" else "live"
        return cls(mode)

    def get(self, base: str, params: dict[str, str] | None = None) -> Response:
        url = build_url(base, params)
        check_url(url)  # before any I/O, in every mode
        if self.mode == "replay":
            return _raise_for_status(self._replay(url))
        resp = self._live_get(url)
        if self.mode == "record":
            self._save(resp)  # error answers too, so replay fails the same way
        return _raise_for_status(resp)

    def _live_get(self, url: str) -> Response:
        req = urllib.request.Request(
            url, method="GET",
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                # A redirect could leave the allowlist; check where we ended up.
                check_url(r.geturl())
                raw = r.read(MAX_BODY_BYTES + 1)
                if len(raw) > MAX_BODY_BYTES:
                    raise FetchError(f"response from {url} is larger than {MAX_BODY_BYTES} bytes")
                status = r.status
                ctype = r.headers.get_content_type() if r.headers else "application/json"
        except urllib.error.HTTPError as e:
            with e:
                detail = e.read().decode("utf-8", errors="replace")[:300]
            if e.code >= 500 or e.code == 429:
                # Transient: never recorded, always an error.
                raise FetchError(f"HTTP {e.code} from {url}: {detail}", e.code, detail) from e
            return Response(url, e.code, detail, _now(), replayed=False)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise FetchError(f"could not reach {url}: {e}") from e
        if _is_text(ctype):
            return Response(url, status, raw.decode("utf-8"), _now(), replayed=False)
        return Response(url, status, "", _now(), replayed=False, content=raw)

    def _save(self, resp: Response) -> None:
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        path = recording_path(resp.url, self.recordings_dir)
        record = {"url": resp.url, "status": resp.status, "retrieved_at": resp.retrieved_at}
        if resp.content is not None:
            record["body_base64"] = base64.b64encode(resp.content).decode("ascii")
        else:
            record["body"] = resp.body
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")

    def _replay(self, url: str) -> Response:
        path = recording_path(url, self.recordings_dir)
        if not path.exists():
            raise RecordingMissing(
                f"no recording for {url} (expected {path.name}); "
                "run with NORFIGURES_RECORD=1 to create it")
        rec = json.loads(path.read_text(encoding="utf-8"))
        if rec["url"] != url:
            raise RecordingMissing(f"recording {path.name} is for a different URL")
        if "body_base64" in rec:
            return Response(url, rec["status"], "", rec["retrieved_at"], replayed=True,
                            content=base64.b64decode(rec["body_base64"]))
        return Response(url, rec["status"], rec["body"], rec["retrieved_at"], replayed=True)


def _raise_for_status(resp: Response) -> Response:
    if resp.status >= 400:
        raise FetchError(f"HTTP {resp.status} from {resp.url}: {resp.body}", resp.status, resp.body)
    return resp


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
