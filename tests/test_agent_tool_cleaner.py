import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent_tool_cleaner as atc


class ToolRegistryTest(unittest.TestCase):
    def test_unique_ids(self):
        ids = [d["id"] for d in atc.TOOL_DEFINITIONS]
        self.assertEqual(len(ids), len(set(ids)), "tool ids must be unique")

    def test_required_fields(self):
        for d in atc.TOOL_DEFINITIONS:
            self.assertIn("detect", d)
            self.assertIn("uninstall", d)
            self.assertIn("remnants", d)
            self.assertIn("name", d)


class ActionBuilderTest(unittest.TestCase):
    def test_npm_uninstall_action(self):
        definition = {
            "id": "test-agent",
            "name": "Test Agent",
            "kind": "CLI",
            "detect": {"commands": ["test-agent"], "npm": ["@example/test-agent"]},
            "uninstall": {"npm": ["@example/test-agent"], "pip": [], "brew": [], "cask": [], "dirs": []},
            "remnants": {"dirs": [], "files": [], "windows_dirs": [], "mac_apps": [], "linux_desktop": []},
        }
        det = atc.Detection(definition=definition)
        actions = atc.build_uninstall_actions(det)
        self.assertTrue(any(a["kind"] == "npm" and a["package"] == "@example/test-agent" for a in actions))

    def test_uninstall_does_not_delete_config_dirs_as_main_action(self):
        definition = {
            "id": "test-gui",
            "name": "Test GUI",
            "kind": "GUI",
            "detect": {"windows_dirs": ["AppData/Roaming/TestGUI", "AppData/Local/Programs/TestGUI"]},
            "uninstall": {"npm": [], "pip": [], "brew": [], "cask": [], "dirs": ["AppData/Local/Programs/TestGUI"]},
            "remnants": {"dirs": [], "files": [], "windows_dirs": ["AppData/Roaming/TestGUI"], "mac_apps": [], "linux_desktop": []},
        }
        det = atc.Detection(definition=definition)
        # A Roaming config path must not appear as an uninstall delete action.
        det.install_paths = [Path("C:/Users/test/AppData/Roaming/TestGUI"), Path("C:/Users/test/AppData/Local/Programs/TestGUI")]
        actions = atc.build_uninstall_actions(det)
        remove_paths = [a["path"] for a in actions if a["kind"] == "remove_path"]
        self.assertNotIn("C:/Users/test/AppData/Roaming/TestGUI", remove_paths)

    def test_cleanup_actions_only_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "residue.txt"
            p.write_text("data", encoding="utf-8")
            det = atc.Detection(definition={})
            det.remnant_paths = [p, Path(tmp) / "missing.txt"]
            actions = atc.build_cleanup_actions(det)
            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0]["path"], str(p))


if __name__ == "__main__":
    unittest.main()
