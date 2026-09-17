---
name: codex-usage
description: Configure, inspect, or remove the native Codex CLI usage footer showing permissions, context remaining, context-window size, and five-hour and weekly limits. Use when the user asks to enable, repair, check, or remove this live status line; do not use for API billing analysis or unrelated terminal customization.
---

# Codex Usage

Configure Codex's built-in TUI status items. Do not scrape `/status` or copy values into static text; the native items update from the current session state.

## Configure

1. Locate the plugin root two directories above this skill and use `scripts/configure_status_line.py` from that root.
2. Run it with `python` on Windows or `python3` on macOS/Linux. The script resolves `$CODEX_HOME/config.toml`, falling back to `~/.codex/config.toml`. Pass `--config PATH` only when the user names a different config.
3. Report the changed config path and backup path. Tell the user to start a new Codex CLI session so the footer is loaded.

The configured native items, in order, are:

```toml
[tui]
status_line = ["permissions", "context-remaining", "context-window-size", "five-hour-limit", "weekly-limit"]
```

The script is idempotent. It preserves unrelated config, records the previous `status_line` value, and refuses to overwrite a later user modification unless the user explicitly authorizes `--force`.

If Python is unavailable, make the same narrow edit directly: preserve all unrelated keys, back up the config first, and never create a second `[tui]` table or duplicate `status_line` key.

## Inspect

Run the script with `--check`. Treat exit code 0 as configured and exit code 1 as not configured. Rate-limit items may be absent from the rendered footer until Codex receives usage data, and narrow terminals may truncate later items.

## Remove

Run the script with `--remove`. It restores the prior `status_line` captured during setup without rolling back other config changes. If the current value was changed after setup, stop and explain the conflict; use `--force` only after explicit user authorization.

The native status line shows remaining percentages, not reset timestamps. Keep `/status` as the detailed view for reset times.
