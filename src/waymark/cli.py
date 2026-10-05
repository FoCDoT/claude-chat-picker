"""Command-line interface."""

from __future__ import annotations

import argparse
import os
import shlex
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from . import __version__, naming, paths, picker, stats, transcripts
from .picker import BOLD, DIM, RESET
from .text import human_size, one_line, relative_time
from .transcripts import Session

RECENTLY_ACTIVE_SECONDS = 120


class Context:
    def __init__(self, folder: Path, skip_permissions: bool) -> None:
        self.folder = folder
        self.project = paths.project_dir(folder)
        self.skip_permissions = skip_permissions
        self.config = naming.load_config()

    def sessions(self) -> list[Session]:
        if not self.project.is_dir():
            return []
        return transcripts.load_sessions(self.project)

    @property
    def permission_mode(self) -> str:
        return "skipping permissions" if self.skip_permissions else "with permission prompts"

    @property
    def permission_hint(self) -> str:
        """One header line saying how claude will run and how to change it."""
        if self.skip_permissions:
            return (
                "Runs claude with --dangerously-skip-permissions"
                " · use waymark --no-perms to keep prompts"
            )
        return "Permission prompts on (--no-perms) · run waymark without it to skip them"

    def claude_command(self, *args: str) -> list[str]:
        flags = ["--dangerously-skip-permissions"] if self.skip_permissions else []
        return ["claude", *flags, *args]


# ---------------------------------------------------------------------------- commands


def cmd_menu(ctx: Context) -> int:
    _require_fzf()
    sessions = ctx.sessions()
    while True:
        rows = [("new", f"New session  {DIM}{ctx.permission_mode}{RESET}")]
        if sessions:
            unnamed = sum(1 for s in sessions if not s.title)
            rows[:0] = [
                ("resume", f"Resume a session  {DIM}{ctx.permission_mode}{RESET}"),
                ("rename", f"Rename sessions  {DIM}{unnamed} of {len(sessions)} unnamed{RESET}"),
            ]
        choice = picker.pick(rows, header=f"{ctx.folder}\n{ctx.permission_hint}")
        if choice is None:
            return 0
        if choice.value == "new":
            cmd_new(ctx)
        _browse(ctx, sessions, rename_mode=choice.value == "rename")


def cmd_resume(ctx: Context) -> int:
    _browse(ctx, _require_sessions(ctx), rename_mode=False)
    return 0


def cmd_rename(ctx: Context) -> int:
    _browse(ctx, _require_sessions(ctx), rename_mode=True)
    return 0


def cmd_new(ctx: Context) -> NoReturn:
    _exec_claude(ctx, ctx.claude_command())


def cmd_suggest(ctx: Context, session_id: str, direction: str) -> int:
    session = next((s for s in ctx.sessions() if s.id == session_id), None)
    if session is None:
        print(f"waymark: no session {session_id} in {ctx.folder}", file=sys.stderr)
        return 1
    try:
        suggestion = _request_names(ctx, session, direction=direction)
    except naming.NamingError as error:
        print(f"waymark: {error}", file=sys.stderr)
        return 1
    print("\n".join(suggestion.names))
    return 0 if suggestion.names else 1


def cmd_stats() -> int:
    print(stats.report(stats.read_events()))
    return 0


def cmd_preview(project: str, session_id: str) -> int:
    """Rendered inside fzf's preview pane. Arguments come from fzf, so they are checked."""
    project_path = Path(project).resolve()
    if project_path.parent != paths.projects_dir().resolve():
        return 1
    if not transcripts.SESSION_ID.match(session_id):
        return 1
    session = next((s for s in transcripts.load_sessions(project_path) if s.id == session_id), None)
    if session is None:
        return 1

    summary = session.summary
    print(f"{BOLD}{one_line(session.title or '(unnamed)', 100)}{RESET}   {DIM}{session.id}{RESET}")
    if summary.ai_title and not session.title:
        print(f"{DIM}auto title:{RESET} {one_line(summary.ai_title, 100)}")
    meta = f"{relative_time(session.mtime)} · {human_size(session.size)}"
    print(f"{DIM}{meta} · {len(summary.prompts)} prompts shown{RESET}\n")
    for prompt in summary.prompts[:10]:
        print(f"› {one_line(prompt, 220)}")
    return 0


# ---------------------------------------------------------------------------- flows


def _browse(ctx: Context, sessions: list[Session], *, rename_mode: bool) -> None:
    """List sessions until cancelled. Renaming returns to the list; resuming replaces us."""
    if rename_mode:
        keys = "enter rename · ctrl-o resume · esc back"
    else:
        keys = "enter resume · ctrl-r rename · esc back"
    header = f"{keys}\n{ctx.permission_hint}"

    while True:
        ordered = (
            sorted(sessions, key=lambda s: (bool(s.title), -s.mtime)) if rename_mode else sessions
        )
        choice = picker.pick(
            [(s.id, _row_label(s)) for s in ordered],
            header=header,
            preview=_preview_command(ctx.project),
            expect=("ctrl-r", "ctrl-o"),
        )
        if choice is None:
            return
        session = next(s for s in sessions if s.id == choice.value)
        wants_rename = choice.key != "ctrl-o" if rename_mode else choice.key == "ctrl-r"
        if wants_rename:
            _rename(ctx, session)
        else:
            _exec_claude(ctx, ctx.claude_command("--resume", session.id))


def _rename(ctx: Context, session: Session) -> None:
    print(f"\n{BOLD}Renaming{RESET} {session.title or '(unnamed)'}  {DIM}{session.id}{RESET}")
    if time.time() - session.mtime < RECENTLY_ACTIVE_SECONDS:
        print(
            f"{DIM}This session was active in the last two minutes. If it is open, the new "
            f"title appears there after it is resumed.{RESET}"
        )

    shown: list[str] = []
    direction = ""
    while True:
        print(f"{DIM}Requesting suggestions from {ctx.config.model}…{RESET}", flush=True)
        try:
            names = _request_names(ctx, session, avoid=shown, direction=direction).names
        except naming.NamingError as error:
            print(f"No suggestions: {error}")
            names = []
        shown += names

        hint = f"current: {one_line(direction, 40)}" if direction else "e.g. 'name the client'"
        rows = [(f"use:{name}", f"{BOLD}{name}{RESET}") for name in names]
        rows += [
            ("more", "More suggestions"),
            ("direction", f"Suggest with a direction…  {DIM}{hint}{RESET}"),
            ("type", "Enter a title"),
            ("cancel", "Cancel"),
        ]
        choice = picker.pick(rows, header="Choose a title", prompt="title> ")
        if choice is None or choice.value == "cancel":
            return
        if choice.value == "more":
            continue
        if choice.value == "direction":
            given = input("Direction (Enter keeps the current one): ").strip()
            if given:
                direction, shown = given, []  # a new direction makes earlier names fair game
            continue

        if choice.value == "type":
            title, method = input("Title: ").strip(), "typed"
        else:
            proposed = choice.value.removeprefix("use:")
            typed = input(f"Title [{BOLD}{proposed}{RESET}] (Enter to accept): ").strip()
            title = typed or proposed
            method = "edited" if typed else "suggested"
        if not title:
            return

        session.title = transcripts.write_title(ctx.project, session.id, title)
        stats.record(
            "rename",
            session=session.id,
            folder=session.folder,
            title=session.title,
            how=f"{method}+direction" if direction and method != "typed" else method,
        )
        print(f"Renamed to {BOLD}{session.title}{RESET}")
        return


def _request_names(
    ctx: Context, session: Session, *, avoid: Sequence[str] = (), direction: str = ""
) -> naming.Suggestion:
    suggestion = naming.suggest(
        session.summary,
        ctx.config,
        folder=session.folder or str(ctx.folder),
        avoid=avoid,
        direction=direction,
    )
    stats.record(
        "model",
        model=suggestion.model,
        session=session.id,
        cost_usd=suggestion.cost_usd,
        **suggestion.usage,
    )
    return suggestion


# ---------------------------------------------------------------------------- helpers


def _row_label(session: Session) -> str:
    if session.title:
        name = f"{BOLD}{one_line(session.title, 60)}{RESET}"
    else:
        hint = session.summary.ai_title or session.summary.prompts[0]
        name = f"{DIM}(unnamed){RESET} {one_line(hint, 60)}"
    return f"{name}  {DIM}{relative_time(session.mtime)} · {human_size(session.size)}{RESET}"


def _preview_command(project: Path) -> str:
    # fzf substitutes {1} already quoted; quote our own arguments, as paths can contain spaces.
    parts = [sys.executable, "-m", "waymark", "_preview", str(project)]
    return " ".join(shlex.quote(part) for part in parts) + " {1}"


def _require_fzf() -> None:
    if not picker.available():
        raise SystemExit("waymark: fzf is required (https://github.com/junegunn/fzf)")


def _require_sessions(ctx: Context) -> list[Session]:
    _require_fzf()
    sessions = ctx.sessions()
    if not sessions:
        raise SystemExit(
            f"waymark: no Claude Code sessions for {ctx.folder}; start one with waymark new"
        )
    return sessions


def _exec_claude(ctx: Context, command: list[str]) -> NoReturn:
    print(f"{DIM}$ {shlex.join(command)}{RESET}")
    os.chdir(ctx.folder)  # --resume looks the session up under the current folder's project
    os.execvp(command[0], command)


# ---------------------------------------------------------------------------- entry point


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-C", "--dir", default=argparse.SUPPRESS, metavar="PATH",
        help="folder whose sessions to use (default: current folder)",
    )  # fmt: skip
    common.add_argument(
        "--no-perms", action="store_true", default=argparse.SUPPRESS,
        help="keep permission prompts (by default claude runs with "
        "--dangerously-skip-permissions)",
    )  # fmt: skip
    # Accepted for compatibility with 0.3.0, where skipping was opt-in; it is now the default.
    common.add_argument(
        "--skip-permissions", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS
    )

    parser = argparse.ArgumentParser(
        prog="waymark",
        description="Find, resume and name Claude Code sessions.",
        parents=[common],
    )
    parser.add_argument(
        "--new", action="store_true", help="start a new session (same as waymark new)"
    )
    parser.add_argument("--version", action="version", version=f"waymark {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="{resume,rename,new,suggest,stats}")
    commands.add_parser("resume", parents=[common], help="pick a session to resume")
    commands.add_parser("rename", parents=[common], help="pick sessions to rename")
    commands.add_parser("new", parents=[common], help="start a new session")
    suggest = commands.add_parser(
        "suggest", parents=[common], help="print suggested titles for a session"
    )
    suggest.add_argument("session_id")
    suggest.add_argument("--direction", default="", help="guidance for the suggestions")
    commands.add_parser("stats", help="show suggestion usage and renames")
    preview = commands.add_parser("_preview")
    preview.add_argument("project")
    preview.add_argument("session_id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "_preview":
        return cmd_preview(args.project, args.session_id)
    if args.command == "stats":
        return cmd_stats()

    folder = Path(getattr(args, "dir", None) or os.getcwd()).resolve()
    ctx = Context(folder, skip_permissions=not getattr(args, "no_perms", False))
    try:
        if args.command == "resume":
            return cmd_resume(ctx)
        if args.command == "rename":
            return cmd_rename(ctx)
        if args.command == "new" or args.new:
            return cmd_new(ctx)
        if args.command == "suggest":
            return cmd_suggest(ctx, args.session_id, args.direction)
        return cmd_menu(ctx)
    except KeyboardInterrupt:
        print()
        return 130
