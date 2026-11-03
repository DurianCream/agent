"""Real trusted-fixture execution and pure production guard tests; no deployment."""
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "runtime"))
import p2_executor as executor
from control_contracts import canonical_digest


def bundle(program=b"print('ok')\n"):
    content = "sha256:" + hashlib.sha256(program).hexdigest()
    return {"binding": {"repository_id": "fixture", "task_id": "executor-fixture", "scope": {"project": "fixture", "service": "runtime", "environment": "test", "issue": "executor"},
                         "enrollment_id": "11111111-1111-4111-8111-111111111111", "base_commit": "a" * 40, "policy_digest": "sha256:" + "b" * 64},
            "files": [{"path": "program.py", "kind": "blob", "mode": "100644", "size": len(program), "digest": content}], "blobs": {content: program}}


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / "work/p2-host-isolation/executor-fixtures" if os.name == "nt" else None
        if parent: parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runner = executor.FixtureExecutor(self.root, trusted_fixtures=True)

    def profile(self, *extra, **kwargs):
        return executor.ExecutionProfile("fixture", (sys.executable, "-I", "-S", "-B", "/input/program.py", *extra), **kwargs)

    def test_real_fixture_output_and_file_measurements(self):
        data = bundle(b"import sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_bytes(b'answer')\nsys.stdout.buffer.write(b'ok')\n")
        profile = self.profile("/output/result.txt")
        result = self.runner.run(data, profile)
        self.assertEqual(result.exit_code, 0); self.assertEqual(result.stdout, b"ok")
        self.assertEqual(result.outputs, {"result.txt": b"answer"})
        self.assertTrue(result.fixture_mode); self.assertFalse(result.isolation_verified)
        self.assertFalse(result.production_eligible)
        self.assertEqual(result.candidate_digest, canonical_digest({"binding": data["binding"], "files": data["files"]}))
        self.assertEqual(result.profile_digest, executor.execution_profile_digest(profile))

    def test_fixture_requires_explicit_trust_flag(self):
        with self.assertRaises(executor.ExecutorError): executor.FixtureExecutor(self.root)

    def test_real_fixture_timeout(self):
        result = self.runner.run(bundle(b"import time; time.sleep(20)\n"), self.profile(timeout_seconds=1))
        self.assertTrue(result.timed_out); self.assertFalse(result.production_eligible)

    def test_real_fixture_output_limit(self):
        result = self.runner.run(bundle(b"import sys;sys.stdout.buffer.write(b'x'*65536)\n"), self.profile(output_bytes=1024))
        self.assertTrue(result.output_limited); self.assertLessEqual(len(result.stdout) + len(result.stderr), 1024)

    def test_fixture_environment_does_not_inherit_secret(self):
        with mock.patch.dict(os.environ, {"P2_TEST_SECRET": "synthetic-canary"}):
            result = self.runner.run(bundle(b"import os;print(os.environ.get('P2_TEST_SECRET','absent'))\n"), self.profile())
        self.assertEqual(result.stdout.strip(), b"absent")

    def test_changed_blob_is_rejected_before_process(self):
        value = bundle(); value["blobs"][value["files"][0]["digest"]] = b"changed"
        with mock.patch.object(executor.subprocess, "Popen") as process:
            with self.assertRaises(executor.ExecutorError): self.runner.run(value, self.profile())
            process.assert_not_called()

    def test_manifest_path_and_unknown_fields_rejected(self):
        for edit in (lambda v: v["files"][0].update(path="../outside"), lambda v: v.update(command="bad")):
            value = bundle(); edit(value)
            with self.assertRaises(ValueError): executor.validate_bundle(value)

    def test_input_modification_detected_after_real_fixture(self):
        program = b"from pathlib import Path\nPath(__file__).write_text('changed')\n"
        with self.assertRaisesRegex(executor.ExecutorError, "input_changed"):
            self.runner.run(bundle(program), self.profile())

    def test_result_maps_are_readonly(self):
        result = self.runner.run(bundle(), self.profile())
        with self.assertRaises(TypeError): result.outputs["fake"] = b"passed"

    def test_profile_budgets_and_roundtrip(self):
        profile = self.profile(stdin=b"input")
        self.assertEqual(executor._profile(executor.profile_value(profile)), profile)
        for field, value in (("timeout_seconds", 0), ("tasks", 100), ("memory_bytes", True)):
            with self.assertRaises(executor.ExecutorError): executor.execution_profile_digest(self.profile(**{field: value}))

    def test_output_regular_size_and_alias_rules(self):
        output = self.root / "out"; output.mkdir(); (output / "a").write_bytes(b"123")
        with self.assertRaises(executor.ExecutorError): executor.read_outputs(output, 2)
        os.link(output / "a", output / "b")
        with self.assertRaisesRegex(executor.ExecutorError, "output_type"): executor.read_outputs(output, 100)

    @unittest.skipUnless(os.name == "posix", "POSIX fixture only")
    def test_output_symlink_and_fifo_never_read(self):
        output = self.root / "out"; output.mkdir(); (output / "link").symlink_to(self.root / "outside")
        with self.assertRaisesRegex(executor.ExecutorError, "output_alias"): executor.read_outputs(output, 100)
        (output / "link").unlink(); os.mkfifo(output / "fifo")
        with self.assertRaisesRegex(executor.ExecutorError, "output_type"): executor.read_outputs(output, 100)

    def test_bwrap_has_exact_namespaces_and_trusted_gate(self):
        config = {"bwrap_path": "/opt/multi-p2/bin/bwrap", "rootfs_path": "/var/lib/multi-p2/rootfs/image-" + "a" * 64}
        profile = executor.ExecutionProfile("prod", ("/usr/bin/python3", "-I", "/input/program.py"))
        argv = executor.build_bwrap_command(config, profile, "/owned/input", "/owned/output", grant_fd=3, info_fd=4, life_fd=5, ack_fd=6, token=b"x" * 32)
        for name in ("user", "pid", "net", "ipc", "uts", "cgroup"): self.assertIn("--unshare-" + name, argv)
        self.assertIn("--as-pid-1", argv); self.assertIn("--disable-userns", argv)
        self.assertNotIn("--block-fd", argv); self.assertNotIn("--unshare-all", argv)
        self.assertFalse(any(arg.endswith("-try") for arg in argv))
        self.assertIn("/p2/sandbox_gate.py", argv)
        self.assertNotIn("--dev-bind", argv)

    def test_root_backend_never_falls_back_on_current_host(self):
        with mock.patch.object(executor.sys, "platform", "win32"):
            with self.assertRaisesRegex(executor.ExecutorError, "root_linux"):
                executor.BwrapExecutor.from_config(self.root / "missing")

    def test_budget_exceeded_is_not_production_eligible(self):
        value = executor.ExecutionResult("a", "b", "bwrap", False, True, 0, False, False, b"", b"", {}, {}, True)
        self.assertFalse(value.production_eligible)

    def test_config_drift_rejected_before_launch(self):
        backend = object.__new__(executor.BwrapExecutor)
        backend.config_path = self.root / "config.json"
        backend.config = {"value": "old"}; backend.config_digest = executor.executor_configuration_digest(backend.config)
        backend.config_path.write_text('{"value":"new"}')
        with mock.patch.object(executor.sys, "platform", "linux"), mock.patch.object(executor.os, "geteuid", return_value=0, create=True), mock.patch.object(executor.sys, "flags", types.SimpleNamespace(isolated=1, no_site=1)), mock.patch.object(executor, "_trusted"), mock.patch.object(executor.subprocess, "Popen") as process:
            with self.assertRaisesRegex(executor.ExecutorError, "config_changed"): backend.preflight()
            process.assert_not_called()

    def test_unknown_filecap_error_fails_closed(self):
        with mock.patch.object(executor.os, "getxattr", side_effect=OSError(5, "fixture"), create=True):
            with self.assertRaisesRegex(executor.ExecutorError, "capability_metadata"):
                executor._file_capabilities("fixture")

    def test_input_depth_is_bounded(self):
        value = bundle(); value["files"][0]["path"] = "/".join(["part"] * 17) + "/program.py"
        with self.assertRaisesRegex(executor.ExecutorError, "depth_limit"): executor.validate_bundle(value)


@unittest.skipUnless(sys.platform == "linux", "Pipe/kill fixture requires Linux; not namespace assurance")
class GateProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name)
        self.gate = ROOT / "runtime/p2_sandbox_gate.py"
        self.processes = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for process in self.processes:
            if process.poll() is None: process.kill()
            process.wait(timeout=5)

    def spawn_gate(self, *, token=b"x" * 32):
        grant_r, grant_w = os.pipe(); life_r, life_w = os.pipe(); ack_r, ack_w = os.pipe()
        marker = self.root / "marker"
        source = "import importlib.util,sys; s=importlib.util.spec_from_file_location('g',sys.argv[1]);g=importlib.util.module_from_spec(s);s.loader.exec_module(g);sys.exit(g.supervise([sys.executable,'-I','-S','-c',sys.argv[6]],int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]),bytes.fromhex(sys.argv[5]),fixture=True))"
        command = "from pathlib import Path;Path(" + repr(str(marker)) + ").write_text('ran')"
        process = subprocess.Popen([sys.executable, "-I", "-S", "-c", source, str(self.gate), str(grant_r), str(life_r), str(ack_w), token.hex(), command], pass_fds=(grant_r, life_r, ack_w))
        self.processes.append(process)
        os.close(grant_r); os.close(life_r); os.close(ack_w)
        return process, grant_w, life_w, ack_r, marker

    def test_eof_never_releases_candidate(self):
        process, grant, life, ack, marker = self.spawn_gate()
        os.close(grant); self.assertEqual(process.wait(timeout=5), 125)
        self.assertFalse(marker.exists()); os.close(life); os.close(ack)

    def test_wrong_token_never_releases_candidate(self):
        process, grant, life, ack, marker = self.spawn_gate()
        os.write(grant, b"z" * 32); os.close(grant)
        self.assertEqual(process.wait(timeout=5), 125); self.assertFalse(marker.exists())
        os.close(life); os.close(ack)

    def test_dead_lifeline_beats_queued_token(self):
        process, grant, life, ack, marker = self.spawn_gate()
        os.close(life)
        try: os.write(grant, b"x" * 32)
        except BrokenPipeError: pass
        os.close(grant)
        self.assertEqual(process.wait(timeout=5), 125); self.assertFalse(marker.exists()); os.close(ack)

    def test_exact_token_executes_trusted_fixture(self):
        process, grant, life, ack, marker = self.spawn_gate()
        os.write(grant, b"x" * 32); os.close(grant)
        self.assertEqual(process.wait(timeout=5), 0); self.assertEqual(marker.read_text(), "ran")
        messages = [json.loads(line) for line in os.read(ack, 2048).splitlines()]
        self.assertTrue(messages[0]["started"]); self.assertEqual(messages[1]["reason"], "exited")
        os.close(life); os.close(ack)

    def test_actual_seccomp_socket_keyring_and_bypass_denials(self):
        code = """import ctypes,errno,importlib.util,json,socket,sys
s=importlib.util.spec_from_file_location('g',sys.argv[1]);g=importlib.util.module_from_spec(s);s.loader.exec_module(g)
baseline=socket.socket(socket.AF_INET,socket.SOCK_STREAM);baseline.close()
assert g.install_payload_filter()
libc=ctypes.CDLL(None,use_errno=True)
results={}
for family in (2,10,40,17,38,16):
 ctypes.set_errno(0);rc=libc.syscall(41,family,1,0);results['socket_'+str(family)]=(rc,ctypes.get_errno());assert rc==-1 and ctypes.get_errno()==errno.EPERM
left,right=socket.socketpair();left.close();right.close()
for nr in (101,248,249,250,310,311,321,425,426,427,438):
 ctypes.set_errno(0);rc=libc.syscall(nr,0,0,0,0,0,0);results['syscall_'+str(nr)]=(rc,ctypes.get_errno());assert rc==-1 and ctypes.get_errno()==errno.EPERM
print(json.dumps(results))
"""
        result = subprocess.run([sys.executable, "-I", "-S", "-c", code, str(self.gate)], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["socket_40"], [-1, 1])

    def test_supervisor_sigkill_before_and_after_authorization(self):
        for authorize in (False, True):
            with self.subTest(authorize=authorize):
                ready = self.root / ("ready-" + str(authorize)); marker = self.root / ("marker-" + str(authorize)); done = self.root / ("done-" + str(authorize))
                supervisor = """import importlib.util,json,os,subprocess,sys,time
from pathlib import Path
gr,gw=os.pipe();lr,lw=os.pipe();ar,aw=os.pipe();token=b'x'*32
candidate="from pathlib import Path;import time;Path("+repr(sys.argv[3])+").write_text('started');time.sleep(20);Path("+repr(sys.argv[4])+").write_text('escaped')"
gate="import importlib.util,sys; s=importlib.util.spec_from_file_location('g',sys.argv[1]);g=importlib.util.module_from_spec(s);s.loader.exec_module(g);sys.exit(g.supervise([sys.executable,'-I','-S','-c',sys.argv[6]],int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]),bytes.fromhex(sys.argv[5]),fixture=True))"
p=subprocess.Popen([sys.executable,'-I','-S','-c',gate,sys.argv[1],str(gr),str(lr),str(aw),token.hex(),candidate],pass_fds=(gr,lr,aw))
os.close(gr);os.close(lr);os.close(aw)
if sys.argv[5]=='yes':
 os.write(gw,token);os.close(gw);data=os.read(ar,1024)
else:data=b''
Path(sys.argv[2]).write_text(json.dumps({'gate_pid':p.pid,'started_ack':data.decode()}))
time.sleep(30)
"""
                process = subprocess.Popen([sys.executable, "-I", "-S", "-c", supervisor, str(self.gate), str(ready), str(marker), str(done), "yes" if authorize else "no"])
                self.processes.append(process)
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline: time.sleep(.02)
                self.assertTrue(ready.exists())
                if authorize:
                    deadline = time.monotonic() + 3
                    while not marker.exists() and time.monotonic() < deadline: time.sleep(.02)
                    self.assertTrue(marker.exists())
                process.kill(); process.wait(timeout=5)
                gate_pid = json.loads(ready.read_text())["gate_pid"]
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    try: status = Path(f"/proc/{gate_pid}/stat").read_text().split()[2]
                    except FileNotFoundError: break
                    if status == "Z": break
                    time.sleep(.02)
                else: self.fail("Trusted fixture gate did not exit after supervisor SIGKILL")
                self.assertFalse(done.exists())
                if not authorize: self.assertFalse(marker.exists())

    def test_gate_enforces_own_wall_budget(self):
        grant_r, grant_w = os.pipe(); life_r, life_w = os.pipe(); ack_r, ack_w = os.pipe()
        code = "import importlib.util,sys;s=importlib.util.spec_from_file_location('g',sys.argv[1]);g=importlib.util.module_from_spec(s);s.loader.exec_module(g);sys.exit(g.supervise([sys.executable,'-c','import time;time.sleep(20)'],int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]),b'x'*32,timeout_seconds=1,fixture=True))"
        process = subprocess.Popen([sys.executable, "-I", "-S", "-c", code, str(self.gate), str(grant_r), str(life_r), str(ack_w)], pass_fds=(grant_r, life_r, ack_w))
        self.processes.append(process); os.close(grant_r); os.close(life_r); os.close(ack_w)
        os.write(grant_w, b"x" * 32); os.close(grant_w)
        self.assertEqual(process.wait(timeout=5), 125)
        messages = [json.loads(line) for line in os.read(ack_r, 2048).splitlines()]
        self.assertEqual(messages[-1]["reason"], "wall_budget")
        os.close(life_w); os.close(ack_r)


class SetupDiagnosticTests(unittest.TestCase):
    def test_bounded_redacted_exclusive(self):
        token = bytes.fromhex("ab" * 32)
        data = b"error " + token.hex().encode() + b"\xff"
        sink = io.StringIO()
        context = mock.MagicMock()
        context.__enter__.return_value = sink
        process = mock.Mock(); process.stderr.fileno.return_value = 10
        with mock.patch.object(executor.os, "set_blocking") as block, mock.patch.object(executor.os, "read", return_value=data) as read, mock.patch.object(executor.os, "open", return_value=11) as opened, mock.patch.object(executor.os, "O_NOFOLLOW", 0x20000, create=True), mock.patch.object(executor.os, "fdopen", return_value=context):
            executor._setup_diagnostic(Path("job"), process, token, 78)
        block.assert_called_once_with(10, False); read.assert_called_once_with(10, 4096)
        self.assertEqual(opened.call_args.args[2], 0o600)
        self.assertTrue(opened.call_args.args[1] & os.O_EXCL)
        result = json.loads(sink.getvalue())
        self.assertEqual(result["exit_code"], 78)
        self.assertNotIn(token.hex(), result["stderr"])
        self.assertIn("[redacted]", result["stderr"])

    def test_read_error_does_not_change_failure(self):
        process = mock.Mock(); process.stderr.fileno.return_value = 10
        with mock.patch.object(executor.os, "set_blocking", side_effect=OSError), mock.patch.object(executor.os, "open") as opened:
            executor._setup_diagnostic(Path("job"), process, b"a" * 32, 1)
        opened.assert_not_called()


if __name__ == "__main__":
    unittest.main()
