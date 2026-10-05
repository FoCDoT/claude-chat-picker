from __future__ import annotations

import pytest
from conftest import SESSION_ID, user, write_transcript

from waymark import cli, paths, stats


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert capsys.readouterr().out.startswith("waymark ")


def test_context_permission_flag(tmp_path) -> None:
    assert cli.Context(tmp_path, skip_permissions=False).claude_command("--resume", "x") == [
        "claude",
        "--resume",
        "x",
    ]
    assert cli.Context(tmp_path, skip_permissions=True).claude_command()[1] == (
        "--dangerously-skip-permissions"
    )


def test_global_options_work_before_and_after_the_command() -> None:
    parser = cli.build_parser()
    assert parser.parse_args(["--no-perms", "resume"]).no_perms
    assert parser.parse_args(["resume", "--no-perms"]).no_perms
    assert not hasattr(parser.parse_args(["resume"]), "no_perms")


def test_permissions_are_skipped_unless_no_perms(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = []
    monkeypatch.setattr(cli, "cmd_new", lambda ctx: seen.append(ctx.skip_permissions) or 0)
    cli.main(["new"])
    cli.main(["new", "--no-perms"])
    assert seen == [True, False]


def test_preview_rejects_paths_outside_projects(tmp_path) -> None:
    assert cli.main(["_preview", str(tmp_path), SESSION_ID]) == 1


def test_preview_prints_session(capsys: pytest.CaptureFixture[str]) -> None:
    project = paths.project_dir("/work/app")
    write_transcript(project, SESSION_ID, [user("add retries to the uploader")])
    assert cli.main(["_preview", str(project), SESSION_ID]) == 0
    assert "add retries to the uploader" in capsys.readouterr().out


def test_stats_report(capsys: pytest.CaptureFixture[str]) -> None:
    stats.record("model", model="m", session=SESSION_ID, **{"in": 100, "out": 10})
    stats.record("rename", session=SESSION_ID, folder="/work/app", title="t", how="suggested")
    assert cli.main(["stats"]) == 0
    out = capsys.readouterr().out
    assert "1 requests" in out and "Renames: 1" in out
    assert paths.stats_file().stat().st_mode & 0o777 == 0o600
