"""Project context override integration and adapter safety checks."""
import importlib.util
import json
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("sync_codex_context_test", SOURCE / "runtime/sync_codex.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class ContextSettingsTests(unittest.TestCase):
    def setUp(self):
        self.scratch = (SOURCE / "work").resolve()
        self.scratch.mkdir(exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix="context-test-", dir=self.scratch)).resolve()
        self.addCleanup(self.cleanup)
        (self.root / "runtime").mkdir()
        (self.root / "shared/skills").mkdir(parents=True)
        (self.root / "registry.json").write_text(json.dumps({"modules": []}), encoding="utf-8")
        (self.root / "shared/skills/skills.json").write_text(json.dumps({"skills": []}), encoding="utf-8")
        self.settings = self.root / "runtime/codex-settings.toml"
        self.config = self.root / ".codex/config.toml"
        self.state = self.root / "runtime/native-map.json"

    def cleanup(self):
        target = self.root.resolve()
        if not target.is_relative_to(self.scratch) or not target.name.startswith("context-test-"):
            raise RuntimeError("Refusing cleanup outside verified test workspace")
        shutil.rmtree(target)

    def write_settings(self, body):
        self.settings.write_text(body, encoding="utf-8")

    def test_missing_optional_settings_preserve_legacy_config(self):
        generated, _, _ = sync.render(self.root)
        self.assertEqual(generated[".codex/config.toml"],
                         sync.MARKER + "\n# Project scope. Model, permissions and MCP inherit from the parent.\n\n"
                         "[agents]\nenabled = true\n")

    def test_context_settings_are_top_level_and_survive_resynchronization(self):
        self.write_settings("model_context_window = 1000000\nmodel_auto_compact_token_limit = 900000\n")
        self.assertTrue(sync.synchronize(self.root, write=True)["ok"])
        parsed = tomllib.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(parsed["model_context_window"], 1000000)
        self.assertEqual(parsed["model_auto_compact_token_limit"], 900000)
        self.assertEqual(parsed["agents"], {"enabled": True})
        before = self.config.read_bytes(), self.state.read_bytes()
        self.assertTrue(sync.synchronize(self.root, write=True)["ok"])
        self.assertEqual(before, (self.config.read_bytes(), self.state.read_bytes()))
        self.assertTrue(sync.synchronize(self.root)["ok"])

    def test_invalid_settings_fail_before_any_adapter_write(self):
        sync.synchronize(self.root, write=True)
        before = self.config.read_bytes(), self.state.read_bytes()
        invalid = [
            'model = ""\n',
            'model_context_window = true\n',
            'model_context_window = 0\n',
            'model_context_window = -1\n',
            'model_context_window = 1000000.0\n',
            'model_context_window = "1000000"\n',
            'model_auto_compact_token_limit = 900000\n',
            'model_context_window = 1000000\nmodel_auto_compact_token_limit = 1000000\n',
            'model_context_window = 1000000\nmodel_auto_compact_token_limit = 1000001\n',
            'model_context_window = 1000000\nmodel_auto_compact_token_limit = false\n',
            '[agents]\nenabled = false\n',
            'model_context_window = [1000000]\n',
        ]
        for body in invalid:
            with self.subTest(settings=body):
                self.write_settings(body)
                with self.assertRaises(ValueError):
                    sync.synchronize(self.root, write=True)
                self.assertEqual(before, (self.config.read_bytes(), self.state.read_bytes()))

    def test_context_change_preserves_manual_adapter_protection(self):
        self.write_settings("model_context_window = 1000000\nmodel_auto_compact_token_limit = 900000\n")
        sync.synchronize(self.root, write=True)
        self.config.write_text(self.config.read_text(encoding="utf-8") + "# manual edit\n", encoding="utf-8")
        before = self.config.read_bytes(), self.state.read_bytes()
        self.write_settings("model_context_window = 900000\nmodel_auto_compact_token_limit = 800000\n")
        with self.assertRaisesRegex(ValueError, "Manual change detected"):
            sync.synchronize(self.root, write=True)
        self.assertEqual(before, (self.config.read_bytes(), self.state.read_bytes()))

    def test_context_management_is_a_feature_table_and_survives_resynchronization(self):
        self.write_settings("model_context_window = 1000000\nmodel_auto_compact_token_limit = 900000\n"
                            "[features]\ncontext_management = true\n")
        self.assertTrue(sync.synchronize(self.root, write=True)["ok"])
        parsed = tomllib.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(parsed["model_context_window"], 1000000)
        self.assertEqual(parsed["model_auto_compact_token_limit"], 900000)
        self.assertEqual(parsed["features"], {"context_management": True})
        self.assertEqual(parsed["agents"], {"enabled": True})
        before = self.config.read_bytes(), self.state.read_bytes()
        self.assertTrue(sync.synchronize(self.root, write=True)["ok"])
        self.assertEqual(before, (self.config.read_bytes(), self.state.read_bytes()))
        self.assertTrue(sync.synchronize(self.root)["ok"])

    def test_invalid_features_fail_before_any_adapter_write(self):
        sync.synchronize(self.root, write=True)
        before = self.config.read_bytes(), self.state.read_bytes()
        invalid = [
            'features = true\n',
            'features = ["context_management"]\n',
            '[features]\nunknown_feature = true\n',
            '[features]\ncontext_management = 1\n',
            '[features]\ncontext_management = "true"\n',
            '[features.context_management]\nenabled = true\n',
        ]
        for body in invalid:
            with self.subTest(settings=body):
                self.write_settings(body)
                with self.assertRaises(ValueError):
                    sync.synchronize(self.root, write=True)
                self.assertEqual(before, (self.config.read_bytes(), self.state.read_bytes()))

    def test_feature_change_preserves_manual_adapter_protection(self):
        self.write_settings("[features]\ncontext_management = true\n")
        sync.synchronize(self.root, write=True)
        self.config.write_text(self.config.read_text(encoding="utf-8") + "# manual edit\n", encoding="utf-8")
        before = self.config.read_bytes(), self.state.read_bytes()
        self.write_settings("[features]\ncontext_management = false\n")
        with self.assertRaisesRegex(ValueError, "Manual change detected"):
            sync.synchronize(self.root, write=True)
        self.assertEqual(before, (self.config.read_bytes(), self.state.read_bytes()))


    def test_hook_template_survives_sync_and_protects_manual_edits(self):
        template = {"hooks": {"PostToolUse": [{"hooks": [{"type": "command", "command": '"{python}" "{root}/runtime/context_checkpoint.py"', "timeout": 5}]}]}}
        (self.root / "runtime/context-hooks.json").write_text(json.dumps(template), encoding="utf-8")
        self.assertTrue(sync.synchronize(self.root, write=True)["ok"])
        hook_file = self.root / ".codex/hooks.json"
        generated = hook_file.read_bytes()
        command = json.loads(generated)["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
        self.assertNotIn("{root}", command)
        self.assertNotIn("{python}", command)
        self.assertIn(self.root.as_posix(), command)
        self.assertTrue(sync.synchronize(self.root, write=True)["ok"])
        self.assertEqual(generated, hook_file.read_bytes())
        hook_file.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Manual change detected"):
            sync.synchronize(self.root, write=True)

    def test_project_model_survives_generation(self):
        self.write_settings('model = "gpt-6-astra"\nmodel_context_window = 1000000\nmodel_auto_compact_token_limit = 900000\n[features]\ncontext_management = true\n')
        sync.synchronize(self.root, write=True)
        parsed = tomllib.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(parsed["model"], "gpt-6-astra")
        self.assertEqual(parsed["model_context_window"], 1000000)
        self.assertTrue(parsed["features"]["context_management"])
        self.assertTrue(sync.synchronize(self.root)["ok"])

if __name__ == "__main__":
    unittest.main()
