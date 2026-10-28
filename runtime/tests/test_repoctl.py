import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agentctl as a
import repoctl as r


class RepositoryMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'framework'
        self.root.mkdir()
        source = Path(a.__file__).resolve().parents[1]
        for name in ('shared', 'modules', 'core'):
            shutil.copytree(source / name, self.root / name)
        for name in ('AGENTS.md', 'registry.json'):
            shutil.copyfile(source / name, self.root / name)
        self.path = Path(self.tmp.name) / 'repo'
        self.path.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.path)], check=True)
        r.register('sample', self.path, self.root)
        a.init_task('coding', 'sample-task', 'Remember task', ['Read after new process'], self.root)

    def test_checkpoint_resume_and_git_change(self):
        r.bind('sample', 'sample-task', self.root)
        value = r.resume('sample', 'sample-task', self.root)
        self.assertEqual(value['record']['result']['objective'], 'Remember task')
        report = (self.path / '.agent-work/tasks/sample-task/report.ko.md').read_text(encoding='utf-8')
        for i, heading in enumerate(a.HEADINGS, 1):
            self.assertIn(f'## {i}. {heading}', report)
        self.assertIn('## Resume procedure', value['spec'])
        (self.path / 'new-file.txt').write_text('new content')
        self.assertTrue(r.resume('sample', 'sample-task', self.root)['git_changed'])
        self.assertIn('sample-task', r.resume('sample', root=self.root)['index']['tasks'])

    def test_same_status_content_changes_are_detected(self):
        tracked = self.path / 'tracked file 한글.txt'
        tracked.write_text('initial', encoding='utf-8')
        subprocess.run(['git', '-C', str(self.path), 'add', '--', tracked.name], check=True)
        tracked.write_text('modified once', encoding='utf-8')
        loose = self.path / 'untracked file 한글.txt'
        loose.write_text('first', encoding='utf-8')
        r.bind('sample', 'sample-task', self.root)
        before = r.resume('sample', 'sample-task', self.root)
        self.assertFalse(before['git_changed'])
        loose.write_text('second', encoding='utf-8')
        after = r.resume('sample', 'sample-task', self.root)
        self.assertEqual(before['current_git']['status'], after['current_git']['status'])
        self.assertTrue(after['git_changed'])
        r.checkpoint('sample-task', self.root)
        self.assertFalse(r.resume('sample', 'sample-task', self.root)['git_changed'])
        tracked.write_text('modified twice', encoding='utf-8')
        self.assertTrue(r.resume('sample', 'sample-task', self.root)['git_changed'])
        r.checkpoint('sample-task', self.root)
        before = r.resume('sample', 'sample-task', self.root)
        tracked.write_text('staged-only change', encoding='utf-8')
        subprocess.run(['git', '-C', str(self.path), 'add', '--', tracked.name], check=True)
        tracked.write_text('modified twice', encoding='utf-8')
        after = r.resume('sample', 'sample-task', self.root)
        self.assertEqual(before['current_git']['status'], after['current_git']['status'])
        self.assertTrue(after['git_changed'])

    def test_identity_mismatch_and_rebinding_rejected(self):
        r.bind('sample', 'sample-task', self.root)
        other = Path(self.tmp.name) / 'other'
        other.mkdir()
        subprocess.run(['git', 'init', '-q', str(other)], check=True)
        r.register('other', other, self.root)
        with self.assertRaises(a.ContractError):
            r.bind('other', 'sample-task', self.root)
        data = a.read_json(self.path / '.agent-work/repository.json')
        data['uuid'] = 'changed'
        a.write_json(self.path / '.agent-work/repository.json', data)
        with self.assertRaises(a.ContractError):
            r.resume('sample', 'sample-task', self.root)

    def test_redaction_and_safe_paths(self):
        self.assertEqual(r.clean_remote('https://user:secret@example.com/repo.git?token=secret#secret'),
                         'https://example.com/repo.git')
        self.assertEqual(r.clean_remote('git@example.com:team/repo.git'), 'example.com:team/repo.git')
        with self.assertRaises(a.ContractError):
            r.resume('sample', '../escape', self.root)
        child = self.path / 'child'; child.mkdir()
        with self.assertRaises(a.ContractError):
            r.register('child', child, self.root)

    def test_spec_tampering_and_task_collision(self):
        r.bind('sample', 'sample-task', self.root)
        file = self.path / '.agent-work/tasks/sample-task/spec.md'
        file.write_text('Changed outside checkpoint', encoding='utf-8')
        with self.assertRaises(a.ContractError):
            r.resume('sample', 'sample-task', self.root)
        record = self.path / '.agent-work/tasks/sample-task/record.json'
        data = a.read_json(record)
        data['result']['created_at'] = '2000-01-01T00:00:00+00:00'
        a.write_json(record, data)
        with self.assertRaises(a.ContractError):
            r.checkpoint('sample-task', self.root)

    def test_cli_init_and_submit_refresh_record(self):
        (self.root / 'runtime').mkdir(exist_ok=True)
        for name in ('agentctl.py', 'repoctl.py'):
            shutil.copyfile(Path(a.__file__).parent / name, self.root / 'runtime' / name)
        def command(*args):
            p = subprocess.run([sys.executable, str(self.root / 'runtime/agentctl.py'), *args],
                               capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            return json.loads(p.stdout)
        command('init', '--repo', 'sample', '--module', 'coding', '--task', 'cli-task',
                '--objective', 'CLI integration', '--criterion', 'Persist task')
        self.assertEqual(r.resume('sample', 'cli-task', self.root)['record']['task_state'], 'queued')
        command('transition', 'cli-task', 'running')
        command('submit', 'cli-task')
        self.assertEqual(r.resume('sample', 'cli-task', self.root)['record']['task_state'], 'submitted')

    def test_new_process_reads_persisted_record(self):
        r.bind('sample', 'sample-task', self.root)
        code = "import pathlib,repoctl; print(repoctl.resume('sample','sample-task',pathlib.Path(__import__('sys').argv[1]))['record']['result']['objective'])"
        p = subprocess.run([sys.executable, '-c', code, str(self.root)],
                           cwd=Path(a.__file__).parent, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), 'Remember task')


if __name__ == '__main__':
    unittest.main()
