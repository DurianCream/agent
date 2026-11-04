"""Linux authenticated intake, with opt-in protected local RPC in config 0.2.

Production authenticates the connecting Unix peer with SO_PEERCRED and requires
root-controlled configuration/runtime plus private service storage. Each socket
carries one bounded request. An authorized peer can proxy/pass its connected FD;
SO_PEERCRED identifies the connection creator, not a separate process behind it.
No child processes or inherited worker handles are launched here.

FixtureBroker is intentionally separate and cannot be selected by configuration
or CLI. Its results are consistency evidence only. Config 0.1 retains stage-only
behavior; config 0.2 separates the submission client from the execution worker.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import stat
import struct
import sys
import time

MAX_FRAME = 128 * 1024
FRAME_TIMEOUT = 5.0
RUNTIME = Path(__file__).absolute().parent


class BrokerError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__("P2 broker rejected the operation: " + code)


def require(value, code):
    if not value:
        raise BrokerError(code)


def _root_controlled(path, *, directory=False):
    require(sys.platform == "linux", "production_platform_unavailable")
    path = Path(path)
    require(path.is_absolute() and ".." not in path.parts, "unsafe_trusted_path")
    for part in [*reversed(path.parents), path]:
        info = part.lstat()
        require(not stat.S_ISLNK(info.st_mode) and info.st_uid == 0 and info.st_mode & 0o022 == 0,
                "untrusted_configuration_or_runtime")
        is_directory = part != path or directory
        require(stat.S_ISDIR(info.st_mode) if is_directory else stat.S_ISREG(info.st_mode), "unsafe_trusted_type")
        if not is_directory:
            require(info.st_nlink == 1, "unsafe_trusted_link")


def _trusted_runtime():
    require(sys.flags.isolated == 1, "isolated_interpreter_required")
    require(sys.flags.no_site == 1, "no_site_interpreter_required")
    for name in ("p2_broker.py", "p2_store.py", "p2_contracts.py", "control_contracts.py",
                 "p2_executor.py", "p2_sandbox_gate.py", "p2_verifier.py", "p2_publisher.py", "p2_rpc.py"):
        _root_controlled(RUNTIME / name)
    # Deployment must also protect the installed interpreter and dependency
    # contents recursively. These startup checks are not an isolation attestation.
    _root_controlled(Path(sys.executable))
    for name in sys.path:
        _trusted_import_path(name)
    private_site = Path(sys.executable).parent.parent / "lib" / ("python" + str(sys.version_info.major) + "." + str(sys.version_info.minor)) / "site-packages"
    _root_controlled(private_site, directory=True)
    count = 0
    for path in private_site.rglob("*"):
        count += 1
        require(count <= 20000, "runtime_file_limit")
        require(path.suffix.casefold() != ".pth" and path.stem.casefold() not in ("sitecustomize", "usercustomize"),
                "startup_hook_rejected")
        _root_controlled(path, directory=stat.S_ISDIR(path.lstat().st_mode))
    if str(private_site) not in sys.path:
        # Do not use site.addsitedir: it executes .pth files.
        sys.path.insert(0, str(private_site))


def _trusted_import_path(name):
    require(bool(name), "unsafe_import_path")
    path = Path(name)
    require(path.is_absolute() and ".." not in path.parts and not path.is_symlink(), "unsafe_import_path")
    if path.exists():
        _root_controlled(path, directory=path.is_dir())
    else:
        ancestor = path.parent
        while not ancestor.exists():
            require(not ancestor.is_symlink(), "unsafe_import_path")
            ancestor = ancestor.parent
        _root_controlled(ancestor, directory=True)


def _modules():
    # Production calls this only after checking the fixed installed source path.
    # Explicit fixtures load local development sources without claiming trust.
    if str(RUNTIME) not in sys.path:
        sys.path.insert(0, str(RUNTIME))
    return importlib.import_module("p2_store"), importlib.import_module("control_contracts")


def kernel_peer(connection):
    require(sys.platform == "linux" and hasattr(socket, "SO_PEERCRED"), "kernel_peer_unavailable")
    require(type(connection) is socket.socket and connection.family == socket.AF_UNIX,
            "unix_socket_required")
    require(connection.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) == socket.SOCK_STREAM,
            "stream_socket_required")
    connection.getpeername()  # Require a connected endpoint, not a listening socket.
    value = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("iII"))
    pid, uid, gid = struct.unpack("iII", value)
    require(pid > 0 and uid > 0 and gid >= 0, "invalid_kernel_peer")
    return {"pid": pid, "uid": uid, "gid": gid}


def _exact(connection, count, deadline, clock):
    output = bytearray()
    while len(output) < count:
        remaining = deadline - clock()
        require(remaining > 0, "frame_deadline")
        connection.settimeout(remaining)
        chunk = connection.recv(count - len(output))
        require(clock() <= deadline, "frame_deadline")
        require(bool(chunk), "incomplete_frame")
        output.extend(chunk)
    return bytes(output)


def read_frame(connection, *, clock=None):
    clock = time.monotonic if clock is None else clock
    deadline = clock() + FRAME_TIMEOUT
    length = struct.unpack("!I", _exact(connection, 4, deadline, clock))[0]
    require(0 < length <= MAX_FRAME, "frame_size")
    return _exact(connection, length, deadline, clock)


def send_frame(connection, value, *, clock=None):
    clock = time.monotonic if clock is None else clock
    deadline = clock() + FRAME_TIMEOUT
    body = json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    require(len(body) <= MAX_FRAME, "response_size")
    data = memoryview(struct.pack("!I", len(body)) + body)
    while data:
        remaining = deadline - clock()
        require(remaining > 0, "frame_deadline")
        connection.settimeout(remaining)
        count = connection.send(data)
        require(clock() <= deadline, "frame_deadline")
        require(0 < count <= len(data), "incomplete_frame")
        data = data[count:]


def blocked(code, *, authenticated=False, fixture=False):
    return {"status": "blocked", "error_code": code, "authorization": False, "published": False,
            "peer_authenticated": authenticated, "p2_isolation_verified": False,
            "assurance": "fixture_consistency_only" if fixture else "kernel_peer_intake_only"}


class Broker:
    def __init__(self, *args, **kwargs):
        raise BrokerError("use_protected_configuration")

    @classmethod
    def from_config(cls, config_path):
        _trusted_runtime()
        _root_controlled(config_path)
        fd = os.open(config_path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
            require(before.st_size <= MAX_FRAME and before.st_uid == 0 and before.st_nlink == 1 and
                    stat.S_ISREG(before.st_mode) and before.st_mode & 0o022 == 0, "untrusted_configuration")
            with os.fdopen(os.dup(fd), "rb") as stream:
                raw = stream.read(MAX_FRAME + 1)
            after = os.fstat(fd)
            require(len(raw) <= MAX_FRAME and (before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns) ==
                    (after.st_ino, after.st_dev, after.st_size, after.st_mtime_ns), "configuration_changed")
        finally:
            os.close(fd)
        store_module, contracts = _modules()
        config = contracts.load_json(raw)
        fields = {"schema_version", "state_root", "socket_path", "controller_uid", "worker_gid", "enrollments"}
        require(type(config) is dict and ((set(config) == fields and config.get("schema_version") == "0.1.0") or
                (set(config) == (fields - {"worker_gid"}) | {"client_gid", "rpc"} and config.get("schema_version") == "0.2.0")), "configuration_fields")
        require(type(config["controller_uid"]) is int and 0 < config["controller_uid"] == os.geteuid(), "controller_identity")
        client_gid = config['worker_gid'] if config['schema_version']=='0.1.0' else config['client_gid']
        require(type(client_gid) is int and 0 < client_gid < (1 << 31), "worker_group")
        require(client_gid in {os.getegid(), *os.getgroups()}, "worker_group_unavailable")
        require(type(config["enrollments"]) is list and len(config["enrollments"]) <= 128, "enrollment_count")
        for name in ("state_root", "socket_path"):
            require(type(config[name]) is str and Path(config[name]).is_absolute() and ".." not in Path(config[name]).parts,
                    "configuration_path")
        require(len(os.fsencode(config["socket_path"])) <= 107, "socket_path_size")
        obj = object.__new__(cls)
        obj.store = store_module.CandidateStore(config["state_root"])
        obj.socket_path = Path(config["socket_path"])
        obj.worker_gid = client_gid
        obj.enrollments = {}
        obj.rpc_workflow = None
        if config["schema_version"] == "0.2.0":
            from p2_rpc import ProductionWorkflow
            obj.rpc_workflow = ProductionWorkflow(obj.store, config["rpc"])
        used_uids = set()
        try:
            for enrollment in config["enrollments"]:
                identity_field = 'worker_uid' if config['schema_version']=='0.1.0' else 'client_uid'
                require(type(enrollment) is dict and set(enrollment) == {"binding", identity_field}, "enrollment_fields")
                uid = enrollment[identity_field]
                require(type(uid) is int and uid != os.geteuid() and uid not in used_uids, "worker_identity")
                obj.store.enroll(enrollment["binding"], uid)
                eid = enrollment["binding"]["enrollment_id"]
                require(eid not in obj.enrollments, "duplicate_enrollment")
                obj.enrollments[eid] = uid
                used_uids.add(uid)
            obj._socket_parent()
        except BaseException:
            obj.store.close()
            raise
        return obj

    def _socket_parent(self):
        store_module, _ = _modules()
        info = store_module.check_protected_path(self.socket_path.parent, owner=os.geteuid(), directory=True)
        require(info.st_uid == os.geteuid() and info.st_gid == self.worker_gid and stat.S_IMODE(info.st_mode) == 0o750,
                "socket_parent_not_protected")

    def _dispatch(self, raw, uid):
        store_module, contracts = _modules()
        peek = contracts.load_json(raw)
        require(type(peek) is dict and type(peek.get("binding")) is dict, "binding_unavailable")
        eid = peek["binding"].get("enrollment_id")
        require(type(eid) is str and self.enrollments.get(eid) == uid, "peer_not_enrolled")
        if peek.get('operation') == 'upload':
            import base64
            require(getattr(self, 'rpc_workflow', None) is not None, 'upload_transport_unavailable')
            require(type(peek) is dict and set(peek) == {'schema_version','operation','binding','digest','data_base64'} and
                    peek['schema_version'] == '0.2.0' and type(peek['data_base64']) is str and
                    len(peek['data_base64']) <= 4 * ((65536+2)//3), 'upload_fields')
            require(peek['binding'] == self.store.expected_binding(eid, uid), 'upload_binding')
            try: data = base64.b64decode(peek['data_base64'], validate=True)
            except (ValueError,UnicodeError): raise BrokerError('upload_encoding') from None
            require(len(data) <= 65536, 'upload_size')
            return {**self.store.put_blob(eid,uid,data,peek['digest']), 'status':'uploaded','published':False}
        if getattr(self, 'rpc_workflow', None) is not None:
            return self.rpc_workflow.process(raw, uid)
        return self.store.process(raw, uid)

    def handle_socket(self, connection):
        authenticated = False
        store_module, contracts = _modules()
        try:
            require(self.store.fixture_mode is False, "production_store_required")
            peer = kernel_peer(connection)
            authenticated = True
            require(peer["uid"] in self.enrollments.values(), "peer_not_enrolled")
            connection.settimeout(5)
            value = self._dispatch(read_frame(connection), peer["uid"])
            return {**value, "peer_authenticated": True,
                    "assurance": "authenticated_local_rpc" if self.rpc_workflow is not None else "kernel_peer_intake_only",
                    "p2_isolation_verified": value.get('p2_isolation_verified', False)}
        except (BrokerError, store_module.StoreError, contracts.ControlContractError) as error:
            if error.code == 'adapter_result_not_recorded':
                return {'status':'unknown','error_code':error.code,'authorization':False,'published':None,
                        'peer_authenticated':authenticated,'p2_isolation_verified':False,
                        'assurance':'authenticated_local_rpc'}
            return blocked(error.code, authenticated=authenticated)
        except (OSError, sqlite3.Error):
            if self.rpc_workflow is not None:
                return {"status":"unknown","error_code":"transport_or_store_unavailable","authorization":False,
                        "published":None,"peer_authenticated":authenticated,"p2_isolation_verified":False}
            return blocked("transport_or_store_unavailable", authenticated=authenticated)

    def serve(self):
        self._socket_parent()
        require(not self.socket_path.exists() and not self.socket_path.is_symlink(), "socket_target_exists")
        previous_umask = os.umask(0o077)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        identity = None
        try:
            listener.bind(str(self.socket_path))
            info = self.socket_path.lstat()
            identity = (info.st_dev, info.st_ino)
            require(stat.S_ISSOCK(info.st_mode) and info.st_uid == os.geteuid(), "unexpected_socket")
            os.chown(self.socket_path, -1, self.worker_gid)
            os.chmod(self.socket_path, 0o660)
            listener.listen(8)
            while True:
                connection, _ = listener.accept()
                with connection:
                    response = self.handle_socket(connection)
                    try:
                        send_frame(connection, response)
                    except (OSError, BrokerError):
                        pass  # Durable request state, if admitted, remains queryable on identical retry.
        finally:
            listener.close()
            os.umask(previous_umask)
            if identity is not None:
                try:
                    current = self.socket_path.lstat()
                    if stat.S_ISSOCK(current.st_mode) and (current.st_dev, current.st_ino) == identity:
                        self.socket_path.unlink()
                except FileNotFoundError:
                    pass
            self.store.close()


class FixtureBroker:
    """Explicit consistency test harness; no kernel authentication claims."""
    def __init__(self, store, enrollment_uids, *, workflow=None):
        require(store.fixture_mode is True, "fixture_store_required")
        self.store = store
        self.enrollments = dict(enrollment_uids)
        self.workflow = workflow
        if workflow is not None:
            adapter = importlib.import_module("p2_publisher")
            require(type(workflow) is adapter.FixtureAdapterWorkflow and workflow.store is store, "fixture_workflow_required")

    def handle_fixture(self, raw, uid):
        store_module, contracts = _modules()
        try:
            if self.workflow is None:
                value = Broker._dispatch(self, raw, uid)
            else:
                peek = contracts.load_json(raw)
                require(type(peek) is dict and type(peek.get("binding")) is dict and
                        self.enrollments.get(peek["binding"].get("enrollment_id")) == uid, "peer_not_enrolled")
                value = self.workflow.process(raw, uid)
            return {**value, "peer_authenticated": False, "p2_isolation_verified": False,
                    "assurance": "fixture_consistency_only"}
        except (BrokerError, store_module.StoreError, contracts.ControlContractError) as error:
            if self.workflow is not None and error.code == "adapter_result_not_recorded":
                return {"status": "unknown", "error_code": error.code, "authorization": False, "published": None,
                        "peer_authenticated": False, "p2_isolation_verified": False, "assurance": "fixture_consistency_only"}
            return blocked(error.code, fixture=True)
        except (OSError, sqlite3.Error):
            if self.workflow is not None:
                return {"status": "unknown", "error_code": "fixture_workflow_store_unavailable", "authorization": False, "published": None,
                        "peer_authenticated": False, "p2_isolation_verified": False, "assurance": "fixture_consistency_only"}
            return blocked("store_unavailable", fixture=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    try:
        Broker.from_config(args.config).serve()
    except Exception as error:
        # No request, private path or OS exception message is exposed.
        code = error.code if isinstance(error, BrokerError) else "startup_unavailable"
        print(json.dumps(blocked(code)), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
