"""Bounded execution: explicit trusted fixtures or a root-observed bwrap sandbox.

The production supervisor never runs candidate code on the host. A protected
child helper joins a private cgroup, drops to the dedicated worker identity,
then executes trusted bubblewrap. The parent checks kernel state before release.
"""
from __future__ import annotations

import argparse
import base64
import errno
from dataclasses import dataclass, field
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from types import MappingProxyType
from uuid import uuid4

MAX_INPUT_BYTES = 256 * 1024 * 1024
MAX_FILES = 512
MAX_OUTPUT_FILES = 128
MAX_RETAINED_JOBS = 64
MAX_RETAINED_BYTES = 1024 * 1024 * 1024
MAX_LAUNCH_BYTES = 512 * 1024
CGROUP_ROOT = "/sys/fs/cgroup/system.slice/multi-p2-executor.service"
NS_NAMES = ("mnt", "pid", "net", "ipc", "uts", "user", "cgroup")


class ExecutorError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__("P2 executor rejected operation: " + code)


def require(condition, code):
    if not condition:
        raise ExecutorError(code)


def _sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _json_digest(value):
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8"))


def _unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def _json(data, limit=256 * 1024):
    require(type(data) is bytes and len(data) <= limit, "json_limit")
    try:
        return json.loads(data.decode("utf-8", "strict"), object_pairs_hook=_unique,
                          parse_constant=lambda value: (_ for _ in ()).throw(ExecutorError("invalid_json_number")))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ExecutorError("invalid_json") from error


@dataclass(frozen=True)
class ExecutionProfile:
    profile_id: str
    argv: tuple[str, ...]
    timeout_seconds: int = 10
    memory_bytes: int = 256 * 1024 * 1024
    cpu_seconds: int = 10
    tasks: int = 32
    output_bytes: int = 1024 * 1024
    stdin: bytes = b""


def profile_value(profile):
    require(type(profile) is ExecutionProfile, "profile_type")
    require(type(profile.profile_id) is str and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", profile.profile_id) is not None, "profile_id")
    require(type(profile.argv) is tuple and 1 <= len(profile.argv) <= 32 and
            all(type(item) is str and 0 < len(item) <= 4096 and "\0" not in item for item in profile.argv), "profile_argv")
    require(sum(len(item.encode("utf-8")) for item in profile.argv) <= 32768, "profile_argv_limit")
    for name, lower, upper in (("timeout_seconds", 1, 300), ("memory_bytes", 16 * 1024 * 1024, 1024 * 1024 * 1024),
                               ("cpu_seconds", 1, 60), ("tasks", 4, 64), ("output_bytes", 1024, 4 * 1024 * 1024)):
        number = getattr(profile, name)
        require(type(number) is int and lower <= number <= upper, "profile_budget")
    require(type(profile.stdin) is bytes and len(profile.stdin) <= 65536, "profile_stdin")
    return {"profile_id": profile.profile_id, "argv": list(profile.argv), "timeout_seconds": profile.timeout_seconds,
            "memory_bytes": profile.memory_bytes, "cpu_seconds": profile.cpu_seconds, "tasks": profile.tasks,
            "output_bytes": profile.output_bytes, "stdin_base64": base64.b64encode(profile.stdin).decode("ascii")}


def execution_profile_digest(profile):
    return _json_digest(profile_value(profile))


def executor_configuration_digest(config):
    """Pure digest helper for operator policy preparation; never authority."""
    require(type(config) is dict, "executor_config_type")
    return _json_digest(config)


def _profile(value):
    require(type(value) is dict and set(value) == {"profile_id", "argv", "timeout_seconds", "memory_bytes", "cpu_seconds", "tasks", "output_bytes", "stdin_base64"}, "profile_fields")
    try:
        require(type(value["argv"]) is list and type(value["stdin_base64"]) is str and len(value["stdin_base64"]) <= 90000, "profile_stdin")
        stdin = base64.b64decode(value["stdin_base64"], validate=True)
        require(base64.b64encode(stdin).decode("ascii") == value["stdin_base64"], "profile_stdin")
        result = ExecutionProfile(value["profile_id"], tuple(value["argv"]), value["timeout_seconds"], value["memory_bytes"],
                                  value["cpu_seconds"], value["tasks"], value["output_bytes"], stdin)
    except (TypeError, ValueError) as error:
        raise ExecutorError("profile_invalid") from error
    profile_value(result)
    return result


@dataclass(frozen=True)
class ExecutionResult:
    candidate_digest: str
    profile_digest: str
    backend: str
    fixture_mode: bool
    isolation_verified: bool
    exit_code: int | None
    timed_out: bool
    output_limited: bool
    stdout: bytes
    stderr: bytes
    outputs: object = field(default_factory=dict)
    observations: object = field(default_factory=dict)
    budget_exceeded: bool = False

    def __post_init__(self):
        object.__setattr__(self, "outputs", MappingProxyType(dict(self.outputs)))
        object.__setattr__(self, "observations", MappingProxyType(dict(self.observations)))

    @property
    def production_eligible(self):
        return self.backend == "bwrap" and not self.fixture_mode and self.isolation_verified and not self.timed_out and not self.output_limited and not self.budget_exceeded


def validate_bundle(bundle):
    """Revalidate the captured CAS body and bytes; never trust a passed label."""
    from p2_contracts import binding, validate_manifest
    from control_contracts import canonical_digest
    require(type(bundle) is dict and set(bundle) == {"binding", "files", "blobs"}, "bundle_fields")
    body = _json(json.dumps({"binding": bundle["binding"], "files": bundle["files"]}, ensure_ascii=False, allow_nan=False).encode())
    binding(body["binding"]); validate_manifest(body["files"])
    directories = set()
    for item in body["files"]:
        parts = PurePosixPath(item["path"]).parts
        require(len(parts) <= 16, "input_depth_limit")
        directories.update(parts[:index] for index in range(1, len(parts)))
    require(len(directories) + len(body["files"]) <= 2048, "input_node_limit")
    require(type(bundle["blobs"]) is dict, "bundle_blobs")
    expected = {item["digest"] for item in body["files"] if item["kind"] == "blob"}
    require(set(bundle["blobs"]) == expected, "bundle_blob_set")
    captured = {}
    for item in body["files"]:
        if item["kind"] == "delete": continue
        data = bundle["blobs"][item["digest"]]
        require(type(data) is bytes and len(data) == item["size"] and _sha(data) == item["digest"], "bundle_blob_mismatch")
        captured[item["digest"]] = data
    return body, captured, canonical_digest(body)


def _safe_relative(name):
    from p2_contracts import portable_path
    portable_path(name)
    return PurePosixPath(name).parts


def _reparse(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _walk(root, limit):
    pending = [Path(root)]; count = 0
    while pending:
        current = pending.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                count += 1; require(count <= limit, "tree_node_limit")
                # Windows DirEntry.stat reports zero nlink/dev/ino. Full lstat
                # is required for the same alias checks used by Linux.
                path = Path(entry.path); info = path.lstat()
                yield path, info
                if stat.S_ISDIR(info.st_mode) and not _reparse(info): pending.append(path)


def _materialize(body, blobs, directory, *, production=False, gid=None):
    directory.mkdir(mode=0o700)
    for item in body["files"]:
        if item["kind"] == "delete": continue
        target = directory.joinpath(*_safe_relative(item["path"]))
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(os.dup(fd), "wb") as stream:
                stream.write(blobs[item["digest"]]); stream.flush(); os.fsync(stream.fileno())
            if production: os.fchown(fd, 0, gid)
            mode = (0o550 if item["mode"] == "100755" else 0o440) if production else (0o755 if item["mode"] == "100755" else 0o644)
            if hasattr(os, "fchmod"): os.fchmod(fd, mode)
            else:
                require(not production, "production_fd_mode_required")
                os.chmod(target, mode)
        finally: os.close(fd)
    if production:
        for path in sorted([directory, *[p for p in directory.rglob("*") if p.is_dir()]], key=lambda p: len(p.parts), reverse=True):
            os.chown(path, 0, gid); os.chmod(path, 0o550)


def _verify_input(body, directory):
    expected = {item["path"]: item for item in body["files"] if item["kind"] == "blob"}
    actual = {}
    for path, info in _walk(directory, 2048):
        require(not _reparse(info), "input_alias")
        if stat.S_ISDIR(info.st_mode): continue
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "input_type")
        name = path.relative_to(directory).as_posix()
        require(name in expected and info.st_size == expected[name]["size"], "input_changed")
        require(_sha(path.read_bytes()) == expected[name]["digest"], "input_changed")
        require(not info.st_mode & 0o6000, "input_mode_changed")
        if os.name == "posix":
            require(bool(info.st_mode & 0o111) == (expected[name]["mode"] == "100755"), "input_mode_changed")
        actual[name] = True
    require(set(actual) == set(expected), "input_changed")


def read_outputs(directory, budget, *, owner=None):
    root = Path(directory)
    root_info = root.lstat()
    require(stat.S_ISDIR(root_info.st_mode) and not _reparse(root_info), "output_root")
    result, total, nodes = {}, 0, 0
    for path, info in _walk(root, 256):
        nodes += 1
        require(nodes <= 256 and len(path.relative_to(root).parts) <= 16, "output_tree_limit")
        require(not _reparse(info), "output_alias")
        if stat.S_ISDIR(info.st_mode):
            require(info.st_dev == root_info.st_dev, "output_mount")
            continue
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_dev == root_info.st_dev and not info.st_mode & 0o6000, "output_type")
        require(owner is None or info.st_uid == owner, "output_owner")
        name = path.relative_to(root).as_posix(); _safe_relative(name)
        require(len(result) < MAX_OUTPUT_FILES and info.st_size <= budget - total, "output_size")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
        try:
            now = os.fstat(fd)
            require((now.st_dev, now.st_ino, now.st_size, now.st_nlink) == (info.st_dev, info.st_ino, info.st_size, 1), "output_changed")
            with os.fdopen(os.dup(fd), "rb") as stream: data = stream.read(budget - total + 1)
            require(len(data) == info.st_size, "output_changed")
        finally: os.close(fd)
        result[name] = data; total += len(data)
    return result


def _capture(process, profile, kill, budget_check=None):
    outputs = {"stdout": bytearray(), "stderr": bytearray()}
    lock = threading.Lock(); overflow = threading.Event()
    def reader(stream, name):
        try:
            while True:
                chunk = stream.read(16384)
                if not chunk: break
                with lock:
                    room = profile.output_bytes - sum(len(x) for x in outputs.values())
                    outputs[name].extend(chunk[:max(room, 0)])
                    if len(chunk) > room: overflow.set(); break
        finally: stream.close()
    readers = [threading.Thread(target=reader, args=(process.stdout, "stdout"), daemon=True),
               threading.Thread(target=reader, args=(process.stderr, "stderr"), daemon=True)]
    for thread in readers: thread.start()
    def feed():
        try:
            if process.stdin: process.stdin.write(profile.stdin); process.stdin.close()
        except (BrokenPipeError, OSError): pass
    feeder = threading.Thread(target=feed, daemon=True); feeder.start()
    deadline = time.monotonic() + profile.timeout_seconds; timed_out = False
    while process.poll() is None:
        budget_failure = bool(budget_check and budget_check())
        if overflow.is_set() or budget_failure or time.monotonic() >= deadline:
            timed_out = not overflow.is_set() and not budget_failure; kill(); break
        time.sleep(0.01)
    try: process.wait(timeout=5)
    except subprocess.TimeoutExpired: kill(); raise ExecutorError("process_cleanup_incomplete") from None
    # The initial process may have exited while descendants retain output FDs.
    # Production's callback kills the entire dedicated cgroup, not a reused PID.
    kill()
    for thread in readers: thread.join(timeout=2)
    require(not any(thread.is_alive() for thread in readers), "output_pipe_not_closed")
    return process.returncode, timed_out, overflow.is_set(), bytes(outputs["stdout"]), bytes(outputs["stderr"])


class FixtureExecutor:
    """Real subprocesses for explicitly trusted fixture programs, never authority."""
    def __init__(self, work_root, *, trusted_fixtures=False):
        require(trusted_fixtures is True, "explicit_trusted_fixture_required")
        self.work_root = Path(work_root).resolve(); self.work_root.mkdir(parents=True, exist_ok=True)
        self.config_digest = None

    def run(self, bundle, profile):
        body, blobs, candidate_digest = validate_bundle(bundle)
        pd = execution_profile_digest(profile)
        with tempfile.TemporaryDirectory(prefix="p2-fixture-", dir=self.work_root) as temporary:
            root = Path(temporary); inputs = root / "input"; output = root / "output"; output.mkdir()
            _materialize(body, blobs, inputs)
            def translate(argument):
                if argument.startswith("/input/"): return str(inputs.joinpath(*_safe_relative(argument[7:])))
                if argument.startswith("/output/"): return str(output.joinpath(*_safe_relative(argument[8:])))
                return argument
            argv = [translate(arg) for arg in profile.argv]
            env = {"PATH": os.defpath, "LANG": "C.UTF-8", "HOME": str(root), "TMPDIR": str(root), "TEMP": str(root), "TMP": str(root)}
            if os.name == "nt": env["SystemRoot"] = os.environ.get("SystemRoot", "C:\\Windows")
            process = subprocess.Popen(argv, cwd=output, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       close_fds=True, start_new_session=os.name == "posix")
            def kill():
                try:
                    if process.poll() is not None: return
                    if os.name == "posix": os.killpg(process.pid, signal.SIGKILL)
                    else: process.kill()
                except ProcessLookupError: pass
            code, timeout, overflow, stdout, stderr = _capture(process, profile, kill)
            _verify_input(body, inputs)
            files = read_outputs(output, profile.output_bytes - len(stdout) - len(stderr))
            return ExecutionResult(candidate_digest, pd, "fixture", True, False, code, timeout, overflow, stdout, stderr, files,
                                   {"executor_config_digest": None, "authority": "trusted_fixture_only", "production_eligible": False})


def _trusted(path, *, directory=False):
    target = Path(path)
    require(target.is_absolute() and ".." not in target.parts, "trusted_path")
    for item in [*reversed(target.parents), target]:
        info = item.lstat()
        require(info.st_uid == 0 and not stat.S_ISLNK(info.st_mode) and info.st_mode & 0o022 == 0, "untrusted_runtime_or_profile")
        require(stat.S_ISDIR(info.st_mode) if item != target or directory else stat.S_ISREG(info.st_mode), "trusted_path_type")
        if item == target and not directory: require(info.st_nlink == 1, "trusted_link")


def _read_bounded(path, maximum=256 * 1024):
    with Path(path).open("rb") as stream: data = stream.read(maximum + 1)
    require(len(data) <= maximum, "trusted_input_limit")
    return data


def _file_capabilities(path):
    try: return os.getxattr(path, "security.capability")
    except OSError as error:
        if error.errno in {errno.ENODATA, errno.ENOTSUP, errno.EOPNOTSUPP}: return b""
        raise ExecutorError("file_capability_metadata_unavailable") from None


def rootfs_digest(root):
    root = Path(root); _trusted(root, directory=True)
    require(root.parent == Path("/var/lib/multi-p2/rootfs") and re.fullmatch(r"image-[0-9a-f]{64}", root.name) is not None, "rootfs_managed_path")
    rows = []; total = 0
    for path, info in _walk(root, 20000):
        require(len(rows) < 20000, "rootfs_file_limit")
        name = path.relative_to(root).as_posix()
        require(info.st_uid == 0 and (stat.S_ISLNK(info.st_mode) or info.st_mode & 0o022 == 0), "untrusted_rootfs")
        require(not (name.split("/")[0] in {"home", "root", "run", "proc", "dev", "sys", "var"} and "/" in name), "rootfs_private_content")
        require(name not in {"etc/shadow", "etc/gshadow", "etc/gitconfig"} and not name.startswith("etc/ssh/") and Path(name).name not in {".gitconfig", ".git-credentials"}, "rootfs_credentials_rejected")
        if stat.S_ISDIR(info.st_mode):
            require(not path.is_mount(), "nested_rootfs_mount_rejected")
            rows.append({"path": name, "kind": "directory", "mode": stat.S_IMODE(info.st_mode)})
        elif stat.S_ISLNK(info.st_mode): rows.append({"path": name, "kind": "symlink", "target": os.readlink(path)})
        else:
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and not info.st_mode & 0o6000 and info.st_size <= 64 * 1024 * 1024, "rootfs_type")
            total += info.st_size; require(total <= 1024 * 1024 * 1024, "rootfs_size")
            rows.append({"path": name, "kind": "file", "mode": stat.S_IMODE(info.st_mode), "digest": _sha(_read_bounded(path, 64 * 1024 * 1024))})
    return _json_digest(sorted(rows, key=lambda value: value["path"].encode("utf-8")))


def sandbox_gate_command(profile, *, grant_fd, life_fd, ack_fd, token):
    require(type(token) is bytes and len(token) == 32, "gate_token")
    return ["/usr/bin/python3", "-I", "-S", "-B", "/p2/sandbox_gate.py", "--grant-fd", str(grant_fd),
            "--lifeline-fd", str(life_fd), "--ack-fd", str(ack_fd), "--token", token.hex(),
            "--timeout-seconds", str(profile.timeout_seconds), "--", *profile.argv]


def build_bwrap_command(config, profile, inputs, output, *, grant_fd, info_fd, life_fd, ack_fd, token):
    profile_value(profile)
    require(profile.argv[0].startswith("/") and not profile.argv[0].startswith(("/input/", "/output/")), "trusted_interpreter_required")
    return [config["bwrap_path"], "--unshare-user", "--unshare-pid", "--unshare-net", "--unshare-ipc", "--unshare-uts", "--unshare-cgroup",
            "--disable-userns", "--assert-userns-disabled", "--die-with-parent", "--new-session", "--as-pid-1", "--uid", "65534", "--gid", "65534",
            "--cap-drop", "ALL", "--clearenv", "--ro-bind", config["rootfs_path"], "/", "--ro-bind", str(inputs), "/input",
            "--bind", str(output), "/output", "--proc", "/proc", "--dev", "/dev", "--size", str(profile.output_bytes), "--tmpfs", "/tmp",
            "--chdir", "/output", "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/nonexistent", "--setenv", "LANG", "C.UTF-8",
            "--info-fd", str(info_fd), "--", *sandbox_gate_command(profile, grant_fd=grant_fd, life_fd=life_fd, ack_fd=ack_fd, token=token)]


def _mount_tmpfs(path, size, uid, gid):
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    libc.mount.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_ulong, ctypes.c_char_p]
    options = f"size={size},nr_inodes=256,uid={uid},gid={gid},mode=0700".encode()
    require(libc.mount(b"tmpfs", os.fsencode(path), b"tmpfs", 2 | 4 | 8, options) == 0, "output_tmpfs_unavailable")


def _unmount(path):
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    libc.umount2.argtypes = [ctypes.c_char_p, ctypes.c_int]
    require(libc.umount2(os.fsencode(path), 0) == 0, "output_unmount_failed")


def _status(pid):
    values = {}
    for line in _read_bounded(f"/proc/{pid}/status", 65536).decode().splitlines():
        name, _, value = line.partition(":"); values[name] = value.strip()
    return values


def observe_sandbox(pid, config, inputs, output, cgroup, gate_command):
    require(type(pid) is int and pid > 1, "sandbox_pid")
    values = _status(pid)
    command = _read_bounded(f"/proc/{pid}/cmdline", 256 * 1024).split(b"\0")[:-1]
    require(command == [arg.encode("utf-8") for arg in gate_command], "trusted_gate_not_running")
    require(set(map(int, values["Uid"].split())) == {config["worker_uid"]} and set(map(int, values["Gid"].split())) == {config["worker_gid"]}, "sandbox_identity")
    require(not values.get("Groups") and values.get("NoNewPrivs") == "1" and values.get("Seccomp") == "2", "sandbox_privileges")
    require(all(int(values.get(name, "1"), 16) == 0 for name in ("CapEff", "CapPrm", "CapInh", "CapAmb")), "sandbox_capabilities")
    namespaces = {name: os.readlink(f"/proc/{pid}/ns/{name}") for name in NS_NAMES}
    require(all(value != os.readlink(f"/proc/self/ns/{name}") for name, value in namespaces.items()), "namespace_not_isolated")
    expected_cgroup = "/" + str(Path(cgroup).relative_to("/sys/fs/cgroup"))
    require(_read_bounded(f"/proc/{pid}/cgroup", 4096).decode().strip() == "0::" + expected_cgroup, "sandbox_cgroup")
    mounts = {}
    for line in _read_bounded(f"/proc/{pid}/mountinfo", 128 * 1024).decode().splitlines():
        fields = line.split(); mounts[fields[4]] = set(fields[5].split(","))
    for inside, outside, readonly in (("/", Path(config["rootfs_path"]), True), ("/input", Path(inputs), True), ("/output", Path(output), False)):
        require(inside in mounts and ("ro" if readonly else "rw") in mounts[inside], "sandbox_mount_mode")
        visible = Path(f"/proc/{pid}/root") / inside.lstrip("/")
        require((visible.stat().st_dev, visible.stat().st_ino) == (outside.stat().st_dev, outside.stat().st_ino), "sandbox_mount_identity")
    interfaces = _read_bounded(f"/proc/{pid}/net/dev", 16384).decode().splitlines()[2:]
    require(all(line.split(":", 1)[0].strip() == "lo" for line in interfaces), "sandbox_network_interface")
    return {"worker_uid": config["worker_uid"], "worker_gid": config["worker_gid"], "namespaces": namespaces,
            "network": "loopback_only", "input_mount": "read_only", "capabilities": "none", "cgroup": expected_cgroup}


def _systemd_lifetime():
    _trusted(Path("/usr/bin/systemctl"))
    names = ("MainPID", "KillMode", "ExitType", "SendSIGKILL", "TimeoutStopUSec", "RuntimeMaxUSec", "PrivateMounts", "DelegateSubgroup", "KeyringMode")
    command = ["/usr/bin/systemctl", "show", "multi-p2-executor.service", "--no-pager", *["--property=" + name for name in names]]
    result = subprocess.run(command, capture_output=True, timeout=5, env={"PATH": "/usr/bin:/bin", "LANG": "C"}, cwd="/")
    require(result.returncode == 0 and len(result.stdout) <= 8192, "systemd_lifetime_unverified")
    values = dict(line.split("=", 1) for line in result.stdout.decode().splitlines() if "=" in line)
    require(values.get("MainPID") == str(os.getpid()) and values.get("KillMode") == "control-group" and
            values.get("ExitType") == "main" and values.get("SendSIGKILL") == "yes" and values.get("PrivateMounts") == "yes" and
            values.get("DelegateSubgroup") == "supervisor" and values.get("KeyringMode") == "private", "independent_job_lifetime_required")
    def seconds(value):
        match = re.fullmatch(r"([0-9]+)(us|ms|s|min)", value or "")
        require(match is not None, "finite_service_budget_required")
        return int(match.group(1)) * {"us": .000001, "ms": .001, "s": 1, "min": 60}[match.group(2)]
    require(0 < seconds(values.get("TimeoutStopUSec")) <= 5 and 0 < seconds(values.get("RuntimeMaxUSec")) <= 360, "service_lifetime_budget")
    return {name: values[name] for name in names}


def _cgroup_values(path):
    return {key: int(value) for key, value in (line.split() for line in _read_bounded(path, 4096).decode().splitlines())}


def _wait_empty(cgroup):
    deadline = time.monotonic() + 5
    while _cgroup_values(cgroup / "cgroup.events").get("populated") and time.monotonic() < deadline:
        time.sleep(.02)
    require(_cgroup_values(cgroup / "cgroup.events").get("populated") == 0, "job_processes_remain")


class BwrapExecutor:
    """Production root observer. Untrusted code starts only after kernel checks."""
    def __init__(self, config_path):
        require(sys.platform == "linux" and os.geteuid() == 0, "root_linux_supervisor_required")
        require(sys.flags.isolated and sys.flags.no_site, "isolated_no_site_supervisor_required")
        import platform
        require("wsl" not in platform.release().lower(), "wsl_not_production")
        require(platform.machine() == "x86_64", "amd64_seccomp_profile_required")
        _trusted(Path(__file__).absolute()); _trusted(Path(sys.executable)); _trusted(Path(config_path))
        value = _json(_read_bounded(config_path))
        keys = {"schema_version", "worker_uid", "worker_gid", "publisher_uid", "enrollment_id", "machine_id_sha256", "rootfs_path", "rootfs_digest",
                "bwrap_path", "bwrap_sha256", "jobs_root", "cgroup_root", "profiles"}
        require(type(value) is dict and set(value) == keys and value["schema_version"] == "0.1.0", "executor_config_fields")
        require(all(type(value[key]) is int and 0 < value[key] <= 2147483647 for key in ("worker_uid", "worker_gid", "publisher_uid")) and value["worker_uid"] != value["publisher_uid"], "separate_worker_identity_required")
        require(hashlib.sha256(_read_bounded("/etc/machine-id", 256)).hexdigest() == value["machine_id_sha256"], "executor_host_mismatch")
        require(value["jobs_root"] == "/var/lib/multi-p2/executor/jobs" and value["cgroup_root"] == CGROUP_ROOT, "executor_roots")
        for name in ("jobs_root", "cgroup_root", "rootfs_path"): _trusted(Path(value[name]), directory=True)
        _trusted(Path(value["bwrap_path"]))
        executable = Path(value["bwrap_path"]).stat()
        require(not executable.st_mode & 0o6000 and _sha(_read_bounded(value["bwrap_path"], 8 * 1024 * 1024)) == value["bwrap_sha256"], "trusted_bwrap_required")
        capabilities = _file_capabilities(value["bwrap_path"])
        require(not capabilities, "privileged_bwrap_rejected")
        require(rootfs_digest(value["rootfs_path"]) == value["rootfs_digest"], "rootfs_digest_mismatch")
        import pwd, grp
        account = pwd.getpwuid(value["worker_uid"])
        require(account.pw_name.startswith("multi-p2-worker") and account.pw_shell in ("/usr/sbin/nologin", "/sbin/nologin", "/bin/false") and account.pw_dir == "/nonexistent", "dedicated_worker_required")
        groups = os.getgrouplist(account.pw_name, value["worker_gid"])
        require(not {grp.getgrgid(gid).gr_name for gid in groups} & {"sudo", "wheel", "admin", "docker", "lxd", "libvirt", "kvm"}, "privileged_worker_rejected")
        require(type(value["profiles"]) is dict and 1 <= len(value["profiles"]) <= 16, "approved_profiles_required")
        self.profiles = {name: _profile(profile) for name, profile in value["profiles"].items()}
        require(all(name == profile.profile_id for name, profile in self.profiles.items()), "profile_id_mismatch")
        self.config = value; self.config_digest = _json_digest(value); self.config_path = Path(config_path)
        self.preflight()

    @classmethod
    def from_config(cls, config_path):
        return cls(config_path)

    def preflight(self):
        require(sys.platform == "linux" and os.geteuid() == 0 and sys.flags.isolated and sys.flags.no_site, "root_supervisor_context")
        _trusted(self.config_path)
        require(_json_digest(_json(_read_bounded(self.config_path))) == self.config_digest == _json_digest(self.config), "executor_config_changed")
        _trusted(Path(__file__).absolute()); _trusted(Path(sys.executable)); _trusted(Path(self.config["bwrap_path"]))
        require(not Path(self.config["bwrap_path"]).stat().st_mode & 0o6000, "privileged_bwrap_rejected")
        require(_sha(_read_bounded(self.config["bwrap_path"], 8 * 1024 * 1024)) == self.config["bwrap_sha256"], "bwrap_changed")
        caps = _file_capabilities(self.config["bwrap_path"])
        require(not caps, "privileged_bwrap_rejected")
        require(rootfs_digest(self.config["rootfs_path"]) == self.config["rootfs_digest"], "rootfs_digest_mismatch")
        gate = Path(__file__).absolute().with_name("p2_sandbox_gate.py")
        image_gate = Path(self.config["rootfs_path"]) / "p2/sandbox_gate.py"
        _trusted(gate); _trusted(image_gate); _trusted(Path(self.config["rootfs_path"]) / "usr/bin/python3")
        require(_read_bounded(gate) == _read_bounded(image_gate), "sandbox_gate_not_installed_release")
        require(os.readlink("/proc/self/ns/mnt") != os.readlink("/proc/1/ns/mnt"), "private_supervisor_mount_namespace_required")
        expected = "/" + str(Path(self.config["cgroup_root"]).relative_to("/sys/fs/cgroup")) + "/supervisor"
        require(_read_bounded("/proc/self/cgroup", 4096).decode().strip() == "0::" + expected, "delegated_supervisor_cgroup_required")
        controllers = (Path(self.config["cgroup_root"]) / "cgroup.subtree_control").read_text().split()
        require({"cpu", "memory", "pids"} <= set(controllers), "delegated_controllers_required")
        jobs = Path(self.config["jobs_root"])
        mounts = []
        for line in _read_bounded("/proc/self/mountinfo", 256 * 1024).decode().splitlines():
            fields = line.split(); mount = Path(re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), fields[4]))
            if jobs == mount or mount in jobs.parents: mounts.append((len(mount.parts), fields[6:fields.index("-")]))
        require(mounts and not any(value.startswith("shared:") for value in max(mounts)[1]), "supervisor_mount_propagation_unsafe")
        _systemd_lifetime()
        return {"prerequisites_checked": True, "isolation_verified": False, "executor_config_digest": self.config_digest}

    def run(self, bundle, profile):
        self.preflight()
        body, blobs, candidate_digest = validate_bundle(bundle); pd = execution_profile_digest(profile)
        require(body["binding"]["enrollment_id"] == self.config["enrollment_id"], "executor_enrollment")
        require(profile.profile_id in self.profiles and execution_profile_digest(self.profiles[profile.profile_id]) == pd, "unapproved_execution_profile")
        import fcntl
        lock_path = Path(self.config["jobs_root"]) / ".executor.lock"
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            used = 0; directories = 0
            for path in Path(self.config["jobs_root"]).iterdir():
                if path.name == ".executor.lock": continue
                info = path.lstat()
                require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode), "job_store_type")
                directories += 1
                for item in path.rglob("*"):
                    require(not item.is_symlink() and not item.is_mount(), "unfinished_job_requires_reconciliation")
                    node = item.lstat()
                    require(stat.S_ISDIR(node.st_mode) or stat.S_ISREG(node.st_mode), "unfinished_job_requires_reconciliation")
                    used += max(node.st_size, getattr(node, "st_blocks", 0) * 512) + 4096
            # One CAS blob may be materialized at many paths. Charge each copy.
            input_directories = set()
            for item in body["files"]:
                parts = PurePosixPath(item["path"]).parts
                input_directories.update(parts[:index] for index in range(1, len(parts)))
            block = max(os.statvfs(self.config["jobs_root"]).f_frsize, 4096)
            needed = sum(item["size"] for item in body["files"] if item["kind"] == "blob") + MAX_LAUNCH_BYTES + (len(input_directories) + len(body["files"]) + 8) * block * 2
            require(directories < MAX_RETAINED_JOBS and used + needed <= MAX_RETAINED_BYTES, "executor_retention_quota")
            for status in Path("/proc").glob("[0-9]*/status"):
                try: values = _status(int(status.parent.name))
                except (OSError, ValueError): continue
                require(self.config["worker_uid"] not in map(int, values["Uid"].split()), "worker_identity_already_active")
            return self._run_locked(body, blobs, candidate_digest, profile, pd)

    def _run_locked(self, body, blobs, candidate_digest, profile, pd):
        root = Path(self.config["jobs_root"]) / ("job-" + uuid4().hex)
        root.mkdir(mode=0o710); os.chown(root, 0, self.config["worker_gid"]); os.chmod(root, 0o710)
        inputs, output = root / "input", root / "output"
        cgroup = Path(self.config["cgroup_root"]) / root.name
        mounted = False; cgroup_created = False; process = None
        descriptors = {}; observed = None; budget_reason = None; token = secrets.token_bytes(32)
        def close(name):
            descriptor = descriptors.pop(name, None)
            if descriptor is not None: os.close(descriptor)
        def kill():
            if cgroup_created and (cgroup / "cgroup.kill").is_file():
                (cgroup / "cgroup.kill").write_text("1")
        def budget_check():
            nonlocal budget_reason
            if _cgroup_values(cgroup / "cpu.stat").get("usage_usec", 0) > profile.cpu_seconds * 1000000:
                budget_reason = "aggregate_cpu_budget"
            if _cgroup_values(cgroup / "memory.events").get("oom_kill", 0): budget_reason = "memory_budget"
            if _cgroup_values(cgroup / "pids.events").get("max", 0): budget_reason = "process_budget"
            return budget_reason
        try:
            _materialize(body, blobs, inputs, production=True, gid=self.config["worker_gid"]); output.mkdir(mode=0o700)
            cgroup.mkdir(mode=0o700); cgroup_created = True
            for name in ("memory.max", "memory.swap.max", "memory.events", "pids.max", "pids.events", "cpu.max", "cpu.stat", "cgroup.kill", "cgroup.procs", "cgroup.events"):
                require((cgroup / name).is_file(), "cgroup_v2_budget_unavailable")
            for name, value in {"memory.max": profile.memory_bytes, "memory.swap.max": 0, "pids.max": profile.tasks, "cpu.max": "100000 100000"}.items():
                (cgroup / name).write_text(str(value))
            require(0 < int((cgroup / "memory.max").read_text()) <= profile.memory_bytes and int((cgroup / "memory.swap.max").read_text()) == 0 and
                    int((cgroup / "pids.max").read_text()) == profile.tasks and (cgroup / "cpu.max").read_text().split() == ["100000", "100000"], "cgroup_budget_readback")
            _mount_tmpfs(output, profile.output_bytes, self.config["worker_uid"], self.config["worker_gid"]); mounted = True
            for kind in ("grant", "life", "info", "ack"):
                descriptors[kind + "_r"], descriptors[kind + "_w"] = os.pipe()
            gate_command = sandbox_gate_command(profile, grant_fd=descriptors["grant_r"], life_fd=descriptors["life_r"], ack_fd=descriptors["ack_w"], token=token)
            launch = {"config": self.config, "profile": profile_value(profile), "root": str(root), "cgroup": str(cgroup),
                      "grant_fd": descriptors["grant_r"], "info_fd": descriptors["info_w"], "life_fd": descriptors["life_r"],
                      "ack_fd": descriptors["ack_w"], "token": token.hex()}
            launch_path = root / "launch.json"
            launch_bytes = json.dumps(launch).encode(); require(len(launch_bytes) <= MAX_LAUNCH_BYTES, "launch_limit")
            fd = os.open(launch_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream: stream.write(launch_bytes)
            descriptors["config"] = os.open(launch_path, os.O_RDONLY | os.O_NOFOLLOW)
            process = subprocess.Popen([sys.executable, "-I", "-S", "-B", str(Path(__file__).absolute()), "--child-launch-fd", str(descriptors["config"])],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd="/", env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                                       close_fds=True, pass_fds=tuple(descriptors[name] for name in ("config", "grant_r", "life_r", "info_w", "ack_w")), start_new_session=True)
            for name in ("config", "grant_r", "life_r", "info_w", "ack_w"): close(name)
            os.set_blocking(descriptors["info_r"], False); info = bytearray(); setup_deadline = time.monotonic() + 10
            while time.monotonic() < setup_deadline:
                try: chunk = os.read(descriptors["info_r"], 16384)
                except BlockingIOError: chunk = b""
                info.extend(chunk); require(len(info) <= 16384, "sandbox_info_limit")
                try: details = _json(bytes(info), 16384)
                except (ExecutorError, ValueError): details = None
                if details and type(details.get("child-pid")) is int:
                    try:
                        observed = observe_sandbox(details["child-pid"], self.config, inputs, output, cgroup, gate_command)
                        break
                    except (ExecutorError, OSError, ValueError, KeyError): pass
                exit_code = process.poll()
                if exit_code is not None:
                    _setup_diagnostic(root, process, token, exit_code)
                    require(False, "sandbox_setup_failed")
                time.sleep(0.01)
            require(observed is not None, "sandbox_postconditions_unverified")
            self.preflight(); require(not budget_check(), "setup_budget_exceeded")
            # This is an exact nonce consumed by the trusted nondumpable PID1
            # shim, not bwrap's EOF-releasing block-fd implementation.
            os.write(descriptors["grant_w"], token); close("grant_w")
            os.set_blocking(descriptors["ack_r"], False); ack_data = bytearray(); ack = None
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try: ack_data.extend(os.read(descriptors["ack_r"], 1024))
                except BlockingIOError: pass
                require(len(ack_data) <= 1024, "gate_ack_limit")
                if b"\n" in ack_data:
                    first_line, remaining = bytes(ack_data).split(b"\n", 1)
                    ack = _json(first_line, 1024); ack_data = bytearray(remaining)
                else: ack = None
                if ack: break
                require(process.poll() is None, "candidate_not_started")
                time.sleep(.01)
            require(type(ack) is dict and set(ack) == {"started", "token_digest", "child_pid", "seccomp_policy"} and ack["started"] is True and
                    ack["token_digest"] == hashlib.sha256(token).hexdigest() and type(ack["child_pid"]) is int and ack["child_pid"] > 1 and
                    ack["seccomp_policy"] == "amd64-af-unix-only-v1", "candidate_start_unverified")
            code, timeout, overflow, stdout, stderr = _capture(process, profile, kill, budget_check)
            kill(); _wait_empty(cgroup); budget_check()
            while True:
                try: tail = os.read(descriptors["ack_r"], 1024)
                except BlockingIOError: break
                if not tail: break
                ack_data.extend(tail); require(len(ack_data) <= 1024, "gate_terminal_limit")
            terminal = None
            if b"\n" in ack_data:
                line, leftover = bytes(ack_data).split(b"\n", 1)
                require(not leftover, "gate_terminal_extra_data")
                terminal = _json(line, 1024)
                require(type(terminal) is dict and set(terminal) == {"finished", "token_digest", "reason", "exit_code"} and terminal["finished"] is True and
                        terminal["token_digest"] == hashlib.sha256(token).hexdigest() and type(terminal["exit_code"]) is int, "gate_terminal_invalid")
                if terminal["reason"] == "wall_budget": timeout = True
            if not timeout and not overflow and not budget_reason:
                require(terminal is not None and terminal["reason"] == "exited" and terminal["exit_code"] == code, "gate_terminal_unverified")
            _verify_input(body, inputs)
            self.preflight()  # Runtime/config approval must also remain current after execution.
            files = read_outputs(output, profile.output_bytes - len(stdout) - len(stderr), owner=self.config["worker_uid"])
            return ExecutionResult(candidate_digest, pd, "bwrap", False, True, code, timeout, overflow, stdout, stderr, files,
                                   {**observed, "executor_config_digest": self.config_digest, "cgroup_empty": True, "execution_started": True,
                                    "seccomp_policy": ack["seccomp_policy"], "keyring_mode": "private",
                                    "aggregate_cpu_usec": _cgroup_values(cgroup / "cpu.stat").get("usage_usec", 0), "termination_reason": budget_reason or (terminal or {}).get("reason")}, bool(budget_reason))
        except Exception as error:
            failure = {"job_id": root.name, "status": "failed_preserved", "code": getattr(error, "code", "setup_or_cleanup_failed"), "candidate_started": False if observed is None else "unverified"}
            try:
                with (root / "failure.json").open("x", encoding="utf-8") as stream: json.dump(failure, stream)
            except OSError: pass
            raise
        finally:
            kill()
            if process is not None:
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
            for name in list(descriptors): close(name)
            if cgroup_created and (cgroup / "cgroup.events").exists(): _wait_empty(cgroup)
            if mounted: _unmount(output)
            if cgroup_created and (cgroup / "cgroup.events").exists(): cgroup.rmdir()
            # Evidence/input directories are preserved for trusted reconciliation.


def _setup_diagnostic(root, process, token, exit_code):
    """Best-effort bounded evidence; never changes the setup rejection."""
    try:
        descriptor = process.stderr.fileno()
        os.set_blocking(descriptor, False)
        try: data = os.read(descriptor, 4096)
        except BlockingIOError: data = b""
        text = data.decode("utf-8", "replace")
        for nonce in (token.hex(), token.hex().upper()):
            text = text.replace(nonce, "[redacted]")
            for size in range(len(nonce) - 1, 0, -1):
                if text.endswith(nonce[:size]):
                    text = text[:-size] + "[redacted-partial]"
                    break
        target = root / "setup-diagnostic.json"
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"exit_code": exit_code, "stderr": text, "stderr_bytes_read": len(data)}, stream)
    except (OSError, ValueError):
        pass


def _child_launch(fd):
    require(sys.platform == "linux" and os.geteuid() == 0 and sys.flags.isolated and sys.flags.no_site, "trusted_root_child_required")
    _trusted(Path(__file__).absolute()); _trusted(Path(sys.executable))
    info = os.fstat(fd)
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1 and info.st_mode & 0o077 == 0, "launch_descriptor")
    with os.fdopen(fd, "rb") as stream: launch = _json(stream.read(MAX_LAUNCH_BYTES + 1), MAX_LAUNCH_BYTES)
    require(set(launch) == {"config", "profile", "root", "cgroup", "grant_fd", "info_fd", "life_fd", "ack_fd", "token"}, "launch_fields")
    require(all(type(launch[name]) is int and launch[name] > 2 for name in ("grant_fd", "info_fd", "life_fd", "ack_fd")) and
            len({launch[name] for name in ("grant_fd", "info_fd", "life_fd", "ack_fd")}) == 4, "launch_descriptors")
    config = launch["config"]; profile = _profile(launch["profile"]); root = Path(launch["root"]); cgroup = Path(launch["cgroup"])
    require(root.parent == Path("/var/lib/multi-p2/executor/jobs") and re.fullmatch(r"job-[0-9a-f]{32}", root.name) is not None, "launch_root")
    require(cgroup == Path(CGROUP_ROOT) / root.name, "launch_cgroup")
    _trusted(root, directory=True); _trusted(cgroup, directory=True); _trusted(Path(config["bwrap_path"]))
    (cgroup / "cgroup.procs").write_text(str(os.getpid()))
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (profile.cpu_seconds, profile.cpu_seconds))
    resource.setrlimit(resource.RLIMIT_FSIZE, (profile.output_bytes, profile.output_bytes))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128)); resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NPROC, (profile.tasks, profile.tasks))
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    require(libc.prctl(38, 1, 0, 0, 0) == 0, "no_new_privileges_unavailable")
    parent = os.getppid()
    os.setgroups([])
    os.setgid(config["worker_gid"])
    os.setuid(config["worker_uid"])
    require(os.geteuid() == config["worker_uid"] != 0 and os.getegid() == config["worker_gid"] and not os.getgroups(), "worker_drop_failed")
    require(libc.prctl(1, signal.SIGKILL, 0, 0, 0) == 0 and os.getppid() == parent, "parent_lifetime_unavailable")
    argv = build_bwrap_command(config, profile, root / "input", root / "output", grant_fd=launch["grant_fd"], info_fd=launch["info_fd"],
                               life_fd=launch["life_fd"], ack_fd=launch["ack_fd"], token=bytes.fromhex(launch["token"]))
    os.execve(config["bwrap_path"], argv, {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child-launch-fd", type=int, required=True)
    args = parser.parse_args(argv)
    try: _child_launch(args.child_launch_fd)
    except Exception as error:
        trace = error.__traceback__
        while trace.tb_next is not None: trace = trace.tb_next
        print(json.dumps({"status": "failed", "code": getattr(error, "code", "child_setup_failed"),
                          "exception_type": type(error).__name__, "errno": getattr(error, "errno", None),
                          "line": trace.tb_lineno}), file=sys.stderr)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
