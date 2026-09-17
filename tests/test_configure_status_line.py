from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "plugins" / "codex-usage" / "scripts" / "configure_status_line.py"
SPEC = importlib.util.spec_from_file_location("configure_status_line", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RenderTests(unittest.TestCase):
    def test_adds_tui_section_to_empty_config(self) -> None:
        updated, state, changed = MODULE.render_install("")
        self.assertTrue(changed)
        self.assertEqual(updated, f"[tui]\n{MODULE.DESIRED_LINE}\n")
        self.assertFalse(state["had_tui_section"])

    def test_replaces_multiline_value_and_preserves_other_keys(self) -> None:
        original = (
            "model = \"gpt-5\"\n\n"
            "[tui]\n"
            "theme = \"ansi\"\n"
            "status_line = [\n"
            "  \"model\",\n"
            "  \"current-dir\",\n"
            "]\n\n"
            "[features]\n"
            "plugins = true\n"
        )
        updated, state, changed = MODULE.render_install(original)
        self.assertTrue(changed)
        self.assertIn(f"theme = \"ansi\"\n{MODULE.DESIRED_LINE}\n", updated)
        self.assertIn("[features]\nplugins = true\n", updated)
        self.assertEqual(
            state["previous_status_line"],
            ['status_line = [\n', '  "model",\n', '  "current-dir",\n', ']\n'],
        )

    def test_install_is_idempotent(self) -> None:
        original = f"[tui]\n{MODULE.DESIRED_LINE}\n"
        updated, state, changed = MODULE.render_install(original)
        self.assertEqual(updated, original)
        self.assertEqual(state, {})
        self.assertFalse(changed)

    def test_replaces_root_dotted_key_without_adding_table(self) -> None:
        original = 'model = "gpt-5"\ntui.status_line = ["model"]\n'
        updated, state, changed = MODULE.render_install(original)
        self.assertTrue(changed)
        self.assertIn("tui." + MODULE.DESIRED_LINE, updated)
        self.assertNotIn("[tui]", updated)
        restored, removed = MODULE.render_remove(updated, state, False)
        self.assertTrue(removed)
        self.assertEqual(restored, original)

    def test_refuses_inline_tui_table(self) -> None:
        with self.assertRaises(MODULE.ConfigConflict):
            MODULE.render_install('tui = { animations = false }\n')

    def test_preserves_crlf(self) -> None:
        original = "[tui]\r\nanimations = false\r\n"
        updated, _, _ = MODULE.render_install(original)
        self.assertEqual(updated.count("\n"), updated.count("\r\n"))

    def test_remove_restores_previous_value(self) -> None:
        original = '[tui]\nstatus_line = ["model"]\nanimations = false\n'
        installed, state, _ = MODULE.render_install(original)
        restored, changed = MODULE.render_remove(installed, state, False)
        self.assertTrue(changed)
        self.assertEqual(restored, original)

    def test_remove_deletes_new_tui_section(self) -> None:
        original = 'model = "gpt-5"\n'
        installed, state, _ = MODULE.render_install(original)
        restored, changed = MODULE.render_remove(installed, state, False)
        self.assertTrue(changed)
        self.assertEqual(restored, original)

    def test_remove_refuses_later_user_change(self) -> None:
        state = {"installed_status_line": MODULE.DESIRED_LINE, "previous_status_line": None}
        current = '[tui]\nstatus_line = ["model"]\n'
        with self.assertRaises(MODULE.ConfigConflict):
            MODULE.render_remove(current, state, False)


class FileTests(unittest.TestCase):
    def test_round_trip_creates_backup_and_removes_only_its_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            original = 'model = "gpt-5"\n[tui]\nanimations = false\n'
            config.write_text(original, encoding="utf-8")

            self.assertEqual(MODULE.configure(config, remove=False, force=False, check=False), 0)
            self.assertIn(MODULE.DESIRED_LINE, config.read_text(encoding="utf-8"))
            self.assertTrue(config.with_name("config.toml.codex-usage.bak").exists())
            self.assertEqual(MODULE.configure(config, remove=False, force=False, check=True), 0)

            self.assertEqual(MODULE.configure(config, remove=True, force=False, check=False), 0)
            self.assertEqual(config.read_text(encoding="utf-8"), original)
            self.assertFalse(config.with_name("config.toml.codex-usage-state.json").exists())


if __name__ == "__main__":
    unittest.main()
