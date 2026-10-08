#!/usr/bin/env python3
"""증거 검사기의 통과 조건과 실패 시 차단 동작을 임시 디렉터리에서 확인한다."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
SCRIPT = Path(__file__).with_name("check_evidence.py")
SPEC = importlib.util.spec_from_file_location("check_evidence", SCRIPT)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class EvidenceGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="infra-gate-", dir="/tmp")
        self.addCleanup(self.temporary.cleanup)
        self.run = Path(self.temporary.name) / "run"
        self.run.mkdir()
        (self.run / "evidence").mkdir()
        self.evidence = self.run / "evidence/result.txt"
        self.evidence.write_text("관찰 결과: 정상\n", encoding="utf-8")
        self.documents = {
            "request.json": {"goal": "로컬 결과 검증", "criteria": [
                {"id": "c1", "description": "결과 확인"}], "required_checks": ["test1"]},
            "plan.json": {"tasks": [{"id": "t1", "description": "결과 작성", "depends_on": []}],
                          "criteria_ids": ["c1"], "required_checks": ["test1"]},
            "work.json": {"status": "COMPLETE", "summary": "확인 완료", "evidence": [
                {"id": "e1", "path": "evidence/result.txt", "sha256": self.digest(self.evidence)}],
                "checks": [{"id": "test1", "status": "PASS", "exit_code": 0, "evidence_ids": ["e1"]}],
                "criteria": [{"id": "c1", "status": "VERIFIED", "evidence_ids": ["e1"],
                              "explanation": "실제 파일 확인"}]},
            "critique.json": {"verdict": "PASS", "summary": "독립 검수 완료", "work_sha256": "",
                              "findings": []},
        }
        self.write()

    @staticmethod
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def write(self, refresh_critique=True):
        for name in ("request.json", "plan.json", "work.json"):
            (self.run / name).write_text(json.dumps(self.documents[name], ensure_ascii=False), encoding="utf-8")
        if refresh_critique:
            self.documents["critique.json"]["work_sha256"] = self.digest(self.run / "work.json")
        (self.run / "critique.json").write_text(
            json.dumps(self.documents["critique.json"], ensure_ascii=False), encoding="utf-8")

    def verdict(self, expected):
        result = CHECKER.evaluate(str(self.run))
        self.assertEqual(result["verdict"], expected, result)
        if expected != "PASS":
            self.assertTrue(result["reasons"])
        return result

    def test_valid_evidence_passes(self):
        result = self.verdict("PASS")
        self.assertEqual(set(result["input_sha256"]), set(CHECKER.DOCUMENTS))

    def test_failed_check_requires_rework(self):
        self.documents["work.json"]["checks"][0].update(status="FAIL", exit_code=1)
        self.write()
        self.verdict("REWORK")

    def test_failed_criterion_requires_rework(self):
        self.documents["work.json"]["criteria"][0]["status"] = "FAILED"
        self.write()
        self.verdict("REWORK")

    def test_unverified_criterion_needs_evidence(self):
        self.documents["work.json"]["criteria"][0]["status"] = "UNVERIFIED"
        self.write()
        self.verdict("NEEDS_EVIDENCE")

    def test_blocked_and_failed_work_cannot_pass(self):
        for status, expected in (("BLOCKED", "NEEDS_EVIDENCE"), ("FAILED", "REWORK")):
            with self.subTest(status=status):
                self.documents["work.json"]["status"] = status
                self.write()
                self.verdict(expected)

    def test_pass_with_nonzero_exit_code_requires_rework(self):
        self.documents["work.json"]["checks"][0]["exit_code"] = 1
        self.write()
        self.verdict("REWORK")

    def test_missing_required_field_requires_rework(self):
        del self.documents["work.json"]["summary"]
        self.write()
        self.verdict("REWORK")

    def test_not_run_needs_evidence(self):
        self.documents["work.json"]["checks"][0].update(status="NOT_RUN", exit_code=None)
        self.write()
        self.verdict("NEEDS_EVIDENCE")

    def test_missing_evidence_file_needs_evidence(self):
        self.evidence.unlink()
        self.verdict("NEEDS_EVIDENCE")

    def test_missing_required_check_needs_evidence(self):
        self.documents["work.json"]["checks"] = []
        self.write()
        self.verdict("NEEDS_EVIDENCE")

    def test_missing_criterion_needs_evidence(self):
        self.documents["work.json"]["criteria"] = []
        self.write()
        self.verdict("NEEDS_EVIDENCE")

    def test_missing_evidence_references_needs_evidence(self):
        self.documents["work.json"]["criteria"][0]["evidence_ids"] = []
        self.write()
        self.verdict("NEEDS_EVIDENCE")

    def test_changed_evidence_requires_rework(self):
        self.evidence.write_text("변경됨", encoding="utf-8")
        self.verdict("REWORK")

    def test_stale_critique_requires_rework(self):
        self.documents["work.json"]["summary"] = "검수 후 변경"
        self.write(refresh_critique=False)
        self.verdict("REWORK")

    def test_path_traversal_and_absolute_paths_rejected(self):
        for path in ("../secret.txt", "/etc/passwd", "evidence/../result.txt", "C:\\secret.txt"):
            with self.subTest(path=path):
                self.documents["work.json"]["evidence"][0]["path"] = path
                self.write()
                self.verdict("REWORK")

    def test_internal_file_symlink_rejected(self):
        link = self.run / "evidence/link.txt"
        link.symlink_to("result.txt")
        self.documents["work.json"]["evidence"][0]["path"] = "evidence/link.txt"
        self.write()
        self.verdict("REWORK")

    def test_directory_symlink_rejected(self):
        (self.run / "linked").symlink_to("evidence", target_is_directory=True)
        self.documents["work.json"]["evidence"][0]["path"] = "linked/result.txt"
        self.write()
        self.verdict("REWORK")

    def test_document_symlink_rejected(self):
        original = self.run / "plan-original.json"
        (self.run / "plan.json").rename(original)
        (self.run / "plan.json").symlink_to(original.name)
        self.verdict("REWORK")

    def test_run_directory_symlink_rejected(self):
        linked = self.run.parent / "linked-run"
        linked.symlink_to(self.run.name, target_is_directory=True)
        self.assertEqual(CHECKER.evaluate(str(linked))["verdict"], "REWORK")

    def test_fifo_is_rejected_without_blocking(self):
        fifo = self.run / "evidence/pipe"
        os.mkfifo(fifo)
        self.documents["work.json"]["evidence"][0]["path"] = "evidence/pipe"
        self.write()
        self.verdict("REWORK")

    def test_bool_is_not_exit_code_zero(self):
        self.documents["work.json"]["checks"][0]["exit_code"] = False
        self.write()
        self.verdict("REWORK")

    def test_wrong_document_and_field_types_rejected(self):
        for name, field, value in (("request.json", "criteria", {}),
                                   ("work.json", "checks", "not-a-list"),
                                   ("critique.json", "findings", None)):
            with self.subTest(name=name, field=field):
                previous = self.documents[name][field]
                self.documents[name][field] = value
                self.write()
                self.verdict("REWORK")
                self.documents[name][field] = previous
        (self.run / "request.json").write_text("[]", encoding="utf-8")
        self.verdict("REWORK")

    def test_duplicate_ids_rejected(self):
        self.documents["work.json"]["evidence"].append(dict(self.documents["work.json"]["evidence"][0]))
        self.write()
        self.verdict("REWORK")

    def test_duplicate_json_keys_rejected(self):
        (self.run / "request.json").write_text('{"goal":"a","goal":"b"}', encoding="utf-8")
        self.verdict("REWORK")

    def test_unknown_evidence_reference_rejected(self):
        self.documents["work.json"]["criteria"][0]["evidence_ids"] = ["unknown"]
        self.write()
        self.verdict("REWORK")

    def test_dependency_cycle_rejected(self):
        self.documents["plan.json"]["tasks"] = [
            {"id": "t1", "description": "작업 1", "depends_on": ["t2"]},
            {"id": "t2", "description": "작업 2", "depends_on": ["t1"]}]
        self.write()
        self.verdict("REWORK")

    def test_unknown_dependency_rejected(self):
        self.documents["plan.json"]["tasks"][0]["depends_on"] = ["absent"]
        self.write()
        self.verdict("REWORK")

    def test_plan_criteria_must_match_request(self):
        self.documents["plan.json"]["criteria_ids"] = []
        self.write()
        self.verdict("REWORK")

    def test_plan_checks_must_match_request(self):
        self.documents["plan.json"]["required_checks"] = []
        self.write()
        self.verdict("REWORK")

    def test_blocking_finding_rejected(self):
        self.documents["critique.json"]["findings"] = [{"blocking": True, "description": "오류 미해결"}]
        self.write()
        self.verdict("REWORK")

    def test_review_request_for_evidence_preserved(self):
        self.documents["critique.json"]["verdict"] = "NEEDS_EVIDENCE"
        self.write()
        self.verdict("NEEDS_EVIDENCE")

    def test_pass_with_missing_exit_code_needs_evidence(self):
        self.documents["work.json"]["checks"][0]["exit_code"] = None
        self.write()
        self.verdict("NEEDS_EVIDENCE")

    def test_no_required_checks_for_document_task(self):
        self.documents["request.json"]["required_checks"] = []
        self.documents["plan.json"]["required_checks"] = []
        self.documents["work.json"]["checks"] = []
        self.write()
        self.verdict("PASS")

    def test_empty_acceptance_criteria_rejected(self):
        self.documents["request.json"]["criteria"] = []
        self.documents["plan.json"]["criteria_ids"] = []
        self.documents["work.json"]["criteria"] = []
        self.write()
        self.verdict("REWORK")

    def test_missing_input_file_needs_evidence(self):
        (self.run / "plan.json").unlink()
        self.verdict("NEEDS_EVIDENCE")

    def test_non_utf8_and_nonfinite_json_rejected(self):
        for content in (b"\xff", b'{"goal": NaN}'):
            with self.subTest(content=content):
                (self.run / "request.json").write_bytes(content)
                self.verdict("REWORK")

    def test_command_strings_not_executed_and_checker_does_not_write(self):
        marker = self.run.parent / "must-not-exist"
        self.documents["work.json"]["command"] = "touch " + str(marker)
        self.documents["work.json"]["summary"] = "$(touch " + str(marker) + ")"
        self.write()
        before = {p.relative_to(self.run): p.read_bytes() for p in self.run.rglob("*") if p.is_file()}
        with mock.patch("os.system", side_effect=AssertionError("명령 실행 금지")), \
                mock.patch("subprocess.run", side_effect=AssertionError("하위 프로세스 실행 금지")), \
                mock.patch("socket.socket", side_effect=AssertionError("네트워크 접근 금지")):
            self.verdict("PASS")
        self.assertFalse(marker.exists())
        after = {p.relative_to(self.run): p.read_bytes() for p in self.run.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_cli_json_and_exit_codes(self):
        for expected, code in (("PASS", 0), ("NEEDS_EVIDENCE", 2), ("REWORK", 1)):
            if expected == "NEEDS_EVIDENCE":
                self.evidence.unlink()
            elif expected == "REWORK":
                self.documents["work.json"]["checks"][0].update(status="FAIL", exit_code=1)
                self.write()
            completed = subprocess.run([sys.executable, "-B", str(SCRIPT), str(self.run)],
                                       capture_output=True, text=True, timeout=10)
            self.assertEqual(completed.returncode, code, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["verdict"], expected)
            self.assertEqual(completed.stderr, "")


if __name__ == "__main__":
    unittest.main()
