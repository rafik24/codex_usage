#!/usr/bin/env python3
"""Claude Code status line: live context and usage limits, the Claude twin of the Codex footer.

Claude Code pipes a JSON payload to the status-line command on every refresh. This prints one line from it:

    Opus 5.5 · high · Context 79% left · 1M window · 5h 97% left (14:30) · weekly 97% left (Sat 09:00)

No network, no files written, no tokens read: only the stdin payload. Missing fields are skipped, so it
degrades cleanly on older Claude Code versions. Set NO_COLOR=1 to disable colour.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Any

SEP = " · "
GREEN, YELLOW, RED, DIM, RESET = "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[0m"


def _color(enabled: bool, code: str, text: str) -> str:
    return f"{code}{text}{RESET}" if enabled else text


def _level(left: float) -> str:
    return GREEN if left > 50 else YELLOW if left > 20 else RED


def _window(tokens: Any) -> str | None:
    if not isinstance(tokens, (int, float)) or tokens <= 0:
        return None
    if tokens >= 1_000_000:
        v = tokens / 1_000_000
        return f"{v:g}M window" if v == int(v) else f"{v:.1f}M window"
    return f"{round(tokens / 1000)}K window"


def _reset(ts: Any, now: datetime) -> str | None:
    if not isinstance(ts, (int, float)) or ts <= 0:
        return None
    when = datetime.fromtimestamp(ts)
    return when.strftime("%H:%M") if when.date() == now.date() else when.strftime("%a %H:%M")


def _limit(label: str, data: Any, now: datetime, color: bool) -> str | None:
    if not isinstance(data, dict) or not isinstance(data.get("used_percentage"), (int, float)):
        return None
    left = max(0, 100 - round(data["used_percentage"]))
    text = _color(color, _level(left), f"{label} {left}% left")
    reset = _reset(data.get("resets_at"), now)
    return f"{text}{_color(color, DIM, f' ({reset})')}" if reset else text


def render(payload: dict[str, Any], now: datetime | None = None, color: bool = True) -> str:
    now = now or datetime.now()
    parts: list[str] = []

    model = (payload.get("model") or {}).get("display_name")
    if model:
        parts.append(str(model))
    effort = (payload.get("effort") or {}).get("level")
    if effort:
        parts.append(str(effort))

    ctx = payload.get("context_window") or {}
    left = ctx.get("remaining_percentage")
    if not isinstance(left, (int, float)) and isinstance(ctx.get("used_percentage"), (int, float)):
        left = 100 - ctx["used_percentage"]
    if isinstance(left, (int, float)):
        left = max(0, round(left))
        parts.append(_color(color, _level(left), f"Context {left}% left"))
    window = _window(ctx.get("context_window_size"))
    if window:
        parts.append(window)

    limits = payload.get("rate_limits") or {}
    for label, key in (("5h", "five_hour"), ("weekly", "seven_day")):
        item = _limit(label, limits.get(key), now, color)
        if item:
            parts.append(item)

    return SEP.join(parts)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    color = not os.environ.get("NO_COLOR")
    print(render(payload, color=color))
    return 0


if __name__ == "__main__":
    sys.exit(main())
