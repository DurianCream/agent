"""Behavioral tests for submission, version pinning, paths, and registration."""
import copy
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("agentctl", SOURCE / "runtime/agentctl.py")
ctl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ctl)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.scratch = (SOURCE / "work").resolve()
        self.scratch.mkdir(exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix="contract-test-", dir=self.scratch)).resolve()
        self.addCleanup(self.cleanup)
        for name in ("core", "modules", "shared"):
            shutil.copytree(SOURCE / name, self.root / name)
        for name in ("AGENTS.md", "registry.json"):
            shutil.copy2(SOURCE / name, self.root / name)
        ctl.init_task("coding", "sample", "예제 산출물 작성", ["파일과 실제 검증 증거가 있다"], self.root)
        ctl.transition("sample", "running", self.root)
        self.run = self.root / "runs/sample"
        self.artifact = self.root / "outputs/sample/example.txt"
        self.artifact.write_text("검증할 산출물\n", encoding="utf-8")
        (self.run / "evidence/check.txt").write_text("실제 검사 결과: PASS\n", encoding="utf-8")
        self.result = ctl.read_json(self.run / "result.json")
        self.result.update(status="completed", summary="예제 파일을 작성하고 검사했다.",
                           work=["파일 작성", "검증 실행"], limitations=[], next_actions=[])
        self.result["artifacts"] = [{"path": "outputs/sample/example.txt", "description": "예제 파일", "sha256": None}]
        self.result["acceptance_criteria"][0]["verification_ids"] = ["check-1"]
        self.result["verification"][0].update(outcome="passed", evidence=["runs/sample/evidence/check.txt"],
                                              notes="증거 파일을 확인했다.")
        self.save()

    def cleanup(self):
        target = self.root.resolve()
        if not target.is_relative_to(self.scratch) or not target.name.startswith("contract-test-"):
            raise RuntimeError("Refusing cleanup outside the verified test workspace")
        shutil.rmtree(target)

    def save(self):
        ctl.write_json(self.run / "result.json", self.result)

    def reject(self):
        self.save()
        with self.assertRaises(ctl.ContractError):
            ctl.validate_result("sample", self.root)

    def test_registered_roles_and_skills(self):
        found = ctl.doctor(self.root)
        self.assertEqual((found["modules"], found["skills"]), (8, 5))

    def test_complete_submission_has_fixed_report_and_sealed_artifact(self):
        ctl.submit("sample", self.root)
        published = self.root / "outputs/sample"
        data = ctl.read_json(published / "result.json")
        self.assertEqual(data["artifacts"][0]["sha256"], ctl.digest(self.artifact.read_bytes()))
        report = (published / "result.md").read_text(encoding="utf-8")
        self.assertEqual([line for line in report.splitlines() if line.startswith("## ")],
                         [f"## {i}. {h}" for i, h in enumerate(ctl.HEADINGS, 1)])
        self.assertEqual(ctl.read_json(self.run / "task.json")["state"], "submitted")
        ctl.validate_result("sample", self.root)

    def test_submit_retry_is_idempotent(self):
        ctl.submit("sample", self.root)
        before = (self.run / "events.jsonl").read_bytes()
        self.assertTrue(ctl.submit("sample", self.root)["idempotent"])
        self.assertEqual(before, (self.run / "events.jsonl").read_bytes())

    def test_submission_recovers_matching_partial_publication(self):
        # An interrupted publication can leave one identical output behind.
        self.result["artifacts"][0]["sha256"] = ctl.digest(self.artifact.read_bytes())
        self.save()
        ctl.write_json(self.root / "outputs/sample/result.json", self.result)
        ctl.submit("sample", self.root)
        self.assertTrue((self.root / "outputs/sample/result.md").is_file())

    def test_submitted_result_cannot_be_rewritten(self):
        ctl.submit("sample", self.root)
        changed = ctl.read_json(self.run / "result.json")
        changed["summary"] = "다른 결과"
        ctl.write_json(self.run / "result.json", changed)
        with self.assertRaises(ctl.ContractError):
            ctl.submit("sample", self.root)

    def test_missing_verification_mapping_cannot_claim_completion(self):
        self.result["acceptance_criteria"][0]["verification_ids"] = []
        self.reject()

    def test_unknown_verification_mapping_is_rejected(self):
        self.result["acceptance_criteria"][0]["verification_ids"] = ["unknown"]
        self.reject()

    def test_passed_check_requires_real_nonempty_evidence(self):
        self.result["verification"][0]["evidence"] = []
        self.reject()
        self.result["verification"][0]["evidence"] = ["runs/sample/evidence/missing.txt"]
        self.reject()
        (self.run / "evidence/empty.txt").write_text("", encoding="utf-8")
        self.result["verification"][0]["evidence"] = ["runs/sample/evidence/empty.txt"]
        self.reject()

    def test_unrun_or_failed_checks_cannot_claim_completion(self):
        for outcome in ("not_run", "failed"):
            with self.subTest(outcome=outcome):
                self.result["verification"][0]["outcome"] = outcome
                self.reject()

    def test_partial_result_is_accepted_but_requires_explanation(self):
        self.result["status"] = "partial"
        self.result["verification"][0].update(outcome="not_run", evidence=[], notes="도구 미연결")
        self.result["acceptance_criteria"][0]["verification_ids"] = []
        self.result["limitations"] = ["도구 미연결로 검사 미실행"]
        self.save()
        ctl.submit("sample", self.root)
        self.assertEqual(ctl.read_json(self.run / "task.json")["result_status"], "partial")

    def test_unexplained_incomplete_result_is_rejected(self):
        self.result["status"] = "blocked"
        self.reject()

    def test_unknown_fields_and_module_version_mismatch_are_rejected(self):
        original = copy.deepcopy(self.result)
        self.result["unrecognized"] = True
        self.reject()
        self.result = original
        self.result["module"]["version"] = "9.9.9"
        self.reject()

    def test_result_cannot_weaken_pinned_acceptance_criteria(self):
        self.result["acceptance_criteria"][0]["required"] = False
        self.reject()

    def test_task_record_cannot_change_pinned_inputs(self):
        task = ctl.read_json(self.run / "task.json")
        task["criteria"][0]["description"] = "완화한 기준"
        ctl.write_json(self.run / "task.json", task)
        with self.assertRaises(ctl.ContractError):
            ctl.validate_result("sample", self.root)

    def test_output_and_evidence_paths_are_confined(self):
        original = copy.deepcopy(self.result)
        for candidate in ("../AGENTS.md", "AGENTS.md", "outputs/../../AGENTS.md", "C:/Windows/test.txt"):
            with self.subTest(path=candidate):
                self.result = copy.deepcopy(original)
                self.result["artifacts"][0]["path"] = candidate
                self.reject()
        self.result = original
        self.result["verification"][0]["evidence"] = ["AGENTS.md"]
        self.reject()

    def test_artifact_hash_detects_post_submission_changes(self):
        ctl.submit("sample", self.root)
        self.artifact.write_text("변조됨", encoding="utf-8")
        with self.assertRaises(ctl.ContractError):
            ctl.validate_result("sample", self.root)

    def test_submitted_evidence_changes_are_detected(self):
        ctl.submit("sample", self.root)
        (self.run / "evidence/check.txt").write_text("내용이 달라짐", encoding="utf-8")
        with self.assertRaises(ctl.ContractError):
            ctl.validate_result("sample", self.root)

    def test_published_report_changes_are_detected(self):
        ctl.submit("sample", self.root)
        (self.root / "outputs/sample/result.md").write_text("다른 양식", encoding="utf-8")
        with self.assertRaises(ctl.ContractError):
            ctl.validate_result("sample", self.root)

    def test_live_schema_changes_do_not_change_running_task_contract(self):
        live = self.root / "shared/schemas/result.schema.json"
        schema = ctl.read_json(live)
        schema["required"].append("new_field")
        ctl.write_json(live, schema)
        ctl.validate_result("sample", self.root)
        self.result["new_field"] = "새 버전 필드"
        self.reject()

    def test_snapshot_changes_are_detected(self):
        file = self.run / "snapshot/files/shared/policies/common.json"
        file.write_text("{}", encoding="utf-8")
        with self.assertRaises(ctl.ContractError):
            ctl.validate_result("sample", self.root)

    def test_cyclic_dependencies_are_rejected(self):
        first = self.root / "core/orchestrator/module.json"
        second = self.root / "core/skill-manager/module.json"
        a, b = ctl.read_json(first), ctl.read_json(second)
        a["dependencies"] = [{"id": b["id"], "version": b["version"]}]
        b["dependencies"] = [{"id": a["id"], "version": a["version"]}]
        ctl.write_json(first, a)
        ctl.write_json(second, b)
        with self.assertRaises(ctl.ContractError):
            ctl.doctor(self.root)

    def new_module(self):
        manifest = ctl.read_json(self.root / "modules/coding/module.json")
        manifest.update(id="data-science", name="데이터 분석", instructions="modules/data-science/instructions.md")
        relative = "modules/data-science/module.json"
        ctl.write_json(self.root / relative, manifest)
        (self.root / manifest["instructions"]).write_text("분석 역할", encoding="utf-8")
        return relative, manifest

    def test_new_module_registration_and_use(self):
        file, _ = self.new_module()
        ctl.register(file, self.root)
        self.assertEqual(ctl.doctor(self.root)["modules"], 9)
        ctl.init_task("data-science", "analysis", "분석 수행", ["분석 결과"], self.root)
        self.assertTrue((self.root / "runs/analysis/snapshot.json").is_file())

    def test_failed_registration_leaves_registry_unchanged(self):
        before = (self.root / "registry.json").read_bytes()
        file, manifest = self.new_module()
        manifest["dependencies"] = [{"id": "missing", "version": "1.0.0"}]
        ctl.write_json(self.root / file, manifest)
        with self.assertRaises(ctl.ContractError):
            ctl.register(file, self.root)
        self.assertEqual(before, (self.root / "registry.json").read_bytes())

    def test_unsupported_schema_keywords_fail_explicitly(self):
        with self.assertRaises(ctl.ContractError):
            ctl.validate_data("x", {"type": "string", "customRule": True})

    def test_ambiguous_json_and_timezone_less_dates_are_rejected(self):
        file = self.root / "duplicate.json"
        file.write_text('{"state":"passed","state":"failed"}', encoding="utf-8")
        with self.assertRaises(ctl.ContractError):
            ctl.read_json(file)
        self.result["created_at"] = "2026-10-26T12:00:00"
        self.reject()

    def test_state_changes_and_missing_tasks_do_not_create_fake_runs(self):
        with self.assertRaises(ctl.ContractError):
            ctl.transition("sample", "running", self.root)
        with self.assertRaises(ctl.ContractError):
            ctl.transition("missing", "running", self.root)
        self.assertFalse((self.root / "runs/missing").exists())
        ctl.transition("sample", "waiting", self.root)
        with self.assertRaises(ctl.ContractError):
            ctl.submit("sample", self.root)
        ctl.transition("sample", "running", self.root)
        ctl.transition("sample", "cancelled", self.root)
        with self.assertRaises(ctl.ContractError):
            ctl.submit("sample", self.root)

    def test_reused_and_unsafe_ids_are_rejected(self):
        for name in ("sample", "../outside", "nul"):
            with self.subTest(task=name), self.assertRaises(ctl.ContractError):
                ctl.init_task("coding", name, "목표", ["기준"], self.root)

    def test_invalid_submission_does_not_publish(self):
        self.result["verification"][0]["outcome"] = "not_run"
        self.save()
        with self.assertRaises(ctl.ContractError):
            ctl.submit("sample", self.root)
        self.assertFalse((self.root / "outputs/sample/result.md").exists())
        self.assertFalse((self.root / "outputs/sample/result.json").exists())
        self.assertEqual(ctl.read_json(self.run / "task.json")["state"], "running")

    def test_report_content_cannot_inject_extra_sections(self):
        self.result["summary"] = "설명\n## 8. 임의 항목"
        self.save()
        ctl.submit("sample", self.root)
        report = (self.root / "outputs/sample/result.md").read_text(encoding="utf-8")
        self.assertEqual(len([line for line in report.splitlines() if line.startswith("## ")]), 7)


if __name__ == "__main__":
    unittest.main()
