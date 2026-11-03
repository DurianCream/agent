"""Read-only Linux capability/identity observation; never an isolation attestation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import subprocess
import sys

MIN_SYSTEMD = 247
REQUIRED_CONTROLLERS = {"cpu", "memory", "pids"}


def _read(path, limit=16384):
    with Path(path).open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("preflight_input_limit")
    return data


def parse_os_release(data):
    text = data.decode("utf-8", "strict")
    values = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key not in {"ID", "VERSION_ID", "PRETTY_NAME", "VERSION"}:
            continue
        if key in values:
            raise ValueError("duplicate_os_release_field")
        parsed = shlex.split(value, posix=True)
        if len(parsed) != 1:
            raise ValueError("invalid_os_release_field")
        values[key] = parsed[0]
    if not values.get("ID") or not values.get("VERSION_ID"):
        raise ValueError("missing_os_identity")
    return values


def _command(arguments):
    result = subprocess.run(arguments, capture_output=True, timeout=5,
                            env={"PATH": "/usr/bin:/bin", "LANG": "C"}, cwd="/")
    if len(result.stdout) > 16384 or len(result.stderr) > 16384:
        raise ValueError("preflight_command_output_limit")
    return result.returncode, result.stdout.decode("utf-8", "replace").strip()


def collect():
    facts = {"schema_version": "0.1.0", "platform": sys.platform,
             "architecture": platform.machine(), "kernel_release": platform.release(),
             "python_version": list(sys.version_info[:3]), "euid": getattr(os, "geteuid", lambda: None)(),
             "python_isolated": bool(sys.flags.isolated), "python_no_site": bool(sys.flags.no_site),
             "os_release": {}, "os_release_sha256": None, "machine_id_sha256": None, "systemd_version": None,
             "pid1_systemd": False, "cgroup_controllers": [], "virtualization": "unverified",
             "namespace_entries": [], "boundary_tests": "not_run", "errors": []}
    if sys.platform != "linux":
        return facts
    try:
        data = _read("/etc/os-release")
        facts["os_release"] = parse_os_release(data)
        facts["os_release_sha256"] = hashlib.sha256(data).hexdigest()
    except (OSError, ValueError, UnicodeError):
        facts["errors"].append("os_release_unavailable")
    probes = {
        "machine_id_sha256": lambda: hashlib.sha256(_read("/etc/machine-id", 256)).hexdigest(),
        "pid1_systemd": lambda: _read("/proc/1/comm", 256).strip() == b"systemd",
        "cgroup_controllers": lambda: sorted(_read("/sys/fs/cgroup/cgroup.controllers", 1024).decode().split()),
        "namespace_entries": lambda: [name for name in ("mnt", "net", "pid", "user") if Path("/proc/self/ns", name).exists()],
    }
    for key, probe in probes.items():
        try:
            facts[key] = probe()
        except (OSError, ValueError, UnicodeError):
            facts["errors"].append(key + "_unavailable")
    try:
        code, output = _command(["/usr/bin/systemd-analyze", "--version"])
        match = re.match(r"systemd ([0-9]+)\b", output)
        if code or not match:
            raise ValueError("systemd_version_unavailable")
        facts["systemd_version"] = int(match.group(1))
    except (OSError, ValueError, subprocess.SubprocessError):
        facts["errors"].append("systemd_version_unavailable")
    try:
        code, output = _command(["/usr/bin/systemd-detect-virt"])
        facts["virtualization"] = output if code in (0, 1) and output else "unverified"
    except (OSError, ValueError, subprocess.SubprocessError):
        facts["errors"].append("virtualization_unavailable")
    # Do not infer root/session isolation from these available interfaces.
    return facts


def check_target(facts, expected_os, expected_version, expected_machine, *, require_root=False,
                 expected_architecture=None, expected_os_release_sha256=None, expected_kernel_release=None):
    reasons = []
    if facts.get("platform") != "linux": reasons.append("linux_required")
    if facts.get("virtualization") not in {"microsoft", "kvm", "qemu", "vmware", "oracle", "xen", "parallels", "bhyve"}:
        reasons.append("dedicated_verified_vm_required")
    if require_root and facts.get("euid") != 0: reasons.append("operator_root_required")
    if facts.get("os_release", {}).get("ID") != expected_os: reasons.append("os_mismatch")
    if facts.get("os_release", {}).get("VERSION_ID") != expected_version: reasons.append("os_version_mismatch")
    if not expected_architecture or facts.get("architecture") != expected_architecture:
        reasons.append("architecture_mismatch")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_os_release_sha256 or "") or facts.get("os_release_sha256") != expected_os_release_sha256:
        reasons.append("exact_os_release_mismatch")
    if expected_kernel_release is not None and facts.get("kernel_release") != expected_kernel_release:
        reasons.append("kernel_release_mismatch")
    version = facts.get("python_version")
    if type(version) is not list or len(version) < 2 or any(type(value) is not int for value in version) or tuple(version[:2]) < (3, 11):
        reasons.append("python_3_11_required")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_machine or "") or facts.get("machine_id_sha256") != expected_machine:
        reasons.append("machine_identity_mismatch")
    if not facts.get("pid1_systemd"): reasons.append("systemd_manager_required")
    if type(facts.get("systemd_version")) is not int or facts["systemd_version"] < MIN_SYSTEMD:
        reasons.append("systemd_capability_baseline_missing")
    if not REQUIRED_CONTROLLERS <= set(facts.get("cgroup_controllers", [])):
        reasons.append("cgroup_v2_controllers_required")
    if not {"mnt", "net", "pid", "user"} <= set(facts.get("namespace_entries", [])):
        reasons.append("namespace_interfaces_missing")
    if facts.get("errors"): reasons.append("preflight_observation_incomplete")
    return {"matches_requested_host": not reasons, "reason_codes": reasons,
            "boundary_tests": "not_run", "execution_authorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(collect(), sort_keys=True))


if __name__ == "__main__":
    main()
