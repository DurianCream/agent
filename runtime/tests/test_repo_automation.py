import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agentctl as a
import repoctl as r
import repo_automation as auto


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'framework'; self.root.mkdir()
        source = Path(a.__file__).resolve().parents[1]
        for name in ('shared', 'modules', 'core'):
            shutil.copytree(source / name, self.root / name)
        for name in ('AGENTS.md', 'registry.json'):
            shutil.copyfile(source / name, self.root / name)
        self.path = self.base / 'repo'; self.path.mkdir()
        self.remote = self.base / 'remote.git'
        subprocess.run(['git', 'init', '-q', '--bare', str(self.remote)], check=True)
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(self.path)], check=True)
        for key, value in [('user.name', 'Test'), ('user.email', 'test@example.invalid')]:
            r.git(self.path, 'config', key, value)
        r.register('sample', self.path, self.root)
        (self.path / 'seed.txt').write_text('seed')
        r.git(self.path, 'add', '--', 'seed.txt', '.agent-work/repository.json')
        r.git(self.path, 'commit', '-m', 'Initial')
        r.git(self.path, 'remote', 'add', 'origin', str(self.remote))
        r.git(self.path, 'push', '-u', 'origin', 'main')
        a.write_json(self.path / '.agent-work/automation.json', {
            'schema_version': '1.0.0', 'enabled': True, 'remote': 'origin',
            'expected_url': str(self.remote), 'branch': 'main'})
        a.init_task('coding', 'auto-task', 'Automated task', ['Persist and publish'], self.root)

    def bind(self):
        r.bind('sample', 'auto-task', self.root, scope={'project': 'test-project', 'service': 'test-service', 'environment': 'test', 'issue': 'publish'})

    def complete(self):
        a.transition('auto-task', 'running', self.root)
        output = self.root / 'outputs/auto-task/output.txt'; output.write_text('done')
        evidence = self.root / 'runs/auto-task/evidence/check.txt'; evidence.write_text('passed')
        file = self.root / 'runs/auto-task/result.json'
        result = a.read_json(file)
        result.update(status='completed', summary='Done', limitations=[], next_actions=[])
        result['artifacts'] = [{'path': 'outputs/auto-task/output.txt', 'description': 'Result', 'sha256': None}]
        result['verification'] = [{'id': 'check', 'name': 'Check', 'method': 'Test', 'outcome': 'passed',
                                   'evidence': ['runs/auto-task/evidence/check.txt'], 'notes': ''}]
        result['acceptance_criteria'][0]['verification_ids'] = ['check']
        a.write_json(file, result)
        a.submit('auto-task', self.root)

    def own_file(self, name='owned [literal].txt'):
        (self.path / name).write_text('owned', encoding='utf-8')
        auto.track('auto-task', [name], self.root)

    def test_real_publish_and_fresh_clone_startup(self):
        (self.path / 'unrelated.txt').write_text('existing')
        (self.path / 'owned l.txt').write_text('must not match bracket pathspec')
        self.bind(); self.own_file(); self.complete()
        result = auto.finish('auto-task', self.root)
        self.assertEqual(result['phase'], 'pushed')
        self.assertEqual(auto.remote_head(self.path, result['policy']), result['commit'])
        self.assertIsNone(r.git(self.path, 'cat-file', '-e', 'HEAD:unrelated.txt', optional=True))
        self.assertIsNone(r.git(self.path, 'cat-file', '-e', 'HEAD:owned l.txt', optional=True))
        self.assertEqual(auto.finish('auto-task', self.root)['commit'], result['commit'])
        clone = self.base / 'clone'
        subprocess.run(['git', 'clone', '-q', '-b', 'main', str(self.remote), str(clone)], check=True)
        clean_framework = self.base / 'new-framework'; clean_framework.mkdir()
        startup = auto.startup(root=clean_framework, cwd=clone, scope={'project': 'test-project', 'service': 'test-service', 'environment': 'test', 'issue': 'publish'})
        self.assertEqual(startup['context'][0]['task_id'], 'auto-task')
        self.assertIn('Do', startup['context'][0]['record']['result']['summary'])

    def test_preexisting_dirty_and_unrelated_staged_rejected(self):
        (self.path / 'preexisting.txt').write_text('existing')
        self.bind()
        with self.assertRaises(a.ContractError): auto.track('auto-task', ['preexisting.txt'], self.root)
        with self.assertRaises(a.ContractError): auto.track('auto-task', ['.env'], self.root)
        self.own_file(); self.complete()
        r.git(self.path, 'add', '--', 'preexisting.txt')
        with self.assertRaises(a.ContractError): auto.finish('auto-task', self.root)

    def test_push_failure_retries_same_commit(self):
        self.bind(); self.own_file(); self.complete()
        real_git = r.git
        def fail_push(path, *args, **kwargs):
            if args[0] == 'push': raise a.ContractError('Simulated network failure')
            return real_git(path, *args, **kwargs)
        with mock.patch.object(r, 'git', side_effect=fail_push):
            with self.assertRaises(a.ContractError): auto.finish('auto-task', self.root)
        receipt = a.read_json(self.root / 'runs/auto-task/publication.json')
        self.assertEqual(receipt['phase'], 'committed')
        self.assertEqual(auto.finish('auto-task', self.root)['commit'], receipt['commit'])

    def test_unrelated_local_commit_rejected(self):
        self.bind(); self.own_file(); self.complete()
        (self.path / 'unrelated-commit.txt').write_text('other work')
        r.git(self.path, 'add', '--', 'unrelated-commit.txt')
        r.git(self.path, 'commit', '-m', 'Unrelated local work')
        with self.assertRaises(a.ContractError): auto.finish('auto-task', self.root)

    def test_other_task_shared_index_change_rejected(self):
        self.bind(); self.own_file(); self.complete()
        file = self.path / '.agent-work/index.json'
        data = a.read_json(file)
        data['tasks']['another-task'] = {'status': 'partial', 'state': 'running', 'saved_at': a.now(),
                                        'summary': 'Other work', 'path': 'tasks/another-task/spec.md'}
        a.write_json(file, data)
        with self.assertRaises(a.ContractError): auto.finish('auto-task', self.root)
        self.assertEqual(auto.staged_paths(self.path), [])

    def test_remote_ahead_and_changed_destination_rejected(self):
        self.bind(); self.own_file(); self.complete()
        other = self.base / 'other'
        subprocess.run(['git', 'clone', '-q', '-b', 'main', str(self.remote), str(other)], check=True)
        r.git(other, 'config', 'user.name', 'Test'); r.git(other, 'config', 'user.email', 'test@example.invalid')
        (other / 'remote.txt').write_text('ahead')
        r.git(other, 'add', '--', 'remote.txt'); r.git(other, 'commit', '-m', 'Remote advance')
        r.git(other, 'push', 'origin', 'main')
        with self.assertRaises(a.ContractError): auto.finish('auto-task', self.root)
        self.assertEqual(auto.staged_paths(self.path), [])
        r.git(self.path, 'remote', 'set-url', '--push', 'origin', str(self.base / 'wrong.git'))
        with self.assertRaises(a.ContractError): auto.finish('auto-task', self.root)


if __name__ == '__main__': unittest.main()
