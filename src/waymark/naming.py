"""Title suggestions from Claude.

Suggestions run through ``claude -p`` with no tools, no MCP servers and no saved session, from
an empty temporary directory. The model sees a digest of the session and nothing else.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .text import clean
from .transcripts import Summary

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_RULES = "3-7 words, lowercase, no trailing period. Say what the session is about."
SUGGESTION_COUNT = 3
_TIMEOUT_SECONDS = 90
_MAX_NAME_CHARS = 80
_MAX_DIGEST_CHARS = 9000


class NamingError(RuntimeError):
    """The model could not be reached or returned nothing usable."""


@dataclass
class Config:
    model: str = DEFAULT_MODEL
    rules: str = DEFAULT_RULES
    folder_rules: dict[str, str] = field(default_factory=dict)


@dataclass
class Suggestion:
    names: list[str]
    model: str
    usage: dict[str, int]
    cost_usd: float


def load_config(path: Path | None = None) -> Config:
    """Read the config file. A missing or unreadable file gives the defaults."""
    try:
        data = json.loads((path or paths.config_file()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Config()
    return Config(
        model=data.get("model") or DEFAULT_MODEL,
        rules=data.get("default") or DEFAULT_RULES,
        folder_rules=dict(data.get("folders") or {}),
    )


def rules_for(config: Config, folder: str) -> str:
    """The default rules plus the rules of the longest folder prefix that matches."""
    best_key, best_len = None, -1
    for key in config.folder_rules:
        prefix = key.rstrip("/")
        matches = folder == prefix or folder.startswith(prefix + "/")
        if matches and len(prefix) > best_len:
            best_key, best_len = key, len(prefix)
    if best_key is None:
        return config.rules
    return f"{config.rules}\n{config.folder_rules[best_key]}"


def build_digest(summary: Summary) -> str:
    lines = [f"Folder: {summary.cwd or '?'}"]
    if summary.ai_title:
        lines.append(f"Auto-generated title (often vague): {summary.ai_title}")
    lines.append("What the person asked, in order:")
    lines += [f"- {prompt[:500]}" for prompt in summary.prompts]
    if summary.tools:
        top = sorted(summary.tools.items(), key=lambda item: -item[1])[:8]
        lines.append("Tools used: " + ", ".join(f"{name}×{count}" for name, count in top))
    if summary.replies:
        lines.append("Some of the assistant's replies:")
        lines += [f"- {reply[:300]}" for reply in summary.replies]
    return "\n".join(lines)[:_MAX_DIGEST_CHARS]


def build_prompt(rules: str, digest: str, avoid: Sequence[str] = (), direction: str = "") -> str:
    sections = [
        "You name Claude Code sessions so the person can find them later in a list.",
        f"Naming conventions:\n{rules}",
        f"Session digest:\n{digest}",
    ]
    if direction:
        sections.append(
            "The person's direction for the name (follow it closely while staying accurate "
            f"to the session and the conventions): {direction}"
        )
    if avoid:
        sections.append(f"Do not repeat these earlier suggestions: {', '.join(avoid)}")
    sections.append(
        f"Give {SUGGESTION_COUNT} different candidate names, most accurate first, one per line, "
        "with no numbering, quotes or commentary. Base them on the whole session, not just "
        "the end. If it covered two unrelated topics, join them with ' + ' "
        "(for example 'mouse bluetooth fix + release notes'). "
        "Never use the folder's own name as the project name."
    )
    return "\n\n".join(sections)


def parse_names(text: str) -> list[str]:
    """Pull candidate names out of a model reply, dropping list markers, quotes and dupes."""
    names: list[str] = []
    for raw in text.splitlines():
        name = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", clean(raw)).strip()
        name = name.rstrip(".").strip("\"'`").rstrip(".").strip()
        if name and len(name) <= _MAX_NAME_CHARS and name not in names:
            names.append(name)
    return names[:SUGGESTION_COUNT]


def suggest(
    summary: Summary,
    config: Config,
    *,
    folder: str,
    avoid: Sequence[str] = (),
    direction: str = "",
) -> Suggestion:
    prompt = build_prompt(rules_for(config, folder), build_digest(summary), avoid, direction)
    command = [
        "claude", "-p",
        "--model", config.model,
        "--no-session-persistence",
        "--tools", "",
        "--strict-mcp-config",
        "--effort", "low",
        "--output-format", "json",
    ]  # fmt: skip
    with tempfile.TemporaryDirectory() as scratch:
        try:
            result = subprocess.run(
                command,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
                cwd=scratch,
                check=False,
            )
        except FileNotFoundError as error:
            raise NamingError("the `claude` command was not found on PATH") from error
        except subprocess.TimeoutExpired as error:
            raise NamingError(f"no reply within {_TIMEOUT_SECONDS}s") from error

    try:
        reply = json.loads(result.stdout)
    except ValueError as error:
        detail = clean(result.stderr.strip() or result.stdout.strip())[:300]
        raise NamingError(detail or "unreadable reply") from error
    if reply.get("is_error"):
        raise NamingError(clean(str(reply.get("result")))[:300])

    usage = reply.get("usage") or {}
    return Suggestion(
        names=parse_names(reply.get("result") or ""),
        model=config.model,
        usage={
            "in": usage.get("input_tokens", 0),
            "out": usage.get("output_tokens", 0),
            "cache_read": usage.get("cache_read_input_tokens", 0),
            "cache_write": usage.get("cache_creation_input_tokens", 0),
        },
        cost_usd=reply.get("total_cost_usd") or 0.0,
    )
