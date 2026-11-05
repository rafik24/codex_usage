#!/usr/bin/env python3
"""Install, check or remove the Claude Code usage status line in ~/.claude/settings.json.

install: copies statusline.py to ~/.claude/claude-usage/statusline.py (so the repo can move) and points
         settings.json "statusLine" at it. Backs settings.json up once to settings.json.claude-usage.bak and
         records the previous statusLine for --remove. Refuses to replace a different statusLine unless --force.
--check: reports whether it is installed.
--remove: restores the recorded previous statusLine (or deletes the key if there was none). Refuses if the
         statusLine was changed after install, unless --force.
CLAUDE_CONFIG_DIR overrides ~/.claude.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARK = "claude-usage/statusline.py"


def config_dir() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else Path.home() / ".claude"


def desired(root: Path) -> dict:
    py = "python" if os.name == "nt" else "python3"
    return {"type": "command", "command": f'{py} "{(root / MARK).as_posix()}"', "padding": 0}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def is_ours(status_line: object) -> bool:
    return isinstance(status_line, dict) and MARK in str(status_line.get("command", ""))


def install(root: Path, force: bool = False) -> str:
    settings_path, state_path = root / "settings.json", root / "claude-usage" / "previous.json"
    settings = _load(settings_path)
    current = settings.get("statusLine")
    if current is not None and not is_ours(current) and not force:
        raise SystemExit(f"a different statusLine is configured ({current.get('command') if isinstance(current, dict) else current!r}); "
                         "re-run with --force to replace it (it is saved for --remove)")
    (root / "claude-usage").mkdir(parents=True, exist_ok=True)
    shutil.copy2(HERE / "statusline.py", root / MARK)
    if not is_ours(current):
        _write_json(state_path, {"previous": current})
        backup = settings_path.with_name("settings.json.claude-usage.bak")
        if settings_path.exists() and not backup.exists():
            shutil.copy2(settings_path, backup)
    settings["statusLine"] = desired(root)
    _write_json(settings_path, settings)
    return f"installed: {settings['statusLine']['command']}"


def check(root: Path) -> str:
    current = _load(root / "settings.json").get("statusLine")
    if is_ours(current) and (root / MARK).exists():
        return "installed"
    return f"not installed (statusLine = {json.dumps(current)})"


def remove(root: Path, force: bool = False) -> str:
    settings_path, state_path = root / "settings.json", root / "claude-usage" / "previous.json"
    settings = _load(settings_path)
    if not is_ours(settings.get("statusLine")) and not force:
        raise SystemExit("statusLine was changed after install; re-run with --force to remove anyway")
    previous = _load(state_path).get("previous") if state_path.exists() else None
    if previous is None:
        settings.pop("statusLine", None)
    else:
        settings["statusLine"] = previous
    _write_json(settings_path, settings)
    shutil.rmtree(root / "claude-usage", ignore_errors=True)
    return f"removed; statusLine restored to {json.dumps(previous)}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true")
    g.add_argument("--remove", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    root = config_dir()
    print(check(root) if a.check else remove(root, a.force) if a.remove else install(root, a.force))
    return 0


if __name__ == "__main__":
    sys.exit(main())
