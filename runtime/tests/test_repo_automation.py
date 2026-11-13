import json
import os
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
        # Seed the bare fixture by fetching objects/refs; no receive hooks are needed.
        r.git(self.remote, 'fetch', str(self.path), 'refs/heads/main:refs/heads/main')
        a.write_json(self.path / '.agent-work/automation.json', {
            'schema_version': '1.0.0', 'enabled': True, 'remote': 'origin',
            'expected_url': str(self.remote), 'branch': 'main'})
        a.init_task('coding', 'auto-task', 'Automated task', ['Persist and publish'], self.root)

    def bind(self):
        r.bind('sample', 'auto-task', self.root, scope={'project': 'test-project', 'service': 'test-service', 'environment': 'test', 'issue': 'publish'})

    def complete(self, submit=True):
        if a.read_json(self.root / 'runs/auto-task/task.json')['state'] != 'running':
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
        if submit:
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
        self.assertEqual(receipt['phase'], 'indexed')
        self.assertEqual(auto.finish('auto-task', self.root)['commit'], receipt['commit'])

    def test_unrelated_local_commit_rejected(self):
        self.bind(); self.own_file(); self.complete()
        (self.path / 'unrelated-commit.txt').write_text('other work')
        r.git(self.path, 'add', '--', 'unrelated-commit.txt')
        r.git(self.path, 'commit', '-m', 'Unrelated local work')
        with self.assertRaises(a.ContractError): auto.finish('auto-task', self.root)

    def test_generated_index_is_local_and_deterministic(self):
        self.bind(); self.own_file(); self.complete()
        expected = r.generated_index(self.path)
        self.assertEqual(expected, r.write_index(self.path))
        self.assertEqual(expected, r.generated_index(self.path))
        (self.path / '.agent-work/index.json').write_text('stale cache')
        result = auto.finish('auto-task', self.root)
        self.assertEqual(result['phase'], 'pushed')
        for name in ('index.json', 'INDEX.md'):
            self.assertIsNone(r.git(self.path, 'cat-file', '-e', 'HEAD:.agent-work/' + name, optional=True))

    def test_closed_partial_does_not_block_next_publication(self):
        self.bind()
        a.transition('auto-task', 'running', self.root)
        result_file = self.root / 'runs/auto-task/result.json'
        result = a.read_json(result_file); result['status'] = 'partial'
        a.write_json(result_file, result)
        a.submit('auto-task', self.root)
        preserved = (self.path / '.agent-work/tasks/auto-task/record.json').read_bytes()
        a.init_task('coding', 'next-task', 'Next task', ['Publish'], self.root)
        r.bind('sample', 'next-task', self.root, scope={'project':'test-project','service':'test-service','environment':'test','issue':'next'})
        a.transition('next-task', 'running', self.root)
        result = a.read_json(self.root / 'runs/next-task/result.json')
        output = self.root / 'outputs/next-task/done.txt'; output.write_text('done')
        evidence = self.root / 'runs/next-task/evidence/check.txt'; evidence.write_text('passed')
        result.update(status='completed', summary='Done', limitations=[], next_actions=[])
        result['artifacts'] = [{'path':'outputs/next-task/done.txt','description':'Result','sha256':None}]
        result['verification'] = [{'id':'check','name':'Check','method':'Local lifecycle','outcome':'passed','evidence':['runs/next-task/evidence/check.txt'],'notes':''}]
        result['acceptance_criteria'][0]['verification_ids'] = ['check']
        a.write_json(self.root / 'runs/next-task/result.json', result)
        a.submit('next-task', self.root)
        published = auto.finish('next-task', self.root)
        self.assertEqual(published['phase'], 'pushed')
        self.assertEqual(auto.remote_head(self.path, published['policy']), published['commit'])
        self.assertEqual((self.path / '.agent-work/tasks/auto-task/record.json').read_bytes(), preserved)

    def test_interrupted_phases_resume_to_one_commit(self):
        """Stop after each saved phase, disturb the checkout, then resume from saved bytes."""
        real_update = auto._update_ref
        def update_then_crash(*args):
            real_update(*args)
            raise a.ContractError('crash after ref update')
        stops = {'prepared': ('_install', a.ContractError('stop')),
                 'submitted': ('_update_ref', update_then_crash),
                 'committed': ('_sync_index', a.ContractError('stop'))}
        for phase, (name, effect) in stops.items():
            with self.subTest(phase=phase):
                fixture = AutomationTests('test_interrupted_phases_resume_to_one_commit')
                fixture.setUp()
                try:
                    fixture.resume_after(phase, name, effect)
                finally:
                    fixture.doCleanups()

    def resume_after(self, phase, name, effect):
        (self.path / 'unrelated.txt').write_text('user work')
        self.bind(); self.own_file('a[1].txt'); self.own_file('owned l.txt')
        a.transition('auto-task', 'running', self.root)
        (self.path / 'owned l.txt').unlink()  # Owned, then reverted: not in the commit.
        self.complete_running()
        with mock.patch.object(auto, name, side_effect=effect):
            with self.assertRaises(a.ContractError): auto.finish('auto-task', self.root)
        saved = a.read_json(self.root / 'runs/auto-task/publication.json')
        self.assertEqual(saved['phase'], phase)
        evidence = self.root / 'runs/auto-task/evidence/check.txt'
        evidence.write_text('changed after review')
        with self.assertRaisesRegex(a.ContractError, 'changed'): auto.finish('auto-task', self.root)
        evidence.write_text('passed')
        if phase == 'prepared':
            r.git(self.path, 'add', '--', 'unrelated.txt')
            with self.assertRaisesRegex(a.ContractError, 'staged'): auto.finish('auto-task', self.root)
            r.git(self.path, 'rm', '-q', '--cached', '--', 'unrelated.txt')
        published = auto.finish('auto-task', self.root)
        self.assertEqual((published['phase'], published['commit']), ('pushed', saved['commit']))
        self.assertEqual(auto.remote_head(self.path, published['policy']), saved['commit'])
        self.assertEqual(r.git(self.path, 'rev-parse', 'HEAD'), saved['commit'])
        self.assertEqual(auto.staged_paths(self.path), [])
        self.assertEqual(r.git(self.path, 'status', '--porcelain', '--', 'unrelated.txt'), '?? unrelated.txt')
        names = set(r.git(self.path, 'diff-tree', '--no-commit-id', '--name-only', '-r', '-z',
                          saved['commit'], strip=False).split('\0')) - {''}
        self.assertIn('a[1].txt', names)
        self.assertNotIn('owned l.txt', names)
        self.assertEqual(a.read_json(self.root / 'runs/auto-task/task.json')['state'], 'submitted')

    def complete_running(self):
        """Finish submits a running task itself."""
        AutomationTests.complete(self, submit=False)

    def test_pushed_publication_rejects_moved_remote_or_local(self):
        self.bind(); self.own_file(); self.complete()
        published = auto.finish('auto-task', self.root)
        r.git(self.path, 'update-ref', 'refs/heads/main', published['base_head'], published['commit'])
        with self.assertRaisesRegex(a.ContractError, 'Local branch moved'): auto.finish('auto-task', self.root)
        r.git(self.path, 'update-ref', 'refs/heads/main', published['commit'], published['base_head'])
        r.git(self.path, 'push', '-q', '--force', 'origin', published['base_head'] + ':refs/heads/main')
        with self.assertRaisesRegex(a.ContractError, 'Remote'): auto.finish('auto-task', self.root)

    def test_lock_owner_states_and_unlock(self):
        self.bind()
        lock = self.path / '.agent-work/publication.lock'
        child = subprocess.run([sys.executable, '-c', 'import os; print(os.getpid())'], capture_output=True, text=True, check=True)
        own = a.process_start(os.getpid())
        cases = [({'pid': os.getpid(), 'start': own}, 'alive'),
                 ({'pid': os.getpid(), 'start': 'reused'}, 'dead'),
                 ({'pid': int(child.stdout), 'start': None}, 'dead'),
                 ('', 'incomplete')]
        for content, expected in cases:
            with self.subTest(expected=expected):
                lock.write_text(content if type(content) is str else json.dumps(content), encoding='utf-8')
                self.assertEqual(a.lock_state(lock), expected)
                with self.assertRaisesRegex(a.ContractError, 'Another operation holds'):
                    auto.finish('auto-task', self.root)
                if expected in ('alive', 'incomplete'):
                    with self.assertRaisesRegex(a.ContractError, 'may still be running'):
                        auto.unlock('auto-task', self.root)
                    self.assertTrue(lock.exists())
                else:
                    self.assertEqual(auto.unlock('auto-task', self.root)['removed'][0]['owner'], 'dead')
                    self.assertFalse(lock.exists())
                lock.unlink(missing_ok=True)
        lock.write_text(json.dumps({'pid': 4242, 'start': None}), encoding='utf-8')
        with mock.patch.object(a, 'process_start', return_value=None):  # e.g. OpenProcess access denied
            self.assertEqual(a.lock_state(lock), 'alive')
        lock.write_text('', encoding='utf-8')
        os.utime(lock, (1, 1))
        self.assertEqual(a.lock_state(lock), 'abandoned')
        self.assertEqual(auto.unlock('auto-task', self.root)['removed'], [{'lock': 'publication.lock', 'scope': 'repository', 'owner': 'abandoned'}])
        events = (self.root / 'runs/auto-task/events.jsonl').read_text(encoding='utf-8')
        self.assertEqual(events.count('"unlock"'), 3)

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
