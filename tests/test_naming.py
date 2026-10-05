from __future__ import annotations

import json
import subprocess

import pytest

from waymark import naming, paths
from waymark.transcripts import Summary


def test_load_config_defaults_when_missing() -> None:
    config = naming.load_config()
    assert config.model == naming.DEFAULT_MODEL
    assert config.rules == naming.DEFAULT_RULES


def test_load_config_reads_file() -> None:
    path = paths.config_file()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"model": "m", "default": "BASE", "folders": {"/w": "W"}}))
    config = naming.load_config()
    assert (config.model, config.rules, config.folder_rules) == ("m", "BASE", {"/w": "W"})


def test_rules_for_uses_longest_matching_prefix() -> None:
    config = naming.Config(rules="BASE", folder_rules={"/w": "W", "/w/app/": "APP", "/w/appx": "X"})
    assert naming.rules_for(config, "/w/app/sub") == "BASE\nAPP"
    assert naming.rules_for(config, "/w/app") == "BASE\nAPP"
    assert naming.rules_for(config, "/w/other") == "BASE\nW"
    assert naming.rules_for(config, "/elsewhere") == "BASE"


def test_build_prompt_includes_direction_and_avoid_list() -> None:
    digest = naming.build_digest(
        Summary(cwd="/w", prompts=["fix uploads"], replies=["done"], tools={"Bash": 2})
    )
    assert "- fix uploads" in digest
    assert "Bash×2" in digest
    prompt = naming.build_prompt("RULES", digest, avoid=["old name"], direction="shorter")
    assert "Do not repeat these earlier suggestions: old name" in prompt
    assert "direction for the name" in prompt and "shorter" in prompt


def test_parse_names_strips_markers_quotes_and_duplicates() -> None:
    reply = '1. "uploader retries".\n- cache cleanup\n\n* uploader retries\nfourth\nfifth'
    assert naming.parse_names(reply) == ["uploader retries", "cache cleanup", "fourth"]


def test_parse_names_removes_terminal_escapes() -> None:
    assert naming.parse_names("evil\x1b[31m red‮ name") == ["evil [31m red  name"]


def _fake_run(stdout: str):
    def run(*args, **kwargs):
        assert kwargs["cwd"] != "."
        assert "--tools" in args[0] and "--strict-mcp-config" in args[0]
        return subprocess.CompletedProcess(args[0], 0, stdout=stdout, stderr="")

    return run


def test_suggest_parses_reply_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    reply = {
        "result": "uploader retries\ncache cleanup",
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "total_cost_usd": 0.01,
    }
    monkeypatch.setattr(subprocess, "run", _fake_run(json.dumps(reply)))
    suggestion = naming.suggest(Summary(prompts=["x"]), naming.Config(), folder="/w")
    assert suggestion.names == ["uploader retries", "cache cleanup"]
    assert suggestion.usage["in"] == 10 and suggestion.cost_usd == 0.01


def test_suggest_raises_on_error_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", _fake_run(json.dumps({"is_error": True, "result": "x"})))
    with pytest.raises(naming.NamingError):
        naming.suggest(Summary(prompts=["x"]), naming.Config(), folder="/w")
