# waymark

[![CI](https://github.com/FoCDoT/waymark/actions/workflows/ci.yml/badge.svg)](https://github.com/FoCDoT/waymark/actions/workflows/ci.yml)

Find, resume and name [Claude Code](https://claude.com/claude-code) sessions from the terminal.

Sessions without a title are hard to find again in `claude --resume`. waymark has two parts:

- **`waymark`**, a command-line picker. It lists the sessions for the current folder with a preview. You can resume a session, or give it a title suggested by Claude from what the session covered.
- **`waymark-nudge`**, a Claude Code mod. It shows a suggested title above the prompt while a session has none. Choosing it fills in `/rename <title>` for you to confirm. It never renames a session on its own.

Titles are written exactly as `/rename` writes them, so they appear everywhere Claude Code shows session names.

## Requirements

- Claude Code, signed in. Suggestions are made with `claude -p` and count toward your plan's usage.
- Python 3.9 or later
- [fzf](https://github.com/junegunn/fzf)

## Installation

```sh
uv tool install git+https://github.com/FoCDoT/waymark
# or: pipx install git+https://github.com/FoCDoT/waymark
```

To install the mod, run these inside Claude Code:

```
/plugin marketplace add FoCDoT/waymark
/plugin install waymark-nudge@waymark
```

## Usage

```
waymark                      menu: resume or rename
waymark resume               pick a session to resume
waymark rename               pick sessions to rename, untitled first
waymark new                  start a new session in this folder
waymark suggest SESSION_ID   print suggested titles without changing anything
waymark stats                suggestion usage and recent renames
```

| Option | Effect |
|---|---|
| `-C`, `--dir PATH` | Use the sessions of another folder. |
| `--skip-permissions` | Pass `--dangerously-skip-permissions` to `claude` when resuming or starting a session. |

In a session list, `enter` performs the list's action, `ctrl-r` renames, `ctrl-o` resumes and `esc` goes back. When you rename, you can:

- accept a suggestion, editing it first if you like,
- ask for more suggestions,
- give a direction such as "name the client",
- or type your own title.

After a rename you return to the list, so you can title several sessions in a row.

If you always run with `--skip-permissions`, add an alias:

```sh
alias waymark='waymark --skip-permissions'
```

### The mod

While a session has no title, the mod shows `Unnamed session · suggested title …` above the prompt, with `use`, `next`, `more` and `dismiss` actions. It refreshes the suggestion after turns 1, 4, 10 and 25 because sessions drift from their first topic. Run `/name-suggest` for a new suggestion at any time. The line disappears once the session has a title.

## Configuration

`~/.config/waymark/config.json` (or under `$XDG_CONFIG_HOME`) is read by both the CLI and the mod:

```json
{
  "model": "claude-sonnet-5-5",
  "default": "3-7 words, lowercase, no trailing period. Describe what the session is about.",
  "folders": {
    "/Users/you/code/my-app": "Start with the area ('api', 'ui', 'billing'), then the task."
  }
}
```

`default` is the naming rule for every session. The `folders` keys are path prefixes. The rule of the longest matching prefix is added to `default`. Every key is optional. See [`examples/config.json`](examples/config.json).

## Files

| Path | Purpose |
|---|---|
| `~/.claude/projects/<folder>/<id>.jsonl` | A `custom-title` record is appended on rename, as `/rename` does. |
| `~/.claude/projects/<folder>/<id>/custom-title.json` | The session title, as `/rename` writes it. |
| `~/.config/waymark/config.json` | Naming rules and model. Read only. |
| `~/.local/state/waymark/stats.jsonl` | One line per suggestion request and rename. Mode 0600. |
| `~/.cache/waymark/` | Cached transcript summaries. Mode 0600. |

`CLAUDE_CONFIG_DIR` and the XDG variables are respected.

## Security

Transcript text and model output are treated as untrusted. Control characters, escape sequences, zero-width characters and bidi overrides are removed before anything is displayed or saved. Suggestion requests run with no tools, no MCP servers and no saved session, from an empty temporary directory, so the model sees only a digest of the session.

## Development

```sh
uv run --with pytest --with-editable . pytest   # Python tests
ruff check . && ruff format --check .          # lint
claude plugin test waymark-nudge                # mod tests
claude plugin validate ./waymark-nudge          # mod manifest and hooks
```

## Uninstall

```sh
uv tool uninstall waymark
rm -rf ~/.config/waymark ~/.local/state/waymark ~/.cache/waymark
```

```
/plugin uninstall waymark-nudge@waymark
/plugin marketplace remove waymark
```

Titles you have set stay, since they are ordinary `/rename` titles.

## License

[MIT](LICENSE)
