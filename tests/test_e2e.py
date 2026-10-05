"""End-to-end tests: run waymark in a pseudo-terminal and drive the real fzf with keystrokes.

A fake ``claude`` on PATH answers suggestion requests and records how it was launched, so
resuming or starting a session can be checked without starting Claude Code.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import pty
import re
import select
import shutil
import struct
import sys
import termios
import time
from pathlib import Path

import pytest
from conftest import assistant, user, write_transcript

from waymark import paths

pytestmark = pytest.mark.skipif(shutil.which("fzf") is None, reason="fzf is not installed")

ENTER, ESC, CTRL_R, CTRL_O = "\r", "\x1b", "\x12", "\x0f"
NEWEST = "aaaaaaaa-0000-4000-8000-000000000001"
OLDER = "bbbbbbbb-0000-4000-8000-000000000002"
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[()][0-9A-Za-z]|\x1b[=>]|\r")

FAKE_CLAUDE = """#!/bin/sh
if [ "$1" = "-p" ]; then
  cat > /dev/null
  printf '%s' '{"result": "uploader retries\\ncache cleanup\\nthird idea",
    "usage": {"input_tokens": 5, "output_tokens": 3}, "total_cost_usd": 0}'
  exit 0
fi
{ pwd; for arg in "$@"; do echo "$arg"; done; } > "$WAYMARK_TEST_LOG"
"""


class Terminal:
    def __init__(self, argv: list[str], env: dict[str, str], cwd: Path) -> None:
        self.pid, self.fd = pty.fork()
        if self.pid == 0:  # child
            os.chdir(cwd)
            os.execvpe(argv[0], argv, env)
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 140, 0, 0))
        self.screen = ""

    def _read(self, timeout: float) -> None:
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if ready:
            with contextlib.suppress(OSError):  # raised once the child has exited
                data = os.read(self.fd, 65536)
                # fzf asks for the cursor position and waits; answer as a terminal would.
                for _ in range(data.count(b"\x1b[6n")):
                    os.write(self.fd, b"\x1b[1;1R")
                self.screen += _ANSI.sub("", data.decode(errors="replace"))

    def expect(self, text: str, timeout: float = 15) -> None:
        deadline = time.monotonic() + timeout
        while text not in self.screen:
            if time.monotonic() > deadline:
                raise AssertionError(f"{text!r} not shown; screen tail: {self.screen[-1500:]!r}")
            self._read(0.1)
        self.screen = self.screen[self.screen.index(text) + len(text) :]

    def send(self, keys: str, settle: float = 0.3) -> None:
        time.sleep(settle)  # let fzf finish drawing before keys arrive
        os.write(self.fd, keys.encode())

    def wait(self, timeout: float = 15) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid:
                return os.waitstatus_to_exitcode(status)
            self._read(0.1)
        os.kill(self.pid, 9)
        raise AssertionError(f"waymark did not exit; screen tail:\n{self.screen[-2000:]}")


@pytest.fixture
def workspace(tmp_path: Path) -> dict:
    folder = (tmp_path / "work").resolve()
    folder.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude").write_text(FAKE_CLAUDE)
    (bin_dir / "claude").chmod(0o755)

    project = paths.project_dir(folder)
    write_transcript(project, OLDER, [user("set up billing webhooks", cwd=str(folder))])
    (project / OLDER).mkdir()
    (project / OLDER / "custom-title.json").write_text(json.dumps({"customTitle": "billing hooks"}))
    write_transcript(
        project,
        NEWEST,
        [user("add retries to the uploader", cwd=str(folder)), assistant("Done.")],
    )
    os.utime(project / f"{OLDER}.jsonl", (time.time() - 3600, time.time() - 3600))

    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "TERM": "xterm"}
    env["WAYMARK_TEST_LOG"] = str(tmp_path / "claude-launch.log")
    return {"folder": folder, "project": project, "env": env, "log": tmp_path / "claude-launch.log"}


def run(workspace: dict, *args: str) -> Terminal:
    argv = [sys.executable, "-m", "waymark", *args]
    return Terminal(argv, workspace["env"], workspace["folder"])


def launched(workspace: dict) -> list[str]:
    return workspace["log"].read_text().splitlines()


def test_menu_resume_skips_permissions_by_default(workspace: dict) -> None:
    term = run(workspace)
    term.expect("Runs claude with --dangerously-skip-permissions")
    term.expect("use waymark --no-perms to keep prompts")
    term.expect("Resume a session  skipping permissions")
    term.expect("1 of 2 unnamed")
    term.send(ENTER)
    term.expect("use waymark --no-perms to keep prompts")  # repeated above the list
    term.expect("add retries to the uploader")  # newest first
    term.expect("billing hooks")
    term.send(ENTER)
    assert term.wait() == 0
    folder = str(workspace["folder"])
    assert launched(workspace) == [folder, "--dangerously-skip-permissions", "--resume", NEWEST]


@pytest.mark.parametrize("args", [("resume", "--no-perms"), ("--no-perms", "resume")])
def test_no_perms_keeps_prompts(workspace: dict, args: tuple[str, ...]) -> None:
    term = run(workspace, *args)
    term.expect("Permission prompts on (--no-perms)")
    term.expect("billing hooks")
    term.send(ENTER)
    assert term.wait() == 0
    assert launched(workspace)[1:] == ["--resume", NEWEST]


def test_menu_with_no_perms_says_prompts_are_on(workspace: dict) -> None:
    term = run(workspace, "--no-perms")
    term.expect("Permission prompts on (--no-perms)")
    term.expect("Resume a session  with permission prompts")
    term.send(ESC)
    assert term.wait() == 0


def test_legacy_skip_permissions_flag_is_accepted(workspace: dict) -> None:
    term = run(workspace, "--skip-permissions", "resume")
    term.expect("billing hooks")
    term.send(ENTER)
    assert term.wait() == 0
    assert launched(workspace)[1] == "--dangerously-skip-permissions"


@pytest.mark.parametrize(
    ("args", "expected"),
    [(("new",), ["--dangerously-skip-permissions"]), (("new", "--no-perms"), [])],
)
def test_new_session(workspace: dict, args: tuple[str, ...], expected: list[str]) -> None:
    assert run(workspace, *args).wait() == 0
    assert launched(workspace) == [str(workspace["folder"]), *expected]


def test_escape_from_menu_exits_cleanly(workspace: dict) -> None:
    term = run(workspace)
    term.expect("Resume a session")
    term.send(ESC)
    assert term.wait() == 0
    assert not workspace["log"].exists()


def test_rename_with_suggestion_then_resume_from_list(workspace: dict) -> None:
    term = run(workspace, "rename")
    term.expect("(unnamed)")  # untitled sessions are listed first
    term.send(ENTER)
    term.expect("uploader retries")
    term.send(ENTER)
    term.expect("Enter to accept")
    term.send(ENTER)
    term.expect("Renamed to uploader retries")
    term.expect("uploader retries")  # back in the list with the new title
    term.send(CTRL_O)  # resume the highlighted session
    assert term.wait() == 0
    assert launched(workspace)[-1] == NEWEST

    project = workspace["project"]
    assert json.loads((project / NEWEST / "custom-title.json").read_text()) == {
        "customTitle": "uploader retries"
    }
    last = (project / f"{NEWEST}.jsonl").read_text().splitlines()[-1]
    assert json.loads(last)["type"] == "custom-title"
    events = [json.loads(line) for line in paths.stats_file().read_text().splitlines()]
    assert [e["kind"] for e in events] == ["model", "rename"]


def test_rename_with_typed_title_from_resume_list(workspace: dict) -> None:
    term = run(workspace, "resume")
    term.expect("billing hooks")
    term.send(CTRL_R)
    term.expect("Enter a title")
    term.send("Enter a title")  # filter the options down to this one
    term.expect("1/7")  # fzf's match counter: the filter has been applied
    term.send(ENTER)
    term.expect("Title:")
    term.send("my own title\r")
    term.expect("Renamed to my own title")
    term.send(ESC)
    assert term.wait() == 0
    title = json.loads((workspace["project"] / NEWEST / "custom-title.json").read_text())
    assert title == {"customTitle": "my own title"}


def test_cancelling_a_rename_changes_nothing(workspace: dict) -> None:
    term = run(workspace, "rename")
    term.expect("(unnamed)")
    term.send(ENTER)
    term.expect("Cancel")
    term.send(ESC)
    term.expect("(unnamed)")
    term.send(ESC)
    assert term.wait() == 0
    assert not (workspace["project"] / NEWEST / "custom-title.json").exists()
