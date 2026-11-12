"""Recovery never rewrites originals and keeps normal P1 publication checks."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import agentctl as a
import control_gate as g
import repoctl as r
import repo_automation as auto
import task_recovery as recovery
import task_evidence
from test_control_gate import GateFixture

class RecoveryTests(GateFixture,unittest.TestCase):
    def before_initial_commit(self):
        a.write_json(self.root/task_evidence.CONFIG,task_evidence.POLICY)

    def compact_summary(self, task_id, evidence):
        name='.agent-work/tasks/'+task_id+'/evidence/summary.json'
        summary={'checks':[{'id':'fixture','result':'passed','command':'Recovery lifecycle fixture',
                           'metrics':{},'evidence':[{'path':evidence,'sha256':a.digest((self.root/evidence).read_bytes())}]}]}
        a.write_json(self.root/name,summary)
        a.write_json(self.root/('runs/'+task_id+'/evidence/summary.json'),summary)
        auto.track(task_id,[name],self.root)

    def successor(self, status='partial', cancelled=False):
        if task_evidence.enabled(self.root,a.read_json(self.run/'publication.json')):
            self.compact_summary('gate-task','runs/gate-task/evidence/check.txt')
        result=a.read_json(self.run/'result.json');result['status']=status;result['limitations']=['Incomplete']
        a.write_json(self.run/'result.json',result)
        if cancelled:
            a.transition('gate-task','cancelled',self.root)
            r.checkpoint('gate-task',self.root)
        else:
            a.submit('gate-task',self.root)
            r.checkpoint('gate-task',self.root)
        a.init_task('coding','followup','Follow up',['Verify recovery'],self.root)
        r.bind('sample','followup',self.root,scope={**self.profile['selector'],'issue':'gate'},new_task=True)
        a.transition('followup','running',self.root)
        folders=(self.run,self.root/'.agent-work/tasks/gate-task')
        self.originals={str(p.relative_to(self.root)):p.read_bytes() for folder in folders for p in folder.rglob('*') if p.is_file()}
        return self.root/'runs/followup'

    def test_transfer_requires_exact_hash_and_preserves_originals(self):
        target=self.successor()
        receipt=recovery.prepare('followup','gate-task',['product.txt'],self.root)
        self.assertEqual(receipt['kind'],'transfer')
        self.assertNotIn('receipts',receipt)
        self.assertFalse((self.root/'.agent-work/tasks/gate-task/recovery').exists())
        self.assertFalse((self.root/'.agent-work/tasks/followup/recovery').exists())
        for name,raw in self.originals.items(): self.assertEqual((self.root/name).read_bytes(),raw)
        current=g.candidate('followup',self.root)
        self.assertIn('product.txt',{e['path'] for e in current['candidate']['entries']})
        with self.assertRaisesRegex(a.ContractError,'test evidence missing'):
            g._proofs('followup',current,self.root)

    def test_wrong_hash_and_unowned_path_rejected(self):
        self.successor()
        (self.root/'product.txt').write_text('not original')
        with self.assertRaisesRegex(a.ContractError,'differs from original'):
            recovery.prepare('followup','gate-task',['product.txt'],self.root)
        with self.assertRaisesRegex(a.ContractError,'not original owned'):
            recovery.prepare('followup','gate-task',['unknown.txt'],self.root)

    def test_records_only_excludes_sources_and_pins_index(self):
        target=self.successor()
        receipt=recovery.prepare('followup','gate-task',root=self.root)
        pub=a.read_json(target/'publication.json')
        self.assertNotIn('product.txt',pub['paths'])
        with self.assertRaisesRegex(a.ContractError,'cannot track product'):
            auto.track('followup',['product.txt'],self.root)
        pub['paths'].append('product.txt')
        with self.assertRaisesRegex(a.ContractError,'contains product'):
            recovery.validate('followup',self.root,pub)

    def test_failed_and_cancelled_records_supported(self):
        self.successor('failed')
        self.assertEqual(recovery.prepare('followup','gate-task',root=self.root)['kind'],'records-only')

    def test_cancelled_records_supported(self):
        self.successor(cancelled=True)
        self.assertEqual(recovery.prepare('followup','gate-task',root=self.root)['kind'],'records-only')

    def test_source_record_tamper_blocks(self):
        target=self.successor()
        recovery.prepare('followup','gate-task',root=self.root)
        publication=a.read_json(target/'publication.json')
        folder=self.root/'.agent-work/tasks/gate-task'
        unexpected=folder/'unexpected.txt';unexpected.write_text('extra record')
        with self.assertRaisesRegex(a.ContractError,'exactly four files'):
            recovery.validate('followup',self.root,publication)
        unexpected.unlink()
        report=folder/'report.ko.md';original=report.read_bytes()
        report.write_bytes(b'x'*(task_evidence.POLICY['file_bytes']+1))
        with self.assertRaisesRegex(a.ContractError,'exceeds 65536'):
            recovery.validate('followup',self.root,publication)
        report.write_bytes(original)
        raw=self.run/'evidence/check.txt';original=raw.read_bytes();raw.write_text('changed raw evidence')
        with self.assertRaisesRegex(a.ContractError,'Submitted evidence was changed'):
            recovery.validate('followup',self.root,publication)
        raw.write_bytes(original)
        (self.root/'.agent-work/tasks/gate-task/report.ko.md').write_text('tampered')
        with self.assertRaisesRegex(a.ContractError,'records changed'):
            g.candidate('followup',self.root)

    def test_live_source_and_scope_mismatch_rejected(self):
        with self.assertRaisesRegex(a.ContractError,'closed incomplete'):
            recovery.closed('gate-task',self.root)
        target=self.successor()
        binding=a.read_json(target/'repository.json');binding['scope']['issue']='different'
        a.write_json(target/'repository.json',binding)
        with self.assertRaises(a.ContractError):recovery.prepare('followup','gate-task',root=self.root)

    def test_generated_source_entry_remains_pinned(self):
        target=self.successor()
        recovery.prepare('followup','gate-task',root=self.root)
        pub=a.read_json(target/'publication.json')
        self.assertEqual(recovery.validate('followup',self.root,pub), {'gate-task'})
        file=self.root/'.agent-work/tasks/gate-task/record.json'
        record=a.read_json(file);record['result']['summary']='tampered'
        a.write_json(file,record)
        with self.assertRaisesRegex(a.ContractError,'records changed'):
            recovery.validate('followup',self.root,pub)

    def test_candidate_file_tamper_cannot_replace_submitted_source(self):
        self.successor()
        original = (self.run/'task.json').read_bytes()
        (self.root/'product.txt').write_text('replacement candidate')
        file = self.run/'incomplete-candidate.json'
        saved = a.read_json(file)
        saved['candidate']['candidate']['entries'] = [g._reviewed_blob(self.root, 'product.txt')]
        for rewrite_digest in (False, True):
            if rewrite_digest:
                saved['candidate']['digest'] = g._hash(saved['candidate']['candidate'])
            a.write_json(file, saved)
            with self.assertRaisesRegex(a.ContractError,'submission anchor'):
                recovery.prepare('followup','gate-task',['product.txt'],self.root)
        self.assertEqual((self.run/'task.json').read_bytes(), original)


    def test_partial_submission_without_test_environment_keeps_file_anchor(self):
        for file in (self.root/'.venv-controls').rglob('*'):
            if file.is_file(): file.unlink()
        result=a.read_json(self.run/'result.json');result['status']='partial';result['limitations']=['Runner unavailable']
        a.write_json(self.run/'result.json',result)
        a.submit('gate-task',self.root)
        task=a.read_json(self.run/'task.json')
        saved=a.read_json(self.run/'incomplete-candidate.json')
        self.assertEqual(task['submission']['incomplete_candidate_sha256'],a.digest((self.run/'incomplete-candidate.json').read_bytes()))
        self.assertEqual(saved['candidate']['candidate']['entries'],[g._reviewed_blob(self.root,'product.txt')])
        self.assertEqual(saved['candidate']['candidate']['base_head'],a.read_json(self.run/'publication.json')['base_head'])

    def test_evidence_only_partial_submission_has_no_transfer_candidate(self):
        name='.agent-work/tasks/gate-task/evidence/note.txt'
        file=self.root/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text('Partial evidence')
        publication=a.read_json(self.run/'publication.json');publication['paths']=[name];a.write_json(self.run/'publication.json',publication)
        result=a.read_json(self.run/'result.json');result['status']='partial';result['limitations']=['No product work']
        a.write_json(self.run/'result.json',result)
        a.submit('gate-task',self.root)
        self.assertNotIn('incomplete_candidate_sha256',a.read_json(self.run/'task.json')['submission'])
        self.assertFalse((self.run/'incomplete-candidate.json').exists())


class RecoveryPublicationTests(RecoveryTests):
    # Run only the two additional end-to-end cases in this class.
    def before_initial_commit(self):
        import subprocess
        super().before_initial_commit()
        self.remote = self.root/'work/remote.git'
        self.remote.parent.mkdir(exist_ok=True)
        subprocess.run(['git','init','-q','--bare',str(self.remote)],check=True)
        r.git(self.root,'remote','set-url','origin',str(self.remote))
        policy=a.read_json(self.root/'.agent-work/automation.json');policy['expected_url']=str(self.remote)
        a.write_json(self.root/'.agent-work/automation.json',policy)

    def after_initial_commit(self):
        r.git(self.remote,'fetch',str(self.root),'refs/heads/main:refs/heads/main')

    def publish_successor(self, transfer=False, status='partial', cancelled=False):
        import io
        import subprocess
        from unittest import mock
        target=self.successor(status,cancelled)
        recovery.prepare('followup','gate-task',['product.txt'] if transfer else None,self.root)
        result=a.read_json(target/'result.json')
        evidence=target/'evidence/review.txt';evidence.write_text('Fixture independent evaluation evidence')
        self.compact_summary('followup','runs/followup/evidence/review.txt')
        result.update(status='completed',summary='Recovery verified',limitations=[],next_actions=[])
        artifact=self.root/'outputs/followup/recovery.txt';artifact.write_text('Recovery lifecycle fixture')
        result['artifacts']=[{'path':'outputs/followup/recovery.txt','description':'Recovery fixture result','sha256':None}]
        result['verification']=[{'id':'verified','name':'Recovery','method':'Real local lifecycle with stub test process','outcome':'passed','evidence':['runs/followup/evidence/review.txt'],'notes':'Runner output is fixture; actual Git commit and remote checks execute.'}]
        result['acceptance_criteria'][0]['verification_ids']=['verified']
        a.write_json(target/'result.json',result)
        class Process:
            stdout=io.BytesIO(b'Ran 1 test in 0.001s\n\nOK\n')
            def wait(self,timeout): return 0
            def kill(self): pass
        original=subprocess.Popen
        def dispatch(argv,**kw): return Process() if '.venv-controls' in argv[0] else original(argv,**kw)
        with mock.patch.object(g.subprocess,'Popen',side_effect=dispatch):
            g.run_tests('followup','unit',self.root)
        g.assess('followup',{'candidate_digest':g.candidate('followup',self.root)['digest'],'reviewer':{'subject':'independent','session':'independent-session'},'verdict':'accepted','evidence':['runs/followup/evidence/review.txt','outputs/followup/recovery.txt','runs/followup/evidence/summary.json']},self.root)
        a.submit('followup',self.root)
        published=auto.finish('followup',self.root)
        self.assertEqual(published['phase'],'pushed')
        self.assertEqual(auto.remote_head(self.root,published['policy']),published['commit'])
        actual=set(r.git(self.root,'diff-tree','--no-commit-id','--name-only','-r','-z',published['commit'],strip=False).split('\0'))-{''}
        self.assertEqual('product.txt' in actual,transfer)
        records={'.agent-work/tasks/'+task+'/'+name for task in ('gate-task','followup') for name in task_evidence.FILES}
        self.assertEqual(actual,records | ({'product.txt'} if transfer else set()))
        for task in ('gate-task','followup'):
            publication=a.read_json(self.root/('runs/'+task+'/publication.json'))
            task_evidence.validate(self.root,task,publication,commit=published['commit'])
        for name,raw in self.originals.items(): self.assertEqual((self.root/name).read_bytes(),raw)
        return published

    def test_publish_records_only_actual_commit_and_remote(self):
        self.publish_successor()
        for status,cancelled in (('failed',False),('partial',True)):
            with self.subTest(status=status,cancelled=cancelled):
                fixture=RecoveryPublicationTests('test_publish_records_only_actual_commit_and_remote')
                fixture.setUp()
                try: fixture.publish_successor(status=status,cancelled=cancelled)
                finally: fixture.doCleanups()

    def test_publish_transfer_actual_commit_and_remote(self):
        self.publish_successor(transfer=True)

# Inherited boundary cases already run in RecoveryTests; avoid duplicate fixture executions.
for _name in list(vars(RecoveryTests)):
    if _name.startswith('test_'):
        setattr(RecoveryPublicationTests,_name,None)


class RecoveryIndexEnvelopeTests(unittest.TestCase):
    def test_generated_index_ignores_cache_and_rejects_record_identity_mismatch(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            file=root/'.agent-work/tasks/task/record.json';file.parent.mkdir(parents=True)
            a.write_json(root/'.agent-work/index.json', {'payload':'unreviewed'})
            record={'task_id':'task','task_state':'submitted','saved_at':'fixed','result':{'status':'partial','summary':'saved'}}
            a.write_json(file,record)
            index=r.generated_index(root)
            self.assertEqual(set(index), {'schema_version','tasks'})
            self.assertEqual(index['tasks']['task'], {'status':'partial','state':'submitted','saved_at':'fixed','summary':'saved','path':'tasks/task/spec.md'})
            record['task_id']='wrong';a.write_json(file,record)
            with self.assertRaisesRegex(a.ContractError,'identity mismatch'):
                r.generated_index(root)
