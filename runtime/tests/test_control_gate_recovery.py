"""Incomplete work closes through its own records; a transfer never rewrites the source."""
import copy
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock
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

    def incomplete(self, status='partial'):
        self.compact_summary('gate-task','runs/gate-task/evidence/check.txt')
        result=a.read_json(self.run/'result.json')
        if status!='completed':
            result['status']=status;result['limitations']=['Incomplete']
        a.write_json(self.run/'result.json',result)

    def followup(self):
        a.init_task('coding','followup','Follow up',['Verify recovery'],self.root)
        r.bind('sample','followup',self.root,scope={**self.profile['selector'],'issue':'gate'},new_task=True)
        a.transition('followup','running',self.root)
        folders=(self.run,self.root/'.agent-work/tasks/gate-task')
        self.originals={str(p.relative_to(self.root)):p.read_bytes() for folder in folders for p in folder.rglob('*') if p.is_file()}
        return self.root/'runs/followup'

    def successor(self):
        self.incomplete()
        a.submit('gate-task',self.root)
        r.checkpoint('gate-task',self.root)
        return self.followup()

    def make_legacy(self):
        """Re-enroll under an older version with its removed profile block, consistently in all three places."""
        value={**a.read_json(self.run/'controls.json'),'schema_version':'0.3.0','submission_profile':{'schema_version':'0.1.0'}}
        a.write_json(self.run/'controls.json',value)
        a.write_json(self.root/'runs/control-enrollments/gate-task.json',{'digest':g._hash(value),'enrollment':value})
        a.write_json(self.run/'task.json',{**a.read_json(self.run/'task.json'),'control_enrollment':g._hash(value)})
        # The standing configuration moved on since that enrollment.
        a.write_json(self.root/g.CONFIG,{**self.profile,'timeout_seconds':20})

    def test_transfer_requires_exact_hash_and_preserves_originals(self):
        self.successor()
        receipt=recovery.prepare('followup','gate-task',['product.txt'],self.root)
        self.assertEqual((receipt['kind'],set(receipt['anchor'])),('transfer',{'result_sha256','incomplete_candidate_sha256'}))
        publication=a.read_json(self.root/'runs/followup/publication.json')
        self.assertEqual(publication['paths'],['product.txt'])  # The source keeps its own records.
        for name,raw in self.originals.items(): self.assertEqual((self.root/name).read_bytes(),raw)
        a.init_task('coding','second','Second',['Verify recovery'],self.root)
        r.bind('sample','second',self.root,scope={**self.profile['selector'],'issue':'gate'},new_task=True)
        a.transition('second','running',self.root)
        with self.assertRaisesRegex(a.ContractError,'already transferred'):
            recovery.prepare('second','gate-task',['product.txt'],self.root)
        # Continuing the file is the point of a transfer; it must pass the successor's own gate.
        (self.root/'product.txt').write_text('continued\n')
        self.assertEqual(recovery.validate('followup',self.root,publication),{'gate-task'})
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

    def test_live_source_and_scope_mismatch_rejected(self):
        with self.assertRaisesRegex(a.ContractError,'Only submitted partial'):
            recovery.anchor('gate-task',self.root)
        target=self.successor()
        binding=a.read_json(target/'repository.json');binding['scope']['issue']='different'
        a.write_json(target/'repository.json',binding)
        with self.assertRaises(a.ContractError):recovery.prepare('followup','gate-task',['product.txt'],self.root)

    def test_source_submission_change_blocks_transferred_successor(self):
        target=self.successor()
        recovery.prepare('followup','gate-task',['product.txt'],self.root)
        publication=a.read_json(target/'publication.json')
        old={**publication,'recovery':{**publication['recovery'],'kind':'records-only'}}
        with self.assertRaisesRegex(a.ContractError,'Unsupported recovery manifest'):
            recovery.validate('followup',self.root,old)
        task=a.read_json(self.run/'task.json');task['submission']['result_sha256']='0'*64
        a.write_json(self.run/'task.json',task)
        with self.assertRaises(a.ContractError):
            g.candidate('followup',self.root)

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

    def test_legacy_enrollment_loads_only_to_close_records(self):
        self.incomplete()
        self.make_legacy()
        a.load_task('gate-task',self.root)  # The loader no longer rejects it before it can be closed.
        with self.assertRaisesRegex(a.ContractError,'start a new task'):
            g.candidate('gate-task',self.root)
        self.review(kind='records',extra=('runs/gate-task/evidence/summary.json',))
        self.assertEqual(g.check_submission('gate-task',self.root,publish=True)['publication_kind'],'records')
        # A legacy enrollment cannot claim completion, and damage is still damage.
        result=a.read_json(self.run/'result.json');result.update(status='completed',limitations=[])
        with self.assertRaisesRegex(a.ContractError,'start a new task'):
            g.check_submission('gate-task',self.root,result=result)
        ledger=self.root/'runs/control-enrollments/gate-task.json';saved=ledger.read_bytes()
        ledger.unlink()
        with self.assertRaisesRegex(a.ContractError,'missing or downgraded'):
            a.load_task('gate-task',self.root)
        ledger.write_bytes(saved)
        a.write_json(self.run/'controls.json',{**a.read_json(self.run/'controls.json'),'nonce':'changed'})
        with self.assertRaisesRegex(a.ContractError,'differs from local ledger'):
            a.load_task('gate-task',self.root)

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
    # Run only the additional end-to-end cases in this class.
    def before_initial_commit(self):
        super().before_initial_commit()
        self.remote = self.root/'work/remote.git'
        self.remote.parent.mkdir(exist_ok=True)
        subprocess.run(['git','init','-q','--bare',str(self.remote)],check=True)
        r.git(self.root,'remote','set-url','origin',str(self.remote))
        policy=a.read_json(self.root/'.agent-work/automation.json');policy['expected_url']=str(self.remote)
        a.write_json(self.root/'.agent-work/automation.json',policy)

    def after_initial_commit(self):
        r.git(self.remote,'fetch',str(self.root),'refs/heads/main:refs/heads/main')

    def advance_remote(self, name):
        """Another checkout pushes first; this checkout does not have that commit."""
        other=self.root/'work/other'
        subprocess.run(['git','clone','-q','-b','main',str(self.remote),str(other)],check=True)
        r.git(other,'config','user.name','Other');r.git(other,'config','user.email','other@example.invalid')
        file=other/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text('remote work')
        r.git(other,'add','-f','--',name);r.git(other,'commit','-q','-m','Remote advance');r.git(other,'push','-q','origin','main')
        return r.git(other,'rev-parse','HEAD')

    def changed(self, commit):
        return set(r.git(self.root,'diff-tree','--no-commit-id','--name-only','-r','-z',commit,strip=False).split('\0'))-{''}

    def close(self, close, status='partial', legacy=False, advance=None):
        base=r.git(self.root,'rev-parse','HEAD')
        if status=='completed':  # Completed without product: nothing owned but the records.
            publication=a.read_json(self.run/'publication.json');publication['paths']=[]
            a.write_json(self.run/'publication.json',publication)
        self.incomplete(status)
        if legacy: self.make_legacy()
        if status=='completed': self.execute()
        with self.assertRaisesRegex(a.ContractError,'review missing'):
            auto.finish('gate-task',self.root,close=close)
        self.review(kind='records',extra=('runs/gate-task/evidence/summary.json',))
        tip=self.advance_remote(advance) if advance else base
        if advance and advance.startswith('.agent-work/tasks/gate-task/'):
            with self.assertRaisesRegex(a.ContractError,'records changed on the remote'):
                auto.finish('gate-task',self.root,close=close)
            self.assertEqual(a.read_json(self.run/'publication.json')['phase'],'begun')
            self.assertEqual(a.read_json(self.run/'task.json')['state'],'running')
            return None
        published=auto.finish('gate-task',self.root,close=close)
        commit=published['commit']
        self.assertEqual((published['phase'],published['kind'],published['parent']),('pushed','records',tip))
        self.assertEqual(auto.remote_head(self.root,published['policy']),commit)
        self.assertEqual(self.changed(commit),{'.agent-work/tasks/gate-task/'+name for name in task_evidence.FILES})
        # Unfinished product is neither published nor disturbed.
        self.assertEqual((self.root/'product.txt').read_text(),'after\n')
        self.assertEqual(r.git(self.root,'show',base+':product.txt'),'before')
        self.assertEqual(r.git(self.root,'show',commit+':product.txt'),'before')
        self.assertEqual(published['mode'],'remote-only' if advance else 'local-update')
        self.assertEqual(r.git(self.root,'rev-parse','HEAD'),base if advance else commit)
        self.assertEqual('notice' in published,bool(advance))
        self.assertEqual(auto.staged_paths(self.root),[])
        record=json.loads(r.git(self.root,'show',commit+':.agent-work/tasks/gate-task/record.json'))
        state='cancelled' if close=='cancelled' else 'submitted'
        self.assertEqual((record['task_state'],record['result']['status'],a.read_json(self.run/'task.json')['state']),(state,status,state))
        self.assertEqual((record['assessment']['publication_kind'],record['assessment']['verdict'],record['assessment']['reviewer']['subject']),
                         ('records','accepted','reviewer'))
        self.assertEqual(a.digest((self.root/record['assessment']['record']).read_bytes()),record['assessment']['sha256'])
        self.assertEqual((self.run/'incomplete-candidate.json').exists(),close=='partial')
        self.assertEqual(auto.finish('gate-task',self.root)['commit'],commit)
        with self.assertRaisesRegex(a.ContractError,'another --close'):
            auto.finish('gate-task',self.root,close='failed' if close!='failed' else 'partial')
        return published

    def test_close_publishes_own_records_actual_commit_and_remote(self):
        self.close('partial')
        for case in (dict(close='failed',status='failed',advance='remote.txt'),
                     dict(close='cancelled',legacy=True,advance='remote.txt'),
                     dict(close=None,status='completed'),
                     dict(close='partial',advance='.agent-work/tasks/gate-task/foreign.txt')):
            with self.subTest(**case):
                fixture=RecoveryPublicationTests('test_close_publishes_own_records_actual_commit_and_remote')
                fixture.setUp()
                try: fixture.close(**case)
                finally: fixture.doCleanups()

    def test_transfer_after_source_published_its_records(self):
        source=self.close('partial')
        target=self.followup()
        recovery.prepare('followup','gate-task',['product.txt'],self.root)
        (self.root/'product.txt').write_text('finished\n')
        # The source's saved publication still verifies after the successor continues its file.
        self.assertEqual(auto.finish('gate-task',self.root)['commit'],source['commit'])
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
        review={'kind':'records','candidate_digest':g.candidate('followup',self.root)['digest'],'reviewer':{'subject':'independent','session':'independent-session'},'verdict':'accepted','evidence':['runs/followup/evidence/review.txt','outputs/followup/recovery.txt','runs/followup/evidence/summary.json']}
        with self.assertRaisesRegex(a.ContractError,'differs from the publication kind'):
            g.assess('followup',review,self.root)
        forged=g.assess('followup',{**review,'kind':'product'},self.root)
        file=target/'gates'/forged['record'];accepted=file.read_bytes()
        a.write_json(file,{**a.read_json(file),'publication_kind':'records'})
        with self.assertRaisesRegex(a.ContractError,'another publication kind'):  # A records review cannot publish product.
            auto.finish('followup',self.root)
        file.write_bytes(accepted)
        published=auto.finish('followup',self.root)
        self.assertEqual((published['phase'],published['kind'],published['parent']),('pushed','product',source['commit']))
        self.assertEqual(auto.remote_head(self.root,published['policy']),published['commit'])
        self.assertEqual(self.changed(published['commit']),{'product.txt'}|{'.agent-work/tasks/followup/'+name for name in task_evidence.FILES})
        for name,raw in self.originals.items(): self.assertEqual((self.root/name).read_bytes(),raw)

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
