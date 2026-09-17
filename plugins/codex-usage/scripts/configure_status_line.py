#!/usr/bin/env python3
"""Configure Codex's native live usage status line without a TOML dependency."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Sequence


ITEMS = (
    "permissions",
    "context-remaining",
    "context-window-size",
    "five-hour-limit",
    "weekly-limit",
)
DESIRED_VALUE = "[" + ", ".join(json.dumps(item) for item in ITEMS) + "]"
DESIRED_LINE = f"status_line = {DESIRED_VALUE}"
TABLE_RE = re.compile(r"^\s*\[([^\[\]]+)\]\s*(?:#.*)?(?:\r?\n)?$")
KEY_RE = re.compile(r"^\s*status_line\s*=")
ROOT_KEY_RE = re.compile(r"^\s*tui\.status_line\s*=")
INLINE_TUI_RE = re.compile(r"^\s*tui\s*=")


class ConfigConflict(RuntimeError):
    """Raised when removing or reinstalling would overwrite a later user edit."""


def default_config_path() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    root = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return root / "config.toml"


def _newline_for(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _table_bounds(lines: Sequence[str], table: str) -> tuple[int | None, int | None]:
    start = None
    for index, line in enumerate(lines):
        match = TABLE_RE.match(line)
        if not match:
            continue
        if start is None and match.group(1).strip() == table:
            start = index
            continue
        if start is not None:
            return start, index
    return (start, len(lines) if start is not None else None)


def _array_value_end(lines: Sequence[str], start: int, limit: int) -> int:
    """Return the exclusive end of a possibly multiline array assignment."""
    depth = 0
    saw_array = False
    in_string = False
    escaped = False

    for index in range(start, limit):
        line = lines[index]
        in_comment = False
        for char in line:
            if in_comment:
                continue
            if escaped:
                escaped = False
                continue
            if in_string and char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string and char == "#":
                in_comment = True
                continue
            if not in_string and char == "[":
                saw_array = True
                depth += 1
            elif not in_string and char == "]" and saw_array:
                depth -= 1
        if not saw_array or depth <= 0:
            return index + 1
    return limit


def _status_line_bounds(lines: Sequence[str], section_start: int, section_end: int) -> tuple[int, int] | None:
    for index in range(section_start + 1, section_end):
        if KEY_RE.match(lines[index]):
            return index, _array_value_end(lines, index, section_end)
    return None


def _root_status_line_bounds(lines: Sequence[str]) -> tuple[int, int] | None:
    """Find a root-level `tui.status_line` dotted key before the first table."""
    for index, line in enumerate(lines):
        if TABLE_RE.match(line):
            return None
        if ROOT_KEY_RE.match(line):
            return index, _array_value_end(lines, index, len(lines))
    return None


def _has_root_inline_tui(lines: Sequence[str]) -> bool:
    for line in lines:
        if TABLE_RE.match(line):
            return False
        if INLINE_TUI_RE.match(line):
            return True
    return False


def _normalized(segment: Sequence[str]) -> str:
    return "".join(segment).replace("\r", "").strip()


def _desired_segment(newline: str) -> list[str]:
    return [DESIRED_LINE + newline]


def render_install(text: str) -> tuple[str, dict[str, object], bool]:
    newline = _newline_for(text)
    lines = text.splitlines(keepends=True)
    tui_start, tui_end = _table_bounds(lines, "tui")
    root_bounds = _root_status_line_bounds(lines)
    prior: list[str] | None = None
    installed_line = DESIRED_LINE

    if root_bounds:
        value_start, value_end = root_bounds
        prior = list(lines[value_start:value_end])
        installed_line = "tui." + DESIRED_LINE
        if _normalized(prior) == installed_line:
            return text, {}, False
        lines[value_start:value_end] = [installed_line + newline]
    elif tui_start is not None and tui_end is not None:
        bounds = _status_line_bounds(lines, tui_start, tui_end)
        if bounds:
            value_start, value_end = bounds
            prior = list(lines[value_start:value_end])
            if _normalized(prior) == DESIRED_LINE:
                return text, {}, False
            lines[value_start:value_end] = _desired_segment(newline)
        else:
            insert_at = tui_end
            lines[insert_at:insert_at] = _desired_segment(newline)
    else:
        if _has_root_inline_tui(lines):
            raise ConfigConflict(
                "The config uses a root-level inline `tui = {...}` table. Convert it to a "
                "[tui] table before installing Codex Usage."
            )
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += newline
        if lines and lines[-1].strip():
            lines.append(newline)
        lines.extend([f"[tui]{newline}", *_desired_segment(newline)])

    state: dict[str, object] = {
        "schema_version": 1,
        "installed_status_line": installed_line,
        "previous_status_line": prior,
        "had_tui_section": tui_start is not None,
    }
    return "".join(lines), state, True


def render_remove(text: str, state: dict[str, object] | None, force: bool) -> tuple[str, bool]:
    newline = _newline_for(text)
    lines = text.splitlines(keepends=True)
    tui_start, tui_end = _table_bounds(lines, "tui")
    root_bounds = _root_status_line_bounds(lines)
    bounds = root_bounds
    if bounds is None and tui_start is not None and tui_end is not None:
        bounds = _status_line_bounds(lines, tui_start, tui_end)
    if not bounds:
        return text, False
    value_start, value_end = bounds
    current = _normalized(lines[value_start:value_end])
    default_installed = "tui." + DESIRED_LINE if root_bounds else DESIRED_LINE
    installed = str((state or {}).get("installed_status_line", default_installed))
    if current != installed and not force:
        raise ConfigConflict(
            "tui.status_line changed after Codex Usage setup; refusing to overwrite it. "
            "Re-run with --force only if that change may be discarded."
        )

    previous = (state or {}).get("previous_status_line")
    if isinstance(previous, list) and all(isinstance(line, str) for line in previous):
        replacement = list(previous)
    else:
        replacement = []
    lines[value_start:value_end] = replacement

    if root_bounds is None and not bool((state or {}).get("had_tui_section", True)):
        tui_start, tui_end = _table_bounds(lines, "tui")
        if tui_start is not None and tui_end is not None:
            body = lines[tui_start + 1 : tui_end]
            if not any(line.strip() and not line.lstrip().startswith("#") for line in body):
                remove_start = tui_start
                if remove_start > 0 and not lines[remove_start - 1].strip():
                    remove_start -= 1
                del lines[remove_start:tui_end]

    result = "".join(lines)
    if result and not result.endswith(("\n", "\r")):
        result += newline
    return result, result != text


def _paths(config: Path) -> tuple[Path, Path]:
    return (
        config.with_name(config.name + ".codex-usage.bak"),
        config.with_name(config.name + ".codex-usage-state.json"),
    )


def _atomic_write(path: Path, content: str, *, bom: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoding = "utf-8-sig" if bom else "utf-8"
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding=encoding,
        newline="",
        dir=path.parent,
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(content)
        if path.exists():
            shutil.copymode(path, temp_path)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _read(path: Path) -> tuple[str, bool]:
    if not path.exists():
        return "", False
    data = path.read_bytes()
    bom = data.startswith(b"\xef\xbb\xbf")
    return data.decode("utf-8-sig"), bom


def configure(config: Path, *, remove: bool, force: bool, check: bool) -> int:
    backup_path, state_path = _paths(config)
    text, bom = _read(config)
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else None

    if check:
        lines = text.splitlines(keepends=True)
        tui_start, tui_end = _table_bounds(lines, "tui")
        root_bounds = _root_status_line_bounds(lines)
        configured = bool(
            root_bounds
            and _normalized(lines[root_bounds[0] : root_bounds[1]]) == "tui." + DESIRED_LINE
        )
        if tui_start is not None and tui_end is not None:
            bounds = _status_line_bounds(lines, tui_start, tui_end)
            configured = configured or bool(
                bounds and _normalized(lines[bounds[0] : bounds[1]]) == DESIRED_LINE
            )
        print(f"{'configured' if configured else 'not configured'}: {config}")
        return 0 if configured else 1

    if remove:
        updated, changed = render_remove(text, state, force)
        if changed:
            _atomic_write(config, updated, bom=bom)
        if state_path.exists() and (changed or DESIRED_LINE not in text):
            state_path.unlink()
        print(f"{'restored' if changed else 'unchanged'}: {config}")
        return 0

    if state and not force:
        installed = str(state.get("installed_status_line", DESIRED_LINE))
        if installed not in text:
            raise ConfigConflict(
                "A Codex Usage state file exists but tui.status_line no longer matches the installed "
                "value. Re-run with --force only if the current value may be replaced."
            )

    updated, new_state, changed = render_install(text)
    if not changed:
        print(f"already configured: {config}")
        return 0

    config.parent.mkdir(parents=True, exist_ok=True)
    if config.exists() and not backup_path.exists():
        shutil.copy2(config, backup_path)
    if not state:
        new_state["config_path"] = str(config.resolve())
        _atomic_write(state_path, json.dumps(new_state, indent=2) + "\n")
    _atomic_write(config, updated, bom=bom)
    print(f"configured: {config}")
    if backup_path.exists():
        print(f"backup: {backup_path}")
    print("Start a new Codex CLI session to load the footer.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=default_config_path())
    parser.add_argument("--remove", action="store_true", help="Restore the prior status_line")
    parser.add_argument("--check", action="store_true", help="Check whether the footer is configured")
    parser.add_argument("--force", action="store_true", help="Replace a status_line changed after setup")
    args = parser.parse_args(argv)
    if args.remove and args.check:
        parser.error("--remove and --check cannot be used together")
    try:
        return configure(args.config.expanduser(), remove=args.remove, force=args.force, check=args.check)
    except (ConfigConflict, json.JSONDecodeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
