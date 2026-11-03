"""Ordinary configuration/fixture tests, never live P2 enforcement evidence."""
from __future__ import annotations

import configparser
from contextlib import contextmanager
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import types
import unittest
from unittest import mock

BASE = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location("p2_linux_test_" + name, BASE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


preflight = load("preflight")
installer = load("install")
worker = load("worker_entry")


def facts():
    return {"platform": "linux", "architecture": "x86_64", "euid": 0,
            "python_version": [3, 12, 3], "kernel_release": "fixture-kernel", "os_release_sha256": "b" * 64,
            "os_release": {"ID": "fixture-os", "VERSION_ID": "3.2"},
            "machine_id_sha256": "a" * 64, "systemd_version": 255, "pid1_systemd": True,
            "virtualization": "microsoft", "cgroup_controllers": ["cpu", "memory", "pids"],
            "namespace_entries": ["mnt", "net", "pid", "user"], "errors": []}


EXPECTED = {"os": "fixture-os", "version": "3.2", "machine": "a" * 64,
            "architecture": "x86_64", "os_release_sha256": "b" * 64, "kernel_release": "fixture-kernel"}


def job():
    return {"schema_version": "0.1.0", "job_id": "job-" + "1" * 32,
            "enrollment_id": "11111111-1111-4111-8111-111111111111", "worker_uid": 1001,
            "worker_gid": 1002, "input_tree_digest": "sha256:" + "2" * 64,
            "entry_sha256": "sha256:" + "3" * 64,
            "limits": {"cpu_seconds": 10, "memory_bytes": 128 * 1024 * 1024, "tasks": 8}}


class PreflightTests(unittest.TestCase):
    def check(self, value):
        return preflight.check_target(value, EXPECTED["os"], EXPECTED["version"], EXPECTED["machine"], require_root=True,
                                      expected_architecture=EXPECTED["architecture"], expected_os_release_sha256=EXPECTED["os_release_sha256"],
                                      expected_kernel_release=EXPECTED["kernel_release"])

    def test_capable_host_is_observation_not_attestation(self):
        result = self.check(facts())
        self.assertTrue(result["matches_requested_host"])
        self.assertFalse(result["execution_authorized"])
        self.assertEqual(result["boundary_tests"], "not_run")

    def test_wsl_and_containers_are_not_deployment_targets(self):
        for kind in ("wsl", "docker", "lxc", "none", "unverified"):
            value = facts(); value["virtualization"] = kind
            self.assertIn("dedicated_verified_vm_required", self.check(value)["reason_codes"])

    def test_wrong_os_version_identity_and_nonroot_fail(self):
        for key, value, expected in (("euid", 1000, "operator_root_required"),
                                     ("machine_id_sha256", "b" * 64, "machine_identity_mismatch")):
            current = facts(); current[key] = value
            self.assertIn(expected, self.check(current)["reason_codes"])
        current = facts(); current["os_release"]["VERSION_ID"] = "other"
        self.assertIn("os_version_mismatch", self.check(current)["reason_codes"])

    def test_missing_kernel_service_features_fail(self):
        for key, value in (("systemd_version", 246), ("pid1_systemd", False),
                           ("cgroup_controllers", ["cpu"]), ("namespace_entries", [])):
            current = facts(); current[key] = value
            self.assertFalse(self.check(current)["matches_requested_host"])

    def test_os_release_parser_never_executes_values(self):
        value = preflight.parse_os_release(b'ID=fixture\nVERSION_ID="3.2"\nPRETTY_NAME="$(touch marker)"\n')
        self.assertEqual(value["PRETTY_NAME"], "$(touch marker)")
        with self.assertRaises(ValueError):
            preflight.parse_os_release(b"ID=fixture\nID=other\nVERSION_ID=3\n")

    def test_selected_architecture_exact_release_and_python_are_checked(self):
        for key, value, reason in (("architecture", "aarch64", "architecture_mismatch"),
                                   ("os_release_sha256", "c" * 64, "exact_os_release_mismatch"),
                                   ("kernel_release", "another-build", "kernel_release_mismatch"),
                                   ("python_version", [3, 10, 12], "python_3_11_required")):
            current = facts(); current[key] = value
            self.assertIn(reason, self.check(current)["reason_codes"])


class WorkerTests(unittest.TestCase):
    def test_valid_contract_still_cannot_execute(self):
        result = worker.validate_job(job())
        self.assertTrue(result["contract_valid"])
        self.assertFalse(result["execution_permitted"])

    def test_no_caller_command_or_host_path(self):
        for key in ("command", "path", "root", "credentials", "remote"):
            value = job(); value[key] = "caller value"
            with self.assertRaises(ValueError): worker.validate_job(value)

    def test_root_identity_bad_digest_and_limits_rejected(self):
        for key, value in (("worker_uid", 0), ("worker_gid", True), ("entry_sha256", "bad")):
            current = job(); current[key] = value
            with self.assertRaises(ValueError): worker.validate_job(current)
        current = job(); current["limits"]["tasks"] = 65
        with self.assertRaises(ValueError): worker.validate_job(current)

    def test_run_has_no_host_fallback(self):
        with mock.patch("subprocess.run") as process, mock.patch("os.execve") as execute, mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(worker.main(["--run"]), 78)
            self.assertFalse(json.loads(output.getvalue())["candidate_executed"])
            process.assert_not_called(); execute.assert_not_called()


class InstallerTests(unittest.TestCase):
    def setUp(self):
        temporary_parent = None
        if os.name == "nt":
            temporary_parent = BASE.parents[3] / "work/p2-host-isolation/linux-fixtures"
            temporary_parent.mkdir(parents=True, exist_ok=True)
            self.assertTrue(temporary_parent.resolve().is_relative_to((BASE.parents[3] / "work").resolve()))
        self.temp = tempfile.TemporaryDirectory(dir=temporary_parent)
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name)
        for name in installer.ALLOWLIST:
            path = self.source / name; path.parent.mkdir(parents=True, exist_ok=True)
            data = ((BASE / Path(name).name).read_bytes() if name in (
                "modules/infrastructure/p2/linux/install.py", "modules/infrastructure/p2/linux/preflight.py")
                else ("fixture " + name).encode())
            path.write_bytes(data)

    @contextmanager
    def root_apply_fixture(self):
        # Simulate context only; mutations and protected-bootstrap approval are
        # mocked in fixture tests. This never changes the actual OS identity.
        with mock.patch.object(installer.sys, "platform", "linux"), mock.patch.object(installer.os, "geteuid", return_value=0, create=True), mock.patch.object(installer, "ensure_bootstrap"):
            yield

    def test_manifest_exact_allowlist_no_secret_copy(self):
        (self.source / "private-token.txt").write_text("synthetic-never-captured")
        captured, manifest, sha = installer.read_release(self.source)
        self.assertEqual(set(captured), set(installer.ALLOWLIST))
        self.assertNotIn("private-token.txt", manifest)
        self.assertEqual(sha, installer.digest(manifest))

    def test_changed_bytes_change_release_digest(self):
        before = installer.read_release(self.source)[2]
        (self.source / "runtime/p2_store.py").write_bytes(b"changed")
        self.assertNotEqual(before, installer.read_release(self.source)[2])

    def test_source_symlink_rejected(self):
        file = self.source / "runtime/p2_store.py"; file.unlink()
        target = self.source / "other"; target.write_text("fixture")
        try: file.symlink_to(target)
        except OSError: self.skipTest("Host does not allow fixture symlinks")
        with self.assertRaises(ValueError): installer.read_release(self.source)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO fixture requires Linux")
    def test_fifo_source_rejected_without_open(self):
        file = self.source / "runtime/p2_store.py"; file.unlink(); os.mkfifo(file)
        with self.assertRaisesRegex(ValueError, "regular_single_link"):
            installer.read_release(self.source)

    def test_hardlinked_source_rejected(self):
        file = self.source / "runtime/p2_store.py"
        os.link(file, self.source / "alias")
        with self.assertRaisesRegex(ValueError, "regular_single_link"):
            installer.read_release(self.source)

    def test_changed_bootstrap_pair_rejected(self):
        captured, manifest, sha = installer.read_release(self.source)
        captured["modules/infrastructure/p2/linux/preflight.py"] = b"other helper"
        with self.root_apply_fixture(), mock.patch.object(installer, "_preflight") as helper:
            with self.assertRaisesRegex(ValueError, "bootstrap_pair"):
                installer.apply_install(captured, manifest, sha, EXPECTED, sha)
            helper.assert_not_called()

    def test_plan_has_no_effects_or_activation(self):
        captured, manifest, sha = installer.read_release(self.source)
        with mock.patch.object(installer, "_mkdir") as mkdir, mock.patch("subprocess.run") as process:
            value = installer.installation_plan(facts(), manifest, sha, EXPECTED)
        mkdir.assert_not_called(); process.assert_not_called()
        self.assertFalse(value["effects_performed"])
        self.assertEqual(value["default_enrollments"], [])
        self.assertEqual(value["worker_execution"], "implemented_prerequisites_unverified")

    def test_wrong_release_rejected_before_host_mutation(self):
        captured, manifest, sha = installer.read_release(self.source)
        with self.root_apply_fixture(), mock.patch.object(installer, "check_resources") as resources:
            with self.assertRaises(ValueError): installer.apply_install(captured, manifest, sha, EXPECTED, "wrong")
            resources.assert_not_called()

    def test_wsl_apply_rejected_before_host_mutation(self):
        captured, manifest, sha = installer.read_release(self.source)
        value = facts(); value["virtualization"] = "wsl"
        probe = types.SimpleNamespace(collect=lambda: value, check_target=preflight.check_target)
        with self.root_apply_fixture(), mock.patch.object(installer, "_preflight", return_value=probe), mock.patch.object(installer, "check_resources") as resources:
            with self.assertRaisesRegex(ValueError, "verified_linux_vm"):
                installer.apply_install(captured, manifest, sha, EXPECTED, sha)
            resources.assert_not_called()

    def test_nonroot_apply_does_not_import_helper_or_capture(self):
        with mock.patch.object(installer.sys, "platform", "linux"), mock.patch.object(installer.os, "geteuid", return_value=1000, create=True), mock.patch.object(installer, "_preflight") as helper, mock.patch.object(installer, "read_release") as capture, mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(installer.main(["--apply"]), 2)
            helper.assert_not_called(); capture.assert_not_called()

    def test_root_bootstrap_checks_before_helper_import(self):
        with mock.patch.object(installer.sys, "platform", "linux"), mock.patch.object(installer.os, "geteuid", return_value=0, create=True), mock.patch.object(installer.sys, "flags", types.SimpleNamespace(isolated=0)), mock.patch.object(installer.importlib.util, "spec_from_file_location") as load:
            with self.assertRaisesRegex(ValueError, "isolated_trusted"):
                installer._preflight()
            load.assert_not_called()

    def test_root_bootstrap_requires_no_site_before_import(self):
        with mock.patch.object(installer.sys, "platform", "linux"), mock.patch.object(installer.os, "geteuid", return_value=0, create=True), mock.patch.object(installer.sys, "flags", types.SimpleNamespace(isolated=1, no_site=0)), mock.patch.object(installer.importlib.util, "spec_from_file_location") as load:
            with self.assertRaisesRegex(ValueError, "no_site"):
                installer._preflight()
            load.assert_not_called()

    def test_dependency_check_does_not_process_site_hooks(self):
        with mock.patch.object(installer.subprocess, "run", return_value=types.SimpleNamespace(returncode=0)) as process:
            installer.check_dependencies(b"fixture-package==1.0\n")
        argv = process.call_args.args[0]
        self.assertEqual(argv[1:4], ["-I", "-S", "-B"])
        self.assertIn("distributions(path=[str(site)])", argv[5])
        self.assertNotIn("addsitedir", argv[5])

    def test_external_environment_alias_is_rejected_without_resolve(self):
        base = self.source / "env"; path = base / "lib64"
        with self.assertRaisesRegex(ValueError, "external_alias"):
            installer.internal_environment_alias(base, path, str(self.source / "worker" / "site"))
        self.assertEqual(installer.internal_environment_alias(base, path, "lib"), base / "lib")

    @unittest.skipUnless(os.name == "posix", "POSIX mode fixture requires Linux")
    def test_write_new_exact_mode_under_restrictive_umask(self):
        target = self.source / "controlled"
        previous = os.umask(0o077)
        try:
            with mock.patch.object(installer.os, "fchown"):
                installer._write_new(target, b"fixture", 0o640)
        finally: os.umask(previous)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o640)
        with mock.patch.object(installer.os, "fchown"):
            with self.assertRaises(FileExistsError): installer._write_new(target, b"changed", 0o640)
        self.assertEqual(target.read_bytes(), b"fixture")

    def test_mock_apply_installs_inactive_without_credentials_or_worker_rootfs(self):
        captured, manifest, sha = installer.read_release(self.source)
        identities = {name: types.SimpleNamespace(pw_uid=1001 + i, pw_gid=2001 + i) for i, name in enumerate(installer.USERS)}
        fake_pwd = types.SimpleNamespace(getpwnam=lambda name: identities[name])
        fake_grp = types.SimpleNamespace(getgrnam=lambda name: types.SimpleNamespace(gr_gid=3001))
        probe = types.SimpleNamespace(collect=facts, check_target=preflight.check_target)
        with self.root_apply_fixture(), mock.patch.dict(sys.modules, {"pwd": fake_pwd, "grp": fake_grp}), mock.patch.object(installer, "_preflight", return_value=probe), mock.patch.object(installer, "check_resources"), mock.patch.object(installer, "check_dependencies"), mock.patch.object(installer, "_mkdir") as mkdir, mock.patch.object(installer, "_write_new") as write, mock.patch.object(installer.os, "chown", create=True), mock.patch.object(installer.os, "chmod"), mock.patch.object(installer.subprocess, "run") as process:
            value = installer.apply_install(captured, manifest, sha, EXPECTED, sha)
        self.assertEqual(value["status"], "installed_inactive")
        self.assertFalse(value["services_started"])
        self.assertFalse(value["credentials_provisioned"])
        self.assertEqual(value["enrollments"], [])
        self.assertFalse(any("worker-rootfs" in str(call) for call in mkdir.call_args_list))
        commands = [call.args[0] for call in process.call_args_list]
        self.assertEqual(commands[-1], ["/usr/bin/systemctl", "daemon-reload"])
        self.assertFalse(any("start" in command or "enable" in command for command in commands))
        config_call = next(call for call in write.call_args_list if str(call.args[0]) == "/etc/multi-p2/broker.json")
        config = json.loads(config_call.args[1])
        self.assertEqual(config["controller_uid"], 1001)
        self.assertEqual(config["worker_gid"], 3001)
        self.assertEqual(config["enrollments"], [])

    def test_partial_creation_is_not_rolled_back_or_reused(self):
        captured, manifest, sha = installer.read_release(self.source)
        probe = types.SimpleNamespace(collect=facts, check_target=preflight.check_target)
        with self.root_apply_fixture(), mock.patch.dict(sys.modules, {"pwd": types.SimpleNamespace(), "grp": types.SimpleNamespace()}), mock.patch.object(installer, "_preflight", return_value=probe), mock.patch.object(installer, "check_resources"), mock.patch.object(installer, "check_dependencies"), mock.patch.object(installer, "_mkdir"), mock.patch.object(installer, "_write_new"), mock.patch.object(installer.subprocess, "run", side_effect=RuntimeError("fixture")), mock.patch.object(installer.os, "unlink") as unlink:
            with self.assertRaisesRegex(RuntimeError, "partial_installation_preserved"):
                installer.apply_install(captured, manifest, sha, EXPECTED, sha)
            unlink.assert_not_called()


class UnitTests(unittest.TestCase):
    def unit(self, name):
        # systemd permits repeated list directives such as AssertPathExists.
        # Scalar security options below still use their final effective value.
        value = configparser.ConfigParser(interpolation=None, strict=False)
        value.read(BASE / "systemd" / name, encoding="utf-8")
        return value

    def test_controller_socket_identity_and_private_state(self):
        service = self.unit("multi-p2-control.service")["Service"]
        self.assertEqual(service["User"], "multi-p2-control")
        self.assertEqual(service["Group"], "multi-p2-workers")
        self.assertEqual(service["SupplementaryGroups"], "multi-p2-control")
        self.assertEqual(service["RuntimeDirectoryMode"], "0750")
        self.assertEqual(service["StateDirectoryMode"], "0700")
        self.assertNotIn("PrivateUsers", service)
        self.assertIn(" -I -S -B ", service["ExecStart"])

    def test_worker_has_no_host_fallback_or_bind_mounts(self):
        unit = self.unit("multi-p2-worker.service"); service = unit["Service"]
        self.assertEqual(service["User"], "multi-p2-worker")
        self.assertEqual(service["RootDirectory"], "/var/lib/multi-p2/worker-rootfs")
        self.assertIn("AssertPathIsDirectory", unit["Unit"])
        self.assertNotIn("BindPaths", service); self.assertNotIn("BindReadOnlyPaths", service)
        self.assertNotIn("PrivatePIDs", service)
        self.assertIn(" -I -S -B ", service["ExecStart"])
        self.assertNotIn("Install", unit)

    def test_units_have_bounded_no_privilege_network_profiles(self):
        for name in installer.UNITS:
            service = self.unit(name)["Service"]
            self.assertEqual(service["NoNewPrivileges"], "yes")
            if name == "multi-p2-executor.service":
                self.assertNotIn("User", service)  # System-manager default root; explicit UID drops CAP_SETUID on v255.
                self.assertEqual(service["Group"], "root")
                self.assertNotIn("AmbientCapabilities", service)
                self.assertEqual(service["PrivateMounts"], "yes")
                self.assertEqual(service["PrivateNetwork"], "yes")
                self.assertEqual(service["DelegateSubgroup"], "supervisor")
                self.assertEqual(set(service["Delegate"].split()), {"cpu", "memory", "pids"})
                self.assertEqual(service["KillMode"], "control-group")
                self.assertEqual(service["ExitType"], "main")
                self.assertEqual(service["SendSIGKILL"], "yes")
                self.assertEqual(service["TimeoutStopSec"], "5s")
                self.assertEqual(service["RuntimeMaxSec"], "360s")
                self.assertEqual(service["KeyringMode"], "private")
                self.assertNotIn("Install", self.unit(name))
                continue
            self.assertEqual(service["CapabilityBoundingSet"], "")
            self.assertEqual(service["PrivateNetwork"], "yes")
            self.assertEqual(service["RestrictAddressFamilies"], "AF_UNIX")
            self.assertEqual(service["ProtectSystem"], "strict")
            self.assertEqual(service["ProtectHome"], "yes")
            self.assertEqual(service["KillMode"], "control-group")
            self.assertEqual(service["Restart"], "no")
            self.assertIn("MemoryMax", service); self.assertIn("TasksMax", service)


class PrivateMountPreparationTests(unittest.TestCase):
    def run_case(self, *, current="mnt:[123]", host="mnt:[1]", uid=0, result=0):
        libc = mock.Mock()
        libc.mount.return_value = result
        with mock.patch.object(worker.sys, "platform", "linux"), mock.patch.object(worker.os, "geteuid", return_value=uid, create=True), mock.patch.object(worker.os, "readlink", side_effect=[current, host]), mock.patch.object(worker.ctypes, "CDLL", return_value=libc) as load, mock.patch.object(worker.ctypes, "get_errno", return_value=1):
            try:
                worker.prepare_private_mounts()
            except (ValueError, OSError):
                if uid != 0 or current == host or not current.startswith("mnt:["):
                    load.assert_not_called()
                raise
        libc.mount.assert_called_once_with(None, b"/", None, (1 << 14) | (1 << 18), None)

    def test_private_namespace_recursively_privatized(self):
        self.run_case()

    def test_host_namespace_rejected_before_mount(self):
        with self.assertRaisesRegex(ValueError, "private_supervisor"):
            self.run_case(current="mnt:[1]")

    def test_invalid_namespace_rejected_before_mount(self):
        with self.assertRaisesRegex(ValueError, "private_supervisor"):
            self.run_case(current="unknown")

    def test_nonroot_rejected_before_mount(self):
        with self.assertRaisesRegex(ValueError, "trusted_root"):
            self.run_case(uid=1000)

    def test_mount_denied_fails_closed(self):
        with self.assertRaisesRegex(OSError, "private_mount_propagation_failed"):
            self.run_case(result=-1)


class DelegatedControllerTests(unittest.TestCase):
    def run_case(self, *, membership=None, processes="", available="cpu memory pids", enabled="", readback=True, write_error=False):
        values = {"cgroup": membership or "0::/system.slice/multi-p2-executor.service/supervisor",
                  "cgroup.procs": processes, "cgroup.controllers": available,
                  "cgroup.subtree_control": enabled}
        writes = []
        def read(path, *args, **kwargs):
            return values[path.name]
        def write(path, data, *args, **kwargs):
            self.assertEqual(path, Path("/sys/fs/cgroup/system.slice/multi-p2-executor.service/cgroup.subtree_control"))
            if write_error: raise PermissionError("readonly")
            writes.append(data)
            if readback: values[path.name] = "cpu memory pids"
            return len(data)
        with mock.patch.object(Path, "read_text", read), mock.patch.object(Path, "write_text", write):
            worker.prepare_delegated_controllers()
        return writes

    def test_enable_and_readback(self):
        self.assertEqual(self.run_case(), ["+cpu +memory +pids\n"])

    def test_already_enabled_no_write(self):
        self.assertEqual(self.run_case(enabled="cpu memory pids"), [])

    def test_wrong_membership_rejected(self):
        with self.assertRaisesRegex(ValueError, "delegated_supervisor"):
            self.run_case(membership="0::/system.slice/ssh.service")

    def test_nonempty_root_rejected(self):
        with self.assertRaisesRegex(ValueError, "delegated_root_not_empty"):
            self.run_case(processes="123")

    def test_missing_controller_rejected(self):
        with self.assertRaisesRegex(ValueError, "controllers_unavailable"):
            self.run_case(available="cpu memory")

    def test_failed_readback_rejected(self):
        with self.assertRaisesRegex(ValueError, "controllers_enable_failed"):
            self.run_case(readback=False)

    def test_denied_write_rejected(self):
        with self.assertRaises(PermissionError):
            self.run_case(write_error=True)


if __name__ == "__main__":
    unittest.main()
