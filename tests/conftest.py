"""Helpers to build synthetic session files (never real user data)."""

import json
from pathlib import Path

import pytest


def ts(minute: int) -> str:
    return f"2026-11-20T10:{minute:02d}:00.000Z"


def user(text_or_blocks, minute: int, **extra) -> dict:
    return {"type": "user", "timestamp": ts(minute), "cwd": "C:\\dev\\demo", "entrypoint": "cli",
            "message": {"role": "user", "content": text_or_blocks}, **extra}


def assistant(msg_id: str, block: dict, minute: int) -> dict:
    return {"type": "assistant", "timestamp": ts(minute), "cwd": "C:\\dev\\demo",
            "message": {"id": msg_id, "role": "assistant", "content": [block]}}


@pytest.fixture
def write_session(tmp_path: Path):
    def _write(records: list, folder: str = "C--dev-demo", sid: str = "11111111-aaaa",
               raw_lines: list[str] | None = None) -> Path:
        d = tmp_path / "projects" / folder
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{sid}.jsonl"
        lines = [json.dumps(r) for r in records] + (raw_lines or [])
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return f
    return _write
