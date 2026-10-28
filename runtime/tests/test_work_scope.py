import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agentctl as a
import repoctl as r
import repo_automation as auto
import test_repoctl as fixtures


class WorkScopeTests(unittest.TestCase):
    def setUp(self):
        fixtures.RepositoryMemoryTests.setUp(self)
        self.scope = {'project': 'project-a', 'service': 'vpn', 'environment': 'production', 'issue': 'incident-one'}

    def save(self, task_id, scope, sentinel):
        if task_id != 'sample-task':
            a.init_task('coding', task_id, 'Scoped work', ['Record correctly'], self.root)
        file = self.root / 'runs' / task_id / 'result.json'
        result = a.read_json(file); result['summary'] = sentinel
        a.write_json(file, result)
        r.bind('sample', task_id, self.root, scope=scope)

    def test_exact_scope_isolates_every_dimension_and_loads_all_matches(self):
        self.save('sample-task', self.scope, 'MATCHED-CONTENT')
        for field in r.SCOPE_FIELDS:
            self.save('other-' + field, {**self.scope, field: 'other-value'}, 'EXCLUDED-' + field)
        for number in range(4):
            self.save('matching-' + str(number), self.scope, 'MATCH-' + str(number))
        data = auto.startup('sample', root=self.root, scope=self.scope)
        self.assertEqual(len(data['context']), 5)
        text = json.dumps(data)
        self.assertIn('MATCHED-CONTENT', text)
        self.assertNotIn('EXCLUDED-', text)
        self.assertEqual(len(data['index']), 5)
        report = (self.path / '.agent-work/tasks/sample-task/report.ko.md').read_text(encoding='utf-8')
        self.assertIn('환경: production', report)
        self.assertIn('프로젝트: project-a', report)

    def test_unscoped_and_partial_startup_never_include_record_bodies(self):
        self.save('sample-task', self.scope, 'PRIVATE-BODY-SENTINEL')
        for scope in (None, {'project': 'project-a'}, {k: v for k, v in self.scope.items() if k != 'environment'}):
            data = auto.startup('sample', root=self.root, scope=scope)
            self.assertEqual(data['context'], [])
            self.assertNotIn('PRIVATE-BODY-SENTINEL', json.dumps(data))
        data = auto.startup('sample', 'sample-task', self.root, scope={'project': 'project-a'})
        self.assertEqual(data['context'], [])
        self.assertNotIn('PRIVATE-BODY-SENTINEL', json.dumps(r.resume('sample', root=self.root)))

    def test_explicit_task_scope_mismatch_and_legacy_isolation(self):
        self.save('sample-task', None, 'LEGACY-BODY')
        self.assertEqual(auto.startup('sample', root=self.root, scope=self.scope)['context'], [])
        explicit = auto.startup('sample', 'sample-task', self.root)
        self.assertTrue(explicit['context'][0]['legacy_unscoped'])
        with self.assertRaises(a.ContractError): auto.startup('sample', 'sample-task', self.root, scope=self.scope)
        r.set_scope('sample-task', self.scope, self.root)
        with self.assertRaises(a.ContractError): r.resume('sample', 'sample-task', self.root, scope={**self.scope, 'issue': 'other'})

    def test_scope_is_immutable_and_closed_legacy_not_migrated(self):
        self.save('sample-task', self.scope, 'SCOPE')
        with self.assertRaises(a.ContractError): r.set_scope('sample-task', {**self.scope, 'environment': 'development'}, self.root)
        self.save('legacy-task', None, 'LEGACY')
        a.transition('legacy-task', 'cancelled', self.root)
        with self.assertRaises(a.ContractError): r.set_scope('legacy-task', self.scope, self.root)

    def test_malformed_scope_fails_closed_even_without_query(self):
        self.save('sample-task', self.scope, 'DO-NOT-LOAD')
        file = self.path / '.agent-work/tasks/sample-task/record.json'
        data = a.read_json(file); data['scope'] = {'project': 'project-a'}
        a.write_json(file, data)
        with self.assertRaises(a.ContractError): auto.startup('sample', root=self.root)
        with self.assertRaises(a.ContractError): r.resume('sample', 'sample-task', self.root)

    def test_cli_requires_complete_scope_before_creating_bound_task(self):
        (self.root / 'runtime').mkdir(exist_ok=True)
        for name in ('agentctl.py', 'repoctl.py'):
            shutil.copyfile(Path(a.__file__).parent / name, self.root / 'runtime' / name)
        command = [sys.executable, str(self.root / 'runtime/agentctl.py'), 'init', '--repo', 'sample',
                   '--module', 'coding', '--task', 'missing-scope', '--objective', 'Scope', '--criterion', 'Required']
        for extra in ([], ['--project', 'project-a', '--service', 'vpn', '--issue', 'one']):
            proc = subprocess.run(command + extra, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(proc.returncode, 1)
            self.assertFalse((self.root / 'runs/missing-scope').exists())

    def test_direct_resume_rejects_repository_id_mismatch(self):
        self.save('sample-task', self.scope, 'WRONG-REPOSITORY')
        file = self.path / '.agent-work/tasks/sample-task/record.json'
        data = a.read_json(file); data['repository_id'] = 'another-repository'
        a.write_json(file, data)
        with self.assertRaises(a.ContractError): r.resume('sample', 'sample-task', self.root)

    def test_record_scope_cannot_reclassify_existing_specification(self):
        self.save('sample-task', self.scope, 'WRONG-SCOPE-CONTENT')
        file = self.path / '.agent-work/tasks/sample-task/record.json'
        data = a.read_json(file)
        changed_scope = {**self.scope, 'environment': 'development'}
        data['scope'] = changed_scope
        a.write_json(file, data)
        with self.assertRaises(a.ContractError): r.resume('sample', 'sample-task', self.root, scope=changed_scope)
        with self.assertRaises(a.ContractError): auto.startup('sample', root=self.root, scope=changed_scope)

    def test_scope_restores_in_fresh_process(self):
        self.save('sample-task', self.scope, 'RESTORED-SCOPE-CONTENT')
        code = "import json,pathlib,repo_automation,sys; print(json.dumps(repo_automation.startup('sample',root=pathlib.Path(sys.argv[1]),scope=json.loads(sys.argv[2]))))"
        proc = subprocess.run([sys.executable, '-c', code, str(self.root), json.dumps(self.scope)],
                              cwd=Path(a.__file__).parent, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('RESTORED-SCOPE-CONTENT', proc.stdout)


if __name__ == '__main__': unittest.main()
