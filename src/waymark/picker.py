"""A thin wrapper around fzf."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass

DIM, BOLD, RESET = "\033[2m", "\033[1m", "\033[0m"

_COLORS = "hl:white:bold,hl+:white:bold,pointer:white,prompt:white,header:gray,border:gray"


@dataclass
class Choice:
    key: str
    """The key that ended the selection: empty for Enter, else one of ``expect``."""
    value: str


def available() -> bool:
    return shutil.which("fzf") is not None


def pick(
    rows: Sequence[tuple[str, str]],
    *,
    header: str,
    prompt: str = "> ",
    preview: str | None = None,
    expect: Sequence[str] = (),
) -> Choice | None:
    """Show ``(value, label)`` rows and return the chosen value, or None if cancelled."""
    command = [
        "fzf", "--ansi", "--no-sort", "--reverse", "--height=90%", "--border=rounded",
        "--delimiter=\t", "--with-nth=2..", f"--color={_COLORS}",
        "--header", header, "--prompt", prompt,
    ]  # fmt: skip
    if preview:
        command += ["--preview", preview, "--preview-window=down,45%,wrap"]
    if expect:
        command += ["--expect", ",".join(expect)]

    lines = "\n".join(f"{value}\t{label}" for value, label in rows)
    result = subprocess.run(command, input=lines, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None

    output = result.stdout.rstrip("\n").split("\n")
    key = output.pop(0) if expect else ""
    selected = output[0] if output else ""
    if not selected:
        return None
    return Choice(key=key, value=selected.split("\t", 1)[0])
