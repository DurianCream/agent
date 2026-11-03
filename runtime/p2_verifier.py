"""Measured oracle verification adapter; fixture records are never production authority.

The first production backend is an explicitly root-approved root supervisor.
Only trusted supervisor/oracle code runs with UID0; the executor must isolate and
drop the candidate child to the distinct worker UID before release. A non-root
verifier RPC design is future work. This module never imports candidate code.
"""
from __future__ import annotations

from contextlib import contextmanager, closing
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
from types import MappingProxyType
from uuid import uuid4

import p2_contracts as contract
from control_contracts import canonical_digest, load_json, MAX_INPUT_BYTES
from p2_store import check_protected_path, reparse


class AdapterError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__("P2 adapter rejected the operation: " + code)


def require(value, code):
    if not value:
        raise AdapterError(code)


def sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def utcnow():
    return datetime.now(timezone.utc)


def _regular(path, limit=MAX_INPUT_BYTES, owner=None):
    info = Path(path).lstat()
    require(not reparse(info) and stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= limit,
            "unsafe_record")
    if owner is not None:
        require(info.st_uid == owner and info.st_mode & 0o022 == 0, "untrusted_record_owner")
    return info


def read_bytes(path, *, limit=MAX_INPUT_BYTES, owner=None):
    before = _regular(path, limit=limit, owner=owner)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        opened = os.fstat(fd)
        require((before.st_dev, before.st_ino) == (opened.st_dev, opened.st_ino), "record_changed")
        with os.fdopen(os.dup(fd), "rb") as stream:
            data = stream.read(limit + 1)
        after = os.fstat(fd)
        require(len(data) <= limit and (opened.st_size, opened.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
                "record_changed")
        return data
    finally:
        os.close(fd)


def read_record(path, owner=None):
    return load_json(read_bytes(path, owner=owner))


def check_ledger(path, owner=None):
    for suffix in ("", "-journal", "-wal", "-shm"):
        item = Path(str(path) + suffix)
        if item.exists() or item.is_symlink(): _regular(item, limit=32 * 1024 * 1024, owner=owner)


def write_record(path, value, *, receipt_gid=None):
    """Exclusive write; no caller-controlled path is accepted by adapter methods."""
    data = json_bytes(value)
    require(len(data) <= MAX_INPUT_BYTES, "record_limit")
    temporary = Path(path).parent / (".tmp-" + uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data); stream.flush()
            if receipt_gid is not None:
                os.fchown(stream.fileno(), -1, receipt_gid)
                os.fchmod(stream.fileno(), 0o440)
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
    finally:
        temporary.unlink(missing_ok=True)
    if os.name == "posix":
        directory = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(directory)
        finally: os.close(directory)


@contextmanager
def service_lock(directory):
    path = Path(directory) / "adapter.lock"
    if path.exists() or path.is_symlink():
        _regular(path, limit=1)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    locked = False
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode) and os.fstat(fd).st_nlink == 1, "unsafe_lock")
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"0"); os.fsync(fd)
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError:
            raise AdapterError("adapter_busy") from None
        yield
    finally:
        if locked:
            os.lseek(fd, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def fixture_root(root):
    root = Path(root).absolute()
    require(not str(root).startswith("\\\\"), "fixture_network_path")
    require(root.is_dir() and not reparse(root.lstat()), "fixture_root")
    marker = root / "p2-fixture.json"
    if not marker.exists():
        require(not any(root.iterdir()), "fixture_root_not_empty")
        write_record(marker, {"fixture_only": True})
    require(read_record(marker) == {"fixture_only": True}, "fixture_marker")
    return root


def fixture_path(root, path):
    path = Path(path).absolute()
    require(path.is_relative_to(root) and path != root and ".." not in path.parts, "fixture_path_escape")
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        try: info = current.lstat()
        except FileNotFoundError: continue
        require(not reparse(info), "fixture_link")
    return path


def policy_binding(policy):
    require(type(policy) is dict and set(policy) == {"schema_version", "identity", "principals", "oracle", "verification", "publication"}
            and policy["schema_version"] == "0.1.0", "policy_fields")
    identity = policy["identity"]
    require(type(identity) is dict and set(identity) == contract.BINDING_FIELDS - {"policy_digest"}, "policy_identity")
    bound = {**identity, "policy_digest": canonical_digest(policy)}
    contract.binding(bound)
    principals = policy["principals"]
    require(type(principals) is dict and set(principals) == {"verifier_uid", "worker_uid", "publisher_uid", "receipt_gid"}, "policy_principals")
    require(principals["verifier_uid"] == 0 and type(principals["verifier_uid"]) is int and
            all(type(principals[k]) is int and 0 < principals[k] < (1 << 31) for k in ("worker_uid", "publisher_uid", "receipt_gid")) and
            principals["worker_uid"] != principals["publisher_uid"], "policy_identity")
    verification = policy["verification"]
    require(type(verification) is dict and set(verification) == {"state_root", "receipt_dir", "ttl_seconds"} and
            type(verification["ttl_seconds"]) is int and 1 <= verification["ttl_seconds"] <= 3600, "verification_policy")
    for name in ("state_root", "receipt_dir"):
        require(type(verification[name]) is str and Path(verification[name]).is_absolute(), "verification_path")
    oracle = policy["oracle"]
    require(type(oracle) is dict and set(oracle) == {"purpose", "execution", "expected", "executor_config_digest"} and
            oracle["purpose"] in ("release", "safety"), "oracle_policy")
    expected = oracle["expected"]
    require(type(expected) is dict and set(expected) == {"exit_code", "stdout_digest", "stderr_digest", "outputs"}
            and type(expected["exit_code"]) is int and -255 <= expected["exit_code"] <= 255 and type(expected["outputs"]) is dict,
            "oracle_expected")
    contract.digest(expected["stdout_digest"]); contract.digest(expected["stderr_digest"])
    require(len(expected["outputs"]) <= 128, "oracle_output_limit")
    for name, digest in expected["outputs"].items(): contract.portable_path(name); contract.digest(digest)
    if oracle["executor_config_digest"] is not None: contract.digest(oracle["executor_config_digest"])
    return bound


def freeze_bundle(bundle):
    require(type(bundle) is dict and set(bundle) == {"binding", "files", "blobs"}, "bundle_fields")
    body = load_json(json_bytes({"binding": bundle["binding"], "files": bundle["files"]}))
    contract.binding(body["binding"]); contract.validate_manifest(body["files"])
    require(type(bundle["blobs"]) is dict, "bundle_blobs")
    wanted = {item["digest"] for item in body["files"] if item["kind"] == "blob"}
    require(set(bundle["blobs"]) == wanted, "bundle_blobs")
    blobs = {}
    for item in body["files"]:
        if item["kind"] == "blob":
            data = bundle["blobs"][item["digest"]]
            require(type(data) is bytes and len(data) == item["size"] and sha(data) == item["digest"], "bundle_blob_mismatch")
            blobs[item["digest"]] = data
    return {**body, "blobs": blobs}, canonical_digest(body)


def execution_profile(policy):
    executor = importlib.import_module("p2_executor")
    value = policy["oracle"]["execution"]
    fields = {"profile_id", "argv", "timeout_seconds", "memory_bytes", "cpu_seconds", "tasks", "output_bytes", "stdin_base64"}
    require(type(value) is dict and set(value) == fields and type(value["argv"]) is list and type(value["stdin_base64"]) is str,
            "execution_profile_fields")
    try: stdin = base64.b64decode(value["stdin_base64"], validate=True)
    except ValueError: raise AdapterError("execution_stdin") from None
    require(len(stdin) <= 65536, "execution_stdin")
    result = executor.ExecutionProfile(**{k: v for k, v in value.items() if k not in ("argv", "stdin_base64")},
                                       argv=tuple(value["argv"]), stdin=stdin)
    executor.execution_profile_digest(result)
    return result


class Verifier:
    def __init__(self, *args, **kwargs):
        raise AdapterError("use_verifier_factory")

    @classmethod
    def for_fixture(cls, root, policy, executor):
        root = fixture_root(root)
        obj = object.__new__(cls)
        obj.fixture_mode = True; obj.root = root
        obj._configure(policy, executor)
        for path in (obj.state, obj.receipts):
            fixture_path(root, path).mkdir(parents=True, exist_ok=True)
        obj._ledger()
        return obj

    @classmethod
    def from_protected_policy(cls, path, executor):
        require(sys.platform == "linux" and os.geteuid() == 0, "verifier_identity_unavailable")
        require(sys.flags.isolated and sys.flags.no_site, "isolated_no_site_verifier_required")
        from p2_broker import _root_controlled
        _root_controlled(path)
        obj = object.__new__(cls); obj.fixture_mode = False
        obj.policy_path = Path(path)
        obj._configure(read_record(path, owner=0), executor)
        require(obj.policy["oracle"]["executor_config_digest"] is not None, "executor_profile_unpinned")
        check_protected_path(obj.state, owner=0, directory=True)
        require(stat.S_IMODE(obj.state.stat().st_mode) == 0o700, "verifier_state_not_private")
        check_protected_path(obj.receipts, owner=0, directory=True)
        require(stat.S_IMODE(obj.receipts.stat().st_mode) == 0o750 and
                obj.receipts.stat().st_gid == obj.policy["principals"]["receipt_gid"], "receipt_directory_policy")
        obj._ledger()
        return obj

    def _configure(self, policy, executor):
        self.policy = load_json(json_bytes(policy)); self.binding = policy_binding(self.policy)
        module = importlib.import_module("p2_executor")
        expected_class = module.FixtureExecutor if self.fixture_mode else module.BwrapExecutor
        require(type(executor) is expected_class, "executor_type")
        if not self.fixture_mode:
            require(executor.config["worker_uid"] == self.policy["principals"]["worker_uid"] and
                    executor.config["publisher_uid"] == self.policy["principals"]["publisher_uid"] and
                    executor.config["enrollment_id"] == self.binding["enrollment_id"] and
                    executor.config_digest == self.policy["oracle"]["executor_config_digest"], "executor_policy_identity")
            import pwd
            publisher = pwd.getpwuid(self.policy["principals"]["publisher_uid"])
            worker = pwd.getpwuid(self.policy["principals"]["worker_uid"])
            require(self.policy["principals"]["receipt_gid"] == publisher.pw_gid and
                    publisher.pw_gid not in os.getgrouplist(worker.pw_name, executor.config["worker_gid"]), "receipt_group_separation")
        self.executor = executor; self.profile = execution_profile(self.policy)
        self.profile_digest = canonical_digest(self.policy["oracle"])
        self.state = Path(self.policy["verification"]["state_root"])
        self.receipts = Path(self.policy["verification"]["receipt_dir"])

    def _recheck(self):
        require(canonical_digest(self.policy) == self.binding["policy_digest"], "verification_policy_changed")
        if not self.fixture_mode:
            require(sys.platform == "linux" and os.geteuid() == 0, "verifier_identity_unavailable")
            from p2_broker import _root_controlled
            _root_controlled(self.policy_path)
            require(read_record(self.policy_path, owner=0) == self.policy, "verification_policy_changed")
            check_protected_path(self.state, owner=0, directory=True)
            check_protected_path(self.receipts, owner=0, directory=True)
            require(stat.S_IMODE(self.state.stat().st_mode) == 0o700 and stat.S_IMODE(self.receipts.stat().st_mode) == 0o750 and
                    self.receipts.stat().st_gid == self.policy["principals"]["receipt_gid"], "verification_directory_drift")
        else:
            fixture_path(self.root, self.state); fixture_path(self.root, self.receipts)

    def _ledger(self):
        self.db = self.state / "verification.sqlite3"
        check_ledger(self.db, owner=None if self.fixture_mode else 0)
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS verification_requests(key TEXT PRIMARY KEY,digest TEXT NOT NULL,state TEXT NOT NULL,receipt TEXT)")
        if os.name == "posix": os.chmod(self.db, 0o600)

    def verify(self, bundle, candidate_id, idempotency_key):
        contract.uuid4(candidate_id); contract.uuid4(idempotency_key)
        bundle, candidate_digest = freeze_bundle(bundle)
        require(bundle["binding"] == self.binding, "verification_binding")
        self._recheck()
        request_digest = canonical_digest({"candidate_id": candidate_id, "candidate_digest": candidate_digest,
                                           "oracle_profile_digest": self.profile_digest, "policy_digest": self.binding["policy_digest"]})
        with service_lock(self.state):
            check_ledger(self.db, owner=None if self.fixture_mode else 0)
            db = sqlite3.connect(self.db)
            try:
                old = db.execute("SELECT digest,state,receipt FROM verification_requests WHERE key=?", (idempotency_key,)).fetchone()
                if old:
                    require(old[0] == request_digest, "verification_idempotency_conflict")
                    require(old[1] in ("verified", "failed") and old[2], "verification_effect_unknown")
                    return read_verification(self.policy, old[2], candidate_id, candidate_digest, fixture_mode=self.fixture_mode)
                require(db.execute("SELECT COUNT(*) FROM verification_requests").fetchone()[0] < 1000, "verification_quota")
                db.execute("INSERT INTO verification_requests VALUES(?,?,?,NULL)", (idempotency_key, request_digest, "pending")); db.commit()
                result = self.executor.run(bundle, self.profile)
                module = importlib.import_module("p2_executor")
                require(type(result) is module.ExecutionResult and result.candidate_digest == candidate_digest and
                        result.profile_digest == module.execution_profile_digest(self.profile), "execution_binding")
                require(result.fixture_mode is self.fixture_mode, "execution_mode")
                require(type(result.timed_out) is bool and type(result.output_limited) is bool and type(result.budget_exceeded) is bool and
                        (result.exit_code is None or type(result.exit_code) is int), "execution_result_types")
                require(type(result.stdout) is bytes and type(result.stderr) is bytes and type(result.outputs) in (dict, MappingProxyType) and
                        len(result.stdout) + len(result.stderr) + sum(len(v) for v in result.outputs.values() if type(v) is bytes) <= self.profile.output_bytes,
                        "execution_output_limit")
                require(all(type(v) is bytes for v in result.outputs.values()), "execution_outputs")
                if not self.fixture_mode:
                    require(result.isolation_verified is True and
                            result.observations.get("executor_config_digest") == self.policy["oracle"]["executor_config_digest"] and
                            result.observations.get("worker_uid") == self.policy["principals"]["worker_uid"],
                            "execution_isolation_unverified")
                require(freeze_bundle(bundle)[1] == candidate_digest, "execution_input_changed")
                observed = {"exit_code": result.exit_code, "timed_out": result.timed_out, "output_limited": result.output_limited,
                            "budget_exceeded": result.budget_exceeded,
                            "stdout_digest": sha(result.stdout), "stderr_digest": sha(result.stderr),
                            "outputs": {name: sha(value) for name, value in result.outputs.items()}}
                expected = self.policy["oracle"]["expected"]
                passed = (not result.timed_out and not result.output_limited and not result.budget_exceeded and
                          all(observed[k] == expected[k] for k in expected))
                now = utcnow(); receipt_id = str(uuid4())
                receipt = {"schema_version": "0.1.0", "record_type": "verification", "verification_id": receipt_id,
                    "candidate_id": candidate_id, "candidate_digest": candidate_digest, "binding": self.binding,
                    "oracle_profile_digest": self.profile_digest, "execution_profile_digest": result.profile_digest,
                    "oracle_purpose": self.policy["oracle"]["purpose"],
                    "observed": observed, "outcome": "verified" if passed else "failed",
                    "trust_mode": "fixture" if self.fixture_mode else "production", "isolation_verified": result.isolation_verified is True and not self.fixture_mode,
                    "observed_worker_uid": None if self.fixture_mode else result.observations["worker_uid"],
                    "issuer_uid": os.geteuid() if hasattr(os, "geteuid") else None,
                    "issued_at": now.isoformat(), "expires_at": (now + timedelta(seconds=self.policy["verification"]["ttl_seconds"])).isoformat()}
                write_record(self.receipts / (receipt_id + ".json"), receipt,
                             receipt_gid=None if self.fixture_mode else self.policy["principals"]["receipt_gid"])
                db.execute("UPDATE verification_requests SET state=?,receipt=? WHERE key=?", (receipt["outcome"], receipt_id, idempotency_key)); db.commit()
                return receipt
            finally:
                db.close()


def read_verification(policy, verification_id, candidate_id, candidate_digest, *, fixture_mode=False, allow_expired=False):
    contract.uuid4(verification_id); contract.uuid4(candidate_id); contract.digest(candidate_digest)
    binding = policy_binding(policy)
    directory = Path(policy["verification"]["receipt_dir"])
    if not fixture_mode:
        require(sys.platform == "linux", "production_platform_unavailable")
        check_protected_path(directory, owner=0, directory=True)
        require(directory.stat().st_gid == policy["principals"]["receipt_gid"] and stat.S_IMODE(directory.stat().st_mode) == 0o750,
                "receipt_directory_policy")
    receipt_path = directory / (verification_id + ".json")
    if not fixture_mode:
        info = _regular(receipt_path, owner=0)
        require(stat.S_IMODE(info.st_mode) == 0o440 and info.st_gid == policy["principals"]["receipt_gid"], "verification_record_permissions")
    record = read_record(receipt_path, owner=None if fixture_mode else 0)
    fields = {"schema_version", "record_type", "verification_id", "candidate_id", "candidate_digest", "binding", "oracle_profile_digest",
              "execution_profile_digest", "oracle_purpose", "observed", "outcome", "trust_mode", "isolation_verified", "observed_worker_uid", "issuer_uid", "issued_at", "expires_at"}
    require(type(record) is dict and set(record) == fields and record["schema_version"] == "0.1.0" and record["record_type"] == "verification",
            "verification_record_fields")
    require(record["verification_id"] == verification_id and record["candidate_id"] == candidate_id and
            record["candidate_digest"] == candidate_digest and record["binding"] == binding and
            record["oracle_profile_digest"] == canonical_digest(policy["oracle"]), "verification_record_binding")
    require(record["oracle_purpose"] == policy["oracle"]["purpose"], "verification_oracle_purpose")
    module = importlib.import_module("p2_executor")
    require(record["execution_profile_digest"] == module.execution_profile_digest(execution_profile(policy)), "verification_execution_profile")
    require(record["trust_mode"] == ("fixture" if fixture_mode else "production"), "verification_trust_mode")
    if not fixture_mode:
        require(record["issuer_uid"] == 0 and record["isolation_verified"] is True and
                record["observed_worker_uid"] == policy["principals"]["worker_uid"], "verification_authority")
    observed = record["observed"]
    expected = policy["oracle"]["expected"]
    require(type(observed) is dict and set(observed) == set(expected) | {"timed_out", "output_limited", "budget_exceeded"} and
            type(observed["timed_out"]) is bool and type(observed["output_limited"]) is bool and type(observed["budget_exceeded"]) is bool and
            (observed["exit_code"] is None or type(observed["exit_code"]) is int),
            "verification_observations")
    passed = not observed["timed_out"] and not observed["output_limited"] and not observed["budget_exceeded"] and all(observed[k] == expected[k] for k in expected)
    require(record["outcome"] == ("verified" if passed else "failed"), "verification_false_success")
    try: issued, expires = datetime.fromisoformat(record["issued_at"]), datetime.fromisoformat(record["expires_at"])
    except (TypeError, ValueError): raise AdapterError("verification_time") from None
    require(issued.tzinfo is not None and expires.tzinfo is not None and 0 < (expires-issued).total_seconds() <= policy["verification"]["ttl_seconds"] and
            issued <= utcnow() + timedelta(seconds=5), "verification_time")
    require(allow_expired or utcnow() <= expires, "verification_expired")
    return record


def load_bundle_export(directory, candidate_id, candidate_digest, *, fixture_mode=False, expected_gid=None):
    """Read a fixed immutable export, never a worker-selected arbitrary host path."""
    directory = Path(directory)
    if not fixture_mode:
        check_protected_path(directory, owner=0, directory=True)
        require(type(expected_gid) is int and expected_gid > 0 and
                stat.S_IMODE(directory.stat().st_mode) == 0o750 and directory.stat().st_gid == expected_gid, "export_directory_policy")
    require(directory.is_dir() and not reparse(directory.lstat()), "unsafe_export_directory")
    blobs_dir = directory / "blobs"
    require(blobs_dir.is_dir() and not reparse(blobs_dir.lstat()), "unsafe_export_directory")
    if not fixture_mode:
        check_protected_path(blobs_dir, owner=0, directory=True)
        require(stat.S_IMODE(blobs_dir.stat().st_mode) == 0o750 and blobs_dir.stat().st_gid == expected_gid, "export_directory_policy")
    manifest = read_record(directory / "manifest.json", owner=None if fixture_mode else 0)
    require(type(manifest) is dict and set(manifest) == {"candidate_id", "candidate_digest", "binding", "files"} and
            manifest["candidate_id"] == candidate_id and manifest["candidate_digest"] == candidate_digest, "export_binding")
    contract.binding(manifest["binding"]); contract.validate_manifest(manifest["files"])
    if not fixture_mode:
        info = (directory / "manifest.json").stat()
        require(stat.S_IMODE(info.st_mode) == 0o440 and info.st_gid == expected_gid, "export_file_policy")
    blobs = {}
    for item in manifest["files"]:
        if item["kind"] == "blob":
            path = blobs_dir / item["digest"][7:]
            info = _regular(path, limit=contract.MAX_FILE_BYTES, owner=None if fixture_mode else 0)
            if not fixture_mode: require(stat.S_IMODE(info.st_mode) == 0o440 and info.st_gid == expected_gid, "export_file_policy")
            require(info.st_size == item["size"], "export_blob_size")
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
            try:
                opened = os.fstat(fd)
                require((opened.st_ino, opened.st_dev) == (info.st_ino, info.st_dev), "export_blob_changed")
                with os.fdopen(os.dup(fd), "rb") as stream: data = stream.read(contract.MAX_FILE_BYTES + 1)
                require(len(data) == item["size"] and sha(data) == item["digest"], "export_blob_digest")
                blobs[item["digest"]] = data
            finally: os.close(fd)
    bundle, actual_digest = freeze_bundle({"binding": manifest["binding"], "files": manifest["files"], "blobs": blobs})
    require(actual_digest == candidate_digest, "export_candidate_digest")
    return bundle


def verify_job(path="/etc/multi-p2/verification-job.json"):
    """Operator-owned fixed root-unit job. It is not a worker RPC interface."""
    require(sys.platform == "linux" and os.geteuid() == 0, "verifier_identity_unavailable")
    from p2_broker import _root_controlled
    _root_controlled(path)
    job = read_record(path, owner=0)
    fields = {"schema_version", "policy_path", "executor_config_path", "export_dir", "candidate_id", "candidate_digest", "idempotency_key"}
    require(type(job) is dict and set(job) == fields and job["schema_version"] == "0.1.0", "verification_job_fields")
    contract.uuid4(job["candidate_id"]); contract.uuid4(job["idempotency_key"]); contract.digest(job["candidate_digest"])
    module = importlib.import_module("p2_executor")
    executor = module.BwrapExecutor.from_config(job["executor_config_path"])
    verifier = Verifier.from_protected_policy(job["policy_path"], executor)
    bundle = load_bundle_export(job["export_dir"], job["candidate_id"], job["candidate_digest"],
                                expected_gid=verifier.policy["principals"]["receipt_gid"])
    return verifier.verify(bundle, job["candidate_id"], job["idempotency_key"])
