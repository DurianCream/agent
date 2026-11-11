"""Selection boundaries use real Git baselines and production enrollment/selection."""
import copy
import json
import sys
import time
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import agentctl as a
import control_gate as g
import impact_tests as impact
import repoctl as r
import repo_automation as auto
import submission_profile as sp
from test_control_gate import GateFixture

class ImpactTests(GateFixture, unittest.TestCase):
    def before_initial_commit(self):
        source = Path(a.__file__).resolve().parents[1]
        a.write_json(self.root / impact.CONFIG, a.read_json(source / impact.CONFIG))
        (self.root/'docs').mkdir()
        (self.root/'docs/guide.md').write_text('Before\n')
        (self.root/'runtime').mkdir(exist_ok=True)
        (self.root/'runtime/context_checkpoint.py').write_text('before\n')
        (self.root/'runtime/agentctl.py').write_text('before\n')
        (self.root/'unknown.txt').write_text('before\n')
        for module in ('p2_contracts', 'p2_store', 'p2_verifier', 'p2_rpc', 'p2_broker', 'p2_executor', 'p2_publisher', 'control_policy', 'legacy_memory'):
            (self.root/('runtime/'+module+'.py')).write_text('before\n')

    def selection(self, names):
        publication = a.read_json(self.run/'publication.json')
        publication['paths'] = names
        a.write_json(self.run/'publication.json', publication)
        for name in names:
            if name != impact.CONFIG:
                p=self.root/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_text('changed\n')
        current = g.candidate('gate-task',self.root)
        start=time.perf_counter()
        selected=g.impact_selection('gate-task',current,g.check_enrollment('gate-task',self.root),self.root)
        print('IMPACT_EXAMPLE '+json.dumps({'paths':names,'suites':[s['id'] for s in selected['suites']],'selection_seconds':time.perf_counter()-start}))
        return selected

    def test_document_selects_fast(self):
        self.assertEqual([s['id'] for s in self.selection(['docs/guide.md'])['suites']],['impact-document-integrity'])

    def test_module_selects_exact_tests(self):
        self.assertEqual([s['id'] for s in self.selection(['runtime/context_checkpoint.py'])['suites']],['context-checkpoint'])

    def test_mixed_scopes_union(self):
        self.assertEqual({s['id'] for s in self.selection(['docs/guide.md','runtime/context_checkpoint.py'])['suites']},{'impact-document-integrity','context-checkpoint'})

    def test_new_document_unmapped_deleted_shared_and_mapping_force_full(self):
        for names in [['docs/new.md'],['unknown.txt'],['runtime/agentctl.py'],[impact.CONFIG]]:
            with self.subTest(names=names):
                self.assertEqual(self.selection(names)['mode'],'full')
        self.selection(['docs/guide.md'])
        (self.root/'docs/guide.md').unlink()
        self.assertEqual(g.impact_selection('gate-task',g.candidate('gate-task',self.root),g.check_enrollment('gate-task',self.root),self.root)['mode'],'full')

    def test_protected_mapping_override_cannot_skip_full(self):
        self.assertEqual(self.selection(['runtime/agentctl.py'])['mode'],'full')

    def test_manual_full_is_irreversible(self):
        self.selection(['docs/guide.md'])
        sp.promote('gate-task','Periodic release full regression',self.root)
        self.assertEqual(g.impact_selection('gate-task',g.candidate('gate-task',self.root),g.check_enrollment('gate-task',self.root),self.root)['mode'],'full')
        with self.assertRaises(a.ContractError):
            sp.promote('gate-task','Cannot downgrade or reset',self.root)

    def test_missing_impact_review_rejected(self):
        current=g.candidate('gate-task',self.root)
        with self.assertRaisesRegex(a.ContractError,'Impact review'):
            g.assess('gate-task',{'candidate_digest':current['digest'],'reviewer':{'subject':'reviewer','session':'review'},'verdict':'accepted','evidence':['runs/gate-task/evidence/check.txt']},self.root)

    def test_uncommitted_policy_does_not_enable_legacy(self):
        enrollment=g.check_enrollment('gate-task',self.root)
        legacy=copy.deepcopy(enrollment); legacy.pop('impact_tests')
        self.assertEqual(impact.select(g.candidate('gate-task',self.root),legacy,self.root)['reasons'][0]['reason'],'legacy enrollment')

    def test_unowned_dependency_forces_full(self):
        self.selection(['docs/guide.md'])
        (self.root/'runtime/context_checkpoint.py').write_text('unowned change\n')
        self.assertEqual(g.impact_selection('gate-task',g.candidate('gate-task',self.root),g.check_enrollment('gate-task',self.root),self.root)['mode'],'full')

    def test_selected_execution_and_independent_review_are_bound(self):
        import io
        import subprocess
        from unittest import mock
        self.selection(['docs/guide.md'])
        class Process:
            stdout=io.BytesIO(b'Ran 4 tests in 0.001s\n\nOK\n')
            def wait(self,timeout): return 0
            def kill(self): pass
        original=subprocess.Popen
        def dispatch(argv,**kw):return Process() if '.venv-controls' in argv[0] else original(argv,**kw)
        with mock.patch.object(g.subprocess,'Popen',side_effect=dispatch):
            test=g.run_tests('gate-task','impact-document-integrity',self.root)
        self.assertEqual(test['impact_selection']['mode'],'impact')
        current=g.candidate('gate-task',self.root)
        selection=g.impact_selection('gate-task',current,g.check_enrollment('gate-task',self.root),self.root)
        value={'candidate_digest':current['digest'],'reviewer':{'subject':'reviewer','session':'review'},'verdict':'accepted',
               'evidence':['outputs/gate-task/artifact.txt','runs/gate-task/evidence/check.txt'],
               'impact_digest':g._hash(selection),'impact_review':{'docs/guide.md':'Verified only existing documentation changed.'}}
        g.assess('gate-task',value,self.root)
        self.assertEqual(g.check_submission('gate-task',self.root)['status'],'passed')
        with self.assertRaisesRegex(a.ContractError,'Unknown mandatory'):
            g.run_tests('gate-task','unit',self.root)
        value['impact_review']={}
        with self.assertRaisesRegex(a.ContractError,'every owned path'):
            g.assess('gate-task',value,self.root)

    def test_shared_runtime_cluster_overrides_specific_suite_mapping(self):
        for module in ('p2_contracts', 'p2_store', 'p2_verifier', 'p2_rpc', 'p2_broker', 'p2_executor', 'p2_publisher', 'control_policy', 'legacy_memory'):
            name = 'runtime/' + module + '.py'
            with self.subTest(module=module):
                selected = self.selection([name])
                reason = next(r for r in selected['reasons'] if r['path'] == name)
                self.assertEqual(reason['reason'], 'protected or shared runtime path')
                self.assertEqual(selected['mode'], 'full')
                (self.root/name).write_text('before\n')
