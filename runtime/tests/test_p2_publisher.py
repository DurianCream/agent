from contextlib import closing
import copy
from datetime import timedelta
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import p2_executor as execution
import p2_publisher as publication
import p2_verifier as verification
import p2_store as storage
import p2_broker as broker
from test_p2_verifier import make_policy, make_bundle, PROGRAM
from test_p2_store import request, raw


class PublisherTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which("git"): self.skipTest("Git unavailable")
        parent = Path(os.environ["P2_TEST_TMP"]) if "P2_TEST_TMP" in os.environ else Path(__file__).resolve().parents[2] / "work/p2-publication-tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent); self.addCleanup(self.temp.cleanup)
        self.root = verification.fixture_root(self.temp.name)
        self.git_binary = shutil.which("git")
        self.remote = self.root / "remote.git"
        template = self.root / "template"; template.mkdir()
        self.git(None, ["init", "--bare", "--template=" + str(template), str(self.remote)])
        oid = self.git(self.remote, ["hash-object", "-w", "--stdin"], b"base\n").strip().decode()
        tree = self.git(self.remote, ["mktree"], ("100644 blob " + oid + "\tbase.txt\n").encode()).strip().decode()
        self.baseline = self.git(self.remote, ["commit-tree", tree], b"baseline\n").strip().decode()
        self.git(self.remote, ["update-ref", "refs/heads/main", self.baseline])
        self.policy = make_policy(self.root, self.baseline)
        self.executor = execution.FixtureExecutor(self.root / "executor", trusted_fixtures=True)
        self.verifier = verification.Verifier.for_fixture(self.root, self.policy, self.executor)
        self.bundle = make_bundle(self.policy); self.candidate_id = str(uuid4())
        self.receipt = self.verifier.verify(self.bundle, self.candidate_id, str(uuid4()))
        self.publisher = publication.Publisher.for_fixture(self.root, self.policy)

    def git(self, repository, args, data=None):
        env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
               "GIT_AUTHOR_NAME": "Fixture", "GIT_COMMITTER_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
        command = [self.git_binary] + (["--git-dir=" + str(repository)] if repository else []) + args
        return subprocess.run(command, input=data, capture_output=True, env=env, check=True).stdout

    def head(self): return self.git(self.remote, ["rev-parse", "refs/heads/main"]).strip().decode()
    def publish(self, key=None):
        return self.publisher.publish(self.bundle, self.candidate_id, self.receipt["verification_id"], key or str(uuid4()))

    def test_real_commit_contains_exact_cas_bytes_and_single_parent(self):
        result = self.publish()
        self.assertTrue(result["published"]); self.assertFalse(result["authorization"])
        self.assertEqual(result["trust_mode"], "fixture")
        self.assertEqual(self.head(), result["commit"])
        self.assertEqual(self.git(self.remote, ["show", result["commit"] + ":program.py"]), PROGRAM)
        self.assertEqual(self.git(self.remote, ["rev-list", "--parents", "-n", "1", result["commit"]]).strip().decode().split(), [result["commit"], self.baseline])

    def test_retry_reconciles_without_another_commit_or_ref_effect(self):
        key = str(uuid4()); first = self.publish(key)
        with mock.patch.object(self.publisher, "_build", side_effect=AssertionError("no duplicate commit")), mock.patch.object(self.publisher, "_update_ref", side_effect=AssertionError("no duplicate update")):
            second = self.publish(key)
        self.assertEqual(first["commit"], second["commit"])
        self.assertTrue(second["reconciled"])

    def test_ref_effect_then_error_preserves_commit_for_recovery(self):
        key = str(uuid4()); original = self.publisher._update_ref
        def changed_then_error(commit):
            original(commit)
            raise publication.AdapterError("simulated_lost_readback")
        with mock.patch.object(self.publisher, "_update_ref", side_effect=changed_then_error), self.assertRaisesRegex(publication.AdapterError, "publication_effect_unknown"):
            self.publish(key)
        observed = self.head()
        with mock.patch.object(self.publisher, "_build", side_effect=AssertionError("no duplicate")):
            result = self.publish(key)
        self.assertEqual(result["commit"], observed)

    def test_unknown_effect_blocks_conflicting_request(self):
        key = str(uuid4())
        with mock.patch.object(self.publisher, "_update_ref", side_effect=publication.AdapterError("interrupted")), self.assertRaises(publication.AdapterError):
            self.publish(key)
        with self.assertRaisesRegex(publication.AdapterError, "publication_target_busy"):
            self.publish()
        self.assertEqual(self.head(), self.baseline)

    def test_wrong_candidate_or_receipt_cannot_publish(self):
        changed = make_bundle(self.policy, PROGRAM + b"# different\n")
        with self.assertRaisesRegex(publication.AdapterError, "verification_record_binding"):
            self.publisher.publish(changed, self.candidate_id, self.receipt["verification_id"], str(uuid4()))
        self.assertEqual(self.head(), self.baseline)

    def test_failed_oracle_does_not_publish(self):
        bundle = make_bundle(self.policy, PROGRAM.replace(b"b'result'", b"b'wrong'"))
        candidate = str(uuid4()); receipt = self.verifier.verify(bundle, candidate, str(uuid4()))
        with self.assertRaisesRegex(publication.AdapterError, "verification_not_release_eligible"):
            self.publisher.publish(bundle, candidate, receipt["verification_id"], str(uuid4()))
        self.assertEqual(self.head(), self.baseline)

    def test_safety_oracle_success_is_not_release_permission(self):
        policy = copy.deepcopy(self.policy); policy["oracle"]["purpose"] = "safety"
        policy["verification"]["state_root"] = str(self.root / "safety-state")
        verifier = verification.Verifier.for_fixture(self.root, policy, self.executor)
        bundle = make_bundle(policy); candidate = str(uuid4())
        receipt = verifier.verify(bundle, candidate, str(uuid4()))
        self.assertEqual(receipt["outcome"], "verified")
        publisher = publication.Publisher.for_fixture(self.root, policy)
        with self.assertRaisesRegex(publication.AdapterError, "verification_not_release_eligible"):
            publisher.publish(bundle, candidate, receipt["verification_id"], str(uuid4()))

    def test_expiry_during_transfer_blocks_ref_change(self):
        original = self.publisher._transfer_objects
        later = verification.utcnow() + timedelta(hours=2)
        def slow_transfer(commit):
            original(commit)
            self.clock_patch = mock.patch.object(verification, "utcnow", return_value=later)
            self.clock_patch.start(); self.addCleanup(self.clock_patch.stop)
        with mock.patch.object(self.publisher, "_transfer_objects", side_effect=slow_transfer), self.assertRaisesRegex(publication.AdapterError, "verification_expired"):
            self.publish()
        self.assertEqual(self.head(), self.baseline)

    def test_changed_branch_baseline_blocks_publication(self):
        tree = self.git(self.remote, ["rev-parse", self.baseline + "^{tree}"]).strip().decode()
        changed = self.git(self.remote, ["commit-tree", tree, "-p", self.baseline], b"other\n").strip().decode()
        self.git(self.remote, ["update-ref", "refs/heads/main", changed, self.baseline])
        with self.assertRaisesRegex(publication.AdapterError, "publication_preparation_failed"):
            self.publish()
        self.assertEqual(self.head(), changed)

    def test_initial_symbolic_target_is_rejected(self):
        self.git(self.remote, ["update-ref", "refs/heads/other", self.baseline])
        self.git(self.remote, ["symbolic-ref", "refs/heads/main", "refs/heads/other"])
        with self.assertRaises(publication.AdapterError): self.publish()
        self.assertEqual(self.git(self.remote, ["rev-parse", "refs/heads/other"]).strip().decode(), self.baseline)

    def test_symref_race_never_updates_other_ref(self):
        self.git(self.remote, ["update-ref", "refs/heads/other", self.baseline])
        original = self.publisher._git
        def race(repository, args, *positional, **kwargs):
            if args[:2] == ["update-ref", "--no-deref"]:
                self.git(self.remote, ["symbolic-ref", "refs/heads/main", "refs/heads/other"])
            return original(repository, args, *positional, **kwargs)
        with mock.patch.object(self.publisher, "_git", side_effect=race):
            try: self.publish()
            except publication.AdapterError: pass
        self.assertEqual(self.git(self.remote, ["rev-parse", "refs/heads/other"]).strip().decode(), self.baseline)

    def test_receive_and_reference_hooks_are_not_executed(self):
        hooks = self.remote / "hooks"; hooks.mkdir(exist_ok=True)
        marker = self.root / "hook-ran"
        for name in ("pre-receive", "reference-transaction"):
            hook = hooks / name
            hook.write_text("#!/bin/sh\nprintf executed > '" + marker.as_posix() + "'\nexit 1\n")
            hook.chmod(0o755)
        self.publish()
        self.assertFalse(marker.exists())

    def test_include_and_alternates_are_rejected(self):
        config = self.remote / "config"; original = config.read_bytes()
        config.write_bytes(original + b'\n[include]\npath = /untrusted/config\n')
        with self.assertRaisesRegex(publication.AdapterError, "unsafe_git_configuration"): self.publish()
        config.write_bytes(original)
        alternate = self.remote / "objects/info/alternates"
        alternate.parent.mkdir(exist_ok=True); alternate.write_text("/untrusted/objects\n")
        with self.assertRaisesRegex(publication.AdapterError, "bare_repository_indirection"): self.publish()

    def test_inherited_git_environment_cannot_select_other_repo(self):
        with mock.patch.dict(os.environ, {"GIT_DIR": str(self.root / "wrong"), "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": "/untrusted", "GIT_SSH_COMMAND": "untrusted"}):
            result = self.publish()
        self.assertEqual(self.head(), result["commit"])

    def test_network_transport_has_no_fixture_escape(self):
        policy = copy.deepcopy(self.policy); policy["publication"]["transport"] = "https"
        policy["publication"]["remote"] = "https://example.invalid/repo.git"
        with self.assertRaisesRegex(publication.AdapterError, "remote_ref_cas_adapter_unavailable"):
            publication.Publisher.for_fixture(self.root, policy)

    def test_policy_mutation_is_rejected(self):
        self.publisher.policy["publication"]["allowed_paths"].append("other")
        with self.assertRaisesRegex(publication.AdapterError, "publication_binding|publication_policy_changed"):
            self.publish()

    def workflow(self):
        root = self.root / "intake"; root.mkdir()
        store = storage.CandidateStore(root, fixture_mode=True)
        self.addCleanup(store.close)
        uid = self.policy["principals"]["worker_uid"]
        bound = self.bundle["binding"]
        store.enroll(bound, uid)
        for digest, data in self.bundle["blobs"].items(): store.put_blob(bound["enrollment_id"], uid, data, digest)
        workflow = publication.FixtureAdapterWorkflow(store, self.verifier, self.publisher)
        client = broker.FixtureBroker(store, {bound["enrollment_id"]: uid}, workflow=workflow)
        staged = client.handle_fixture(raw(request(bound, self.bundle["files"])), uid)
        return store, client, uid, staged

    def test_fixture_json_stage_verify_publish_is_connected(self):
        store, client, uid, staged = self.workflow()
        verified = client.handle_fixture(raw(request(self.bundle["binding"], operation="verify", candidate=staged)), uid)
        self.assertEqual(verified["status"], "verified")
        publish_request = request(self.bundle["binding"], operation="publish", candidate=staged)
        publish_request["payload"]["verification_id"] = verified["verification_id"]
        result = client.handle_fixture(raw(publish_request), uid)
        self.assertEqual(result["status"], "published")
        self.assertEqual(self.head(), result["commit"])
        self.assertFalse(result["authorization"] or result["peer_authenticated"] or result["p2_isolation_verified"])
        self.assertEqual(client.handle_fixture(raw(publish_request), uid)["commit"], result["commit"])

    def test_legacy_blocked_nonce_does_not_upgrade_when_adapters_attached(self):
        store, client, uid, staged = self.workflow()
        req = request(self.bundle["binding"], operation="verify", candidate=staged)
        old = store.process(raw(req), uid)
        self.assertEqual(old["error_code"], "adapter_unavailable")
        with mock.patch.object(self.verifier, "verify", side_effect=AssertionError("no upgrade")):
            after = client.handle_fixture(raw(req), uid)
        self.assertEqual(after["error_code"], "adapter_unavailable")

    def test_adapter_nonce_changes_and_peer_changes_rejected(self):
        store, client, uid, staged = self.workflow()
        req = request(self.bundle["binding"], operation="verify", candidate=staged)
        self.assertEqual(client.handle_fixture(raw(req), uid)["status"], "verified")
        req["request_id"] = str(uuid4())
        self.assertEqual(client.handle_fixture(raw(req), uid)["error_code"], "idempotency_conflict")
        self.assertEqual(client.handle_fixture(raw(req), uid + 1)["error_code"], "peer_not_enrolled")


if __name__ == "__main__": unittest.main()
