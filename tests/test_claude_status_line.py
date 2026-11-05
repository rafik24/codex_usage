import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1] / "plugins" / "claude-usage"
sys.path.insert(0, str(ROOT))

import configure_claude_status_line as cfg  # noqa: E402
import statusline  # noqa: E402

PAYLOAD = {
    "model": {"display_name": "Opus 5.5"},
    "effort": {"level": "high"},
    "context_window": {"context_window_size": 1_000_000, "used_percentage": 21, "remaining_percentage": 79},
    "rate_limits": {"five_hour": {"used_percentage": 3, "resets_at": datetime(2026, 11, 5, 14, 30).timestamp()},
                    "seven_day": {"used_percentage": 3, "resets_at": datetime(2026, 11, 7, 9, 0).timestamp()}},
}
NOW = datetime(2026, 11, 5, 12, 0)


class RenderTest(unittest.TestCase):
    def test_full_line(self):
        self.assertEqual(statusline.render(PAYLOAD, NOW, color=False),
                         "Opus 5.5 · high · Context 79% left · 1M window · 5h 97% left (14:30) · weekly 97% left (Sat 09:00)")

    def test_missing_fields_are_skipped(self):
        self.assertEqual(statusline.render({"model": {"display_name": "Sonnet"}}, NOW, color=False), "Sonnet")
        self.assertEqual(statusline.render({}, NOW, color=False), "")

    def test_used_only_and_k_window(self):
        p = {"context_window": {"context_window_size": 200_000, "used_percentage": 85}}
        self.assertEqual(statusline.render(p, NOW, color=False), "Context 15% left · 200K window")

    def test_colour_thresholds(self):
        p = {"context_window": {"remaining_percentage": 10}}
        self.assertIn(statusline.RED, statusline.render(p, NOW, color=True))

    def test_script_reads_stdin(self):
        out = subprocess.run([sys.executable, str(ROOT / "statusline.py")], input="not json", text=True,
                             capture_output=True, env={**os.environ, "NO_COLOR": "1"}, check=True)
        self.assertEqual(out.stdout.strip(), "")


class ConfigureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.settings = self.root / "settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data):
        self.settings.write_text(json.dumps(data))

    def read(self):
        return json.loads(self.settings.read_text())

    def test_install_fresh_and_remove(self):
        self.write({"theme": "dark"})
        cfg.install(self.root)
        self.assertTrue(cfg.is_ours(self.read()["statusLine"]))
        self.assertTrue((self.root / cfg.MARK).exists())
        self.assertEqual(cfg.check(self.root), "installed")
        cfg.remove(self.root)
        self.assertEqual(self.read(), {"theme": "dark"})

    def test_refuses_foreign_statusline_without_force(self):
        other = {"type": "command", "command": "node other.mjs"}
        self.write({"statusLine": other})
        with self.assertRaises(SystemExit):
            cfg.install(self.root)
        cfg.install(self.root, force=True)
        self.assertTrue((self.root / "settings.json.claude-usage.bak").exists())
        cfg.remove(self.root)
        self.assertEqual(self.read()["statusLine"], other)

    def test_reinstall_keeps_original_previous(self):
        other = {"type": "command", "command": "node other.mjs"}
        self.write({"statusLine": other})
        cfg.install(self.root, force=True)
        cfg.install(self.root)
        cfg.remove(self.root)
        self.assertEqual(self.read()["statusLine"], other)

    def test_remove_refuses_after_user_edit(self):
        self.write({})
        cfg.install(self.root)
        data = self.read(); data["statusLine"] = {"type": "command", "command": "mine"}; self.write(data)
        with self.assertRaises(SystemExit):
            cfg.remove(self.root)

    def test_config_dir_env(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": self.tmp.name}):
            self.assertEqual(cfg.config_dir(), self.root)


if __name__ == "__main__":
    unittest.main()
