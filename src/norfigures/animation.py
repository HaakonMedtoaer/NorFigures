"""README animation: one indicator per worker, made from a run log (spec section 14).

    python -m norfigures.animation            # replay the worked example, write both files
    python -m norfigures.animation LOG OUT    # any run log -> animated SVG

The run is real: the example log comes from the spec's worked example, replayed
offline from the recorded extractor output and API responses. Only the timing
is staged, so each step stays visible. Every caption is built from a log field;
nothing here knows a number.

The SVG is animated with CSS keyframes only: no script, no external files, so
GitHub shows it in the README as an image.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_CASE = REPO_ROOT / "tests" / "cases" / "20_spec_worked_example.json"
EXAMPLE_LOG = REPO_ROOT / "docs" / "example-run.jsonl"
EXAMPLE_SVG = REPO_ROOT / "docs" / "run.svg"
EXAMPLE_TODAY = date(2026, 11, 19)   # same "today" as the long-text tests

# Staged durations, in seconds.
PAUSE, READ, MAP, FETCH, COMPARE, PROVENANCE, REPORT, HOLD = 0.6, 1.6, 0.9, 0.8, 0.9, 0.7, 0.9, 3.2

# (key, name, kind)
INDICATORS = [
    ("extractor", "Extractor", "ai"),
    ("mapper", "Phrase tables + mapper", "code"),
    ("ssb", "SSB", "source"),
    ("norges_bank", "Norges Bank", "source"),
    ("verifier", "Verifier", "code"),
    ("report", "Report", "code"),
]
KIND_LABEL = {"ai": "AI agent · Claude Haiku 5.5", "code": "Code", "source": "Source"}

SHORT = {"kpi_12m": "KPI", "kpi_jae_12m": "KPI-JAE", "kpi_mom": "KPI", "kpi_jae_mom": "KPI-JAE",
         "policy_rate": "policy rate", "eurnok": "EUR/NOK"}
INDICATOR_NAME = {"kpi": "KPI", "kpi_jae": "KPI-JAE", "policy_rate": "Policy rate", "eurnok": "EUR/NOK"}
MEASURE_NAME = {"12_month_change": "12-month", "monthly_change": "monthly", "level": "level",
                "change": "change"}
VERDICT = {"matched": ("✓", "Matched"), "mismatched": ("✗", "Mismatched"),
           "cannot_verify": ("?", "Cannot verify")}


@dataclass
class Step:
    key: str           # indicator
    start: float
    end: float
    caption: str       # shown while running, kept afterwards


@dataclass
class Verdict:
    at: float
    verdict: str
    source_text: str
    detail: str


@dataclass
class Timeline:
    steps: list[Step] = field(default_factory=list)
    verdicts: list[Verdict] = field(default_factory=list)
    total: float = 0.0


def _series_label(sid: str) -> str:
    return SHORT.get(sid, sid)


def _and(names: list[str]) -> str:
    names = list(dict.fromkeys(names))
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _period(d: dict) -> str:
    return d["start"] if d["start"] == d["end"] else f'{d["start"]} to {d["end"]}'


def _num(s: str | None) -> str:
    return "n/a" if s is None else s


def map_caption(d: dict) -> str:
    if d.get("mappings"):
        word = (d.get("phrases") or [d.get("indicator") or "claim"])[0]
        return f"{word} → {_and([_series_label(s) for s in d['mappings']])}"
    ind = INDICATOR_NAME.get(d.get("indicator"), d.get("indicator") or "unknown")
    status = (d.get("claim_status") or "unmapped").replace("_", " ")
    return f"{ind} · {status} → not checked"


def fetch_caption(d: dict, observed: str | None) -> str:
    sid = d["series_id"]
    if d.get("source") == "ssb":
        what = f"{_series_label(sid)} {MEASURE_NAME.get(_measure_of(sid), '')}".strip()
        return f"{d['ref'][0].upper()}{d['ref'][1:]} · {what} · {_period(d)}"
    return f"{d['ref']} · {observed or d['end']}"


def _measure_of(sid: str) -> str:
    return "12_month_change" if sid.endswith("_12m") else "monthly_change" if sid.endswith("_mom") else "level"


def compare_caption(d: dict) -> str:
    stated, readings = d.get("stated"), d.get("readings") or []
    if not readings:
        why = (d.get("labels") or [d.get("claim_status") or ""])[0].replace("_", " ")
        return f"{_num(stated)} · {VERDICT[_verdict(d)][1].lower()} ({why})"
    chosen = next((r for r in readings if r["series_id"] == d.get("chosen")), readings[0])
    return f"{_num(stated)} vs {_num(chosen['official'])}"


def _verdict(d: dict) -> str:
    return d.get("_verdict", "cannot_verify")


def stage_order(events: list[dict]) -> list[dict]:
    """Claims one after another (spec section 14): run-level events before the first
    claim event stay first, the rest last; each claim's own events keep their order.
    The pipeline maps every claim before verifying any, so this changes only what is
    shown when, never what is shown."""
    claim_ids = list(dict.fromkeys(e["claim_id"] for e in events if e["claim_id"]))
    if not claim_ids:
        return list(events)
    first = next(i for i, e in enumerate(events) if e["claim_id"])
    before = [e for e in events[:first] if not e["claim_id"]]
    after = [e for e in events[first:] if not e["claim_id"]]
    grouped = [e for cid in claim_ids for e in events if e["claim_id"] == cid]
    return before + grouped + after


def build(events: list[dict]) -> Timeline:
    """Stage the events of one run as a timeline, claim by claim."""
    events = stage_order(events)
    tl, t = Timeline(), PAUSE

    def step(key, dur, caption):
        nonlocal t
        tl.steps.append(Step(key, t, t + dur, caption))
        t += dur

    compares = {e["claim_id"]: e for e in events if e["stage"] == "compare"}
    for e in events:
        stage, d, cid = e["stage"], e["detail"], e["claim_id"]
        if stage == "extract":
            tl.steps.append(Step("extractor", t, t + READ, "Reading the text…"))
            t += READ
            n = d.get("claims", 0) if e["status"] == "ok" else 0
            word = "claim" if n == 1 else "claims"
            tl.steps.append(Step("extractor", t, t, f"Found {n} {word}" if e["status"] == "ok"
                                 else "Failed extraction"))
        elif stage == "map":
            step("mapper", MAP, map_caption(d))
        elif stage == "fetch":
            observed = None
            comp = compares.get(cid)
            if comp:
                for r in comp["detail"].get("readings") or []:
                    if r["series_id"] == d["series_id"]:
                        observed = r.get("observed")
            key = "ssb" if d.get("source") == "ssb" else "norges_bank"
            caption = fetch_caption(d, observed)
            if e["status"] == "failed":
                caption = "Blocked: " + caption if d.get("guardrail") else "Failed: " + caption
            step(key, FETCH, caption)
        elif stage == "compare":
            d = dict(d, _verdict=e["status"])
            step("verifier", COMPARE, compare_caption(d))
            readings = d.get("readings") or []
            detail = compare_caption(d) if readings else (d.get("labels") or [""])[0].replace("_", " ")
            tl.verdicts.append(Verdict(t, e["status"], d.get("source_text") or "", detail))
        elif stage == "provenance":
            step("verifier", PROVENANCE, "Every official number traced to a fetch"
                 if e["status"] == "ok" else "Provenance check failed")
        elif stage == "report":
            counts = {v: sum(x.verdict == v for x in tl.verdicts) for v in VERDICT}
            step("report", REPORT, f"{counts['matched']} matched · {counts['mismatched']} mismatched · "
                                   f"{counts['cannot_verify']} cannot verify · exit {d.get('exit_code')}")
    tl.total = t + HOLD
    return tl


# ------------------------------------------------------------------------- SVG

W, ROW_H, TOP, PAD = 860, 46, 86, 24
CAPTION_X = 330
COLORS = {
    "ai": "#7c3aed", "code": "#0369a1", "source": "#0f766e",
    "idle": "#b9b8b2", "done": "#0ca30c",
    "matched": "#0ca30c", "mismatched": "#d03b3b", "cannot_verify": "#c98a00",
}


def _pct(t: float, total: float) -> str:
    return f"{100 * t / total:.3f}%"


def _hold_frames(changes: list[tuple[float, str]], total: float, prop: str) -> str:
    """Keyframes that jump between values (used with step-end timing)."""
    frames, seen = [], set()
    for t, v in changes:
        p = _pct(t, total)
        if p in seen:
            frames[-1] = f"{p}{{{prop}:{v}}}"
        else:
            frames.append(f"{p}{{{prop}:{v}}}")
            seen.add(p)
    if "100.000%" not in seen:
        frames.append(f"100%{{{prop}:{changes[-1][1]}}}")
    return "".join(frames)


def render_svg(tl: Timeline, title: str = "") -> str:
    total = tl.total
    n_rows = len(INDICATORS)
    verdict_top = TOP + n_rows * ROW_H + 30
    height = verdict_top + max(len(tl.verdicts), 1) * 26 + 20
    css, body = [], []
    anim = f"{total:.2f}s step-end infinite"

    for i, (key, name, kind) in enumerate(INDICATORS):
        y = TOP + i * ROW_H
        steps = [s for s in tl.steps if s.key == key]
        running = [(s.start, s.end) for s in steps if s.end > s.start]

        # Dot colour: idle -> running (kind colour) -> done (green).
        changes = [(0.0, COLORS["idle"])]
        for a, b in running:
            changes += [(a, COLORS[kind]), (b, COLORS["done"])]
        if steps and not running:
            changes.append((steps[0].start, COLORS["done"]))
        css.append(f"@keyframes d{i}{{{_hold_frames(changes, total, 'fill')}}}"
                   f".d{i}{{animation:d{i} {anim}}}")

        # Pulse ring while running.
        frames = ["0%{stroke-opacity:0;r:7px}"]
        for a, b in running:
            k = a
            while k < b - 1e-6:
                frames.append(f"{_pct(k, total)}{{stroke-opacity:.6;r:7px}}")
                k2 = min(k + 0.45, b)
                frames.append(f"{_pct(k2 - 0.001, total)}{{stroke-opacity:0;r:13px}}")
                k = k2
            frames.append(f"{_pct(b, total)}{{stroke-opacity:0;r:7px}}")
        frames.append("100%{stroke-opacity:0;r:7px}")
        css.append(f"@keyframes p{i}{{{''.join(frames)}}}"
                   f".p{i}{{animation:p{i} {total:.2f}s linear infinite}}")

        body.append(f'<circle class="p{i}" cx="{PAD + 8}" cy="{y}" r="7" fill="none" '
                    f'stroke="{COLORS[kind]}" stroke-width="2" stroke-opacity="0"/>')
        body.append(f'<circle class="d{i}" cx="{PAD + 8}" cy="{y}" r="7" fill="{COLORS["idle"]}"/>')
        body.append(f'<text x="{PAD + 26}" y="{y + 1}" class="name">{escape(name)}</text>')
        body.append(f'<text x="{PAD + 26}" y="{y + 17}" class="kind" fill="{COLORS[kind]}">'
                    f'{escape(KIND_LABEL[kind])}</text>')

        # State word, so state is never colour alone: waiting / running / done.
        states = [(0.0, "waiting")]
        for a, b in running:
            states += [(a, "running"), (b, "done")]
        if steps and not running:
            states.append((steps[0].start, "done"))
        for word in ("waiting", "running", "done"):
            ch = [(t, "visible" if w == word else "hidden") for t, w in states]
            css.append(f"@keyframes s{i}{word}{{{_hold_frames(ch, total, 'visibility')}}}"
                       f".s{i}{word}{{animation:s{i}{word} {anim}}}")
            body.append(f'<text x="{CAPTION_X - 14}" y="{y + 5}" text-anchor="end" '
                        f'class="state s{i}{word}" visibility="{'visible' if word == 'waiting' else 'hidden'}">{word}</text>')

        # Captions: each visible from its start until the next caption for this indicator.
        for j, s in enumerate(steps):
            nxt = steps[j + 1].start if j + 1 < len(steps) else total + 1
            ch = [(0.0, "hidden"), (s.start, "visible")] + ([(nxt, "hidden")] if nxt <= total else [])
            cls = f"c{i}_{j}"
            css.append(f"@keyframes {cls}{{{_hold_frames(ch, total, 'visibility')}}}"
                       f".{cls}{{animation:{cls} {anim}}}")
            body.append(f'<text x="{CAPTION_X}" y="{y + 5}" class="cap {cls}" visibility="hidden">'
                        f'{escape(s.caption)}</text>')
        if i < n_rows - 1:
            body.append(f'<line x1="{PAD}" x2="{W - PAD}" y1="{y + ROW_H / 2 + 3}" '
                        f'y2="{y + ROW_H / 2 + 3}" class="rule"/>')

    body.append(f'<text x="{PAD}" y="{verdict_top - 8}" class="kind muted">Verdicts</text>')
    for k, v in enumerate(tl.verdicts):
        y = verdict_top + 14 + k * 26
        icon, word = VERDICT.get(v.verdict, ("?", v.verdict))
        cls = f"v{k}"
        css.append(f"@keyframes {cls}{{{_hold_frames([(0.0, 'hidden'), (v.at, 'visible')], total, 'visibility')}}}"
                   f".{cls}{{animation:{cls} {anim}}}")
        text = v.source_text if len(v.source_text) <= 66 else v.source_text[:65] + "…"
        body.append(f'<g class="{cls}" visibility="hidden">'
                    f'<rect x="{PAD}" y="{y - 13}" width="128" height="20" rx="4" '
                    f'fill="{COLORS[v.verdict]}"/>'
                    f'<text x="{PAD + 8}" y="{y + 1}" class="badge">{icon} {escape(word)}</text>'
                    f'<text x="{PAD + 140}" y="{y + 1}" class="vt">{escape(text)}</text>'
                    f'<text x="{W - PAD}" y="{y + 1}" text-anchor="end" class="state">'
                    f'{escape(v.detail)}</text></g>')

    style = f"""
    .bg{{fill:#fcfcfb;stroke:#e4e3de}}
    text{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;fill:#0b0b0b}}
    .title{{font-size:15px;font-weight:600}}
    .sub,.muted{{fill:#52514e}}
    .sub{{font-size:12px}}
    .name{{font-size:14px;font-weight:600}}
    .kind{{font-size:11px;font-weight:600;letter-spacing:.02em}}
    .state{{font-size:12px;fill:#52514e}}
    .cap{{font-size:13px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}}
    .vt{{font-size:13px}}
    .badge{{font-size:12px;font-weight:700;fill:#fff}}
    .rule{{stroke:#ecebe7}}
    @media (prefers-color-scheme: dark){{
      .bg{{fill:#1a1a19;stroke:#33322f}} text{{fill:#f0efec}} .sub,.muted,.state{{fill:#c3c2b7}}
      .rule{{stroke:#2a2a28}} .badge{{fill:#fff}}
    }}
    @media (prefers-reduced-motion: reduce){{ *{{animation-play-state:paused}} }}
    {''.join(css)}"""
    head = (f'<text x="{PAD}" y="30" class="title">{escape(title or "NorFigures: one run, worker by worker")}</text>'
            f'<text x="{PAD}" y="47" class="sub">Replayed from a real run log. '
            f'Only the timing is staged.</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" '
            f'viewBox="0 0 {W} {height}" role="img" aria-label="Animation of a NorFigures run: '
            f'extractor, mapper, SSB, Norges Bank, verifier and report, one claim at a time.">'
            f'<style>{style}</style>'
            f'<rect class="bg" x="0.5" y="0.5" width="{W - 1}" height="{height - 1}" rx="10"/>'
            f'{head}{"".join(body)}</svg>\n')


# ---------------------------------------------------------------------- example

def record_example(path: Path = EXAMPLE_LOG) -> Path:
    """Run the spec's worked example offline and write its log."""
    from .claims import parse_json
    from .events import RunLog
    from .ledger import load
    from .net import Client
    from .pipeline import check_text
    from .report import exit_code

    case = parse_json(EXAMPLE_CASE.read_text(encoding="utf-8"))
    if path.exists():
        path.unlink()
    log = RunLog(path=path)
    log.emit("load", "ok", source="memo.txt", published=case["published"], offline=True, kind="text")
    out = check_text(case["text"], Client.from_env(offline=True), load(), "replay",
                     published=date.fromisoformat(case["published"]), today=EXAMPLE_TODAY, log=log)
    log.emit("report", "ok", exit_code=exit_code(out.results))
    return path


def read_log(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        if len(argv) != 2:
            print("usage: python -m norfigures.animation [LOG OUT.svg]", file=sys.stderr)
            return 3
        log, out = Path(argv[0]), Path(argv[1])
    else:
        log, out = record_example(), EXAMPLE_SVG
    tl = build(read_log(log))
    out.write_text(render_svg(tl), encoding="utf-8")
    print(f"{out}: {tl.total:.1f} s, {len(tl.steps)} steps, {len(tl.verdicts)} verdicts (from {log})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
