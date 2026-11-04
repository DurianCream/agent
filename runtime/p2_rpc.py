"""Bounded same-host RPC to root verification and a separate publisher.

Systemd owns the listening sockets: clients authenticate the protected endpoint
and its root-manager credentials, not a claimed publisher UID in reply JSON.
Each server authenticates controller SO_PEERCRED and enforces its actual role.
"""
from __future__ import annotations
import base64
import importlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import stat
import struct
import time

MAX_BUNDLE_BYTES = 64 * 1024
REQUEST_TIMEOUT = 330
SOCKETS = {'verify': '/run/multi-p2-rpc/verify.sock', 'publish': '/run/multi-p2-rpc/publish.sock'}


class RPCError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code):
    if not condition: raise RPCError(code)


def peer(connection):
    require(connection.family == socket.AF_UNIX, 'rpc_unix_required')
    pid, uid, gid = struct.unpack('iII', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('iII')))
    require(pid > 0, 'rpc_peer_unavailable')
    return {'pid': pid, 'uid': uid, 'gid': gid}


def receive(connection, timeout=5):
    from p2_broker import _exact, MAX_FRAME
    deadline = time.monotonic() + timeout
    size = struct.unpack('!I', _exact(connection, 4, deadline, time.monotonic))[0]
    require(0 < size <= MAX_FRAME, 'rpc_frame_size')
    return _exact(connection, size, deadline, time.monotonic)


def encode_bundle(bundle):
    from p2_verifier import freeze_bundle
    frozen, _ = freeze_bundle(bundle)
    require(sum(len(value) for value in frozen['blobs'].values()) <= MAX_BUNDLE_BYTES, 'rpc_bundle_quota')
    return {**frozen, 'blobs': {key: base64.b64encode(value).decode('ascii') for key, value in frozen['blobs'].items()}}


def decode_bundle(value):
    from p2_verifier import freeze_bundle
    require(type(value) is dict and set(value) == {'binding', 'files', 'blobs'} and type(value['blobs']) is dict, 'rpc_bundle_fields')
    blobs = {}; total = 0
    for key, item in value['blobs'].items():
        require(type(item) is str and len(item) <= 4 * ((MAX_BUNDLE_BYTES + 2) // 3), 'rpc_blob_size')
        try: data = base64.b64decode(item, validate=True)
        except (ValueError, UnicodeError): raise RPCError('rpc_blob_encoding') from None
        total += len(data); require(total <= MAX_BUNDLE_BYTES, 'rpc_bundle_quota')
        blobs[key] = data
    bundle, digest = freeze_bundle({**value, 'blobs': blobs})
    require(sum(item.get('size',0) for item in bundle['files']) <= MAX_BUNDLE_BYTES, 'rpc_bundle_quota')
    return bundle, digest


def call(role, publisher_uid, value):
    from p2_broker import _root_controlled, send_frame
    from control_contracts import load_json
    require(role in SOCKETS, 'rpc_role')
    path = Path(SOCKETS[role]); _root_controlled(path.parent, directory=True)
    info = path.lstat()
    require(stat.S_ISSOCK(info.st_mode) and info.st_uid == (0 if role == 'verify' else publisher_uid) and
            stat.S_IMODE(info.st_mode) == 0o660, 'rpc_endpoint_identity')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(5); connection.connect(str(path))
        identity = peer(connection)
        require(identity['uid'] == 0 and identity['pid'] == 1, 'rpc_system_manager_peer_required')
        current = path.lstat()
        require((current.st_dev,current.st_ino) == (info.st_dev,info.st_ino), 'rpc_endpoint_changed')
        send_frame(connection, value)
        response = load_json(receive(connection, REQUEST_TIMEOUT))
        require(type(response) is dict and response.get('backend_key') == value['backend_key'], 'rpc_response_binding')
        require(type(response.get('result')) is dict, 'rpc_response_fields')
        require(response.get('server_uid') == (0 if role == 'verify' else publisher_uid), 'rpc_server_role_assertion')
        return {**response['result'], 'rpc_transport': {'listener_uid':identity['uid'], 'listener_pid':identity['pid'],
                'service_uid':response['server_uid'], 'controller_uid':response.get('controller_uid')}}


class ProductionWorkflow:
    def __init__(self, store, config):
        require(not store.fixture_mode and type(config) is dict and set(config) == {'publisher_uid', 'listener_identity'} and
                type(config['publisher_uid']) is int and config['publisher_uid'] > 0 and
                config['listener_identity'] == 'systemd-root', 'rpc_configuration')
        self.store = store; self.publisher_uid = config['publisher_uid']

    def process(self, raw, uid):
        return self.store.production_adapter_call(raw, uid, self.handle)

    def handle(self, request, uid, backend_key):
        try:
            payload = request['payload']; eid = request['binding']['enrollment_id']
            candidate = self.store.candidate(eid,uid,payload['candidate_id'],payload['candidate_digest'])
            require(sum(item.get('size',0) for item in candidate['files']) <= MAX_BUNDLE_BYTES, 'rpc_bundle_quota')
            bundle = self.store.export_bundle(eid, uid, payload['candidate_id'], payload['candidate_digest'])
            message = {'schema_version': '0.1.0', 'request': request, 'client_uid': uid, 'backend_key': backend_key, 'bundle': encode_bundle(bundle)}
            return call(request['operation'], self.publisher_uid, message)
        except (OSError, ValueError) as error:
            return {'status': 'unknown', 'error_code': getattr(error, 'code', 'rpc_transport_unknown'),
                    'authorization': False, 'published': None, 'trust_mode': 'production'}


def _configuration():
    from p2_verifier import read_record
    from p2_broker import _root_controlled
    path = Path('/etc/multi-p2/rpc.json'); _root_controlled(path)
    value = read_record(path, owner=0)
    require(type(value) is dict and set(value) == {'schema_version','controller_uid','publisher_uid','policies'} and value['schema_version']=='0.1.0', 'rpc_configuration')
    require(type(value['controller_uid']) is int and value['controller_uid'] > 0 and type(value['publisher_uid']) is int and
            value['publisher_uid'] > 0 and value['controller_uid'] != value['publisher_uid'], 'rpc_principals')
    require(type(value['policies']) is list and 0 < len(value['policies']) <= 128, 'rpc_policy_count')
    for item in value['policies']:
        require(type(item) is dict and set(item) == {'policy_path','executor_config_path','client_uid'} and
                type(item['client_uid']) is int and item['client_uid'] > 0 and
                item['client_uid'] not in (value['controller_uid'], value['publisher_uid']), 'rpc_policy_fields')
        for name in ('policy_path','executor_config_path'): _root_controlled(item[name])
    return value


def dispatch(role, raw, config):
    from control_contracts import load_json
    import p2_contracts as contract
    from p2_verifier import read_record, policy_binding, Verifier
    value = load_json(raw)
    require(type(value) is dict and set(value)=={'schema_version','request','backend_key','bundle','client_uid'} and value['schema_version']=='0.1.0', 'rpc_request_fields')
    contract.uuid4(value['backend_key'])
    request = value['request']
    require(type(request) is dict and request.get('operation') == role, 'rpc_operation')
    selected=[]
    for item in config['policies']:
        policy = read_record(item['policy_path'], owner=0)
        if policy_binding(policy) == request.get('binding'): selected.append((item,policy))
    require(len(selected)==1, 'rpc_policy_binding')
    item, policy = selected[0]
    require(type(value['client_uid']) is int and value['client_uid']==item['client_uid'], 'rpc_delegated_client')
    require(policy['principals']['publisher_uid']==config['publisher_uid'] and
            policy['principals']['worker_uid'] not in (0,config['controller_uid'],config['publisher_uid'],item['client_uid']), 'rpc_role_separation')
    contract.validate_request(json.dumps(request,separators=(',',':')).encode(), expected_binding=policy_binding(policy))
    bundle, digest = decode_bundle(value['bundle'])
    payload=request['payload']
    require(bundle['binding']==request['binding'] and digest==payload['candidate_digest'], 'rpc_candidate_binding')
    if role=='verify':
        from p2_executor import BwrapExecutor
        verifier=Verifier.from_protected_policy(item['policy_path'], BwrapExecutor.from_config(item['executor_config_path']))
        receipt=verifier.verify(bundle,payload['candidate_id'],value['backend_key'])
        result={'status':receipt['outcome'],'verification_id':receipt['verification_id'],'candidate_digest':receipt['candidate_digest'],
                'authorization':False,'published':False,'trust_mode':'production','p2_isolation_verified':receipt['isolation_verified']}
    else:
        from p2_publisher import Publisher
        publisher=Publisher.from_protected_policy(item['policy_path'])
        result=publisher.publish(bundle,payload['candidate_id'],payload['verification_id'],value['backend_key'])
    return {'backend_key':value['backend_key'],'result':result}


def serve(role):
    from p2_broker import send_frame
    from control_contracts import load_json
    require(role in SOCKETS and os.environ.get('LISTEN_PID')==str(os.getpid()) and os.environ.get('LISTEN_FDS')=='1', 'rpc_socket_activation_required')
    config=_configuration()
    require(os.geteuid()==(0 if role=='verify' else config['publisher_uid']), 'rpc_server_identity')
    listener=socket.socket(fileno=3)
    require(listener.family==socket.AF_UNIX and listener.getsockopt(socket.SOL_SOCKET,socket.SO_ACCEPTCONN)==1 and listener.getsockname()==SOCKETS[role], 'rpc_listener_identity')
    os.set_inheritable(3,False)
    listener.settimeout(20)
    try:
        # One request per activation: a later request must receive a fresh
        # service RuntimeMaxSec budget, not the previous request's remaining age.
        for _ in range(1):
            try: connection,_=listener.accept()
            except socket.timeout: return
            with connection:
                key=None
                identity=None
                try:
                    identity=peer(connection)
                    require(identity['uid']==config['controller_uid'], 'rpc_controller_required')
                    raw=receive(connection)
                    peek=load_json(raw)
                    if type(peek) is dict: key=peek.get('backend_key')
                    # Reload protected configuration on every operation.
                    current=_configuration(); require(current==config, 'rpc_configuration_changed')
                    response=dispatch(role,raw,current)
                except (ValueError,OSError,sqlite3.Error) as error:
                    code=getattr(error,'code','rpc_operation_unknown')
                    response={'backend_key':key,'result':{'status':'unknown','error_code':code,'authorization':False,'published':None,'trust_mode':'production'}}
                response['server_uid']=os.geteuid()
                response['controller_uid']=identity['uid'] if identity is not None else None
                try: send_frame(connection,response)
                except (OSError,ValueError): pass
    finally:
        listener.close()
