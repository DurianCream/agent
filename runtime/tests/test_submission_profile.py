"""Prose profile regressions; synthetic identities and local remotes only."""
import copy
import io
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
import control_gate as g
import repoctl as r
import repo_automation as auto
import submission_profile as p


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.source = Path(a.__file__).resolve().parents[1]
        base = self.source / 'work/profile-fixtures'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'checkout'
        self.root.mkdir()
        for name in ('shared', 'core', 'modules', 'runtime'):
            shutil.copytree(self.source / name, self.root / name,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'repos.local.json'))
        for name in ('registry.json', 'AGENTS.md'):
            shutil.copyfile(self.source / name, self.root / name)
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(self.root)], check=True)
        self.remote = self.base / 'remote.git'
        subprocess.run(['git', 'init', '-q', '--bare', str(self.remote)], check=True)
        for key, value in [('user.name', 'Fixture'), ('user.email', 'fixture@example.invalid'), ('core.autocrlf', 'false')]:
            r.git(self.root, 'config', key, value)
        (self.root / '.gitignore').write_text('__pycache__/\n*.py[cod]\n.agent-work/*.lock\nruns/\noutputs/\n.venv-controls/\nwork/\nruntime/repos.local.json\n')
        r.register('sample', self.root, self.root)
        r.git(self.root, 'remote', 'add', 'origin', str(self.remote))
        a.write_json(self.root / '.agent-work/automation.json', {'schema_version': '1.0.0', 'enabled': True,
            'remote': 'origin', 'expected_url': str(self.remote), 'branch': 'main'})
        self.profile = {'schema_version': '0.1.0', 'enabled': True, 'repository_id': 'sample',
            'selector': {'project': 'sample', 'service': 'agents', 'environment': 'development'},
            'required_suites': [{'id': 'unit', 'argv': ['@project-python', '-m', 'unittest', 'discover',
                '-s', 'fixture_checks', '-p', 'test_full.py', '-v']}],
            'timeout_seconds': 60, 'policy': {'submission': 'allow', 'publication': 'allow'},
            'author': {'subject': 'author', 'session': 'author-session'}}
        a.write_json(self.root / g.CONFIG, self.profile)
        self.doc = 'docs/prose/overview.txt'
        (self.root / self.doc).parent.mkdir(parents=True)
        (self.root / self.doc).write_text('A friendly project overview.\n', encoding='utf-8')
        a.write_json(self.root / p.CONFIG, {'schema_version': p.VERSION, 'profile': p.PROFILE, 'paths': [self.doc]})
        (self.root / 'fixture_checks').mkdir()
        (self.root / 'fixture_checks/test_full.py').write_text('import unittest\nclass Full(unittest.TestCase):\n def test_full(self): self.assertTrue(True)\n')
        r.git(self.root, 'add', '--', '.')
        r.git(self.root, 'commit', '-q', '-m', 'Baseline')
        r.git(self.root, 'push', '-q', 'origin', 'main')
        self.task = 'profile-task'
        self.run = self.root / 'runs' / self.task

    def initialize(self, cli=False):
        if cli:
            self.cli('runtime/agentctl.py', 'init', '--module', 'coding', '--task', self.task,
                     '--objective', 'Improve ordinary prose', '--criterion', 'Reviewed prose edit', '--repo', 'sample',
                     '--project', 'sample', '--service', 'agents', '--environment', 'development', '--issue', 'prose')
            self.cli('runtime/agentctl.py', 'transition', self.task, 'running')
        else:
            a.init_task('coding', self.task, 'Improve ordinary prose', ['Reviewed prose edit'], self.root)
            r.bind('sample', self.task, self.root, scope={**self.profile['selector'], 'issue': 'prose'}, new_task=True)
            a.transition(self.task, 'running', self.root)
        auto.track(self.task, [self.doc], self.root)
        (self.root / self.doc).write_text('A clear and friendly project overview.\n', encoding='utf-8')
        (self.run / 'evidence/review.txt').write_text('Synthetic fixture review: wording only; no control or behavioral effects.\n')
        artifact = self.root / ('outputs/' + self.task + '/wording.txt')
        artifact.write_text('Reviewed wording summary.\n')
        result = a.read_json(self.run / 'result.json')
        result['artifacts'] = [{'path': 'outputs/' + self.task + '/wording.txt', 'description': '문구 요약', 'sha256': None}]
        result.update(status='completed', summary='문구 검토 완료', work=['Light tier: ordinary prose wording only.'], limitations=[], next_actions=[])
        result['verification'] = [{'id': 'check', 'name': '문구 검토', 'method': 'fixture review and real profile checker',
            'outcome': 'passed', 'evidence': ['runs/' + self.task + '/evidence/review.txt'], 'notes': 'Synthetic identity; local fixture only.'}]
        result['acceptance_criteria'][0]['verification_ids'] = ['check']
        a.write_json(self.run / 'result.json', result)
        executable = self.root / ('.venv-controls/Scripts/python.exe' if os.name == 'nt' else '.venv-controls/bin/python')
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b'fixture')
        (self.root / '.venv-controls/pyvenv.cfg').write_text('fixture')

    def cli(self, *argv, success=True):
        result = subprocess.run([sys.executable, '-X', 'utf8', *argv], cwd=self.root,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
        if success:
            self.assertEqual(result.returncode, 0, (argv, result.stdout.decode('utf-8', errors='replace'), result.stderr.decode('utf-8', errors='replace')))
        else:
            self.assertNotEqual(result.returncode, 0, argv)
        text = result.stdout.decode('utf-8')
        value = json.loads(text)
        if hasattr(self, 'transcript'):
            self.transcript.append({'command': list(argv), 'exit_code': result.returncode, 'response': value})
        return value.get('data')

    def selection(self):
        return {'candidate_digest': g.candidate(self.task, self.root)['digest'],
            'reviewer': {'subject': 'reviewer', 'session': 'independent-session'},
            'reason': 'Only ordinary descriptive wording changes; no unresolved material uncertainty.',
            'impact': {self.doc: {'ordinary_prose': True, 'no_behavior_change': True, 'uncertainty': 'none',
                'rationale': 'Read both versions: only a descriptive adjective changes.'}},
            'evidence': ['runs/' + self.task + '/evidence/review.txt']}

    def choose(self):
        return p.select(self.task, self.selection(), self.root)

    def execute(self, suite=p.SUITE['id']):
        class Process:
            stdout = io.BytesIO(b'Ran 3 tests in 0.001s\n\nOK\n')
            def wait(self, timeout): return 0
            def kill(self): pass
        original = subprocess.Popen
        def dispatch(argv, **kwargs):
            return Process() if '.venv-controls' in argv[0] else original(argv, **kwargs)
        with mock.patch.object(g.subprocess, 'Popen', side_effect=dispatch):
            return g.run_tests(self.task, suite, self.root)

    def review(self):
        return g.assess(self.task, {'candidate_digest': g.candidate(self.task, self.root)['digest'],
            'reviewer': {'subject': 'reviewer', 'session': 'independent-session'}, 'verdict': 'accepted',
            'evidence': ['runs/' + self.task + '/evidence/review.txt', 'outputs/' + self.task + '/wording.txt']}, self.root)

    def test_cli_real_light_lifecycle(self):
        self.transcript = []
        self.initialize(cli=True)
        # Replace the explicit fake environment used by unit fixtures with a real interpreter.
        shutil.rmtree(self.root / '.venv-controls')
        subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(self.root / '.venv-controls')], check=True, timeout=90)
        input_path = 'runs/' + self.task + '/evidence/selection.json'
        a.write_json(self.root / input_path, self.selection())
        self.cli('runtime/control_gate.py', 'select-profile', '--task', self.task, '--input', input_path)
        check = self.cli('runtime/control_gate.py', 'run-tests', '--task', self.task, '--suite', p.SUITE['id'])
        self.assertEqual(check['tests_run'], 3)
        self.assertEqual(check['outcome'], 'passed')
        a.write_json(self.root / input_path, {'candidate_digest': g.candidate(self.task, self.root)['digest'],
            'reviewer': {'subject': 'reviewer', 'session': 'independent-session'}, 'verdict': 'accepted',
            'evidence': ['runs/' + self.task + '/evidence/review.txt', 'outputs/' + self.task + '/wording.txt']})
        self.cli('runtime/control_gate.py', 'assess', '--task', self.task, '--input', input_path)
        self.cli('runtime/repoctl.py', 'checkpoint', '--task', self.task)
        self.cli('runtime/agentctl.py', 'validate', self.task)
        self.cli('runtime/agentctl.py', 'submit', self.task)
        finish = self.cli('runtime/repoctl.py', 'finish', '--task', self.task)
        self.assertEqual(finish['phase'], 'pushed')
        self.assertEqual(auto.remote_head(self.root, finish['policy']), finish['commit'])
        self.assertEqual(g.check_submission(self.task, self.root)['status'], 'passed')
        output = os.environ.get('PROFILE_LIFECYCLE_EVIDENCE')
        if output:
            # Sanitize local fixture paths; retain actual command results/digests/counts.
            text = json.dumps({'identity': 'synthetic local fixture, not authenticated', 'transcript': self.transcript}, ensure_ascii=False, indent=2)
            text = text.replace(str(self.root).replace('\\', '\\\\'), '<fixture-checkout>').replace(str(self.remote).replace('\\', '\\\\'), '<local-bare-remote>')
            Path(output).write_text(text + '\n', encoding='utf-8')

    def test_default_full_and_light_requires_independent_semantics(self):
        self.initialize()
        with self.assertRaisesRegex(a.ContractError, 'Unknown mandatory'):
            self.execute()
        for change in ('self', 'unknown', 'missing'):
            value = self.selection()
            if change == 'self': value['reviewer'] = self.profile['author']
            elif change == 'unknown': value['impact'][self.doc]['uncertainty'] = 'unknown'
            else: value['impact'] = {}
            with self.subTest(change=change), self.assertRaises(a.ContractError):
                p.select(self.task, value, self.root)
        self.choose(); self.execute(); self.review()
        self.assertEqual(g.check_submission(self.task, self.root)['status'], 'passed')

    def test_candidate_mutation_and_reselection_invalidate_tests(self):
        self.initialize(); self.choose(); self.execute(); self.review()
        self.choose()
        with self.assertRaisesRegex(a.ContractError, 'approval changed'):
            g.check_submission(self.task, self.root)
        (self.root / self.doc).write_text('A different descriptive overview.\n')
        with self.assertRaisesRegex(a.ContractError, 'stale'):
            self.execute()
        self.choose(); self.execute(); self.review()
        self.assertEqual(g.check_submission(self.task, self.root)['status'], 'passed')

    def test_control_union_staged_deletion_and_untracked_addition(self):
        self.initialize()
        target = self.root / 'runtime/agentctl.py'
        original = target.read_bytes()
        r.git(self.root, 'rm', '--', 'runtime/agentctl.py')
        with self.assertRaisesRegex(a.ContractError, 'unchanged control'):
            self.choose()
        target.write_bytes(original)
        r.git(self.root, 'add', '--', 'runtime/agentctl.py')
        extra = self.root / 'runtime/extra.py'
        extra.write_text('new = True\n')
        with self.assertRaisesRegex(a.ContractError, 'unchanged control'):
            self.choose()

    def test_protected_mixed_and_new_paths_rejected(self):
        self.initialize(); self.choose()
        auto.track(self.task, ['AGENTS.md'], self.root)
        value = self.selection()
        value['impact']['AGENTS.md'] = copy.deepcopy(value['impact'][self.doc])
        with self.assertRaisesRegex(a.ContractError, 'not opted-in'):
            p.select(self.task, value, self.root)
        with self.assertRaisesRegex(a.ContractError, 'stale'):
            self.execute()

    def test_document_boundaries(self):
        self.initialize()
        for content in (b'python tool.py\n', b'{"key": 1}\n', b'\x00bad', b'\xff', b'x' * (p.MAX_DOCUMENT + 1)):
            (self.root / self.doc).write_bytes(content)
            with self.subTest(content=content[:20]), self.assertRaises(a.ContractError): self.choose()
        (self.root / self.doc).unlink()
        with self.assertRaises(a.ContractError): self.choose()

    def test_evidence_and_mirrored_state_deletion_fail_closed(self):
        self.initialize(); self.choose(); self.execute()
        statefile = self.run / 'submission-profile-state.json'
        original = statefile.read_bytes()
        statefile.unlink()
        with self.assertRaisesRegex(a.ContractError, 'state missing'): self.execute()
        statefile.write_bytes(original)
        (self.run / 'evidence/review.txt').write_text('Changed review evidence')
        with self.assertRaisesRegex(a.ContractError, 'evidence bytes'): self.execute()

    def test_full_promotion_allows_config_maintenance_without_enrollment_rewrite(self):
        self.initialize()
        shutil.rmtree(self.root / '.venv-controls')
        subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(self.root / '.venv-controls')], check=True, timeout=90)
        self.choose()
        light = self.cli('runtime/control_gate.py', 'run-tests', '--task', self.task, '--suite', p.SUITE['id'])
        self.assertEqual(light['tests_run'], 3)
        original = (self.run / 'controls.json').read_bytes()
        auto.track(self.task, [p.CONFIG], self.root)
        config = a.read_json(self.root / p.CONFIG); config['paths'] = []
        a.write_json(self.root / p.CONFIG, config)
        with self.assertRaises(a.ContractError): self.execute()
        p.promote(self.task, 'Profile configuration maintenance requires full regression.', self.root)
        with self.assertRaisesRegex(a.ContractError, 'irreversible'): self.choose()
        with self.assertRaisesRegex(a.ContractError, 'test evidence missing'): self.review()
        full = self.cli('runtime/control_gate.py', 'run-tests', '--task', self.task, '--suite', 'unit')
        self.assertEqual(full['tests_run'], 1)
        self.review()
        self.assertEqual(g.check_submission(self.task, self.root)['status'], 'passed')
        self.assertEqual((self.run / 'controls.json').read_bytes(), original)
        a.submit(self.task, self.root)
        self.assertEqual(auto.finish(self.task, self.root)['phase'], 'pushed')

    def test_legacy_absence_never_enables_light(self):
        (self.root / p.CONFIG).unlink()
        r.git(self.root, 'add', '--', p.CONFIG)
        r.git(self.root, 'commit', '-q', '-m', 'Legacy baseline without capability')
        self.initialize()
        self.assertEqual(g.check_enrollment(self.task, self.root)['schema_version'], g.VERSION)
        a.write_json(self.root / p.CONFIG, {'schema_version': p.VERSION, 'profile': p.PROFILE, 'paths': [self.doc]})
        with self.assertRaisesRegex(a.ContractError, 'no light capability'): self.choose()
        self.execute('unit'); self.review()
        self.assertEqual(g.check_submission(self.task, self.root)['status'], 'passed')

    def test_linked_document_rejected(self):
        self.initialize()
        target = self.root / 'work/linked-target.txt'
        target.parent.mkdir(exist_ok=True)
        target.write_text('Ordinary descriptive text.\n')
        document = self.root / self.doc
        document.unlink()
        try:
            document.symlink_to(target)
        except OSError as error:
            self.skipTest('Host cannot create a symlink; OS error ' + str(getattr(error, 'winerror', error.errno)))
        with self.assertRaisesRegex(a.ContractError, 'Linked paths'):
            self.choose()

    def test_unknown_root_and_workflow_configuration_rejected(self):
        self.initialize()
        for name in ('build.json', '.agent-work/unknown-workflow.json', 'docs/prose/unowned.txt'):
            file = self.root / name
            file.write_text('{}\n')
            with self.subTest(path=name), self.assertRaisesRegex(a.ContractError, 'unchanged control'):
                self.choose()
            file.unlink()

    def test_assume_unchanged_control_mutation_rejected(self):
        self.initialize()
        r.git(self.root, 'update-index', '--assume-unchanged', '--', 'runtime/agentctl.py')
        target = self.root / 'runtime/agentctl.py'
        target.write_bytes(target.read_bytes() + b'\n# hidden modification\n')
        with self.assertRaisesRegex(a.ContractError, 'unchanged control'):
            self.choose()

    def test_mode_and_unregistered_new_document_rejected(self):
        self.initialize()
        r.git(self.root, 'update-index', '--chmod=+x', '--', self.doc)
        with self.assertRaisesRegex(a.ContractError, 'nonexecutable'):
            self.choose()
        r.git(self.root, 'update-index', '--chmod=-x', '--', self.doc)
        extra = 'docs/prose/new-document.txt'
        auto.track(self.task, [extra], self.root)
        (self.root / extra).write_text('Another ordinary description.\n')
        value = self.selection()
        value['impact'][extra] = copy.deepcopy(value['impact'][self.doc])
        with self.assertRaisesRegex(a.ContractError, 'not opted-in'):
            p.select(self.task, value, self.root)

    def test_profile_marker_record_and_enrollment_tampering_rejected(self):
        self.initialize(); self.choose()
        taskfile = self.run / 'task.json'
        original = taskfile.read_bytes()
        value = a.read_json(taskfile); value.pop('submission_profile_state')
        a.write_json(taskfile, value)
        with self.assertRaisesRegex(a.ContractError, 'state missing'):
            self.execute()
        taskfile.write_bytes(original)
        state = a.read_json(self.run / 'submission-profile-state.json')
        record = self.run / 'gates' / state['record']
        original = record.read_bytes(); record.unlink()
        with self.assertRaises(a.ContractError): self.execute()
        record.write_bytes(original)
        value = a.read_json(self.run / 'controls.json'); value['schema_version'] = '0.1.0'
        a.write_json(self.run / 'controls.json', value)
        with self.assertRaisesRegex(a.ContractError, 'ledger'):
            g.check_enrollment(self.task, self.root)

    def test_unknown_committed_profile_version_fails_new_enrollment(self):
        config = a.read_json(self.root / p.CONFIG); config['schema_version'] = '9.0.0'
        a.write_json(self.root / p.CONFIG, config)
        r.git(self.root, 'add', '--', p.CONFIG)
        r.git(self.root, 'commit', '-q', '-m', 'Unsupported profile version')
        with self.assertRaisesRegex(a.ContractError, 'Unsupported submission profile'):
            self.initialize()
        self.assertEqual(a.read_json(self.run / 'task.json')['control_enrollment'], 'pending')

    def test_companion_deletion_or_version_change_cannot_downgrade(self):
        self.initialize(); self.choose()
        original = (self.root / p.CONFIG).read_bytes()
        (self.root / p.CONFIG).unlink()
        with self.assertRaises(a.ContractError): self.execute()
        (self.root / p.CONFIG).write_bytes(original)
        config = a.read_json(self.root / p.CONFIG); config['schema_version'] = '9.0.0'
        a.write_json(self.root / p.CONFIG, config)
        with self.assertRaises(a.ContractError): self.execute()
        self.assertEqual(g.check_enrollment(self.task, self.root)['schema_version'], p.ENROLLMENT_VERSION)
        # Explicit full maintenance is available, never automatic light fallback.
        p.promote(self.task, 'Unknown configuration requires full repair and review.', self.root)
        self.execute('unit')


if __name__ == '__main__':
    unittest.main()
