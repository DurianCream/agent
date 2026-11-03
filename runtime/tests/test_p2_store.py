import copy
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest import mock
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import p2_store as s
from control_contracts import canonical_digest, ControlContractError


def binding():
    return {"repository_id": "multi", "task_id": "fixture-task", "enrollment_id": str(uuid4()),
            "base_commit": "a" * 40, "policy_digest": "sha256:" + "b" * 64,
            "scope": {"project": "multi", "service": "agent-framework", "environment": "development", "issue": "fixture"}}


def request(bound, files=None, operation="stage", candidate=None):
    payload = {"files": files, "manifest_digest": canonical_digest(files)} if operation == "stage" else {
        "candidate_id": candidate["candidate_id"], "candidate_digest": candidate["candidate_digest"]}
    if operation == "publish":
        payload["verification_id"] = str(uuid4())
    return {"schema_version": "0.1.0", "operation": operation, "request_id": str(uuid4()),
            "idempotency_key": str(uuid4()), "binding": copy.deepcopy(bound), "payload": payload}


def raw(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


class StoreTests(unittest.TestCase):
    def setUp(self):
        parent = Path(os.environ["P2_TEST_TMP"]) if "P2_TEST_TMP" in os.environ else Path(__file__).resolve().parents[2] / "work/p2-store-tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = s.CandidateStore(self.root, fixture_mode=True)
        self.addCleanup(self.store.close)
        self.bound = binding()
        self.uid = 21001
        self.store.enroll(self.bound, self.uid)
        self.data = b"hello\n"
        self.digest = "sha256:" + hashlib.sha256(self.data).hexdigest()
        self.store.put_blob(self.bound["enrollment_id"], self.uid, self.data, self.digest)
        self.files = [{"path": "docs/fixture.txt", "kind": "blob", "mode": "100644",
                       "size": len(self.data), "digest": self.digest}]

    def process(self, value):
        return self.store.process(raw(value), self.uid)

    def counts(self):
        with closing(sqlite3.connect(self.store.db_path)) as db, db:
            return {name: db.execute("SELECT COUNT(*) FROM " + name).fetchone()[0]
                    for name in ("requests", "events", "candidates", "blobs")}

    def test_stage_materializes_only_manifest_and_revalidates_blobs(self):
        result = self.process(request(self.bound, self.files))
        self.assertEqual(result["status"], "staged")
        self.assertFalse(result["authorization"] or result["published"])
        candidate = self.store.candidate(self.bound["enrollment_id"], self.uid, result["candidate_id"], result["candidate_digest"])
        self.assertEqual(candidate["files"], self.files)
        self.assertFalse((self.root / "docs").exists())

    def test_identical_retry_returns_same_candidate_without_extra_events(self):
        req = request(self.bound, self.files)
        first = self.process(req)
        counts = self.counts()
        second = self.process(req)
        self.assertTrue(second["replayed"])
        self.assertEqual(first["candidate_id"], second["candidate_id"])
        self.assertEqual(self.counts(), counts)

    def test_retry_after_reopening_is_durable(self):
        req = request(self.bound, self.files)
        first = self.process(req)
        self.store.close()
        self.store = s.CandidateStore(self.root, fixture_mode=True)
        self.addCleanup(self.store.close)
        self.assertEqual(self.process(req)["candidate_id"], first["candidate_id"])

    def test_idempotency_change_is_rejected(self):
        req = request(self.bound, self.files)
        self.process(req)
        req["request_id"] = str(uuid4())
        with self.assertRaisesRegex(s.StoreError, "idempotency_conflict"):
            self.process(req)

    def test_request_id_cannot_be_reused_with_another_key(self):
        req = request(self.bound, self.files)
        self.process(req)
        req["idempotency_key"] = str(uuid4())
        with self.assertRaisesRegex(s.StoreError, "request_id_conflict"):
            self.process(req)

    def test_other_peer_cannot_read_enrollment_or_candidate(self):
        result = self.process(request(self.bound, self.files))
        with self.assertRaisesRegex(s.StoreError, "enrollment_unavailable"):
            self.store.candidate(self.bound["enrollment_id"], self.uid + 1, result["candidate_id"], result["candidate_digest"])

    def test_one_enrollment_per_uid_even_after_revocation(self):
        other = binding()
        with self.assertRaisesRegex(s.StoreError, "worker_uid_unavailable"):
            self.store.enroll(other, self.uid)
        self.store.revoke(self.bound["enrollment_id"])
        with self.assertRaisesRegex(s.StoreError, "worker_uid_unavailable"):
            self.store.enroll(other, self.uid)
        with self.assertRaisesRegex(s.StoreError, "enrollment_unavailable"):
            self.process(request(self.bound, self.files))

    def test_existing_enrollment_cannot_change_scope_or_uid(self):
        self.store.enroll(self.bound, self.uid)
        changed = copy.deepcopy(self.bound)
        changed["scope"]["issue"] = "changed"
        with self.assertRaisesRegex(s.StoreError, "enrollment_conflict"):
            self.store.enroll(changed, self.uid)
        with self.assertRaisesRegex(s.StoreError, "enrollment_conflict"):
            self.store.enroll(self.bound, self.uid + 1)

    def test_scope_tampering_rejected_before_admission(self):
        req = request(self.bound, self.files)
        req["binding"]["scope"]["environment"] = "production"
        with self.assertRaises(ControlContractError):
            self.process(req)
        self.assertEqual(self.counts()["requests"], 0)

    def test_blob_from_other_enrollment_cannot_be_claimed_by_digest(self):
        other = binding()
        self.store.enroll(other, self.uid + 1)
        result = self.store.process(raw(request(other, self.files)), self.uid + 1)
        self.assertEqual((result["status"], result["error_code"]), ("blocked", "blob_unavailable"))

    def test_missing_blob_or_wrong_descriptor_size_blocks_stage(self):
        for field, value in (("digest", "sha256:" + "c" * 64), ("size", 99)):
            files = copy.deepcopy(self.files)
            files[0][field] = value
            result = self.process(request(self.bound, files))
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["error_code"], "blob_unavailable")

    def test_blob_bytes_must_match_digest_and_size_limit(self):
        with self.assertRaisesRegex(s.StoreError, "blob_digest"):
            self.store.put_blob(self.bound["enrollment_id"], self.uid, b"different", self.digest)
        with mock.patch.object(s.contract, "MAX_FILE_BYTES", 1), self.assertRaisesRegex(s.StoreError, "blob_size"):
            self.store.put_blob(self.bound["enrollment_id"], self.uid, self.data, self.digest)

    def test_internal_io_cannot_escape_store_namespace(self):
        for folder, name in (("blobs", "../outside"), ("blobs", ".."), ("../outside", "x")):
            with self.assertRaisesRegex(s.StoreError, "unsafe_internal_name"):
                self.store._write_once(folder, name, b"not written")
            with self.assertRaisesRegex(s.StoreError, "unsafe_internal_name"):
                self.store._read(folder, name, 64)
        self.assertFalse((self.root / "outside").exists())

    def test_tampered_blob_and_replay_are_rejected(self):
        req = request(self.bound, self.files)
        self.process(req)
        (self.root / "blobs" / self.digest[7:]).write_bytes(b"evil!!")
        with self.assertRaisesRegex(s.StoreError, "blob_corrupt"):
            self.process(req)

    def test_tampered_candidate_manifest_is_rejected(self):
        result = self.process(request(self.bound, self.files))
        (self.root / "candidates" / (result["candidate_id"] + ".json")).write_bytes(b"{}")
        with self.assertRaisesRegex(s.StoreError, "candidate_corrupt"):
            self.store.candidate(self.bound["enrollment_id"], self.uid, result["candidate_id"], result["candidate_digest"])

    def test_delete_descriptor_does_not_delete_host_file(self):
        target = self.root / "keep.txt"
        target.write_text("keep")
        result = self.process(request(self.bound, [{"path": "keep.txt", "kind": "delete"}]))
        self.assertEqual(result["status"], "staged")
        self.assertEqual(target.read_text(), "keep")

    def test_verify_and_publish_are_terminal_blocked_and_replay_stays_blocked(self):
        candidate = self.process(request(self.bound, self.files))
        for operation in ("verify", "publish"):
            req = request(self.bound, operation=operation, candidate=candidate)
            first, second = self.process(req), self.process(req)
            self.assertEqual(first["error_code"], "adapter_unavailable")
            self.assertEqual(second["status"], "blocked")
            self.assertTrue(second["replayed"])
            self.assertFalse(second["authorization"] or second["published"])

    def test_forged_success_in_ledger_never_becomes_authority(self):
        for changes in ({"status": "published"}, {"authorization": True}, {"published": True}, {"extra": "unexpected"}):
            req = request(self.bound, self.files)
            result = self.process(req)
            result.update(changes)
            with closing(sqlite3.connect(self.store.db_path)) as db, db:
                db.execute("UPDATE requests SET response=? WHERE idempotency=?", (raw(result), req["idempotency_key"]))
            with self.assertRaisesRegex(s.StoreError, "ledger_corrupt"):
                self.process(req)

    def test_request_quota_does_not_grow_denial_records_or_break_replay(self):
        with mock.patch.object(s, "MAX_ENROLLMENT_REQUESTS", 1):
            req = request(self.bound, self.files)
            self.process(req)
            counts = self.counts()
            with self.assertRaisesRegex(s.StoreError, "request_quota"):
                self.process(request(self.bound, self.files))
            self.assertEqual(self.counts(), counts)
            self.assertTrue(self.process(req)["replayed"])

    def test_store_byte_and_object_quota_preserve_existing_blob(self):
        with mock.patch.object(s, "MAX_STORE_BYTES", len(self.data)), mock.patch.object(s, "MAX_OBJECTS", 1):
            self.store.put_blob(self.bound["enrollment_id"], self.uid, self.data, self.digest)
            extra = b"x"
            with self.assertRaisesRegex(s.StoreError, "store_quota"):
                self.store.put_blob(self.bound["enrollment_id"], self.uid, extra, "sha256:" + hashlib.sha256(extra).hexdigest())
        self.assertEqual(self.counts()["blobs"], 1)

    def test_per_enrollment_blob_quota(self):
        with mock.patch.object(s.contract, "MAX_TOTAL_BYTES", len(self.data)):
            with self.assertRaisesRegex(s.StoreError, "enrollment_blob_quota"):
                self.store.put_blob(self.bound["enrollment_id"], self.uid, b"x", "sha256:" + hashlib.sha256(b"x").hexdigest())

    def test_candidate_quota_has_no_false_stage(self):
        with mock.patch.object(s, "MAX_ENROLLMENT_CANDIDATES", 0):
            result = self.process(request(self.bound, self.files))
        self.assertEqual((result["status"], result["error_code"]), ("blocked", "candidate_quota"))
        self.assertEqual(self.counts()["candidates"], 0)

    def test_transaction_failure_is_not_completed_or_automatically_reexecuted(self):
        req = request(self.bound, self.files)
        with closing(sqlite3.connect(self.store.db_path)) as db, db:
            db.execute("CREATE TRIGGER fail_candidate BEFORE INSERT ON candidates BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.process(req)
        self.assertEqual(self.counts()["candidates"], 0)
        with closing(sqlite3.connect(self.store.db_path)) as db, db:
            db.execute("DROP TRIGGER fail_candidate")
        self.assertEqual(self.process(req)["status"], "in_progress")
        self.store.mark_interrupted(self.bound["enrollment_id"], req["idempotency_key"])
        self.assertEqual(self.process(req)["status"], "unknown")

    def test_concurrent_identical_requests_have_one_candidate(self):
        req = request(self.bound, self.files)
        results, errors = [], []
        def invoke():
            try:
                results.append(self.process(req))
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=invoke) for _ in range(4)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(10)
        self.assertFalse(errors)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(self.counts()["candidates"], 1)
        self.assertEqual(self.counts()["requests"], 1)
        self.assertTrue(any(item["status"] == "staged" for item in results))

    def test_hardlinked_ledger_is_rejected(self):
        linked = self.root / "alias.sqlite3"
        try:
            os.link(self.store.db_path, linked)
        except OSError as error:
            self.skipTest("Host cannot create fixture hardlinks: " + type(error).__name__)
        with self.assertRaisesRegex(s.StoreError, "unsafe_file"):
            self.store.expected_binding(self.bound["enrollment_id"], self.uid)

    def test_symlinked_blob_is_rejected_without_reading_target(self):
        blob = self.root / "blobs" / self.digest[7:]
        target = self.root / "outside.txt"
        target.write_bytes(self.data)
        blob.unlink()
        try:
            blob.symlink_to(target)
        except OSError as error:
            self.skipTest("Host cannot create fixture symlinks: " + type(error).__name__)
        result = self.process(request(self.bound, self.files))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error_code"], "unsafe_file")

    def test_production_has_no_windows_fixture_fallback(self):
        if sys.platform == "linux":
            self.skipTest("Windows refusal case only; Linux configuration checks tested separately")
        with self.assertRaisesRegex(s.StoreError, "production_identity_unavailable"):
            s.CandidateStore(self.root)


if __name__ == "__main__":
    unittest.main()
