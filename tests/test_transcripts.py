from __future__ import annotations

import json

import pytest
from conftest import SESSION_ID, assistant, user, write_transcript

from waymark import paths, transcripts


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (user("fix the login bug"), "fix the login bug"),
        (user("<command-name>/review</command-name><command-args>42</command-args>"), "/review 42"),
        (user("<bash-stdout>ok</bash-stdout>"), None),
        (user("<system-reminder>x</system-reminder>"), None),
        (user('[Image #1] <pasted_content id="a">trace</pasted_content>'), "trace"),
        (user("hello", isMeta=True), None),
        (user("hello", isSidechain=True), None),
        ({"type": "user", "message": {"content": [{"type": "tool_result"}]}}, None),
        ({"type": "user", "message": {"content": [{"type": "text", "text": "hi"}]}}, "hi"),
    ],
)
def test_extract_prompt(record: dict, expected: str | None) -> None:
    assert transcripts.extract_prompt(record) == expected


def test_summarize_collects_prompts_replies_and_tools(tmp_path) -> None:
    path = write_transcript(
        tmp_path,
        SESSION_ID,
        [
            {"type": "summary", "cwd": "/work/app"},
            user("add retries to the uploader", cwd="/work/app"),
            assistant("Added exponential backoff.", tools=("Edit", "Edit", "Bash")),
            {"type": "ai-title", "aiTitle": "Uploader changes"},
        ],
    )
    with path.open("a") as handle:
        handle.write('{"type":"user", truncated\n')  # a partial line is skipped

    summary = transcripts.summarize(path)

    assert summary.cwd == "/work/app"
    assert summary.prompts == ["add retries to the uploader"]
    assert summary.replies == ["Added exponential backoff."]
    assert summary.tools == {"Edit": 2, "Bash": 1}
    assert summary.ai_title == "Uploader changes"


def test_summarize_keeps_start_and_end_of_long_sessions(tmp_path) -> None:
    path = write_transcript(tmp_path, SESSION_ID, [user(f"prompt {i}") for i in range(40)])
    prompts = transcripts.summarize(path).prompts
    assert prompts[:12] == [f"prompt {i}" for i in range(12)]
    assert prompts[12:] == [f"prompt {i}" for i in range(32, 40)]


def test_write_title_matches_rename_and_is_read_back() -> None:
    project = paths.project_dir("/work/app")
    write_transcript(project, SESSION_ID, [user("add retries")])

    title = transcripts.write_title(project, SESSION_ID, "  uploader\nretries \x1b[31m ")

    assert title == "uploader retries [31m"
    last = (project / f"{SESSION_ID}.jsonl").read_text().splitlines()[-1]
    assert json.loads(last) == {
        "type": "custom-title",
        "customTitle": title,
        "sessionId": SESSION_ID,
    }
    assert transcripts.read_title(project, SESSION_ID) == title
    [session] = transcripts.load_sessions(project)
    assert session.title == title


@pytest.mark.parametrize("bad_id", ["../etc/passwd", "not-a-session", ""])
def test_write_title_rejects_invalid_session_ids(tmp_path, bad_id: str) -> None:
    with pytest.raises(ValueError):
        transcripts.write_title(tmp_path, bad_id, "title")


def test_load_sessions_skips_empty_sessions_and_uses_cache(tmp_path) -> None:
    project = paths.project_dir("/work/app")
    write_transcript(project, SESSION_ID, [user("first prompt")])
    write_transcript(project, "11111111-2222-4333-8444-555555555555", [assistant("no prompt")])

    first = transcripts.load_sessions(project)
    second = transcripts.load_sessions(project)

    assert [s.id for s in first] == [SESSION_ID]
    assert second[0].summary == first[0].summary
    assert (paths.cache_dir() / f"{project.name}.json").stat().st_mode & 0o777 == 0o600
