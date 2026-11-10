"""Task workspace allocation and entry-point safety."""
import concurrent.futures
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agentctl as a


class AgentWorkspaceTests(unittest.TestCase):
    def setUp(self):
        (a.ROOT / "work").mkdir(exist_ok=True)
        self.scratch = tempfile.TemporaryDirectory(dir=a.ROOT / "work")
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name).resolve()
        for name in ("core", "modules", "shared"):
            shutil.copytree(a.ROOT / name, self.root / name)
        for name in ("registry.json", "AGENTS.md"):
            shutil.copyfile(a.ROOT / name, self.root / name)
        a.init_task("coding", "first", "test", ["separate instances"], self.root)

    def allocate(self, role):
        result = a.allocate_workspace("first", role, self.root)
        return self.root / result["workspace"]

    def test_parallel_instances_and_tasks(self):
        with concurrent.futures.ThreadPoolExecutor(3) as pool:
            paths = list(pool.map(self.allocate, ["coding", "coding", "evaluator"]))
        self.assertEqual(len(set(paths)), 3)
        for path, role in zip(paths, ("coding", "coding", "evaluator")):
            self.assertEqual(path.parent, self.root / "work/agents/first" / role)
            (path / "same-name.txt").write_text(path.name, encoding="utf-8")
        self.assertEqual([p.name for p in paths], [(p/"same-name.txt").read_text() for p in paths])
        a.init_task("coding", "second", "test", ["distinct tasks"], self.root)
        other = a.allocate_workspace("second", "coding", self.root)
        self.assertEqual((self.root / other["workspace"]).parent, self.root / "work/agents/second/coding")

    def test_invalid_role_task_and_closed_task(self):
        for task, role in (("../first", "coding"), ("missing", "coding"), ("first", "../coding"),
                           ("first", "unknown-role"), ("first", "nul")):
            with self.subTest(task=task, role=role), self.assertRaises(a.ContractError):
                a.allocate_workspace(task, role, self.root)
        a.transition("first", "cancelled", self.root)
        with self.assertRaisesRegex(a.ContractError, "closed"):
            self.allocate("coding")
        self.assertFalse((self.root/"work/agents").exists())

    def test_existing_task_and_registered_roles(self):
        run = self.root / "runs/first"
        frozen = {name: (run / name).read_bytes() for name in ("task.json", "snapshot.json", "result.json")}
        registry = a.read_json(self.root / "registry.json")
        for entry in registry["modules"]:
            if entry["enabled"]:
                self.assertTrue(self.allocate(entry["id"]).is_dir())
        self.assertEqual(frozen, {name: (run / name).read_bytes() for name in frozen})
        next(entry for entry in registry["modules"] if entry["id"] == "coding")["enabled"] = False
        a.write_json(self.root / "registry.json", registry)
        with self.assertRaisesRegex(a.ContractError, "disabled"):
            self.allocate("coding")

    def test_linked_workspace_tree(self):
        external = self.root / "elsewhere"
        external.mkdir()
        link = self.root / "work/agents"
        link.parent.mkdir(exist_ok=True)
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(external), str(link))
        else:
            link.symlink_to(external, target_is_directory=True)
        with self.assertRaises(a.ContractError):
            self.allocate("coding")
        self.assertEqual(list(external.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
