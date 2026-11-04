"""Fixed trusted-root verification entry; candidate execution is delegated to bwrap."""
from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
from uuid import UUID


def validate_job(value):
    keys = {"schema_version", "job_id", "enrollment_id", "worker_uid", "worker_gid",
            "input_tree_digest", "entry_sha256", "limits"}
    if type(value) is not dict or set(value) != keys or value["schema_version"] != "0.1.0":
        raise ValueError("invalid_worker_job_fields")
    if type(value["job_id"]) is not str or not re.fullmatch(r"job-[0-9a-f]{32}", value["job_id"]):
        raise ValueError("invalid_worker_job_id")
    try:
        if str(UUID(value["enrollment_id"])) != value["enrollment_id"]:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ValueError("invalid_worker_enrollment") from None
    for field in ("worker_uid", "worker_gid"):
        if type(value[field]) is not int or not 1 <= value[field] <= 2147483647:
            raise ValueError("invalid_worker_identity")
    for field in ("input_tree_digest", "entry_sha256"):
        if type(value[field]) is not str or not re.fullmatch(r"sha256:[0-9a-f]{64}", value[field]):
            raise ValueError("invalid_worker_digest")
    limits = value["limits"]
    if type(limits) is not dict or set(limits) != {"cpu_seconds", "memory_bytes", "tasks"}:
        raise ValueError("invalid_worker_limits")
    for name, maximum in (("cpu_seconds", 30), ("memory_bytes", 512 * 1024 * 1024), ("tasks", 64)):
        if type(limits[name]) is not int or not 1 <= limits[name] <= maximum:
            raise ValueError("worker_limit_outside_profile")
    return {"contract_valid": True, "execution_permitted": False,
            "entrypoint": "/job/input/candidate.py", "output_root": "/job/output",
            "status": "requires_protected_verification_job"}


def prepare_private_mounts():
    """Privatize propagation only inside an already separate Linux namespace."""
    if sys.platform != "linux" or os.geteuid() != 0:
        raise ValueError("trusted_root_supervisor_required")
    current = os.readlink("/proc/self/ns/mnt")
    host = os.readlink("/proc/1/ns/mnt")
    if not all(re.fullmatch(r"mnt:\[\d+\]", value) for value in (current, host)) or current == host:
        raise ValueError("private_supervisor_mount_namespace_required")
    libc = ctypes.CDLL(None, use_errno=True)
    mount = libc.mount
    mount.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_ulong, ctypes.c_void_p]
    mount.restype = ctypes.c_int
    # Linux MS_REC | MS_PRIVATE: affect this namespace only, never host PID 1.
    if mount(None, b"/", None, (1 << 14) | (1 << 18), None) != 0:
        error = ctypes.get_errno()
        raise OSError(error, "private_mount_propagation_failed")


def prepare_delegated_controllers():
    """Enable controllers only inside the unit's already-delegated empty root."""
    root = Path("/sys/fs/cgroup/system.slice/multi-p2-executor.service")
    expected = "0::/system.slice/multi-p2-executor.service/supervisor"
    if Path("/proc/self/cgroup").read_text().strip() != expected:
        raise ValueError("delegated_supervisor_cgroup_required")
    if (root / "cgroup.procs").read_text().strip():
        raise ValueError("delegated_root_not_empty")
    required = {"cpu", "memory", "pids"}
    if not required <= set((root / "cgroup.controllers").read_text().split()):
        raise ValueError("delegated_controllers_unavailable")
    control = root / "cgroup.subtree_control"
    if not required <= set(control.read_text().split()):
        control.write_text("+cpu +memory +pids\n")
    if not required <= set(control.read_text().split()):
        raise ValueError("delegated_controllers_enable_failed")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--rpc", action="store_true")
    args=parser.parse_args(argv)
    verification_started = False
    try:
        if sys.platform != "linux" or os.geteuid() != 0 or not sys.flags.isolated or not sys.flags.no_site:
            raise ValueError("trusted_root_supervisor_required")
        runtime = Path("/opt/multi-p2/runtime")
        def trusted(path):
            for part in [*reversed(path.parents), path]:
                info = part.lstat()
                if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
                    raise ValueError("trusted_entry_path_required")
        trusted(Path(__file__).absolute()); trusted(runtime / "p2_broker.py")
        spec = importlib.util.spec_from_file_location("multi_p2_entry_bootstrap", runtime / "p2_broker.py")
        bootstrap = importlib.util.module_from_spec(spec); spec.loader.exec_module(bootstrap)
        bootstrap._trusted_runtime()
        sys.path.insert(0, str(runtime))
        from p2_verifier import verify_job
        prepare_private_mounts()
        prepare_delegated_controllers()
        if args.rpc:
            from p2_rpc import serve
            serve('verify')
            return 0
        verification_started = True
        result = verify_job("/etc/multi-p2/verification-job.json")
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, ImportError) as error:
        print(json.dumps({"status": "unknown" if verification_started else "blocked", "reason": getattr(error, "code", type(error).__name__),
                          "execution_permitted": False, "candidate_executed": "unverified" if verification_started else False}))
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
