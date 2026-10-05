from __future__ import annotations

import json
from pathlib import Path

import pytest

SESSION_ID = "0b6f2c1e-8d4a-4f3e-9a71-2c5d8e9f1a3b"


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every waymark and Claude Code path into a temporary directory."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return tmp_path


def write_transcript(project: Path, session_id: str, records: list[dict]) -> Path:
    project.mkdir(parents=True, exist_ok=True)
    path = project / f"{session_id}.jsonl"
    # Claude Code writes compact JSON; waymark's line pre-filter relies on that.
    lines = "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in records)
    path.write_text(lines, encoding="utf-8")
    return path


def user(text: str, **extra: object) -> dict:
    return {"type": "user", "message": {"role": "user", "content": text}, **extra}


def assistant(text: str = "", tools: tuple[str, ...] = ()) -> dict:
    blocks: list[dict] = [{"type": "text", "text": text}] if text else []
    blocks += [{"type": "tool_use", "name": name} for name in tools]
    return {"type": "assistant", "message": {"role": "assistant", "content": blocks}}
