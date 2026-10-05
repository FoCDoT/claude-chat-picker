"""Filesystem locations.

Claude Code's own data is found through ``CLAUDE_CONFIG_DIR`` (default ``~/.claude``).
waymark's files follow the XDG base directory spec.
"""

from __future__ import annotations

import os
import re
from pathlib import Path


def _xdg(variable: str, fallback: str) -> Path:
    value = os.environ.get(variable)
    return Path(value) if value else Path.home() / fallback


def claude_dir() -> Path:
    value = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(value) if value else Path.home() / ".claude"


def projects_dir() -> Path:
    return claude_dir() / "projects"


def project_dir(folder: str | os.PathLike[str]) -> Path:
    """Where Claude Code keeps the transcripts for sessions started in ``folder``."""
    return projects_dir() / re.sub(r"[^A-Za-z0-9]", "-", str(folder))


def config_file() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config") / "waymark" / "config.json"


def stats_file() -> Path:
    return _xdg("XDG_STATE_HOME", ".local/state") / "waymark" / "stats.jsonl"


def cache_dir() -> Path:
    return _xdg("XDG_CACHE_HOME", ".cache") / "waymark"
