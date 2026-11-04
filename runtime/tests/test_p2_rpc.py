"""Focused RPC framing/byte validation tests; real roles are tested in the VM."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from uuid import uuid4
import unittest
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import p2_rpc as rpc
from p2_broker import BrokerError
from p2_broker import Broker
from p2_store import CandidateStore
from control_contracts import canonical_digest


def bundle(data=b'print(1)\n'):
    digest='sha256:'+hashlib.sha256(data).hexdigest()
    return {'binding':{'repository_id':'multi','task_id':'rpc-test','scope':{'project':'multi','service':'agent-framework','environment':'development','issue':'p2-automatic-rpc'},'enrollment_id':'11111111-1111-4111-8111-111111111111','base_commit':'a'*40,'policy_digest':'sha256:'+'b'*64},'files':[{'path':'test.py','kind':'blob','mode':'100644','size':len(data),'digest':digest}],'blobs':{digest:data}}


class RPCContractTests(unittest.TestCase):
    def test_wire_roundtrip_rehashes_bytes(self):
        original=bundle(); result,digest=rpc.decode_bundle(rpc.encode_bundle(original))
        self.assertEqual(result,original); self.assertTrue(digest.startswith('sha256:'))

    def test_forged_blob_cannot_keep_original_digest(self):
        value=rpc.encode_bundle(bundle()); key=next(iter(value['blobs']))
        value['blobs'][key]=base64.b64encode(b'forged').decode()
        with self.assertRaises(ValueError):rpc.decode_bundle(value)

    def test_inline_bundle_bound(self):
        with self.assertRaisesRegex(rpc.RPCError,'rpc_bundle_quota'):rpc.encode_bundle(bundle(b'x'*(rpc.MAX_BUNDLE_BYTES+1)))

    def test_oversized_header_does_not_read_body(self):
        with mock.patch('p2_broker._exact',return_value=struct.pack('!I',128*1024+1)) as exact:
            with self.assertRaisesRegex(rpc.RPCError,'rpc_frame_size'):rpc.receive(mock.Mock())
        self.assertEqual(exact.call_count,1)

    def test_transport_deadline_propagates(self):
        with mock.patch('p2_broker._exact',side_effect=BrokerError('frame_deadline')):
            with self.assertRaises(BrokerError):rpc.receive(mock.Mock())

    def test_no_caller_selected_host_paths(self):
        value=rpc.encode_bundle(bundle());value['path']='/etc/shadow'
        with self.assertRaisesRegex(rpc.RPCError,'rpc_bundle_fields'):rpc.decode_bundle(value)

    def test_duplicate_digest_paths_still_charge_materialized_bytes(self):
        value=rpc.encode_bundle(bundle(b'x'*40000))
        first=value['files'][0];value['files']=[{**first,'path':'a.py'},{**first,'path':'b.py'}]
        with self.assertRaisesRegex(rpc.RPCError,'rpc_bundle_quota'):rpc.decode_bundle(value)


class ReviewRegressionTests(unittest.TestCase):
    def test_effect_then_save_failure_is_unknown_and_retry_keeps_backend_key(self):
        # Real fixture ledger transactions, modeled backend effect and kernel
        # boundary: this is not an actual production publication claim.
        with tempfile.TemporaryDirectory() as temporary:
            store=CandidateStore(Path(temporary),fixture_mode=True)
            self.addCleanup(store.close)
            body=bundle();bound=body['binding'];uid=1001
            store.enroll(bound,uid)
            for digest,data in body['blobs'].items():store.put_blob(bound['enrollment_id'],uid,data,digest)
            stage={'schema_version':'0.1.0','operation':'stage','request_id':str(uuid4()),'idempotency_key':str(uuid4()),'binding':bound,
                   'payload':{'files':body['files'],'manifest_digest':canonical_digest(body['files'])}}
            candidate=store.process(json.dumps(stage).encode(),uid)
            request={**stage,'operation':'publish','request_id':str(uuid4()),'idempotency_key':str(uuid4()),
                     'payload':{'candidate_id':candidate['candidate_id'],'candidate_digest':candidate['candidate_digest'],'verification_id':str(uuid4())}}
            raw=json.dumps(request).encode();keys=[];effects={};fault={'armed':False,'used':False}
            original=store._transaction
            @contextmanager
            def transaction():
                if fault['armed']:
                    fault['armed']=False;raise sqlite3.OperationalError('injected result save failure')
                with original() as db:yield db
            def backend(request,uid,key):
                keys.append(key)
                effects.setdefault(key,'c'*40)
                if not fault['used']:fault.update(armed=True,used=True)
                return {'status':'published','commit':effects[key],'published':True,'authorization':False,'trust_mode':'fixture'}
            broker=object.__new__(Broker)
            broker.store=mock.Mock(fixture_mode=False);broker.enrollments={bound['enrollment_id']:uid};broker.rpc_workflow=object()
            broker._dispatch=lambda data,peer_uid:store.fixture_adapter_call(data,peer_uid,backend)
            with mock.patch.object(store,'_transaction',transaction),mock.patch('p2_broker.kernel_peer',return_value={'uid':uid,'gid':uid,'pid':123}),mock.patch('p2_broker.read_frame',return_value=raw):
                first=broker.handle_socket(mock.Mock())
                self.assertEqual(first['status'],'unknown');self.assertIsNone(first['published'])
                self.assertEqual(first['error_code'],'adapter_result_not_recorded')
                second=broker.handle_socket(mock.Mock())
            self.assertEqual(second['status'],'published');self.assertEqual(second['commit'],'c'*40)
            self.assertEqual(len(effects),1);self.assertEqual(keys,[keys[0],keys[0]])
            store.close()

    def test_each_socket_activation_serves_only_one_request(self):
        for role,uid in [('verify',0),('publish',990)]:
            with self.subTest(role=role):
                listener=mock.Mock();listener.family=1;listener.getsockopt.return_value=1
                listener.getsockname.return_value=rpc.SOCKETS[role]
                connection=mock.MagicMock()
                listener.accept.side_effect=[(connection,None),AssertionError('second request accepted in old service budget')]
                config={'controller_uid':995,'publisher_uid':990}
                response={'backend_key':str(uuid4()),'result':{'status':'verified'}}
                with mock.patch.dict(os.environ,{'LISTEN_PID':str(os.getpid()),'LISTEN_FDS':'1'}),mock.patch.object(rpc.os,'geteuid',return_value=uid,create=True),mock.patch.object(rpc.os,'set_inheritable'),mock.patch.object(rpc.socket,'AF_UNIX',1,create=True),mock.patch.object(rpc.socket,'socket',return_value=listener),mock.patch.object(rpc,'_configuration',return_value=config),mock.patch.object(rpc,'peer',return_value={'uid':995,'pid':123,'gid':995}),mock.patch.object(rpc,'receive',return_value=json.dumps({'backend_key':response['backend_key']}).encode()),mock.patch.object(rpc,'dispatch',return_value=response),mock.patch('p2_broker.send_frame'):
                    rpc.serve(role)
                self.assertEqual(listener.accept.call_count,1);listener.close.assert_called_once()


if __name__=='__main__':unittest.main()
