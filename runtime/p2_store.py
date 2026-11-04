"""P2 candidate intake and durable consistency ledger; no execution or publisher.

Production storage requires a private Linux service-owned root outside worker
write access. The explicit fixture mode provides consistency tests only. This
module's numeric peer argument is not authentication: only a trusted transport
may supply it. Blob upload transport, trusted verification and publication are
not implemented. Candidate paths are data; no candidate tree is executed/extracted.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
from uuid import uuid4

import p2_contracts as contract
from control_contracts import canonical_digest, load_json, MAX_INPUT_BYTES

MAX_OBJECTS = 4096
MAX_STORE_BYTES = 1024 * 1024 * 1024
MAX_REQUESTS = 10000
MAX_CANDIDATES = 1000
MAX_ENROLLMENTS = 128
MAX_ENROLLMENT_REQUESTS = 1024
MAX_ENROLLMENT_CANDIDATES = 128
MAX_LEDGER_BYTES = 32 * 1024 * 1024


class StoreError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__("P2 store rejected the operation: " + code)


def require(value, code):
    if not value:
        raise StoreError(code)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def reparse(value):
    return stat.S_ISLNK(value.st_mode) or bool(getattr(value, "st_file_attributes", 0) & 0x400)


def check_protected_path(path, *, owner, directory, root_only=False):
    """Linux ownership check. Never falls back to fixture behavior."""
    require(sys.platform == "linux", "production_platform_unavailable")
    path = Path(path)
    require(path.is_absolute() and ".." not in path.parts, "unsafe_root")
    for part in [*reversed(path.parents), path]:
        info = part.lstat()
        require(not reparse(info), "unsafe_link")
        allowed = {0} if root_only or part != path else {owner}
        # Root-owned ancestors are required for root-only config; service-owned
        # ancestors are also allowed for its private data root.
        if not root_only and part != path:
            allowed = {0, owner}
        require(info.st_uid in allowed and info.st_mode & 0o022 == 0, "untrusted_ownership")
        require(stat.S_ISDIR(info.st_mode) if part != path or directory else stat.S_ISREG(info.st_mode), "unsafe_type")
    return path.lstat()


class CandidateStore:
    def __init__(self, root, *, fixture_mode=False):
        self.root = Path(root).absolute()
        self.fixture_mode = fixture_mode is True
        require(type(fixture_mode) is bool, "invalid_mode")
        info = self.root.lstat()
        require(not reparse(info) and stat.S_ISDIR(info.st_mode), "unsafe_root")
        if not self.fixture_mode:
            require(sys.platform == "linux" and os.geteuid() != 0, "production_identity_unavailable")
            check_protected_path(self.root, owner=os.geteuid(), directory=True)
            require(stat.S_IMODE(info.st_mode) == 0o700, "state_root_not_private")
        self.identity = (info.st_dev, info.st_ino)
        self._fds = {}
        for name in ("blobs", "candidates"):
            folder = self.root / name
            try:
                folder.mkdir(mode=0o700)
            except FileExistsError:
                pass
            self._directory(folder)
            if os.name == "posix":
                self._fds[name] = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.db_path = self.root / "ledger.sqlite3"
        if not self.db_path.exists() and not self.db_path.is_symlink():
            fd = os.open(self.db_path, os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
            os.close(fd)
        with self._transaction() as db:
            schema = """
                CREATE TABLE IF NOT EXISTS enrollments(id TEXT PRIMARY KEY, binding BLOB NOT NULL,
                    worker_uid INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
                CREATE UNIQUE INDEX IF NOT EXISTS one_worker_identity ON enrollments(worker_uid);
                CREATE TABLE IF NOT EXISTS blobs(digest TEXT PRIMARY KEY, size INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS enrollment_blobs(enrollment TEXT NOT NULL, digest TEXT NOT NULL,
                    PRIMARY KEY(enrollment,digest));
                CREATE TABLE IF NOT EXISTS candidates(id TEXT PRIMARY KEY, enrollment TEXT NOT NULL,
                    digest TEXT NOT NULL, UNIQUE(enrollment,digest));
                CREATE TABLE IF NOT EXISTS requests(enrollment TEXT NOT NULL, worker_uid INTEGER NOT NULL,
                    idempotency TEXT NOT NULL, request_id TEXT NOT NULL, digest TEXT NOT NULL,
                    operation TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('admitted','staged','blocked','unknown')),
                    response BLOB, PRIMARY KEY(enrollment,worker_uid,idempotency), UNIQUE(enrollment,request_id));
                CREATE TABLE IF NOT EXISTS events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    enrollment TEXT NOT NULL, request_id TEXT NOT NULL, state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS fixture_adapter_calls(enrollment TEXT NOT NULL, worker_uid INTEGER NOT NULL,
                    idempotency TEXT NOT NULL, request_id TEXT NOT NULL, digest TEXT NOT NULL, backend_key TEXT NOT NULL,
                    state TEXT NOT NULL, error_code TEXT, PRIMARY KEY(enrollment,worker_uid,idempotency), UNIQUE(enrollment,request_id));
            """
            for statement in schema.split(";"):
                if statement.strip():
                    db.execute(statement)

    def close(self):
        for fd in self._fds.values():
            os.close(fd)
        self._fds.clear()

    def _directory(self, path):
        info = path.lstat()
        require(not reparse(info) and stat.S_ISDIR(info.st_mode), "unsafe_directory")
        if not self.fixture_mode:
            require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700, "unsafe_directory")

    def _root_check(self):
        info = self.root.lstat()
        require(not reparse(info) and (info.st_dev, info.st_ino) == self.identity, "state_root_changed")
        if not self.fixture_mode:
            check_protected_path(self.root, owner=os.geteuid(), directory=True)
            require(stat.S_IMODE(info.st_mode) == 0o700, "state_root_not_private")
        for name in ("blobs", "candidates"):
            self._directory(self.root / name)
            if name in self._fds:
                actual = (self.root / name).stat()
                opened = os.fstat(self._fds[name])
                require((actual.st_dev, actual.st_ino) == (opened.st_dev, opened.st_ino), "store_directory_changed")

    def _regular(self, info):
        require(not reparse(info) and stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "unsafe_file")
        if not self.fixture_mode:
            require(info.st_uid == os.geteuid() and info.st_mode & 0o077 == 0, "unsafe_file")

    def _read(self, folder, name, limit):
        self._root_check()
        require(folder in ("blobs", "candidates") and type(name) is str and
                re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}", name) is not None, "unsafe_internal_name")
        path = self.root / folder / name
        self._regular(path.lstat())
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = (os.open(name, flags, dir_fd=self._fds[folder]) if folder in self._fds else os.open(path, flags))
        try:
            before = os.fstat(fd)
            self._regular(before)
            require(before.st_size <= limit, "object_too_large")
            with os.fdopen(os.dup(fd), "rb") as stream:
                data = stream.read(limit + 1)
            after = os.fstat(fd)
            current = path.lstat()
            self._regular(current)
            require(len(data) <= limit and len(data) == before.st_size and
                    (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) and
                    (current.st_dev, current.st_ino) == (before.st_dev, before.st_ino), "object_changed")
            return data
        finally:
            os.close(fd)

    def _write_once(self, folder, name, data):
        self._root_check()
        require(folder in ("blobs", "candidates") and type(name) is str and
                re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}", name) is not None, "unsafe_internal_name")
        final = self.root / folder / name
        if final.exists() or final.is_symlink():
            require(self._read(folder, name, len(data)) == data, "immutable_object_conflict")
            return
        temporary = ".tmp-" + uuid4().hex
        path = self.root / folder / temporary
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(temporary, flags, 0o600, dir_fd=self._fds[folder]) if folder in self._fds else os.open(path, flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                if not self.fixture_mode:
                    os.fchmod(stream.fileno(), 0o400)
                os.fsync(stream.fileno())
            # An exclusive hard-link publish never overwrites an existing object.
            # Remove the temporary name before any successful return/read.
            try:
                if folder in self._fds:
                    os.link(temporary, name, src_dir_fd=self._fds[folder], dst_dir_fd=self._fds[folder], follow_symlinks=False)
                else:
                    os.link(path, final, follow_symlinks=False)
            except FileExistsError:
                pass
        finally:
            if folder in self._fds:
                os.unlink(temporary, dir_fd=self._fds[folder])
            else:
                path.unlink(missing_ok=True)
        if folder in self._fds:
            os.fsync(self._fds[folder])
        require(self._read(folder, name, len(data)) == data, "immutable_object_conflict")

    def _db_safe(self):
        self._root_check()
        for suffix in ("", "-journal", "-wal", "-shm"):
            path = Path(str(self.db_path) + suffix)
            if path.exists() or path.is_symlink():
                self._regular(path.lstat())

    @contextmanager
    def _transaction(self):
        self._db_safe()
        db = sqlite3.connect(self.db_path, timeout=5, isolation_level=None)
        try:
            db.execute("PRAGMA synchronous=FULL")
            page_size = db.execute("PRAGMA page_size").fetchone()[0]
            require(db.execute("PRAGMA page_count").fetchone()[0] * page_size <= MAX_LEDGER_BYTES, "ledger_quota")
            db.execute("PRAGMA max_page_count=" + str(MAX_LEDGER_BYTES // page_size))
            db.execute("BEGIN IMMEDIATE")
            yield db
            if db.in_transaction:
                db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    @staticmethod
    def _uid(uid):
        require(type(uid) is int and 0 < uid < (1 << 32), "invalid_worker_uid")

    def enroll(self, binding, worker_uid):
        """Trusted installation API, never exposed as a worker request."""
        contract.binding(binding)
        self._uid(worker_uid)
        if not self.fixture_mode:
            require(worker_uid != os.geteuid(), "worker_is_controller")
        data = encoded(binding)
        with self._transaction() as db:
            row = db.execute("SELECT binding,worker_uid,revoked FROM enrollments WHERE id=?", (binding["enrollment_id"],)).fetchone()
            if row:
                require(row == (data, worker_uid, 0), "enrollment_conflict")
                return
            require(db.execute("SELECT 1 FROM enrollments WHERE worker_uid=?", (worker_uid,)).fetchone() is None,
                    "worker_uid_unavailable")
            require(db.execute("SELECT COUNT(*) FROM enrollments").fetchone()[0] < MAX_ENROLLMENTS, "enrollment_quota")
            db.execute("INSERT INTO enrollments(id,binding,worker_uid) VALUES(?,?,?)", (binding["enrollment_id"], data, worker_uid))

    def revoke(self, enrollment_id):
        """Trusted maintenance; it never releases a UID for another enrollment.

        Worker termination and safe OS identity recycling are not implemented.
        """
        contract.uuid4(enrollment_id)
        with self._transaction() as db:
            db.execute("UPDATE enrollments SET revoked=1 WHERE id=?", (enrollment_id,))

    @staticmethod
    def _binding(db, enrollment_id, uid):
        row = db.execute("SELECT binding,worker_uid,revoked FROM enrollments WHERE id=?", (enrollment_id,)).fetchone()
        require(row is not None and row[1] == uid and row[2] == 0, "enrollment_unavailable")
        return load_json(row[0])

    def expected_binding(self, enrollment_id, uid):
        contract.uuid4(enrollment_id)
        self._uid(uid)
        with self._transaction() as db:
            return self._binding(db, enrollment_id, uid)

    def put_blob(self, enrollment_id, uid, data, expected_digest):
        """Trusted intake API; the broker authenticates upload and enrollment."""
        contract.digest(expected_digest)
        contract.uuid4(enrollment_id)
        self._uid(uid)
        require(type(data) is bytes and len(data) <= contract.MAX_FILE_BYTES, "blob_size")
        require("sha256:" + hashlib.sha256(data).hexdigest() == expected_digest, "blob_digest")
        with self._transaction() as db:
            self._binding(db, enrollment_id, uid)
            associated = db.execute("SELECT COUNT(*),COALESCE(SUM(b.size),0) FROM enrollment_blobs e JOIN blobs b ON b.digest=e.digest WHERE e.enrollment=?",
                                    (enrollment_id,)).fetchone()
            already = db.execute("SELECT 1 FROM enrollment_blobs WHERE enrollment=? AND digest=?", (enrollment_id, expected_digest)).fetchone()
            require(associated[0] + (0 if already else 1) <= contract.MAX_FILES and
                    associated[1] + (0 if already else len(data)) <= contract.MAX_TOTAL_BYTES, "enrollment_blob_quota")
            objects = list((self.root / "blobs").iterdir())
            target_exists = (self.root / "blobs" / expected_digest[7:]).exists()
            require(len(objects) + (0 if target_exists else 1) <= MAX_OBJECTS, "store_quota")
            total = 0
            for path in objects:
                self._regular(path.lstat())
                total += path.stat().st_size
            known = db.execute("SELECT size FROM blobs WHERE digest=?", (expected_digest,)).fetchone()
            require(total + (0 if target_exists else len(data)) <= MAX_STORE_BYTES, "store_quota")
            self._write_once("blobs", expected_digest[7:], data)
            db.execute("INSERT OR IGNORE INTO blobs VALUES(?,?)", (expected_digest, len(data)))
            require(db.execute("SELECT size FROM blobs WHERE digest=?", (expected_digest,)).fetchone()[0] == len(data), "blob_conflict")
            db.execute("INSERT OR IGNORE INTO enrollment_blobs VALUES(?,?)", (enrollment_id, expected_digest))
        return {"digest": expected_digest, "size": len(data), "authorization": False}

    def _verify_files(self, db, enrollment_id, files):
        contract.validate_manifest(files)
        for item in files:
            if item["kind"] == "delete":
                continue  # A descriptor only; never delete a host filesystem path.
            row = db.execute("SELECT b.size FROM blobs b JOIN enrollment_blobs e ON e.digest=b.digest WHERE e.enrollment=? AND b.digest=?",
                             (enrollment_id, item["digest"])).fetchone()
            require(row is not None and row[0] == item["size"], "blob_unavailable")
            data = self._read("blobs", item["digest"][7:], contract.MAX_FILE_BYTES)
            require(len(data) == item["size"] and "sha256:" + hashlib.sha256(data).hexdigest() == item["digest"], "blob_corrupt")

    def candidate(self, enrollment_id, uid, candidate_id, expected_digest):
        contract.uuid4(enrollment_id)
        self._uid(uid)
        contract.uuid4(candidate_id)
        contract.digest(expected_digest)
        with self._transaction() as db:
            binding = self._binding(db, enrollment_id, uid)
            return self._candidate(db, binding, candidate_id, expected_digest)

    def export_bundle(self, enrollment_id, uid, candidate_id, expected_digest):
        """Copy verified immutable input bytes for a trusted adapter.

        This is not a worker upload or authority API. Adapters must independently
        revalidate the bundle and authenticate their own service context.
        """
        contract.uuid4(enrollment_id)
        self._uid(uid)
        contract.uuid4(candidate_id)
        contract.digest(expected_digest)
        with self._transaction() as db:
            expected = self._binding(db, enrollment_id, uid)
            body = self._candidate(db, expected, candidate_id, expected_digest)
            blobs = {}
            for item in body["files"]:
                if item["kind"] == "blob":
                    value = self._read("blobs", item["digest"][7:], contract.MAX_FILE_BYTES)
                    require(len(value) == item["size"] and "sha256:" + hashlib.sha256(value).hexdigest() == item["digest"],
                            "blob_corrupt")
                    blobs[item["digest"]] = value
            return {**body, "blobs": blobs}

    def _candidate(self, db, binding, candidate_id, expected_digest):
        row = db.execute("SELECT enrollment,digest FROM candidates WHERE id=?", (candidate_id,)).fetchone()
        require(row == (binding["enrollment_id"], expected_digest), "candidate_unavailable")
        try:
            body = load_json(self._read("candidates", candidate_id + ".json", MAX_INPUT_BYTES))
        except contract.ControlContractError as error:
            raise StoreError("candidate_corrupt") from error
        require(type(body) is dict and set(body) == {"binding", "files"} and body["binding"] == binding and
                canonical_digest(body) == expected_digest, "candidate_corrupt")
        self._verify_files(db, binding["enrollment_id"], body["files"])
        return body

    def process(self, raw, uid):
        """Consistency engine; only a trusted transport may supply numeric uid."""
        self._uid(uid)
        peek = load_json(raw)
        require(type(peek) is dict and type(peek.get("binding")) is dict, "binding_unavailable")
        eid = peek["binding"].get("enrollment_id")
        expected = self.expected_binding(eid, uid)
        validated = contract.validate_request(raw, expected_binding=expected)
        request = validated.as_dict()["request"]
        key = (eid, uid, request["idempotency_key"])
        with self._transaction() as db:
            self._binding(db, eid, uid)
            old = db.execute("SELECT digest,state,response FROM requests WHERE enrollment=? AND worker_uid=? AND idempotency=?", key).fetchone()
            if old:
                require(old[0] == validated.request_digest, "idempotency_conflict")
                if old[2] is not None:
                    response = load_json(old[2])
                    staged_fields = {"status", "candidate_id", "candidate_digest", "request_id", "authorization", "published", "replayed"}
                    blocked_fields = {"status", "error_code", "request_id", "authorization", "published", "replayed"}
                    require(type(response) is dict and response.get("status") == old[1] and
                            response.get("request_id") == request["request_id"] and
                            response.get("authorization") is False and response.get("published") is False and
                            response.get("replayed") is False, "ledger_corrupt")
                    if response["status"] == "staged":
                        require(request["operation"] == "stage" and set(response) == staged_fields, "ledger_corrupt")
                        contract.uuid4(response["candidate_id"])
                        contract.digest(response["candidate_digest"])
                        self._candidate(db, expected, response["candidate_id"], response["candidate_digest"])
                    else:
                        require(response["status"] == "blocked" and set(response) == blocked_fields and
                                type(response["error_code"]) is str and re.fullmatch(r"[a-z0-9_]{1,64}", response["error_code"]), "ledger_corrupt")
                    return {**response, "replayed": True}
                require(old[1] in ("admitted", "unknown"), "ledger_corrupt")
                return {"status": "in_progress" if old[1] == "admitted" else "unknown", "authorization": False,
                        "published": False, "request_id": request["request_id"], "replayed": True}
            require(db.execute("SELECT 1 FROM requests WHERE enrollment=? AND request_id=?", (eid, request["request_id"])).fetchone() is None,
                    "request_id_conflict")
            require(db.execute("SELECT 1 FROM fixture_adapter_calls WHERE enrollment=? AND (idempotency=? OR request_id=?)",
                               (eid, request["idempotency_key"], request["request_id"])).fetchone() is None, "adapter_request_conflict")
            require(db.execute("SELECT (SELECT COUNT(*) FROM requests)+(SELECT COUNT(*) FROM fixture_adapter_calls)").fetchone()[0] < MAX_REQUESTS, "request_quota")
            require(db.execute("SELECT (SELECT COUNT(*) FROM requests WHERE enrollment=?)+(SELECT COUNT(*) FROM fixture_adapter_calls WHERE enrollment=?)", (eid, eid)).fetchone()[0] < MAX_ENROLLMENT_REQUESTS,
                    "request_quota")
            db.execute("INSERT INTO requests VALUES(?,?,?,?,?,?,?,NULL)", (*key, request["request_id"], validated.request_digest, request["operation"], "admitted"))
            db.execute("INSERT INTO events(enrollment,request_id,state) VALUES(?,?,?)", (eid, request["request_id"], "admitted"))
        # A crash after admission is never inferred as successful or reexecuted.
        with self._transaction() as db:
            require(db.execute("SELECT state FROM requests WHERE enrollment=? AND worker_uid=? AND idempotency=?", key).fetchone()[0] == "admitted",
                    "request_state_conflict")
            try:
                binding = self._binding(db, eid, uid)
                if request["operation"] == "stage":
                    files = request["payload"]["files"]
                    self._verify_files(db, eid, files)
                    body = {"binding": binding, "files": files}
                    candidate_digest = canonical_digest(body)
                    row = db.execute("SELECT id FROM candidates WHERE enrollment=? AND digest=?", (eid, candidate_digest)).fetchone()
                    if row:
                        candidate_id = row[0]
                        self._candidate(db, binding, candidate_id, candidate_digest)
                    else:
                        require(db.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] < MAX_CANDIDATES, "candidate_quota")
                        require(db.execute("SELECT COUNT(*) FROM candidates WHERE enrollment=?", (eid,)).fetchone()[0] < MAX_ENROLLMENT_CANDIDATES,
                                "candidate_quota")
                        physical = list((self.root / "candidates").iterdir())
                        require(len(physical) < MAX_CANDIDATES, "candidate_quota")
                        for path in physical:
                            self._regular(path.lstat())
                            require(path.stat().st_size <= MAX_INPUT_BYTES, "candidate_quota")
                        candidate_id = str(uuid4())
                        body_bytes = encoded(body)
                        require(len(body_bytes) <= MAX_INPUT_BYTES, "candidate_quota")
                        self._write_once("candidates", candidate_id + ".json", body_bytes)
                        db.execute("INSERT INTO candidates VALUES(?,?,?)", (candidate_id, eid, candidate_digest))
                    response = {"status": "staged", "candidate_id": candidate_id, "candidate_digest": candidate_digest}
                else:
                    self._candidate(db, binding, request["payload"]["candidate_id"], request["payload"]["candidate_digest"])
                    response = {"status": "blocked", "error_code": "adapter_unavailable"}
                response.update(request_id=request["request_id"], authorization=False, published=False, replayed=False)
            except StoreError as error:
                response = {"status": "blocked", "error_code": error.code, "request_id": request["request_id"],
                            "authorization": False, "published": False, "replayed": False}
            db.execute("UPDATE requests SET state=?,response=? WHERE enrollment=? AND worker_uid=? AND idempotency=?",
                       (response["status"], encoded(response), *key))
            db.execute("INSERT INTO events(enrollment,request_id,state) VALUES(?,?,?)", (eid, request["request_id"], response["status"]))
        return response

    def mark_interrupted(self, enrollment_id, idempotency_key):
        """Trusted stopped-service recovery only; never retries a possible effect."""
        contract.uuid4(enrollment_id)
        contract.uuid4(idempotency_key)
        with self._transaction() as db:
            db.execute("UPDATE requests SET state='unknown' WHERE enrollment=? AND idempotency=? AND state='admitted'",
                       (enrollment_id, idempotency_key))

    def fixture_adapter_call(self, raw, uid, handler):
        """Explicit fixture dispatch only; production needs protected service RPC.

        The map binds external idempotency to server-selected backend keys. It
        never trusts a cached success JSON: backend receipts/readback are checked
        again on retries. Existing stage-only blocked requests stay blocked.
        """
        require(self.fixture_mode is True, "production_adapter_transport_unavailable")
        return self._adapter_call(raw, uid, handler)

    def production_adapter_call(self, raw, uid, handler):
        """Admit only the protected local RPC workflow, retaining backend keys."""
        from p2_rpc import ProductionWorkflow
        require(self.fixture_mode is False and type(getattr(handler, '__self__', None)) is ProductionWorkflow and
                handler.__self__.store is self, 'production_rpc_workflow_required')
        return self._adapter_call(raw, uid, handler)

    def _adapter_call(self, raw, uid, handler):
        # Historical table name is retained for ledger compatibility; production
        # and fixture stores cannot share an ownership/trust mode.
        mode = 'fixture' if self.fixture_mode else 'production'
        self._uid(uid)
        peek = load_json(raw)
        require(type(peek) is dict and type(peek.get("binding")) is dict, "binding_unavailable")
        eid = peek["binding"].get("enrollment_id")
        expected = self.expected_binding(eid, uid)
        valid = contract.validate_request(raw, expected_binding=expected)
        request = valid.as_dict()["request"]
        if request["operation"] == "stage": return self.process(raw, uid)
        key = (eid, uid, request["idempotency_key"])
        legacy = False
        with self._transaction() as db:
            self._binding(db, eid, uid)
            legacy = db.execute("SELECT 1 FROM requests WHERE enrollment=? AND worker_uid=? AND idempotency=?", key).fetchone() is not None
            if not legacy:
                require(db.execute("SELECT 1 FROM requests WHERE enrollment=? AND request_id=?", (eid, request["request_id"])).fetchone() is None,
                        "request_id_conflict")
                old = db.execute("SELECT digest,backend_key,state,error_code FROM fixture_adapter_calls WHERE enrollment=? AND worker_uid=? AND idempotency=?", key).fetchone()
                if old:
                    require(old[0] == valid.request_digest, "idempotency_conflict")
                    backend_key = old[1]; contract.uuid4(backend_key)
                    if old[2] == "blocked":
                        require(type(old[3]) is str and re.fullmatch(r"[a-z0-9_]{1,64}", old[3]), "ledger_corrupt")
                        return {"status": "blocked", "error_code": old[3], "authorization": False, "published": False,
                                "trust_mode": mode, "request_id": request["request_id"], "replayed": True}
                else:
                    require(db.execute("SELECT (SELECT COUNT(*) FROM requests)+(SELECT COUNT(*) FROM fixture_adapter_calls)").fetchone()[0] < MAX_REQUESTS,
                            "request_quota")
                    require(db.execute("SELECT (SELECT COUNT(*) FROM requests WHERE enrollment=?)+(SELECT COUNT(*) FROM fixture_adapter_calls WHERE enrollment=?)", (eid,eid)).fetchone()[0] < MAX_ENROLLMENT_REQUESTS,
                            "request_quota")
                    require(db.execute("SELECT 1 FROM fixture_adapter_calls WHERE enrollment=? AND request_id=?", (eid, request["request_id"])).fetchone() is None,
                            "request_id_conflict")
                    backend_key = str(uuid4())
                    db.execute("INSERT INTO fixture_adapter_calls VALUES(?,?,?,?,?,?,?,NULL)",
                               (*key, request["request_id"], valid.request_digest, backend_key, "pending"))
        if legacy: return self.process(raw, uid)
        result = handler(request, uid, backend_key)
        try:
            # An effect may already exist. Invalid or unrecordable replies are
            # unknown, never a claim that publication did not happen.
            require(type(result) is dict and result.get("trust_mode") == mode and
                    (not self.fixture_mode or result.get("authorization") is False),
                    "fixture_adapter_false_authority")
            require(result.get("status") in ("verified", "failed", "published", "blocked", "unknown", "in_progress"), "fixture_adapter_state")
            with self._transaction() as db:
                error = result.get("error_code")
                if result["status"] == "blocked":
                    require(type(error) is str and re.fullmatch(r"[a-z0-9_]{1,64}", error), "fixture_adapter_error")
                db.execute("UPDATE fixture_adapter_calls SET state=?,error_code=? WHERE enrollment=? AND worker_uid=? AND idempotency=?",
                           (result["status"], error, *key))
        except (sqlite3.Error, OSError, StoreError):
            raise StoreError("adapter_result_not_recorded") from None
        return {**result, "request_id": request["request_id"]}
