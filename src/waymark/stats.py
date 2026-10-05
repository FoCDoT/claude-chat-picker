"""Usage log shared by the CLI and the waymark-nudge mod.

One JSON object per line: ``kind`` is ``model`` for a suggestion request or ``rename`` for a
title change, and ``source`` is ``cli`` or ``mod``.
"""

from __future__ import annotations

import contextlib
import json
from datetime import datetime
from pathlib import Path

from . import paths
from .text import one_line, write_private


def record(kind: str, **fields: object) -> None:
    """Append an event. Failures are ignored: the log is informational."""
    event = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": "cli",
        "kind": kind,
        **fields,
    }
    line = json.dumps(event, ensure_ascii=False) + "\n"
    with contextlib.suppress(OSError):
        write_private(paths.stats_file(), line, append=True)


def read_events(path: Path | None = None) -> list[dict]:
    events = []
    try:
        with (path or paths.stats_file()).open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return events


def report(events: list[dict]) -> str:
    if not events:
        return f"No usage recorded yet ({paths.stats_file()})."

    calls = [e for e in events if e.get("kind") == "model"]
    renames = [e for e in events if e.get("kind") == "rename"]
    lines = [f"waymark usage since {events[0].get('ts', '?')[:10]}", "", "Suggestion requests"]

    for source, label in (("cli", "cli"), ("mod", "nudge")):
        subset = [e for e in calls if e.get("source") == source]
        if subset:
            lines.append(f"  {label:<6} {_usage_line(subset)}")
    lines.append(f"  {'total':<6} {_usage_line(calls)}")
    lines.append("  Subscription use counts toward plan limits; cost is the API-equivalent price.")

    lines += ["", f"Renames: {len(renames)}"]
    by_method: dict[str, int] = {}
    for event in renames:
        method = event.get("how", "?")
        by_method[method] = by_method.get(method, 0) + 1
    if by_method:
        lines.append("  " + ", ".join(f"{k} {v}" for k, v in sorted(by_method.items())))
    for event in renames[-8:][::-1]:
        when = event.get("ts", "")[:16].replace("T", " ")
        folder = Path(event.get("folder") or "?").name
        lines.append(f"  {when}  {one_line(folder, 18):<18}  {one_line(event.get('title'), 70)}")
    return "\n".join(lines)


def _usage_line(events: list[dict]) -> str:
    tokens_in = sum(
        e.get("in", 0) + e.get("cache_read", 0) + e.get("cache_write", 0) for e in events
    )
    tokens_out = sum(e.get("out", 0) for e in events)
    cost = sum(e.get("cost_usd") or 0 for e in events)
    text = f"{len(events):>4} requests  {tokens_in:>9,} tokens in  {tokens_out:>7,} out"
    return text + (f"  ~${cost:.2f}" if cost else "")
