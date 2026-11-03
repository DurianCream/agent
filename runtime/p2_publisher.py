"""Fixed local-bare Git publication with immutable CAS, trusted receipts and CAS refs.

This adapter never uses a candidate checkout, .git, hooks, filters or credentials.
The implemented target backend is a controlled local bare repository. It transfers
objects without updating refs, then atomically updates the one approved ref with
an expected-old OID. Network/credential publication remains unavailable rather
than pretending ordinary preflight checks provide remote compare-and-swap.
"""
from __future__ import annotations

from contextlib import closing
import argparse
import configparser
import errno
from datetime import timezone
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import threading
import time
from uuid import uuid4

import p2_contracts as contract
from control_contracts import canonical_digest, load_json
from p2_store import check_protected_path, reparse, StoreError
from control_contracts import ControlContractError
from p2_verifier import (AdapterError, require, sha, json_bytes, utcnow, _regular, read_record,
                         service_lock, fixture_root, fixture_path, freeze_bundle, policy_binding, read_verification, check_ledger)
from p2_verifier import read_bytes
from p2_verifier import load_bundle_export
from p2_verifier import Verifier

MAX_GIT_OUTPUT = 4 * 1024 * 1024
MAX_REPOSITORY_BYTES = 512 * 1024 * 1024


def _capture_git(command, *, data, environment, directory, limit):
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=environment, cwd=directory, close_fds=True)
    values = {"stdout": bytearray(), "stderr": bytearray()}
    mutex = threading.Lock(); overflow = threading.Event()
    def drain(stream, name):
        try:
            while True:
                chunk = stream.read(65536)
                if not chunk: break
                with mutex:
                    room = limit - sum(len(v) for v in values.values())
                    values[name].extend(chunk[:max(0, room)])
                    if len(chunk) > room:
                        overflow.set(); break
        finally: stream.close()
    def feed():
        try:
            if data: process.stdin.write(data)
        except (BrokenPipeError, OSError): pass
        finally:
            try: process.stdin.close()
            except (BrokenPipeError, OSError): pass
    threads = [threading.Thread(target=drain, args=(process.stdout, "stdout"), daemon=True),
               threading.Thread(target=drain, args=(process.stderr, "stderr"), daemon=True),
               threading.Thread(target=feed, daemon=True)]
    for thread in threads: thread.start()
    deadline = time.monotonic() + 30
    timed_out = False
    while process.poll() is None:
        if overflow.is_set() or time.monotonic() >= deadline:
            timed_out = not overflow.is_set(); process.kill(); break
        time.sleep(0.01)
    try: process.wait(timeout=5)
    except subprocess.TimeoutExpired: raise AdapterError("git_cleanup_unknown") from None
    for thread in threads: thread.join(2)
    require(not any(thread.is_alive() for thread in threads), "git_streams_not_closed")
    require(not timed_out, "git_timeout")
    require(not overflow.is_set(), "git_output_limit")
    require(process.returncode == 0, "git_operation_failed")
    return bytes(values["stdout"])


class Publisher:
    def __init__(self, *args, **kwargs):
        raise AdapterError("use_publisher_factory")

    @classmethod
    def for_fixture(cls, root, policy):
        root = fixture_root(root)
        obj = object.__new__(cls); obj.fixture_mode = True; obj.root = root
        obj._configure(policy)
        for path in (obj.state, obj.remote, obj.receipts): fixture_path(root, path)
        obj.state.mkdir(parents=True, exist_ok=True)
        obj._initialize()
        return obj

    @classmethod
    def from_protected_policy(cls, path):
        require(sys.platform == "linux", "production_platform_unavailable")
        require(sys.flags.isolated and sys.flags.no_site, "isolated_no_site_publisher_required")
        from p2_broker import _root_controlled
        _root_controlled(path)
        policy = read_record(path, owner=0)
        obj = object.__new__(cls); obj.fixture_mode = False
        obj.policy_path = Path(path)
        obj._configure(policy)
        require(obj.policy["oracle"]["executor_config_digest"] is not None and obj.policy["oracle"]["purpose"] == "release" and
                obj.policy["oracle"]["expected"]["exit_code"] == 0, "production_release_profile_required")
        require(os.geteuid() == obj.policy["principals"]["publisher_uid"] and os.geteuid() != 0,
                "publisher_identity_unavailable")
        obj._process_identity()
        require(obj.policy["principals"]["receipt_gid"] in {os.getegid(), *os.getgroups()}, "receipt_group_unavailable")
        _root_controlled(obj.git_binary)
        obj._git_privileges()
        for folder in (obj.state, obj.remote):
            check_protected_path(folder, owner=os.geteuid(), directory=True)
            require(stat_mode(folder) == 0o700, "publisher_directory_not_private")
        check_protected_path(obj.receipts, owner=0, directory=True)
        obj._initialize()
        return obj

    def _configure(self, policy):
        self.policy = load_json(json_bytes(policy)); self.binding = policy_binding(self.policy)
        value = self.policy["publication"]
        fields = {"transport", "remote", "ref", "state_root", "git_binary", "git_binary_digest", "allowed_paths", "author_name", "author_email"}
        require(type(value) is dict and set(value) == fields, "publication_policy_fields")
        require(value["transport"] == "local-bare", "remote_ref_cas_adapter_unavailable")
        for key in ("remote", "state_root", "git_binary"):
            require(type(value[key]) is str and Path(value[key]).is_absolute() and ".." not in Path(value[key]).parts,
                    "publication_policy_path")
        require(type(value["ref"]) is str and value["ref"].startswith("refs/heads/") and
                len(value["ref"].encode("utf-8")) <= 256 and
                not any(c.isspace() or ord(c) < 32 for c in value["ref"]), "publication_ref")
        require(type(value["allowed_paths"]) is list and 0 < len(value["allowed_paths"]) <= contract.MAX_FILES and
                len(set(value["allowed_paths"])) == len(value["allowed_paths"]), "publication_paths")
        for name in value["allowed_paths"]: contract.portable_path(name)
        for key in ("author_name", "author_email"):
            require(type(value[key]) is str and 0 < len(value[key]) <= 128 and
                    not any(ord(c) < 32 or c in '<>' for c in value[key]), "publication_author")
        require("@" in value["author_email"], "publication_author")
        self.state = Path(value["state_root"])
        self.remote = Path(value["remote"])
        self.receipts = Path(self.policy["verification"]["receipt_dir"])
        self.git_binary = Path(value["git_binary"])
        contract.digest(value["git_binary_digest"])
        self._check_git_binary()
        self.ref = value["ref"]
        self.profile_digest = canonical_digest(value)
        require(self.remote != self.state and not self.remote.is_relative_to(self.state) and not self.state.is_relative_to(self.remote),
                "publication_directory_overlap")

    def _initialize(self):
        for folder in (self.state, self.remote, self.receipts):
            require(folder.is_dir() and not reparse(folder.lstat()), "unsafe_publication_directory")
        self.home = self.state / "home"
        self.hooks = self.state / "empty-hooks"
        self.template = self.state / "empty-template"
        for folder in (self.home, self.hooks, self.template):
            folder.mkdir(mode=0o700, exist_ok=True)
            require(not reparse(folder.lstat()) and folder.is_dir(), "unsafe_publication_directory")
        require(not any(self.hooks.iterdir()) and not any(self.template.iterdir()), "publisher_hook_directory_not_empty")
        self.cache = self.state / "objects.git"
        require(not self.cache.is_symlink(), "unsafe_bare_repository")
        if not self.cache.exists():
            self._git(None, ["init", "--bare", "--object-format=" + ("sha256" if len(self.binding["base_commit"]) == 64 else "sha1"),
                             "--template=" + str(self.template), str(self.cache)])
            if os.name == "posix": os.chmod(self.cache, 0o700)
        self._check_repository(self.cache)
        self._check_repository(self.remote)
        require(self._git(self.cache, ["rev-parse", "--is-bare-repository"]).strip() == b"true" and
                self._git(self.remote, ["rev-parse", "--is-bare-repository"]).strip() == b"true", "bare_repository_required")
        self._git(self.cache, ["check-ref-format", self.ref])
        self.db = self.state / "publication.sqlite3"
        check_ledger(self.db, owner=None if self.fixture_mode else os.geteuid())
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS publications(key TEXT PRIMARY KEY,digest TEXT NOT NULL,candidate_id TEXT NOT NULL,candidate_digest TEXT NOT NULL,verification_id TEXT NOT NULL,verification_hash TEXT NOT NULL,commit_oid TEXT,tree_oid TEXT,state TEXT NOT NULL,response BLOB)")
        if os.name == "posix": os.chmod(self.db, 0o600)

    def _check_repository(self, repository):
        require(repository.is_dir() and not reparse(repository.lstat()), "unsafe_bare_repository")
        if self.fixture_mode:
            fixture_path(self.root, repository)
        else:
            check_protected_path(repository, owner=os.geteuid(), directory=True)
            require(stat_mode(repository) == 0o700, "publisher_directory_not_private")
        forbidden = ("objects/info/alternates", "objects/info/http-alternates", "info/grafts", "commondir", "config.worktree", "shallow")
        for name in forbidden:
            path = repository / name
            require(not path.exists() and not path.is_symlink(), "bare_repository_indirection")
        replacements = repository / "refs/replace"
        require(not replacements.is_symlink(), "bare_repository_replacements")
        require(not replacements.exists() or not any(replacements.iterdir()), "bare_repository_replacements")
        count = 0; total = 0
        for path in repository.rglob("*"):
            count += 1
            require(count <= 100000, "repository_entry_limit")
            info = path.lstat()
            require(not reparse(info) and (path.is_dir() or (path.is_file() and info.st_nlink == 1)), "unsafe_repository_entry")
            if not self.fixture_mode:
                require(info.st_uid == os.geteuid() and info.st_mode & 0o022 == 0, "repository_permission_drift")
            if path.is_file(): total += info.st_size
            require(total <= MAX_REPOSITORY_BYTES, "repository_byte_limit")
        config_file = repository / "config"
        _regular(config_file, limit=16384, owner=None if self.fixture_mode else os.geteuid())
        parser = configparser.RawConfigParser(strict=True, interpolation=None)
        try:
            parser.read_string(read_bytes(config_file, limit=16384, owner=None if self.fixture_mode else os.geteuid()).decode("utf-8"))
        except (ValueError, configparser.Error, UnicodeError):
            raise AdapterError("unsafe_git_configuration") from None
        require(not parser.defaults() and set(parser.sections()) <= {"core", "extensions"} and "core" in parser, "unsafe_git_configuration")
        allowed = {"repositoryformatversion": {"0", "1"}, "filemode": {"true", "false"}, "bare": {"true"},
                   "logallrefupdates": {"true", "false"}, "ignorecase": {"true", "false"}, "symlinks": {"true", "false"}}
        require(all(key in allowed and value.lower() in allowed[key] for key, value in parser.items("core")) and
                parser["core"].get("bare", "").lower() == "true", "unsafe_git_configuration")
        if "extensions" in parser:
            require(set(parser["extensions"]) == {"objectformat"} and parser["extensions"]["objectformat"] in ("sha1", "sha256"),
                    "unsafe_git_configuration")
        return total

    def _process_identity(self):
        import pwd, grp
        account = pwd.getpwuid(os.geteuid())
        require(account.pw_name.startswith("multi-p2-publish") and account.pw_dir == "/nonexistent" and
                account.pw_shell in ("/usr/sbin/nologin", "/sbin/nologin", "/bin/false") and
                account.pw_gid == self.policy["principals"]["receipt_gid"], "dedicated_publisher_required")
        groups = set(os.getgroups()) | set(os.getgrouplist(account.pw_name, account.pw_gid)) | {os.getegid()}
        require(not {grp.getgrgid(gid).gr_name for gid in groups} & {"sudo", "wheel", "admin", "docker", "lxd", "libvirt", "kvm", "multi-p2-workers"},
                "privileged_publisher_group")
        status = Path("/proc/self/status").read_text(encoding="ascii")
        values = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
        require(values.get("NoNewPrivs", "").strip() == "1" and
                all(int(values.get(key, "-1").strip(), 16) == 0 for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")),
                "publisher_privileges_not_dropped")
        interfaces = Path("/proc/self/net/dev").read_text(encoding="ascii").splitlines()[2:]
        require(bool(interfaces) and all(line.split(":", 1)[0].strip() == "lo" for line in interfaces), "publisher_network_not_private")

    def _git_privileges(self):
        require(not self.git_binary.stat().st_mode & 0o6000, "privileged_git_rejected")
        try: caps = os.getxattr(self.git_binary, "security.capability")
        except OSError as error:
            require(error.errno in (errno.ENODATA, errno.ENOTSUP), "git_capability_check_failed")
            caps = b""
        require(not caps, "privileged_git_rejected")

    def _recheck(self):
        require(canonical_digest(self.policy) == self.binding["policy_digest"] and
                self.remote == Path(self.policy["publication"]["remote"]) and
                self.state == Path(self.policy["publication"]["state_root"]) and self.ref == self.policy["publication"]["ref"],
                "publication_policy_changed")
        self._check_git_binary()
        if not self.fixture_mode:
            require(os.geteuid() == self.policy["principals"]["publisher_uid"] and os.geteuid() != 0, "publisher_identity_unavailable")
            self._process_identity(); self._git_privileges()
            from p2_broker import _root_controlled
            _root_controlled(self.policy_path)
            require(read_record(self.policy_path, owner=0) == self.policy, "publication_policy_changed")
            check_protected_path(self.state, owner=os.geteuid(), directory=True)
            require(stat_mode(self.state) == 0o700, "publisher_directory_not_private")
        else:
            fixture_path(self.root, self.state)
        require(not reparse(self.hooks.lstat()) and not any(self.hooks.iterdir()), "publisher_hook_directory_not_empty")
        self._check_repository(self.cache); self._check_repository(self.remote)

    def _check_git_binary(self):
        if self.fixture_mode:
            # Installed Git for Windows uses hard-linked launcher names. This
            # exception is only for an explicitly trusted fixture executable,
            # never records, CAS data, or the production publisher.
            info = self.git_binary.lstat()
            import stat
            require(not reparse(info) and stat.S_ISREG(info.st_mode) and 0 < info.st_size <= 64 * 1024 * 1024, "unsafe_fixture_git")
        else:
            _regular(self.git_binary, limit=64 * 1024 * 1024)
        require(sha(self.git_binary.read_bytes()) == self.policy["publication"]["git_binary_digest"], "git_binary_changed")

    def _environment(self, index=None):
        # Do not inherit HOME, GIT_*, SSH_*, credential helpers, proxy or trace flags.
        value = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP") if key in os.environ}
        value["PATH"] = str(self.git_binary.parent) + os.pathsep + os.defpath
        value.update(HOME=str(self.home), USERPROFILE=str(self.home), XDG_CONFIG_HOME=str(self.home),
                     GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_GLOBAL=os.devnull,
                     GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="", SSH_ASKPASS="", GIT_NO_REPLACE_OBJECTS="1")
        if index is not None: value["GIT_INDEX_FILE"] = str(index)
        publication = self.policy["publication"]
        value.update(GIT_AUTHOR_NAME=publication["author_name"], GIT_COMMITTER_NAME=publication["author_name"],
                     GIT_AUTHOR_EMAIL=publication["author_email"], GIT_COMMITTER_EMAIL=publication["author_email"])
        return value

    def _git(self, repository, arguments, data=None, index=None, limit=MAX_GIT_OUTPUT):
        command = [str(self.git_binary), "--no-pager", "--literal-pathspecs", "-c", "core.hooksPath=" + str(self.hooks),
                   "-c", "core.fsmonitor=false", "-c", "credential.helper=", "-c", "protocol.allow=never",
                   "-c", "protocol.file.allow=always", "-c", "fetch.fsckObjects=true", "-c", "transfer.fsckObjects=true",
                   "-c", "gc.auto=0", "-c", "maintenance.auto=false"]
        if repository is not None: command += ["--git-dir=" + str(repository)]
        return _capture_git(command + arguments, data=data, environment=self._environment(index), directory=self.state, limit=limit)

    def _head(self):
        self._direct_ref()
        value = self._git(self.remote, ["rev-parse", "--verify", self.ref]).strip().decode("ascii")
        require(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value), "remote_ref_invalid")
        return value

    def _direct_ref(self):
        path = self.remote.joinpath(*self.ref.split("/"))
        if path.exists() or path.is_symlink():
            _regular(path, limit=256, owner=None if self.fixture_mode else os.geteuid())
            value = read_bytes(path, limit=256, owner=None if self.fixture_mode else os.geteuid()).strip()
            require(re.fullmatch(rb"(?:[0-9a-f]{40}|[0-9a-f]{64})", value), "symbolic_publication_ref_rejected")

    def _release_receipt(self, receipt):
        require(receipt["outcome"] == "verified" and receipt["oracle_purpose"] == "release" and
                self.policy["oracle"]["purpose"] == "release" and self.policy["oracle"]["expected"]["exit_code"] == 0 and
                receipt["observed"]["exit_code"] == 0 and not receipt["observed"]["timed_out"] and
                not receipt["observed"]["output_limited"] and not receipt["observed"]["budget_exceeded"], "verification_not_release_eligible")

    def _build(self, bundle):
        baseline = self.binding["base_commit"]
        require(self._head() == baseline, "publication_baseline_changed")
        self._git(self.cache, ["fetch", "--no-tags", "--no-recurse-submodules", "--no-write-fetch-head", str(self.remote), baseline])
        require(self._git(self.cache, ["cat-file", "-t", baseline]).strip() == b"commit", "baseline_commit_required")
        require(self._check_repository(self.cache) + sum(len(v) for v in bundle["blobs"].values()) + 1024 * 1024 <= MAX_REPOSITORY_BYTES,
                "repository_byte_limit")
        index = self.state / ("index-" + uuid4().hex)
        try:
            self._git(self.cache, ["read-tree", baseline], index=index)
            for item in bundle["files"]:
                if item["kind"] == "delete":
                    self._git(self.cache, ["update-index", "--force-remove", "--", item["path"]], index=index)
                else:
                    oid = self._git(self.cache, ["hash-object", "-w", "--stdin"], data=bundle["blobs"][item["digest"]]).strip().decode("ascii")
                    self._git(self.cache, ["update-index", "--add", "--cacheinfo", item["mode"], oid, item["path"]], index=index)
            tree = self._git(self.cache, ["write-tree"], index=index).strip().decode("ascii")
            self._validate_tree(self.cache, tree, bundle)
            message = "P2 verified candidate " + canonical_digest({"binding": bundle["binding"], "files": bundle["files"]}) + "\n"
            commit = self._git(self.cache, ["commit-tree", tree, "-p", baseline], data=message.encode()).strip().decode("ascii")
            require(self._git(self.cache, ["rev-list", "--parents", "-n", "1", commit]).strip().decode().split() == [commit, baseline], "publication_parent")
            return commit, tree
        finally:
            index.unlink(missing_ok=True)
            Path(str(index) + ".lock").unlink(missing_ok=True)

    def _transfer_objects(self, commit):
        # Object transfer does not update the destination ref or FETCH_HEAD.
        self._git(self.remote, ["fetch", "--no-tags", "--no-recurse-submodules", "--no-write-fetch-head", str(self.cache), commit])

    def _update_ref(self, commit):
        self._direct_ref()
        self._git(self.remote, ["update-ref", "--no-deref", self.ref, commit, self.binding["base_commit"]])

    def _entry(self, repository, tree, path):
        value = self._git(repository, ["ls-tree", "-z", tree, "--", path])
        if not value: return None
        require(value.endswith(b"\0") and value.count(b"\0") == 1, "publication_tree_entry")
        metadata, actual = value[:-1].split(b"\t", 1)
        require(actual.decode("utf-8") == path, "publication_tree_entry")
        return tuple(metadata.decode("ascii").split())

    def _validate_tree(self, repository, tree, bundle):
        baseline = self.binding["base_commit"]
        expected_changed = set()
        for item in bundle["files"]:
            before = self._entry(repository, baseline, item["path"])
            actual = self._entry(repository, tree, item["path"])
            if item["kind"] == "delete":
                require(actual is None, "publication_tree_content")
                after = None
            else:
                oid = self._git(repository, ["hash-object", "--stdin"], data=bundle["blobs"][item["digest"]]).strip().decode("ascii")
                after = (item["mode"], "blob", oid)
                require(actual == after, "publication_tree_content")
                contents = self._git(repository, ["cat-file", "blob", oid], limit=contract.MAX_FILE_BYTES + 65536)
                require(len(contents) == item["size"] and sha(contents) == item["digest"], "publication_object_digest")
            if before != after: expected_changed.add(item["path"])
        changed = set(filter(None, self._git(repository, ["diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "--no-renames", baseline, tree]).decode("utf-8").split("\0")))
        require(changed and changed == expected_changed and changed <= set(self.policy["publication"]["allowed_paths"]), "publication_change_scope")

    def publish(self, bundle, candidate_id, verification_id, idempotency_key):
        contract.uuid4(candidate_id); contract.uuid4(verification_id); contract.uuid4(idempotency_key)
        bundle, candidate_digest = freeze_bundle(bundle)
        require(bundle["binding"] == self.binding, "publication_binding")
        self._recheck()
        request_digest = canonical_digest({"candidate_id": candidate_id, "candidate_digest": candidate_digest,
            "verification_id": verification_id, "profile_digest": self.profile_digest, "policy_digest": self.binding["policy_digest"]})
        with service_lock(self.state):
            check_ledger(self.db, owner=None if self.fixture_mode else os.geteuid())
            db = sqlite3.connect(self.db)
            try:
                row = db.execute("SELECT digest,verification_hash,commit_oid,tree_oid,state,response FROM publications WHERE key=?", (idempotency_key,)).fetchone()
                if row:
                    require(row[0] == request_digest, "publication_idempotency_conflict")
                    require(row[4] != "blocked", "publication_preparation_failed")
                    commit, tree = row[2], row[3]
                    require(commit and tree and row[4] in ("committed", "unknown", "published"), "publication_effect_unknown")
                    receipt = read_verification(self.policy, verification_id, candidate_id, candidate_digest,
                                                fixture_mode=self.fixture_mode, allow_expired=True)
                    require(canonical_digest(receipt) == row[1], "publication_verification_changed")
                    self._release_receipt(receipt)
                    current = self._head()
                    require(current in (self.binding["base_commit"], commit), "publication_remote_conflict")
                    if current == commit:
                        self._validate_tree(self.remote, tree, bundle)
                        return self._complete(db, idempotency_key, commit, tree, candidate_digest, verification_id, reconciled=True)
                    require(row[4] != "published", "published_ref_moved")
                else:
                    require(db.execute("SELECT COUNT(*) FROM publications").fetchone()[0] < 1000, "publication_quota")
                    require(db.execute("SELECT 1 FROM publications WHERE state IN ('preparing','committed','unknown')").fetchone() is None,
                            "publication_target_busy")
                    receipt = read_verification(self.policy, verification_id, candidate_id, candidate_digest, fixture_mode=self.fixture_mode)
                    self._release_receipt(receipt)
                    db.execute("INSERT INTO publications VALUES(?,?,?,?,?,?,NULL,NULL,?,NULL)",
                               (idempotency_key, request_digest, candidate_id, candidate_digest, verification_id, canonical_digest(receipt), "preparing")); db.commit()
                    try:
                        commit, tree = self._build(bundle)
                    except (AdapterError, OSError, subprocess.SubprocessError):
                        db.execute("UPDATE publications SET state='blocked' WHERE key=?", (idempotency_key,)); db.commit()
                        raise AdapterError("publication_preparation_failed") from None
                    db.execute("UPDATE publications SET commit_oid=?,tree_oid=?,state='committed' WHERE key=?", (commit, tree, idempotency_key)); db.commit()
                # A new effect always needs a current matching trusted receipt.
                try:
                    current_receipt = read_verification(self.policy, verification_id, candidate_id, candidate_digest, fixture_mode=self.fixture_mode)
                    require(canonical_digest(current_receipt) == canonical_digest(receipt), "publication_verification_changed")
                    self._release_receipt(current_receipt)
                except AdapterError:
                    state = db.execute("SELECT state FROM publications WHERE key=?", (idempotency_key,)).fetchone()[0]
                    if state == "committed":
                        db.execute("UPDATE publications SET state='blocked' WHERE key=?", (idempotency_key,)); db.commit()
                    elif state == "unknown":
                        raise AdapterError("publication_effect_unknown") from None
                    raise
                require(self._git(self.cache, ["rev-list", "--parents", "-n", "1", commit]).strip().decode().split() == [commit, self.binding["base_commit"]] and
                        self._git(self.cache, ["rev-parse", commit + '^{tree}']).strip().decode() == tree, "publication_commit_changed")
                self._validate_tree(self.cache, tree, bundle)
                self._recheck()
                require(self._check_repository(self.remote) + sum(len(v) for v in bundle["blobs"].values()) + 1024 * 1024 <= MAX_REPOSITORY_BYTES,
                        "repository_byte_limit")
                self._transfer_objects(commit)
                self._recheck()
                try:
                    current_receipt = read_verification(self.policy, verification_id, candidate_id, candidate_digest, fixture_mode=self.fixture_mode)
                    require(canonical_digest(current_receipt) == canonical_digest(receipt), "publication_verification_changed")
                    self._release_receipt(current_receipt)
                except AdapterError:
                    # A known preparation with no attempted ref update can end
                    # blocked; an earlier unknown attempt stays unresolved.
                    state = db.execute("SELECT state FROM publications WHERE key=?", (idempotency_key,)).fetchone()[0]
                    if state == "committed":
                        db.execute("UPDATE publications SET state='blocked' WHERE key=?", (idempotency_key,)); db.commit()
                    elif state == "unknown":
                        raise AdapterError("publication_effect_unknown") from None
                    raise
                db.execute("UPDATE publications SET state='unknown' WHERE key=?", (idempotency_key,)); db.commit()
                try:
                    self._update_ref(commit)
                    require(self._head() == commit, "publication_readback")
                    self._validate_tree(self.remote, tree, bundle)
                except (AdapterError, OSError, subprocess.SubprocessError):
                    db.execute("UPDATE publications SET state='unknown' WHERE key=?", (idempotency_key,)); db.commit()
                    raise AdapterError("publication_effect_unknown") from None
                return self._complete(db, idempotency_key, commit, tree, candidate_digest, verification_id, reconciled=False)
            finally:
                db.close()

    def _complete(self, db, key, commit, tree, candidate_digest, verification_id, *, reconciled):
        try:
            return self._complete_record(db, key, commit, tree, candidate_digest, verification_id, reconciled=reconciled)
        except (AdapterError, OSError, sqlite3.Error, subprocess.SubprocessError):
            raise AdapterError("publication_effect_unknown") from None

    def _complete_record(self, db, key, commit, tree, candidate_digest, verification_id, *, reconciled):
        require(self._git(self.remote, ["rev-parse", commit + '^{tree}']).strip().decode() == tree and
                self._git(self.remote, ["rev-list", "--parents", "-n", "1", commit]).strip().decode().split() == [commit, self.binding["base_commit"]],
                "publication_readback")
        response = {"schema_version": "0.1.0", "status": "published", "commit": commit, "tree": tree, "ref": self.ref,
                    "candidate_digest": candidate_digest, "verification_id": verification_id, "profile_digest": self.profile_digest,
                    "published": True, "authorization": not self.fixture_mode, "trust_mode": "fixture" if self.fixture_mode else "production",
                    "target_kind": "local-bare", "reconciled": reconciled, "p2_isolation_verified": False}
        db.execute("UPDATE publications SET state='published',response=? WHERE key=?", (json_bytes(response), key)); db.commit()
        return response


def stat_mode(path):
    import stat
    return stat.S_IMODE(Path(path).stat().st_mode)


class FixtureAdapterWorkflow:
    """Controller-side functional fixture path, never a production transport."""
    def __init__(self, store, verifier, publisher):
        require(store.fixture_mode is True and type(verifier) is Verifier and verifier.fixture_mode is True and
                type(publisher) is Publisher and publisher.fixture_mode is True and verifier.binding == publisher.binding,
                "fixture_workflow_required")
        self.store, self.verifier, self.publisher = store, verifier, publisher

    def process(self, raw, uid):
        return self.store.fixture_adapter_call(raw, uid, self._handle)

    def _handle(self, request, uid, backend_key):
        try:
            payload = request["payload"]
            bundle = self.store.export_bundle(request["binding"]["enrollment_id"], uid, payload["candidate_id"], payload["candidate_digest"])
            if request["operation"] == "verify":
                record = self.verifier.verify(bundle, payload["candidate_id"], backend_key)
                return {"status": record["outcome"], "verification_id": record["verification_id"], "candidate_digest": record["candidate_digest"],
                        "authorization": False, "published": False, "trust_mode": "fixture"}
            return self.publisher.publish(bundle, payload["candidate_id"], payload["verification_id"], backend_key)
        except AdapterError as error:
            unknown = error.code in ("publication_effect_unknown", "verification_effect_unknown")
            busy = error.code in ("adapter_busy", "publication_target_busy")
            return {"status": "unknown" if unknown else "in_progress" if busy else "blocked", "error_code": error.code,
                    "authorization": False, "published": None if unknown or busy else False, "trust_mode": "fixture"}
        except (StoreError, ControlContractError) as error:
            return {"status": "blocked", "error_code": error.code, "authorization": False, "published": False, "trust_mode": "fixture"}
        except Exception as error:
            # Executor failures may occur after an isolated job started. Never
            # convert an unobserved outcome into a successful verification.
            from p2_executor import ExecutorError
            if not isinstance(error, ExecutorError): raise
            return {"status": "unknown", "error_code": "verification_execution_unknown", "authorization": False,
                    "published": None, "trust_mode": "fixture"}


def publish_job(path="/etc/multi-p2/publication-job.json"):
    """Operator-owned fixed publisher-unit job; no worker-controlled CLI paths."""
    require(sys.platform == "linux" and os.geteuid() != 0, "publisher_identity_unavailable")
    from p2_broker import _root_controlled
    _root_controlled(path)
    job = read_record(path, owner=0)
    fields = {"schema_version", "policy_path", "export_dir", "candidate_id", "candidate_digest", "verification_id", "idempotency_key"}
    require(type(job) is dict and set(job) == fields and job["schema_version"] == "0.1.0", "publication_job_fields")
    publisher = Publisher.from_protected_policy(job["policy_path"])
    bundle = load_bundle_export(job["export_dir"], job["candidate_id"], job["candidate_digest"],
                                expected_gid=publisher.policy["principals"]["receipt_gid"])
    return publisher.publish(bundle, job["candidate_id"], job["verification_id"], job["idempotency_key"])


def main(argv=None):
    # The only job path is fixed by this trusted service entry point.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    try:
        import json
        require(args.run, "explicit_publication_job_required")
        print(json.dumps(publish_job(), sort_keys=True))
        return 0
    except Exception as error:
        code = error.code if isinstance(error, AdapterError) else "publication_service_unavailable"
        unknown = code == "publication_effect_unknown"
        print(__import__('json').dumps({"status": "unknown" if unknown else "blocked", "error_code": code,
                                      "published": None}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
