# Changelog

## 0.3.0

Renamed from `claude-chat-picker` to **waymark**.

- Installable package (`uv tool install` / `pipx install`) with a `waymark` command.
- Subcommands: `resume`, `rename`, `new`, `suggest`, `stats`.
- Resuming no longer skips permission prompts by default; pass `--skip-permissions`.
- Config moved to `~/.config/waymark/config.json`, with a `model` setting.
- Usage log moved to `~/.local/state/waymark/stats.jsonl`; cache to `~/.cache/waymark/`.
- The mod is now `waymark-nudge` and reads the same config.
- Test suite and CI.

## 0.2.0

- First public release as `claude-chat-picker` and `chat-name-nudge`.
