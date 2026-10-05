# Changelog

## 0.3.4

- The menu has a **New session** row, and also opens in a folder with no sessions yet.
- `waymark --new` starts a new session, like `waymark new`.

## 0.3.3

- Fix: the picker was invisible with fzf older than 0.53 (such as Ubuntu 24.04's), which draws its interface on stderr; waymark no longer captures stderr.

## 0.3.2

- The menu and session lists say whether permission prompts are skipped and how to change it.
- `--skip-permissions` from 0.3.0 is accepted again (it is the default) so existing aliases keep working.
- End-to-end tests drive the real fzf in a pseudo-terminal; CI installs fzf and also runs on macOS.

## 0.3.1

- Skipping permission prompts is the default again; `--no-perms` keeps them.

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
