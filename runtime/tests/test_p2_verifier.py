import base64
import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import p2_executor as execution
import p2_verifier as verification
from control_contracts import canonical_digest

PROGRAM = b"import pathlib,sys\npathlib.Path(sys.argv[1]).write_bytes(b'result')\nsys.stdout.buffer.write(b'ok\\n')\n"


def make_policy(root, baseline="a" * 40):
    git = Path(shutil.which("git") or "/usr/bin/git").absolute()
    return {"schema_version": "0.1.0",
        "identity": {"repository_id": "multi", "task_id": "adapter-fixture", "scope": {"project": "multi", "service": "agent-framework", "environment": "development", "issue": "adapter-fixture"}, "enrollment_id": str(uuid4()), "base_commit": baseline},
        "principals": {"verifier_uid": 0, "worker_uid": 21001, "publisher_uid": 21002, "receipt_gid": 21003},
        "oracle": {"purpose": "release", "execution": {"profile_id": "fixture-oracle", "argv": [sys.executable, "-I", "-B", "/input/program.py", "/output/result.txt"], "timeout_seconds": 5,
            "memory_bytes": 256 * 1024 * 1024, "cpu_seconds": 5, "tasks": 16, "output_bytes": 1024 * 1024, "stdin_base64": ""},
            "expected": {"exit_code": 0, "stdout_digest": verification.sha(b"ok\n"), "stderr_digest": verification.sha(b""), "outputs": {"result.txt": verification.sha(b"result")}}, "executor_config_digest": None},
        "verification": {"state_root": str(root / "verification-state"), "receipt_dir": str(root / "receipts"), "ttl_seconds": 60},
        "publication": {"transport": "local-bare", "remote": str(root / "remote.git"), "ref": "refs/heads/main", "state_root": str(root / "publisher-state"),
            "git_binary": str(git), "git_binary_digest": verification.sha(git.read_bytes()), "allowed_paths": ["program.py"], "author_name": "P2 Fixture", "author_email": "p2-fixture@example.invalid"}}


def make_bundle(policy, program=PROGRAM):
    digest = verification.sha(program)
    return {"binding": verification.policy_binding(policy), "files": [{"path": "program.py", "kind": "blob", "mode": "100644", "size": len(program), "digest": digest}], "blobs": {digest: program}}


class VerifierTests(unittest.TestCase):
    def setUp(self):
        parent = Path(os.environ["P2_TEST_TMP"]) if "P2_TEST_TMP" in os.environ else Path(__file__).resolve().parents[2] / "work/p2-adapter-tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = verification.fixture_root(self.temp.name)
        self.policy = make_policy(self.root)
        self.executor = execution.FixtureExecutor(self.root / "executor", trusted_fixtures=True)

    def verifier(self):
        return verification.Verifier.for_fixture(self.root, self.policy, self.executor)

    def test_real_output_is_compared_to_operator_oracle(self):
        bundle = make_bundle(self.policy)
        record = self.verifier().verify(bundle, str(uuid4()), str(uuid4()))
        self.assertEqual(record["outcome"], "verified")
        self.assertEqual(record["trust_mode"], "fixture")
        self.assertFalse(record["isolation_verified"])
        self.assertIsNone(record["observed_worker_uid"])
        self.assertEqual(record["observed"]["outputs"], self.policy["oracle"]["expected"]["outputs"])

    def test_candidate_passed_string_cannot_replace_oracle(self):
        program = PROGRAM.replace(b"b'ok\\n'", b"b'{\"passed\":true}\\n'")
        record = self.verifier().verify(make_bundle(self.policy, program), str(uuid4()), str(uuid4()))
        self.assertEqual(record["outcome"], "failed")

    def test_changed_output_file_fails(self):
        record = self.verifier().verify(make_bundle(self.policy, PROGRAM.replace(b"b'result'", b"b'wrong'")), str(uuid4()), str(uuid4()))
        self.assertEqual(record["outcome"], "failed")

    def test_correct_output_with_nonzero_exit_fails(self):
        record = self.verifier().verify(make_bundle(self.policy, PROGRAM + b"sys.exit(7)\n"), str(uuid4()), str(uuid4()))
        self.assertEqual(record["outcome"], "failed")
        self.assertEqual(record["observed"]["exit_code"], 7)

    def test_timeout_never_becomes_release_pass(self):
        self.policy["oracle"]["execution"]["timeout_seconds"] = 1
        program = PROGRAM + b"import time\ntime.sleep(4)\n"
        record = self.verifier().verify(make_bundle(self.policy, program), str(uuid4()), str(uuid4()))
        self.assertEqual(record["outcome"], "failed")
        self.assertTrue(record["observed"]["timed_out"])

    def test_stdin_is_fixed_by_approved_profile(self):
        self.policy["oracle"]["execution"]["stdin_base64"] = base64.b64encode(b"ok\n").decode()
        program = b"import pathlib,sys\npathlib.Path(sys.argv[1]).write_bytes(b'result')\nsys.stdout.buffer.write(sys.stdin.buffer.read())\n"
        self.assertEqual(self.verifier().verify(make_bundle(self.policy, program), str(uuid4()), str(uuid4()))["outcome"], "verified")

    def test_exact_retry_does_not_execute_again(self):
        verifier = self.verifier(); bundle = make_bundle(self.policy); candidate = str(uuid4()); key = str(uuid4())
        first = verifier.verify(bundle, candidate, key)
        with mock.patch.object(self.executor, "run", side_effect=AssertionError("must not execute")):
            second = verifier.verify(bundle, candidate, key)
        self.assertEqual(first, second)

    def test_changed_request_same_key_conflicts(self):
        verifier = self.verifier(); key = str(uuid4())
        verifier.verify(make_bundle(self.policy), str(uuid4()), key)
        with self.assertRaisesRegex(verification.AdapterError, "verification_idempotency_conflict"):
            verifier.verify(make_bundle(self.policy, PROGRAM + b"# changed\n"), str(uuid4()), key)

    def test_cas_bytes_tampering_fails_before_executor(self):
        bundle = make_bundle(self.policy); digest = next(iter(bundle["blobs"]))
        bundle["blobs"][digest] = b"different"
        with mock.patch.object(self.executor, "run", side_effect=AssertionError("must not execute")), self.assertRaisesRegex(verification.AdapterError, "bundle_blob_mismatch"):
            self.verifier().verify(bundle, str(uuid4()), str(uuid4()))

    def test_result_candidate_or_profile_mismatch_is_rejected(self):
        verifier = self.verifier(); bundle = make_bundle(self.policy)
        actual = self.executor.run(bundle, verifier.profile)
        for name in ("candidate_digest", "profile_digest"):
            with mock.patch.object(self.executor, "run", return_value=replace(actual, **{name: "sha256:" + "0" * 64})), self.assertRaisesRegex(verification.AdapterError, "execution_binding"):
                verifier.verify(bundle, str(uuid4()), str(uuid4()))

    def test_resource_budget_event_fails_even_with_matching_outputs(self):
        verifier = self.verifier(); bundle = make_bundle(self.policy)
        actual = self.executor.run(bundle, verifier.profile)
        with mock.patch.object(self.executor, "run", return_value=replace(actual, budget_exceeded=True)):
            record = verifier.verify(bundle, str(uuid4()), str(uuid4()))
        self.assertEqual(record["outcome"], "failed")

    def test_forged_verified_record_is_rejected(self):
        verifier = self.verifier(); candidate = str(uuid4()); bundle = make_bundle(self.policy, PROGRAM.replace(b"b'result'", b"b'wrong'"))
        record = verifier.verify(bundle, candidate, str(uuid4()))
        path = verifier.receipts / (record["verification_id"] + ".json")
        record["outcome"] = "verified"
        path.write_bytes(verification.json_bytes(record))
        with self.assertRaisesRegex(verification.AdapterError, "verification_false_success"):
            verification.read_verification(self.policy, record["verification_id"], candidate, record["candidate_digest"], fixture_mode=True)

    def test_fixture_receipt_cannot_enter_production_reader(self):
        record = self.verifier().verify(make_bundle(self.policy), str(uuid4()), str(uuid4()))
        with self.assertRaises((verification.AdapterError, ValueError)):
            verification.read_verification(self.policy, record["verification_id"], record["candidate_id"], record["candidate_digest"], fixture_mode=False)

    def test_production_cannot_accept_fixture_executor(self):
        obj = object.__new__(verification.Verifier); obj.fixture_mode = False
        with self.assertRaisesRegex(verification.AdapterError, "executor_type"):
            obj._configure(self.policy, self.executor)

    def test_production_executor_role_mismatch_is_rejected(self):
        obj = object.__new__(verification.Verifier); obj.fixture_mode = False
        fake = object.__new__(execution.BwrapExecutor)
        fake.config = {"worker_uid": self.policy["principals"]["publisher_uid"], "publisher_uid": 21001,
                       "enrollment_id": self.policy["identity"]["enrollment_id"]}
        fake.config_digest = None
        with self.assertRaisesRegex(verification.AdapterError, "executor_policy_identity"):
            obj._configure(self.policy, fake)


if __name__ == "__main__": unittest.main()
