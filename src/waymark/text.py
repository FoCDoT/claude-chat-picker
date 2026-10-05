"""Text and file helpers."""

from __future__ import annotations

import os
import re
import time
from datetime import datetime
from pathlib import Path

# C0/C1 control characters (including ESC), zero-width characters and bidi overrides.
# Transcript text and model output are untrusted: they must never reach the terminal as
# escape sequences or end up in a title as a line break.
_UNSAFE = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩]")


def clean(text: str | None) -> str:
    """Replace control, zero-width and bidi characters with spaces."""
    return _UNSAFE.sub(" ", text or "")


def one_line(text: str | None, width: int) -> str:
    """Collapse whitespace and truncate to ``width`` characters."""
    flat = " ".join(clean(text).split())
    return flat if len(flat) <= width else flat[: width - 1] + "…"


def relative_time(timestamp: float, now: float | None = None) -> str:
    age = (now if now is not None else time.time()) - timestamp
    if age < 3600:
        return f"{int(age // 60)}m ago"
    if age < 86400:
        return f"{int(age // 3600)}h ago"
    if age < 7 * 86400:
        return f"{int(age // 86400)}d ago"
    return datetime.fromtimestamp(timestamp).strftime("%d %b")


def human_size(num_bytes: int) -> str:
    return f"{num_bytes / 1e6:.1f}M" if num_bytes >= 1e6 else f"{num_bytes // 1000}K"


def write_private(path: Path, data: str, *, append: bool = False) -> None:
    """Write a file readable only by the current user, creating its directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if append else os.O_TRUNC)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "a" if append else "w", encoding="utf-8") as handle:
        handle.write(data)
