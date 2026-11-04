"""Plan by default; install inactive P2 foundation only on an explicitly verified Linux VM.

This installer does not fetch packages, start services, build a worker rootfs,
move credentials, enroll an actor, or authorize verification/publication.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys

USERS = ("multi-p2-control", "multi-p2-worker", "multi-p2-verify", "multi-p2-publish")
WORKER_GROUP = "multi-p2-workers"
ROOTS = ("/opt/multi-p2", "/etc/multi-p2", "/var/lib/multi-p2")
PYTHON = "/opt/multi-p2-python/bin/python3"
UNITS = ("multi-p2-control.service", "multi-p2-worker.service", "multi-p2-executor.service", "multi-p2-publisher.service")
SOCKET_UNITS = ("multi-p2-executor.socket", "multi-p2-publisher.socket")
ALLOWLIST = {
    "runtime/p2_contracts.py": "runtime/p2_contracts.py",
    "runtime/p2_store.py": "runtime/p2_store.py",
    "runtime/p2_broker.py": "runtime/p2_broker.py",
    "runtime/p2_executor.py": "runtime/p2_executor.py",
    "runtime/p2_sandbox_gate.py": "runtime/p2_sandbox_gate.py",
    "runtime/p2_verifier.py": "runtime/p2_verifier.py",
    "runtime/p2_publisher.py": "runtime/p2_publisher.py",
    "runtime/p2_rpc.py": "runtime/p2_rpc.py",
    "runtime/control_contracts.py": "runtime/control_contracts.py",
    "runtime/control-requirements.txt": "runtime/control-requirements.txt",
    "modules/infrastructure/p2/linux/preflight.py": "preflight.py",
    "modules/infrastructure/p2/linux/install.py": "install.py",
    "modules/infrastructure/p2/linux/worker_entry.py": "worker_entry.py",
    "modules/infrastructure/p2/linux/publisher_entry.py": "publisher_entry.py",
    "modules/infrastructure/p2/linux/rootfs_builder.py": "rootfs_builder.py",
    "modules/infrastructure/p2/linux/profiles/multi-p2-bwrap-rpc.apparmor": "multi-p2-bwrap-rpc.apparmor",
    "modules/infrastructure/p2/linux/systemd/multi-p2-control.service": "units/multi-p2-control.service",
    "modules/infrastructure/p2/linux/systemd/multi-p2-worker.service": "units/multi-p2-worker.service",
    "modules/infrastructure/p2/linux/systemd/multi-p2-executor.service": "units/multi-p2-executor.service",
    "modules/infrastructure/p2/linux/systemd/multi-p2-publisher.service": "units/multi-p2-publisher.service",
    "modules/infrastructure/p2/linux/systemd/multi-p2-executor.socket": "units/multi-p2-executor.socket",
    "modules/infrastructure/p2/linux/systemd/multi-p2-publisher.socket": "units/multi-p2-publisher.socket",
}
MAX_SOURCE = 2 * 1024 * 1024


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_release(source):
    """Capture exact allowlisted bytes once, rejecting links and large files."""
    source = Path(source).absolute()
    for ancestor in (source, *source.parents):
        if ancestor.is_symlink() or (hasattr(ancestor, "is_junction") and ancestor.is_junction()):
            raise ValueError("release_root_alias_rejected")
    if not source.is_dir():
        raise ValueError("release_root_missing")
    captured = {}
    for name in ALLOWLIST:
        cursor = source
        for part in PurePosixPath(name).parts:
            cursor = cursor / part
            if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()):
                raise ValueError("release_symlink_rejected")
        prior = cursor.lstat()
        if not stat.S_ISREG(prior.st_mode) or prior.st_nlink != 1:
            raise ValueError("release_regular_single_link_required")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
        directories = []
        if os.name == "posix":
            directories.append(os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
            try:
                for part in PurePosixPath(name).parts[:-1]:
                    directories.append(os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directories[-1]))
                fd = os.open(PurePosixPath(name).name, flags, dir_fd=directories[-1])
            except Exception:
                for directory in reversed(directories): os.close(directory)
                raise
        else:
            fd = os.open(cursor, flags)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= MAX_SOURCE:
                raise ValueError("release_file_invalid")
            if (info.st_dev, info.st_ino) != (prior.st_dev, prior.st_ino):
                raise ValueError("release_identity_changed_during_capture")
            with os.fdopen(os.dup(fd), "rb") as stream:
                data = stream.read(MAX_SOURCE + 1)
            if len(data) != info.st_size:
                raise ValueError("release_changed_during_capture")
            captured[name] = data
        finally:
            os.close(fd)
            for directory in reversed(directories): os.close(directory)
    manifest = {name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                for name, data in sorted(captured.items())}
    return captured, manifest, digest(manifest)


def secure_root_path(path, *, allow_file=False):
    """No untrusted write or link anywhere on an installed authority path."""
    target = Path(path)
    if not target.is_absolute() or ".." in target.parts:
        raise ValueError("trusted_path_not_absolute")
    for item in reversed((target, *target.parents)):
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("trusted_path_not_root_protected")
        if item != target and not stat.S_ISDIR(info.st_mode):
            raise ValueError("trusted_ancestor_not_directory")
    if not allow_file and not target.is_dir():
        raise ValueError("trusted_directory_required")
    if allow_file and not target.is_file():
        raise ValueError("trusted_regular_file_required")


def check_python_tree():
    base = Path("/opt/multi-p2-python")
    secure_root_path(base)
    count = 0
    for path in base.rglob("*"):
        count += 1
        if count > 50000:
            raise ValueError("python_environment_inventory_limit")
        info = path.lstat()
        if path.suffix == ".pth" or path.name in {"sitecustomize.py", "usercustomize.py"}:
            raise ValueError("python_startup_hook_rejected")
        if info.st_uid != 0 or (not stat.S_ISLNK(info.st_mode) and info.st_mode & 0o022):
            raise ValueError("python_environment_not_root_protected")
        if stat.S_ISLNK(info.st_mode):
            if "site-packages" in path.parts:
                raise ValueError("python_private_package_alias_rejected")
            # Do not resolve through a worker-controlled intermediate alias.
            target = internal_environment_alias(base, path, os.readlink(path))
            # Internal aliases are allowed only when their target/ancestors are
            # real protected paths; its contents are also visited under base.
            secure_root_path(target, allow_file=target.is_file())
        elif not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise ValueError("python_environment_special_file_rejected")
    config_path = base / "pyvenv.cfg"
    secure_root_path(config_path, allow_file=True)
    with config_path.open("rb") as stream:
        config_data = stream.read(16385)
    if len(config_data) > 16384:
        raise ValueError("python_venv_config_limit")
    config = {}
    for line in config_data.decode("utf-8", "strict").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            key = key.strip()
            if key in config: raise ValueError("python_venv_config_duplicate")
            config[key] = value.strip()
    if config.get("include-system-site-packages", "").lower() != "false" or not config.get("home") or not config.get("executable"):
        raise ValueError("approved_private_venv_required")
    secure_root_path(config["home"])
    secure_root_path(config["executable"], allow_file=True)


def internal_environment_alias(base, path, raw):
    raw_target = Path(raw)
    target = Path(os.path.abspath(raw_target if raw_target.is_absolute() else path.parent / raw_target))
    if not target.is_relative_to(base):
        raise ValueError("python_environment_external_alias_rejected")
    return target


def ensure_bootstrap():
    if sys.platform == "linux" and os.geteuid() == 0:
        if not sys.flags.isolated or not sys.flags.no_site:
            raise ValueError("root_bootstrap_requires_isolated_trusted_python_no_site")
        # The operator must independently approve and install these two files
        # outside any candidate-writable directory before invoking with root.
        secure_root_path(Path(__file__).absolute(), allow_file=True)
        secure_root_path(Path(__file__).absolute().with_name("preflight.py"), allow_file=True)
        secure_root_path(Path(sys.executable).absolute(), allow_file=True)


def _preflight():
    ensure_bootstrap()
    location = Path(__file__).absolute().with_name("preflight.py")
    spec = importlib.util.spec_from_file_location("multi_p2_installer_preflight", location)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_apply_context():
    if sys.platform != "linux" or not hasattr(os, "geteuid") or os.geteuid() != 0:
        raise ValueError("linux_operator_root_apply_required")
    ensure_bootstrap()


def installation_plan(facts, manifest, release_sha, expected):
    target = _preflight().check_target(facts, expected.get("os"), expected.get("version"),
                                   expected.get("machine"), require_root=True,
                                   expected_architecture=expected.get("architecture"),
                                   expected_os_release_sha256=expected.get("os_release_sha256"),
                                   expected_kernel_release=expected.get("kernel_release"))
    return {"schema_version": "0.1.0", "mode": "plan", "effects_performed": False,
            "release_sha256": release_sha, "files": manifest, "target_check": target, "observed_host": facts,
            "create_users": list(USERS), "create_group": WORKER_GROUP,
            "create_roots": list(ROOTS), "install_units_inactive": list(UNITS + SOCKET_UNITS),
            "required_python": PYTHON, "default_enrollments": [],
            "worker_execution": "implemented_prerequisites_unverified", "verify_adapter": "implemented_not_activated", "publish_adapter": "implemented_not_activated",
            "credentials_provisioned": False, "boundary_tests": "not_run"}


def check_resources():
    import pwd
    import grp
    for parent in ("/opt", "/etc", "/var/lib", "/etc/systemd/system", "/run"):
        secure_root_path(parent)
    for path in (*ROOTS, *("/etc/systemd/system/" + name for name in UNITS + SOCKET_UNITS), "/run/multi-p2-control"):
        if os.path.lexists(path):
            raise ValueError("existing_installation_resource_requires_operator_review")
    for name in USERS:
        try: pwd.getpwnam(name)
        except KeyError: pass
        else: raise ValueError("existing_service_account_rejected")
    for name in (*USERS, WORKER_GROUP):
        try: grp.getgrnam(name)
        except KeyError: pass
        else: raise ValueError("existing_service_group_rejected")
    # The operator supplies an approved root-owned environment; no pip/network fallback.
    python = Path(PYTHON)
    check_python_tree()
    secure_root_path(python.parent)
    secure_root_path(python, allow_file=True)
    for command in ("/usr/sbin/groupadd", "/usr/sbin/useradd", "/usr/bin/systemctl", "/usr/sbin/nologin"):
        secure_root_path(command, allow_file=True)


def check_dependencies(requirements):
    expected = {}
    for line in requirements.decode("utf-8").splitlines():
        if not line or line.startswith("#"): continue
        name, separator, version = line.partition("==")
        if not separator or not name or not version:
            raise ValueError("dependency_lock_invalid")
        expected[name] = version
    code = "import sys; assert sys.version_info >= (3,11) and sys.flags.isolated and sys.flags.no_site; import importlib.metadata,json,pathlib,re; site=pathlib.Path(sys.executable).parent.parent/'lib'/('python%d.%d'%sys.version_info[:2])/'site-packages'; assert site.is_dir(); norm=lambda x:re.sub(r'[-_.]+','-',x.lower()); rows=[(norm(d.metadata['Name']),d.version) for d in importlib.metadata.distributions(path=[str(site)])]; assert len(dict(rows))==len(rows); p=json.loads(sys.argv[1]); assert all(dict(rows).get(norm(k))==v for k,v in p.items())"
    result = subprocess.run([PYTHON, "-I", "-S", "-B", "-c", code, json.dumps(expected)],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            cwd="/", env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, timeout=30)
    if result.returncode:
        raise ValueError("approved_python_dependencies_unavailable")


def _mkdir(path, mode=0o700):
    os.mkdir(path, mode)
    os.chown(path, 0, 0)


def _write_new(path, data, mode=0o644):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), mode)
    try:
        os.fchown(fd, 0, 0)
        os.fchmod(fd, mode)
        if stat.S_IMODE(os.fstat(fd).st_mode) != mode:
            raise ValueError("installed_file_mode_mismatch")
        with os.fdopen(os.dup(fd), "wb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
    finally:
        os.close(fd)


def apply_install(captured, manifest, release_sha, expected, approved_sha):
    require_apply_context()
    if approved_sha != release_sha:
        raise ValueError("operator_approved_release_digest_mismatch")
    for name in ("install.py", "preflight.py"):
        source = "modules/infrastructure/p2/linux/" + name
        with Path(__file__).absolute().with_name(name).open("rb") as stream:
            bootstrap_bytes = stream.read(MAX_SOURCE + 1)
        if captured.get(source) != bootstrap_bytes:
            raise ValueError("reviewed_bootstrap_pair_differs_from_release")
    probe = _preflight()
    facts = probe.collect()
    target = probe.check_target(facts, expected.get("os"), expected.get("version"), expected.get("machine"), require_root=True,
                                expected_architecture=expected.get("architecture"),
                                expected_os_release_sha256=expected.get("os_release_sha256"),
                                expected_kernel_release=expected.get("kernel_release"))
    if not target["matches_requested_host"]:
        raise ValueError("operator_verified_linux_vm_required:" + ",".join(target["reason_codes"]))
    check_resources()
    check_dependencies(captured["runtime/control-requirements.txt"])
    import pwd
    import grp
    progress = []
    journal = "/var/lib/multi-p2/install-journal.json"
    try:
        # No existing resource is removed, chmodded or taken over after a failure.
        for path in ROOTS:
            _mkdir(path); progress.append("created:" + path)
        _write_new(journal, json.dumps({"status": "incomplete", "release_sha256": release_sha}).encode(), 0o600)
        env = {"PATH": "/usr/sbin:/usr/bin:/bin", "LANG": "C.UTF-8"}
        subprocess.run(["/usr/sbin/groupadd", "--system", WORKER_GROUP], check=True, env=env, cwd="/", timeout=30)
        progress.append("group:" + WORKER_GROUP)
        for name in USERS:
            arguments = ["/usr/sbin/useradd", "--system", "--no-create-home", "--password", "!", "--shell", "/usr/sbin/nologin", "--home-dir", "/nonexistent"]
            arguments += ["--gid", WORKER_GROUP] if name == "multi-p2-worker" else ["--user-group"]
            subprocess.run(arguments + [name], check=True, env=env, cwd="/", timeout=30)
            progress.append("user:" + name)
        identities = {name: pwd.getpwnam(name) for name in USERS}
        if any(item.pw_uid <= 0 for item in identities.values()) or len({item.pw_uid for item in identities.values()}) != len(USERS):
            raise ValueError("service_principals_not_distinct")
        controller = identities["multi-p2-control"]
        publisher = identities["multi-p2-publish"]
        worker_group = grp.getgrnam(WORKER_GROUP)
        for directory in ("/opt/multi-p2/runtime", "/opt/multi-p2/units"):
            _mkdir(directory)
        for source, relative in ALLOWLIST.items():
            destination = Path("/opt/multi-p2") / relative
            data = captured[source]
            if hashlib.sha256(data).hexdigest() != manifest[source]["sha256"]:
                raise ValueError("captured_release_changed")
            _write_new(destination, data)
        config = {"schema_version": "0.1.0", "state_root": "/var/lib/multi-p2/broker",
                  "socket_path": "/run/multi-p2-control/worker.sock", "controller_uid": controller.pw_uid,
                  "worker_gid": worker_group.gr_gid, "enrollments": []}
        _write_new("/etc/multi-p2/broker.json", (json.dumps(config, indent=2) + "\n").encode(), 0o640)
        os.chown("/etc/multi-p2/broker.json", 0, controller.pw_gid)
        _mkdir("/var/lib/multi-p2/broker")
        os.chown("/var/lib/multi-p2/broker", controller.pw_uid, controller.pw_gid)
        # Distinct new authority areas. No policy/job, rootfs, Git repo or
        # credential is invented here, and no existing directory is adopted.
        layout = {
            "/var/lib/multi-p2/executor": (0, 0, 0o711),
            "/var/lib/multi-p2/executor/jobs": (0, 0, 0o711),
            "/var/lib/multi-p2/rootfs": (0, 0, 0o755),
            "/var/lib/multi-p2/verification": (0, publisher.pw_gid, 0o750),
            "/var/lib/multi-p2/verification/state": (0, 0, 0o700),
            "/var/lib/multi-p2/verification/receipts": (0, publisher.pw_gid, 0o750),
            "/var/lib/multi-p2/verification/export": (0, publisher.pw_gid, 0o750),
            "/var/lib/multi-p2/publisher": (publisher.pw_uid, publisher.pw_gid, 0o700),
            "/var/lib/multi-p2/publication-target.git": (publisher.pw_uid, publisher.pw_gid, 0o700),
        }
        for path, (uid, gid, mode) in layout.items():
            _mkdir(path); os.chown(path, uid, gid); os.chmod(path, mode)
        for name in UNITS + SOCKET_UNITS:
            source = "modules/infrastructure/p2/linux/systemd/" + name
            _write_new("/etc/systemd/system/" + name, captured[source])
        for path in ("/opt/multi-p2", "/opt/multi-p2/runtime", "/opt/multi-p2/units", "/etc/multi-p2", "/var/lib/multi-p2"):
            os.chmod(path, 0o755)
        subprocess.run(["/usr/bin/systemctl", "daemon-reload"], check=True, env=env, cwd="/", timeout=30)
        result = {"status": "installed_inactive", "release_sha256": release_sha, "effects_performed": True,
                  "users": list(USERS), "units": list(UNITS + SOCKET_UNITS), "services_started": False,
                  "enrollments": [], "credentials_provisioned": False,
                  "worker_execution": "implemented_prerequisites_unverified", "verify_adapter": "implemented_not_activated", "publish_adapter": "implemented_not_activated",
                  "production_verifier_uid": 0, "publisher_uid": publisher.pw_uid,
                  "boundary_tests": "not_run"}
        _write_new("/var/lib/multi-p2/install-result.json", (json.dumps(result, indent=2) + "\n").encode(), 0o600)
        return result
    except Exception as error:
        # Do not convert partial creation into a rollback claim or delete resources.
        raise RuntimeError("partial_installation_preserved_for_operator:" + type(error).__name__ + ":" + ",".join(progress)) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-release-sha256")
    parser.add_argument("--expected-os-id")
    parser.add_argument("--expected-version-id")
    parser.add_argument("--expected-machine-id-sha256")
    parser.add_argument("--expected-architecture")
    parser.add_argument("--expected-os-release-sha256")
    parser.add_argument("--expected-kernel-release")
    args = parser.parse_args(argv)
    try:
        if args.apply:
            require_apply_context()
        else:
            ensure_bootstrap()
        captured, manifest, release_sha = read_release(args.source)
        expected = {"os": args.expected_os_id, "version": args.expected_version_id, "machine": args.expected_machine_id_sha256,
                    "architecture": args.expected_architecture, "os_release_sha256": args.expected_os_release_sha256,
                    "kernel_release": args.expected_kernel_release}
        if args.apply:
            value = apply_install(captured, manifest, release_sha, expected, args.expected_release_sha256)
        else:
            value = installation_plan(_preflight().collect(), manifest, release_sha, expected)
        print(json.dumps(value, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "failed", "error": str(error), "applied_successfully": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
