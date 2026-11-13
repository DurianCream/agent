"""Real Git blob/remote checks with generated inert canaries, never real keys."""
import codecs
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import agentctl as a
import repoctl as r
import repo_automation as auto
import secret_scan as scan
import task_evidence
import test_repo_automation as automation_fixture
import test_control_gate_recovery as recovery_fixture


def fake():
    return '-'.join(('FAKE', 'CANARY', 'test', 'only'))


class BlobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        r.git(self.path, 'init', '-q', '-b', 'main')
        r.git(self.path, 'config', 'user.name', 'Fixture')
        r.git(self.path, 'config', 'user.email', 'fixture@example.invalid')
        r.git(self.path, 'config', 'core.autocrlf', 'false')
        (self.path / 'seed.txt').write_text('baseline')
        r.git(self.path, 'add', '.')
        r.git(self.path, 'commit', '-qm', 'baseline')

    def stage(self, name, raw):
        file = self.path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(raw)
        r.git(self.path, '--literal-pathspecs', 'add', '--', name)

    def test_patterns_locations_and_no_secret_in_exception(self):
        samples = [fake(), '-----BEGIN ' + 'RSA PRIVATE KEY-----', 'AKIA' + 'A' * 16,
                   'AIza' + 'A' * 35, 'AccountKey' + '=' + 'opaque',
                   'password' + '=' + 'example', 'token' + ' = "' + 'example' + '"']
        for sample in samples:
            with self.subTest(kind=samples.index(sample)):
                self.stage('space [literal].txt', ('clean\n' + sample + '\n').encode())
                with self.assertRaises(a.ContractError) as caught:
                    scan.scan_index(self.path, ['space [literal].txt'])
                self.assertEqual(str(caught.exception), 'Secret scan blocked: "space [literal].txt":2')
                self.assertNotIn(sample, str(caught.exception))

    def test_exact_changed_paths_and_staged_content(self):
        self.stage('unrelated.txt', fake().encode())
        self.stage('clean.txt', b'clean\n')
        scan.scan_index(self.path, ['clean.txt'])
        self.stage('selected.txt', fake().encode())
        (self.path / 'selected.txt').write_text('clean working copy')
        with self.assertRaises(a.ContractError): scan.scan_index(self.path, ['selected.txt'])
        self.stage('selected.txt', b'clean\n')
        (self.path / 'selected.txt').write_text(fake())
        scan.scan_index(self.path, ['selected.txt'])

    def test_quoted_assignments_without_canary_pattern_are_blocked(self):
        samples = ['AccountKey' + '="' + 'opaque' + '"',
                   'SharedAccessKey' + "='" + 'opaque' + "'",
                   'token' + '=" ' + 'opaque' + '"',
                   '{"password"' + ': " ' + 'opaque' + '"}',
                   '{"AccountKey"' + ': "' + 'opaque' + '"}',
                   'password' + "=' '" ]
        for index, sample in enumerate(samples):
            with self.subTest(index=index):
                self.stage('assignment.txt', ('clean\n' + sample).encode())
                with self.assertRaises(a.ContractError) as caught:
                    scan.scan_index(self.path, ['assignment.txt'])
                self.assertEqual(str(caught.exception), 'Secret scan blocked: "assignment.txt":2')
                self.assertTrue('opaque' not in str(caught.exception))
        # Empty assignments have no value; unquoted angle-bracket placeholders
        # remain clean. Quoted nonempty placeholders are conservatively blocked.
        self.stage('assignment.txt', ('password' + '=""\n' + 'token' + '=\n' +
                                     'AccountKey' + '=<placeholder>\n').encode())
        scan.scan_index(self.path, ['assignment.txt'])

    def test_exact_allowlist_from_git_snapshot_only(self):
        self.stage('fixture.txt', fake().encode())
        self.stage(scan.ALLOWLIST, json.dumps({'schema_version':'1.0.0','paths':['fixture.txt']}).encode())
        scan.scan_index(self.path, ['fixture.txt', scan.ALLOWLIST])
        self.stage('fixture.txt', b'\0' * 100)
        with mock.patch.object(scan, 'MAX_BYTES', 80):
            scan.scan_index(self.path, ['fixture.txt'])
        self.stage('fixture.txt', fake().encode())
        self.stage('other.txt', fake().encode())
        with self.assertRaises(a.ContractError): scan.scan_index(self.path, ['other.txt'])
        self.stage(scan.ALLOWLIST, b'{"schema_version":"1.0.0","paths":[]}')
        (self.path / scan.ALLOWLIST).write_text(json.dumps({'schema_version':'1.0.0','paths':['fixture.txt']}))
        with self.assertRaises(a.ContractError): scan.scan_index(self.path, ['fixture.txt'])

    def test_malformed_allowlist_fails_closed_without_payload(self):
        for data in [b'not json', b'{"schema_version":"1.0.0","paths":["*.txt"]}',
                     b'{"schema_version":"1.0.0","paths":[],"paths":[]}',
                     b'{"schema_version":"1.0.0","paths":["../escape"]}',
                     json.dumps({'schema_version':'1.0.0','paths':[scan.ALLOWLIST]}).encode()]:
            self.stage(scan.ALLOWLIST, data)
            with self.assertRaises(a.ContractError) as caught: scan.scan_index(self.path, ['seed.txt'])
            self.assertEqual(str(caught.exception), 'Secret scan blocked: "' + scan.ALLOWLIST + '":0')

    def test_unicode_encodings_and_unreadable_bytes(self):
        for encoding in ('utf-8', 'utf-16', 'utf-32'):
            self.stage('encoded.txt', ('clean\n' + fake()).encode(encoding))
            with self.assertRaisesRegex(a.ContractError, ':2'): scan.scan_index(self.path, ['encoded.txt'])
        for data in [b'\xff' + fake().encode(), codecs.BOM_UTF16_LE + b'x', b'a\0b']:
            self.stage('encoded.txt', data)
            with self.assertRaises(a.ContractError): scan.scan_index(self.path, ['encoded.txt'])

    def test_deleted_paths_symlinks_and_git_error(self):
        r.git(self.path, 'rm', 'seed.txt')
        scan.scan_index(self.path, ['seed.txt'])
        # Direct index mode works on Windows even when OS symlink creation is unavailable.
        oid = subprocess.run(['git','-C',str(self.path),'hash-object','-w','--stdin'],
                             input=fake().encode(),capture_output=True,check=True).stdout.decode().strip()
        r.git(self.path, 'update-index', '--add', '--cacheinfo', '120000,' + oid + ',link')
        with self.assertRaises(a.ContractError): scan.scan_index(self.path, ['link'])
        with mock.patch.object(scan.subprocess, 'run', side_effect=OSError(fake())):
            with self.assertRaises(a.ContractError) as caught: scan.scan_index(self.path, ['link'])
            self.assertNotIn(fake(), str(caught.exception))

    def test_size_limit_and_missing_commit_fail_closed(self):
        self.stage('large.txt', b'clean')
        with mock.patch.object(scan, 'MAX_BYTES', 2):
            with self.assertRaises(a.ContractError): scan.scan_index(self.path, ['large.txt'])
        with self.assertRaises(a.ContractError): scan.scan_commit(self.path, '0'*40, '1'*40, ['large.txt'])

    def test_selected_blobs_use_bounded_batch_reads(self):
        names = ['selected-' + str(i) + '.txt' for i in range(10)]
        for name in names: (self.path / name).write_text('clean')
        (self.path / 'not-selected.txt').write_text(fake())
        r.git(self.path, 'add', '--', *names, 'not-selected.txt')
        with mock.patch.object(scan, '_git', wraps=scan._git) as calls:
            scan.scan_index(self.path, names)
        self.assertEqual(calls.call_count, 5)
        # Force content chunking without changing the per-file bound or scope.
        with mock.patch.object(scan, 'MAX_BYTES', 6): scan.scan_index(self.path, names)
        scan.scan_index(self.path, [])

    def test_malformed_batch_response_blocks_without_payload(self):
        self.stage('clean.txt', b'clean')
        original = scan._git
        def corrupt(path, *args, **kwargs):
            if '--batch' in args: return fake().encode()
            return original(path, *args, **kwargs)
        with mock.patch.object(scan, '_git', side_effect=corrupt):
            with self.assertRaises(a.ContractError) as caught: scan.scan_index(self.path, ['clean.txt'])
            self.assertEqual(str(caught.exception), 'Secret scan blocked: "clean.txt":0')


class PublicationTests(unittest.TestCase):
    setUp = automation_fixture.AutomationTests.setUp
    bind = automation_fixture.AutomationTests.bind
    complete = automation_fixture.AutomationTests.complete
    own_file = automation_fixture.AutomationTests.own_file

    def test_normal_blocks_before_commit_and_clean_changes_publish(self):
        self.bind(); self.own_file('owned.txt'); self.complete()
        base = r.git(self.path, 'rev-parse', 'HEAD')
        (self.path / 'owned.txt').write_text(fake())
        with self.assertRaisesRegex(a.ContractError, 'owned.txt'):
            auto.finish('auto-task', self.root)
        self.assertEqual(r.git(self.path, 'rev-parse', 'HEAD'), base)
        self.assertEqual(auto.remote_head(self.path, auto.policy(self.path)), base)
        self.assertEqual(auto.staged_paths(self.path), [])
        self.assertEqual(a.read_json(self.root / 'runs/auto-task/publication.json')['phase'], 'begun')
        (self.path / 'owned.txt').write_text('clean')
        self.assertEqual(auto.finish('auto-task', self.root)['phase'], 'pushed')

    def test_managed_result_records_are_scanned(self):
        self.bind(); self.own_file('owned.txt')
        # Alter valid result before submission; generated record/report must be scanned.
        original = a.submit
        def submit(*args, **kwargs):
            file = self.root / 'runs/auto-task/result.json'
            data = a.read_json(file); data['summary'] = fake(); a.write_json(file, data)
            return original(*args, **kwargs)
        with mock.patch.object(a, 'submit', side_effect=submit): self.complete()
        with self.assertRaises(a.ContractError) as caught: auto.finish('auto-task', self.root)
        self.assertIn('.agent-work/tasks/auto-task/', str(caught.exception))
        self.assertNotIn(fake(), str(caught.exception))

    def test_edit_after_prepare_blocks_resume_until_restored(self):
        self.bind(); self.own_file('owned.txt'); self.complete()
        with mock.patch.object(auto, '_install', side_effect=a.ContractError('interrupted')):
            with self.assertRaisesRegex(a.ContractError, 'interrupted'): auto.finish('auto-task', self.root)
        receipt = a.read_json(self.root / 'runs/auto-task/publication.json')
        self.assertEqual(receipt['phase'], 'prepared')
        for content in (fake(), 'clean working copy'):
            (self.path / 'owned.txt').write_text(content)
            with self.assertRaisesRegex(a.ContractError, 'changed after publication was prepared'):
                auto.finish('auto-task', self.root)
        self.assertEqual(r.git(self.path, 'rev-parse', 'HEAD'), receipt['base_head'])
        self.assertEqual(auto.remote_head(self.path, receipt['policy']), receipt['base_head'])
        (self.path / 'owned.txt').write_text('owned')
        self.assertEqual(auto.finish('auto-task', self.root)['commit'], receipt['commit'])

    def test_clean_retry_preserves_single_commit(self):
        self.bind(); self.own_file('owned.txt'); self.complete()
        original = r.git
        def fail_push(path, *args, **kwargs):
            if args[0] == 'push': raise a.ContractError('fixture network failure')
            return original(path, *args, **kwargs)
        with mock.patch.object(r, 'git', side_effect=fail_push):
            with self.assertRaises(a.ContractError): auto.finish('auto-task', self.root)
        receipt = a.read_json(self.root / 'runs/auto-task/publication.json')
        self.assertEqual(auto.finish('auto-task', self.root)['commit'], receipt['commit'])


class RecordsOnlyTests(recovery_fixture.RecoveryPublicationTests):
    def reviewed(self, summary=None):
        self.incomplete()
        if summary:
            result = a.read_json(self.run / 'result.json')
            result['summary'] = summary
            a.write_json(self.run / 'result.json', result)
        self.review(kind='records', extra=('runs/gate-task/evidence/summary.json',))

    def test_records_only_secret_blocks_before_any_effect(self):
        self.assertTrue(task_evidence.enabled(self.root,a.read_json(self.run/'publication.json')))
        self.reviewed(fake())
        base = r.git(self.root, 'rev-parse', 'HEAD')
        task = (self.run / 'task.json').read_bytes()
        # The commit object is scanned before any ref, index or record changes; a retry scans again.
        for _ in range(2):
            with self.assertRaisesRegex(a.ContractError, 'Secret scan blocked') as caught:
                auto.finish('gate-task', self.root, close='partial')
            self.assertIn('.agent-work/tasks/gate-task/', str(caught.exception))
            self.assertNotIn(fake(), str(caught.exception))
        receipt = a.read_json(self.run / 'publication.json')
        self.assertEqual(receipt['phase'], 'begun')
        self.assertEqual(auto.staged_paths(self.root), [])
        self.assertEqual(r.git(self.root, 'rev-parse', 'HEAD'), base)
        self.assertEqual(auto.remote_head(self.root, receipt['policy']), base)
        self.assertEqual((self.run / 'task.json').read_bytes(), task)

    def test_records_only_clean_retry_preserves_commit(self):
        self.reviewed()
        tip = self.advance_remote('remote.txt')
        original = r.git
        def fail_push(path, *args, **kwargs):
            if args[0] == 'push': raise a.ContractError('fixture network failure')
            return original(path, *args, **kwargs)
        with mock.patch.object(r, 'git', side_effect=fail_push):
            with self.assertRaisesRegex(a.ContractError, 'fixture network failure'):
                auto.finish('gate-task', self.root, close='partial')
        receipt = a.read_json(self.run / 'publication.json')
        self.assertEqual((receipt['phase'], receipt['mode'], receipt['parent']), ('submitted', 'remote-only', tip))
        # Remote-only never touches the index, yet a foreign staged change still stops the retry.
        (self.root / 'unrelated.txt').write_text('user work')
        r.git(self.root, 'add', '--', 'unrelated.txt')
        with self.assertRaisesRegex(a.ContractError, 'Staged changes block'):
            auto.finish('gate-task', self.root, close='partial')
        self.assertEqual(auto.remote_head(self.root, receipt['policy']), tip)
        self.assertEqual(auto.staged_paths(self.root), ['unrelated.txt'])
        r.git(self.root, 'rm', '-q', '--cached', '--', 'unrelated.txt')
        published = auto.finish('gate-task', self.root, close='partial')
        self.assertEqual(published['commit'], receipt['commit'])
        self.assertEqual(published['phase'], 'pushed')
        self.assertEqual(auto.remote_head(self.root, published['policy']), published['commit'])
        self.assertEqual(r.git(self.root, 'rev-parse', 'HEAD'), receipt['base_head'])
        self.assertEqual(self.changed(published['commit']),
                         {'.agent-work/tasks/gate-task/' + name for name in task_evidence.FILES})


# Reuse setup helpers, not the parent class's already registered test cases.
for _name in dir(recovery_fixture.RecoveryPublicationTests):
    if _name.startswith('test_') and _name not in vars(RecordsOnlyTests):
        setattr(RecordsOnlyTests, _name, None)


if __name__ == '__main__':
    unittest.main()
