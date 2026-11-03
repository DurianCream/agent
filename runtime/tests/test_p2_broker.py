import copy
import json
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import p2_broker as broker
import p2_store as store
from test_p2_store import binding, request, raw


class FixtureBrokerTests(unittest.TestCase):
    def setUp(self):
        parent = Path(os.environ["P2_TEST_TMP"]) if "P2_TEST_TMP" in os.environ else Path(__file__).resolve().parents[2] / "work/p2-broker-tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.store = store.CandidateStore(self.temp.name, fixture_mode=True)
        self.addCleanup(self.store.close)
        self.bound = binding()
        self.uid = 22001
        self.store.enroll(self.bound, self.uid)
        self.broker = broker.FixtureBroker(self.store, {self.bound["enrollment_id"]: self.uid})
        self.files = [{"path": "removed.txt", "kind": "delete"}]

    def test_fixture_staging_never_claims_authentication_or_isolation(self):
        value = self.broker.handle_fixture(raw(request(self.bound, self.files)), self.uid)
        self.assertEqual(value["status"], "staged")
        self.assertEqual(value["assurance"], "fixture_consistency_only")
        self.assertFalse(value["peer_authenticated"] or value["p2_isolation_verified"] or value["authorization"] or value["published"])

    def test_wrong_peer_and_unconfigured_enrollment_rejected(self):
        value = self.broker.handle_fixture(raw(request(self.bound, self.files)), self.uid + 1)
        self.assertEqual(value["error_code"], "peer_not_enrolled")
        other = binding()
        value = self.broker.handle_fixture(raw(request(other, self.files)), self.uid)
        self.assertEqual(value["error_code"], "peer_not_enrolled")

    def test_claimed_uid_and_passed_json_are_not_authority(self):
        for key in ("uid", "peer", "passed", "authorization", "command", "remote"):
            req = request(self.bound, self.files)
            req[key] = "sensitive-value"
            value = self.broker.handle_fixture(raw(req), self.uid)
            self.assertEqual(value["status"], "blocked")
            self.assertNotIn("sensitive-value", json.dumps(value))

    def test_publish_is_blocked_without_trusted_adapter(self):
        staged = self.broker.handle_fixture(raw(request(self.bound, self.files)), self.uid)
        req = request(self.bound, operation="publish", candidate=staged)
        value = self.broker.handle_fixture(raw(req), self.uid)
        self.assertEqual(value["error_code"], "adapter_unavailable")
        self.assertFalse(value["authorization"] or value["published"])

    def test_fixture_api_not_available_on_production_class(self):
        with self.assertRaisesRegex(broker.BrokerError, "use_protected_configuration"):
            broker.Broker(self.store)
        self.assertFalse(hasattr(broker.Broker, "handle_fixture"))

    def test_fixture_store_cannot_enter_production_socket_handler(self):
        accidental = object.__new__(broker.Broker)
        accidental.store = self.store
        result = accidental.handle_socket(mock.Mock())
        self.assertEqual(result["error_code"], "production_store_required")
        self.assertFalse(result["peer_authenticated"])

    def test_production_requires_isolated_interpreter_before_loading_config(self):
        with mock.patch.object(broker.sys, "flags") as flags:
            flags.isolated = 0
            with self.assertRaisesRegex(broker.BrokerError, "isolated_interpreter_required"):
                broker.Broker.from_config("not-read.json")

    def test_production_requires_no_site_before_loading_config(self):
        with mock.patch.object(broker.sys, "flags") as flags:
            flags.isolated = 1
            flags.no_site = 0
            with self.assertRaisesRegex(broker.BrokerError, "no_site_interpreter_required"):
                broker.Broker.from_config("not-read.json")

    def test_forged_python_peer_object_is_rejected(self):
        fake = mock.Mock()
        fake.family = socket.AF_UNIX if hasattr(socket, "AF_UNIX") else 1
        with self.assertRaises(broker.BrokerError):
            broker.kernel_peer(fake)

    def test_malformed_json_is_safely_blocked(self):
        value = self.broker.handle_fixture(b'{"secret":"private",', self.uid)
        self.assertEqual(value["status"], "blocked")
        self.assertNotIn("private", json.dumps(value))


class FramingDeadlineTests(unittest.TestCase):
    class DripSocket:
        def __init__(self, data=b"", step=1.0):
            self.data = data
            self.step = step
            self.now = 0.0
            self.timeouts = []
        def clock(self):
            return self.now
        def settimeout(self, value):
            self.timeouts.append(value)
        def recv(self, count):
            self.now += self.step
            chunk, self.data = self.data[:1], self.data[1:]
            return chunk
        def send(self, data):
            self.now += self.step
            return 1

    def test_drip_header_cannot_reset_idle_timeout(self):
        connection = self.DripSocket(struct.pack("!I", 1) + b"x", step=2)
        with self.assertRaisesRegex(broker.BrokerError, "frame_deadline"):
            broker.read_frame(connection, clock=connection.clock)
        self.assertEqual(connection.timeouts, [5.0, 3.0, 1.0])

    def test_header_and_body_share_one_deadline(self):
        connection = self.DripSocket(struct.pack("!I", 8) + b"abcdefgh", step=0.6)
        with self.assertRaisesRegex(broker.BrokerError, "frame_deadline"):
            broker.read_frame(connection, clock=connection.clock)
        self.assertLess(connection.timeouts[4], 3.0)

    def test_partial_sends_share_a_reply_deadline(self):
        connection = self.DripSocket(step=2)
        with self.assertRaisesRegex(broker.BrokerError, "frame_deadline"):
            broker.send_frame(connection, {"status": "blocked"}, clock=connection.clock)
        self.assertEqual(connection.timeouts, [5.0, 3.0, 1.0])


@unittest.skipUnless(sys.platform == "linux", "Actual Linux SO_PEERCRED tests not run on Windows")
class KernelPeerTests(unittest.TestCase):
    def test_real_unix_socket_uses_current_kernel_identity(self):
        import os
        left, right = socket.socketpair()
        try:
            if os.getuid() == 0:
                with self.assertRaisesRegex(broker.BrokerError, "invalid_kernel_peer"):
                    broker.kernel_peer(right)
            else:
                peer = broker.kernel_peer(right)
                self.assertEqual(peer, {"pid": os.getpid(), "uid": os.getuid(), "gid": os.getgid()})
        finally:
            left.close(); right.close()

    def test_stream_frame_bounds_and_exact_payload(self):
        left, right = socket.socketpair()
        try:
            left.sendall(struct.pack("!I", 3) + b"abc")
            self.assertEqual(broker.read_frame(right), b"abc")
            left.sendall(struct.pack("!I", broker.MAX_FRAME + 1))
            with self.assertRaisesRegex(broker.BrokerError, "frame_size"):
                broker.read_frame(right)
        finally:
            left.close(); right.close()

    def test_worker_owned_config_is_not_trusted(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "config.json"
            file.write_text("{}")
            with self.assertRaises(broker.BrokerError):
                broker._root_controlled(file)

    def test_store_rejects_real_symlink_without_reading_target(self):
        with tempfile.TemporaryDirectory() as folder:
            state = store.CandidateStore(folder, fixture_mode=True)
            try:
                target = Path(folder) / "outside-canary"
                target.write_bytes(b"synthetic canary")
                (Path(folder) / "blobs" / ("a" * 64)).symlink_to(target)
                with self.assertRaisesRegex(store.StoreError, "unsafe_file"):
                    state._read("blobs", "a" * 64, 64)
                self.assertEqual(target.read_bytes(), b"synthetic canary")
            finally:
                state.close()

    def test_store_rejects_symlinked_root(self):
        with tempfile.TemporaryDirectory() as folder:
            actual = Path(folder) / "actual"
            actual.mkdir()
            alias = Path(folder) / "alias"
            alias.symlink_to(actual, target_is_directory=True)
            with self.assertRaisesRegex(store.StoreError, "unsafe_root"):
                store.CandidateStore(alias, fixture_mode=True)

    def test_broken_import_link_and_ancestor_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            alias = Path(folder) / "alias"
            alias.symlink_to(Path(folder) / "absent", target_is_directory=True)
            for path in (alias, alias / "packages"):
                with self.assertRaisesRegex(broker.BrokerError, "unsafe_import_path"):
                    broker._trusted_import_path(path)


if __name__ == "__main__":
    unittest.main()
