"""Shared test helpers."""

import json
import os
from datetime import date
from pathlib import Path

from norfigures.claims import parse_json
from norfigures.net import Client

CASES_DIR = Path(__file__).parent / "cases"
TODAY = date(2026, 11, 15)  # fixed so the future-period guard is deterministic


def client() -> Client:
    """Replay by default. NORFIGURES_RECORD=1 refreshes recordings from the live APIs."""
    return Client("record" if os.environ.get("NORFIGURES_RECORD") == "1" else "replay")


def load_cases() -> list[tuple[str, dict]]:
    return [(p.stem, parse_json(p.read_text(encoding="utf-8")))
            for p in sorted(CASES_DIR.glob("*.json"))]
