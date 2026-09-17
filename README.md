# Codex Usage

Codex Usage adds a live, compact footer to the Codex CLI using Codex's native status-line data:

```text
Full Access · Context 100% left · 372K window · 5h 94% left · weekly 78% left
```

It does not scrape `/status`, make network requests, or read authentication tokens. Values update with the current Codex session.

## Requirements

- Codex CLI 0.154.0 or later
- Python 3.11 or later for the bundled deterministic setup helper; Codex can make the narrow config edit directly if Python is unavailable

## Install from GitHub

```powershell
codex plugin marketplace add rafik24/codex_usage
codex plugin add codex-usage@personal
```

Start a new Codex session, then ask:

```text
Use $codex-usage to configure my live Codex CLI usage footer.
```

Restart the Codex CLI once more to load the new footer.

## What it configures

The setup skill safely adds or updates this value in `$CODEX_HOME/config.toml` (or `~/.codex/config.toml`):

```toml
[tui]
status_line = ["permissions", "context-remaining", "context-window-size", "five-hour-limit", "weekly-limit"]
```

The helper preserves unrelated settings, creates `config.toml.codex-usage.bak`, and records only the previous status-line value for a safe removal. It refuses to overwrite a status line modified after setup unless `--force` is explicitly requested.

To inspect or remove the configuration, ask Codex to use `$codex-usage`, or run the bundled helper with `--check` or `--remove`.

## Limitations

- Native footer items show remaining percentages but not reset timestamps. Run `/status` for reset times.
- Rate-limit items appear after Codex receives usage data.
- Codex may truncate later items in a narrow terminal.

## Development

```powershell
python -m unittest discover -s tests -v
```

The repository is also checked with Codex's bundled skill and plugin validators before release.

## License

MIT
