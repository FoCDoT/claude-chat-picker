# claude-chat-picker

Find, resume and name your Claude Code chats.

Unnamed chats are hard to find again in `claude --resume`. This repo has two small tools that fix that:

- **`claude-chat-picker`**: a terminal picker (Python + fzf). It lists the current folder's chats with a preview and lets you resume one or rename it. Claude Sonnet suggests the names.
- **`chat-name-nudge`**: a Claude Code mod. While a chat has no name, a line above the prompt suggests one. Pressing **use** fills in `/rename <name>` for you to confirm. **It never renames a chat by itself.**

Both write names the same way `/rename` does, so the names show up in `claude --resume` and everywhere else.

## Requirements

- [Claude Code](https://claude.com/claude-code), logged in. Suggestions run through `claude -p` (the picker) or the mod API (the nudge). On a Pro/Max subscription they count toward your usage limits.
- Python 3.8+ and [fzf](https://github.com/junegunn/fzf) for the picker (`brew install fzf`)

## Install

```sh
git clone https://github.com/FoCDoT/claude-chat-picker
cd claude-chat-picker

# the picker
ln -s "$PWD/bin/claude-chat-picker" ~/.local/bin/claude-chat-picker   # any dir on your PATH

# optional: your naming conventions (both tools read this)
cp examples/chat-naming.json ~/.claude/chat-naming.json
```

The mod, from inside Claude Code:

```
/plugin marketplace add FoCDoT/claude-chat-picker
/plugin install chat-name-nudge@claude-chat-picker
```

## Uninstall

```sh
rm ~/.local/bin/claude-chat-picker
rm -rf ~/.cache/claude-chat-picker ~/.claude/chat-naming-stats.jsonl   # optional: cache and stats
```

```
/plugin uninstall chat-name-nudge@claude-chat-picker
/plugin marketplace remove claude-chat-picker
```

Names you already gave chats stay; they are ordinary `/rename` names.

## Picker usage

```
claude-chat-picker              pick a chat here; resume with --dangerously-skip-permissions
claude-chat-picker --no-perms   resume without --dangerously-skip-permissions
claude-chat-picker --dir PATH   use another folder's chats
claude-chat-picker --new        start a new chat here
claude-chat-picker --stats      tokens used and chats renamed (picker + mod)
```

> **Note:** by default the picker resumes chats with `--dangerously-skip-permissions`. Use `--no-perms` (or a shell alias) if you don't want that.

- **Resume**: Enter resumes the chat, Ctrl-R renames it, Esc goes back.
- **Rename**: unnamed chats are listed first. Enter asks Sonnet for three names. You can then:
  - pick one (and edit it before saving),
  - ask for different names,
  - give a direction (for example "mention the client" or "shorter"),
  - or type your own name.

  After renaming, you go back to the list, so you can rename several chats in a row. Ctrl-O opens a chat instead.

## Mod usage

- When a chat has no name, the line `✎ unnamed chat · try <name>` appears above the prompt. Its buttons are **use**, **next**, **more** and **dismiss**.
- The suggestion is updated after turns 1, 4, 10 and 25, because chats drift from their first topic.
- `/name-suggest` asks for a new suggestion straight away.
- Once the chat is named (by `/rename` or `--name`), the line goes away.

## Naming conventions

`~/.claude/chat-naming.json` has a `default` rule and optional per-`folders` rules. Folder keys are path prefixes. The longest match is added to the default. See [`examples/chat-naming.json`](examples/chat-naming.json).

## Files it touches

| Path | What |
|---|---|
| `~/.claude/projects/<folder>/<id>.jsonl` | appends a `custom-title` row on rename (same as `/rename`) |
| `~/.claude/projects/<folder>/<id>/custom-title.json` | the chat's name (same as `/rename`) |
| `~/.claude/chat-naming.json` | your conventions (read only) |
| `~/.claude/chat-naming-stats.jsonl` | one row per suggestion call and rename, mode 0600 |
| `~/.cache/claude-chat-picker/` | cached transcript digests, mode 0600 |

## Security

Transcripts and model output are treated as untrusted. Control characters, escape sequences and bidi overrides are stripped before any text is shown or saved. Suggestions run with no tools, no MCP servers and no saved session, from an empty temp folder.

## License

MIT
