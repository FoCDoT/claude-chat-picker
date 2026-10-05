"""Reading session transcripts and writing session titles.

Claude Code stores each session as ``<projects>/<folder-slug>/<session-id>.jsonl``, one JSON
record per line. A title set with ``/rename`` is recorded twice: as a ``custom-title`` record
appended to the transcript and in ``<session-id>/custom-title.json``. waymark writes both, so
its titles are indistinguishable from ``/rename``.
"""

from __future__ import annotations

import contextlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import paths
from .text import clean, write_private

SESSION_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

MAX_TITLE_CHARS = 120
_CACHE_VERSION = 2
_PROMPT_CHARS = 600
_REPLY_CHARS = 400

# User records that hold harness output rather than something the person typed.
_HARNESS_PREFIXES = (
    "<local-command",
    "<system-reminder",
    "<task-notification",
    "<bash-",
    "Caveat:",
    "[Request interrupted",
    "This session is being continued",
)


@dataclass
class Summary:
    """The parts of a transcript waymark uses. Cached, keyed by file mtime and size."""

    custom_title: str | None = None
    agent_name: str | None = None
    ai_title: str | None = None
    cwd: str | None = None
    prompts: list[str] = field(default_factory=list)
    replies: list[str] = field(default_factory=list)
    tools: dict[str, int] = field(default_factory=dict)


@dataclass
class Session:
    id: str
    path: Path
    size: int
    mtime: float
    title: str | None
    summary: Summary

    @property
    def folder(self) -> str | None:
        return self.summary.cwd


def extract_prompt(record: dict) -> str | None:
    """Return the text a person typed in a ``user`` record, or None for harness records."""
    if record.get("isMeta") or record.get("isSidechain"):
        return None
    content = (record.get("message") or {}).get("content")
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        content = "\n".join(parts) if parts else None
    if not isinstance(content, str):
        return None

    text = content.strip()
    command = re.search(r"<command-name>(.*?)</command-name>", text)
    if command:
        args = re.search(r"<command-args>(.*?)</command-args>", text, re.S)
        return f"{command.group(1)} {args.group(1) if args else ''}".strip()
    if text.startswith(_HARNESS_PREFIXES):
        return None
    text = re.sub(r"<pasted_content[^>]*>|</pasted_content>", "", text)
    text = re.sub(r"\[Image #\d+\]", "", text).strip()
    return text or None


def summarize(path: Path) -> Summary:
    summary = Summary()
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            # Attachment and file-history records are large and never needed.
            if '"type":"' not in line or '"type":"attachment"' in line[:200]:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            _absorb(summary, record)

    # Keep the start and the end of long sessions; the middle adds little to a title.
    summary.prompts = summary.prompts[:12] + summary.prompts[12:][-8:]
    summary.replies = summary.replies[:3] + summary.replies[3:][-5:]
    return summary


def _absorb(summary: Summary, record: dict) -> None:
    kind = record.get("type")
    if record.get("cwd") and not summary.cwd:
        summary.cwd = record["cwd"]
    if kind == "custom-title":
        summary.custom_title = record.get("customTitle") or None
    elif kind == "agent-name":
        summary.agent_name = record.get("agentName") or None
    elif kind == "ai-title":
        summary.ai_title = record.get("aiTitle") or None
    elif kind == "user":
        prompt = extract_prompt(record)
        if prompt:
            summary.prompts.append(prompt[:_PROMPT_CHARS])
    elif kind == "assistant" and not record.get("isSidechain"):
        for block in (record.get("message") or {}).get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text", "").strip():
                summary.replies.append(block["text"].strip()[:_REPLY_CHARS])
            elif block.get("type") == "tool_use":
                name = block.get("name", "?")
                summary.tools[name] = summary.tools.get(name, 0) + 1


def load_sessions(project: Path) -> list[Session]:
    """All sessions in a project directory with at least one prompt, newest first."""
    cache_path = paths.cache_dir() / f"{project.name}.json"
    cached = _read_cache(cache_path)
    fresh: dict[str, dict] = {}
    sessions: list[Session] = []

    for path in project.glob("*.jsonl"):
        session_id = path.stem
        stat = path.stat()
        key = f"{stat.st_mtime_ns}:{stat.st_size}"
        hit = cached.get(session_id)
        summary = Summary(**hit["summary"]) if hit and hit.get("key") == key else summarize(path)
        fresh[session_id] = {"key": key, "summary": asdict(summary)}
        if not summary.prompts:
            continue  # opened and closed without a prompt
        title = read_title(project, session_id) or summary.custom_title or summary.agent_name
        sessions.append(Session(session_id, path, stat.st_size, stat.st_mtime, title, summary))

    with contextlib.suppress(OSError):
        write_private(cache_path, json.dumps({"version": _CACHE_VERSION, "entries": fresh}))
    sessions.sort(key=lambda s: s.mtime, reverse=True)
    return sessions


def _read_cache(path: Path) -> dict[str, dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data.get("entries", {}) if data.get("version") == _CACHE_VERSION else {}


def read_title(project: Path, session_id: str) -> str | None:
    try:
        data = json.loads((project / session_id / "custom-title.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data.get("customTitle") or None


def write_title(project: Path, session_id: str, title: str) -> str:
    """Set a session's title the way ``/rename`` does. Returns the title as written."""
    if not SESSION_ID.match(session_id):
        raise ValueError(f"not a session id: {session_id!r}")
    title = " ".join(clean(title).split())[:MAX_TITLE_CHARS]
    if not title:
        raise ValueError("title is empty")

    record = {"type": "custom-title", "customTitle": title, "sessionId": session_id}
    with (project / f"{session_id}.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    (project / session_id).mkdir(exist_ok=True)
    (project / session_id / "custom-title.json").write_text(
        json.dumps({"customTitle": title}, ensure_ascii=False), encoding="utf-8"
    )
    return title
