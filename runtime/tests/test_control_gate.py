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
import repoctl as r
import repo_automation as auto
import control_gate as g


class GateFixture:
    def before_initial_commit(self):
        pass

    def after_initial_commit(self):
        pass

    def setUp(self):
        source = Path(a.__file__).resolve().parents[1]
        fixture_base = source / 'work/gate-fixtures'
        fixture_base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=fixture_base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('shared', 'core', 'modules'):
            shutil.copytree(source / name, self.root / name)
        for name in ('registry.json', 'AGENTS.md'):
            shutil.copyfile(source / name, self.root / name)
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(self.root)], check=True)
        r.git(self.root, 'config', 'user.name', 'Fixture')
        r.git(self.root, 'config', 'user.email', 'fixture@example.invalid')
        r.git(self.root, 'config', 'core.autocrlf', 'false')
        # Framework files support init/snapshot validation, but are not fixture product.
        # Keep a small real tracked dependency to exercise candidate/commit binding,
        # rather than repeat hundreds of unrelated support-asset Git lookups.
        (self.root / '.gitignore').write_text('runs/\noutputs/\n.venv-controls/\nwork/\nshared/\ncore/\nmodules/\n')
        r.register('sample', self.root, self.root)
        r.git(self.root, 'remote', 'add', 'origin', 'https://example.invalid/repo.git')
        a.write_json(self.root / '.agent-work/automation.json', {
            'schema_version': '1.0.0', 'enabled': True, 'remote': 'origin',
            'expected_url': 'https://example.invalid/repo.git', 'branch': 'main'})
        self.profile = {'schema_version': '0.1.0', 'enabled': True, 'repository_id': 'sample',
            'selector': {'project': 'sample', 'service': 'agents', 'environment': 'development'},
            'required_suites': [{'id': 'unit', 'argv': ['@project-python', '-m', 'unittest', 'tests']}],
            'timeout_seconds': 10, 'policy': {'submission': 'allow', 'publication': 'allow'},
            'author': {'subject': 'author', 'session': 'author-session'}}
        a.write_json(self.root / g.CONFIG, self.profile)
        (self.root / 'product.txt').write_text('before\n')
        (self.root / 'runtime').mkdir(exist_ok=True)
        (self.root / 'runtime/fixture_shared.py').write_text('VALUE = 1\n')
        self.before_initial_commit()
        r.git(self.root, 'add', '--', '.')
        r.git(self.root, 'commit', '-q', '-m', 'baseline')
        self.after_initial_commit()
        a.init_task('coding', 'gate-task', 'Gate fixture', ['Verify gates'], self.root)
        r.bind('sample', 'gate-task', self.root, scope={**self.profile['selector'], 'issue': 'gate'})
        self.run = self.root / 'runs/gate-task'
        g.enroll('gate-task', self.root)
        a.transition('gate-task', 'running', self.root)
        (self.root / 'product.txt').write_text('after\n')
        auto.track('gate-task', ['product.txt'], self.root)
        executable = self.root / ('.venv-controls/Scripts/python.exe' if os.name == 'nt' else '.venv-controls/bin/python')
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b'fixture')
        (self.root / '.venv-controls/pyvenv.cfg').write_text('fixture environment')
        output = self.root / 'outputs/gate-task/artifact.txt'
        output.write_text('artifact')
        evidence = self.run / 'evidence/check.txt'
        evidence.write_text('Actual fixture check')
        result = a.read_json(self.run / 'result.json')
        result.update(status='completed', summary='완료', limitations=[], next_actions=[])
        result['artifacts'] = [{'path': 'outputs/gate-task/artifact.txt', 'description': '산출물', 'sha256': None}]
        result['verification'] = [{'id': 'check', 'name': '검사', 'method': 'fixture', 'outcome': 'passed',
                                   'evidence': ['runs/gate-task/evidence/check.txt'], 'notes': ''}]
        result['acceptance_criteria'][0]['verification_ids'] = ['check']
        a.write_json(self.run / 'result.json', result)

    @staticmethod
    def runner_result(argv, text=b'Ran 1 test in 0.001s\n\nOK\n', **counts):
        """Write what the gate's runner would report for a stubbed test process."""
        import re
        ran = re.findall(rb'Ran ([0-9]+) tests? in ', text)
        value = {**dict.fromkeys(g.COUNTS, 0), 'tests_run': int(ran[-1]) if ran else 0, **counts}
        Path(argv[argv.index(g.RUNNER) + 1]).write_text(json.dumps(value), encoding='utf-8')

    def execute(self, text=b'Ran 1 test in 0.001s\n\nOK\n', code=0, mutation=None, report=True, **counts):
        class Process:
            stdout = io.BytesIO(text)
            def wait(inner, timeout):
                if mutation:
                    mutation()
                return code
            def kill(inner):
                pass
        actual_popen = subprocess.Popen
        def dispatch(argv, **kwargs):
            if '.venv-controls' not in argv[0]:
                return actual_popen(argv, **kwargs)
            if report:
                self.runner_result(argv, text, **counts)
            return Process()
        with mock.patch.object(g.subprocess, 'Popen', side_effect=dispatch):
            return g.run_tests('gate-task', 'unit', self.root)

    def review(self, verdict='accepted', extra=(), kind='product'):
        result = a.read_json(self.run / 'result.json')
        subject = g._subject('gate-task', self.root, result, g.check_enrollment('gate-task', self.root))
        return g.assess('gate-task', {'kind': kind, 'candidate_digest': subject['digest'],
            'reviewer': {'subject': 'reviewer', 'session': 'reviewer-session'}, 'verdict': verdict,
            'evidence': ['outputs/gate-task/artifact.txt', 'runs/gate-task/evidence/check.txt', *extra]}, self.root)

    def ready(self):
        self.execute()
        self.review()


class GateTests(GateFixture, unittest.TestCase):
    def test_valid_gate_and_readonly_validation(self):
        self.ready()
        self.assertEqual(g.check_submission('gate-task', self.root)['status'], 'passed')
        self.assertFalse((self.run / 'gate-submission.json').exists())
        files = g.check_submission('gate-task', self.root, persist=True)['files']
        self.assertEqual(set(files), {'gate-submission.json'})
        self.assertFalse((self.run / 'gate-submission.json').exists())

    def test_missing_tests_blocks(self):
        with self.assertRaisesRegex(a.ContractError, 'test evidence missing'):
            g.check_submission('gate-task', self.root)

    def test_missing_review_blocks(self):
        self.execute()
        with self.assertRaisesRegex(a.ContractError, 'review missing'):
            g.check_submission('gate-task', self.root)

    def test_zero_tests_fail(self):
        self.assertEqual(self.execute(b'Ran 0 tests in 0.001s\nOK\n')['outcome'], 'failed')

    def test_runner_counts_decide_not_the_log(self):
        # Text a test prints cannot stand in for the runner's result, in either direction.
        for name in g.COUNTS[1:]:
            with self.subTest(count=name):
                stopped = self.execute(b'Ran 3 tests in 0.001s\n\nOK\n', **{name: 1})
                self.assertEqual((stopped['outcome'], stopped['counts'][name]), ('failed', 1))
        missing = self.execute(report=False)
        self.assertEqual((missing['outcome'], missing['counts'], 'result' in missing), ('failed', None, False))
        noisy = self.execute(b'FAILED (errors=1)\nOK (skipped=4)\n', tests_run=2)
        self.assertEqual((noisy['outcome'], noisy['tests_run']), ('passed', 2))
        # A stored proof cannot vouch for a result file that says otherwise, nor the reverse.
        self.review()
        self.assertEqual(g.check_submission('gate-task', self.root)['status'], 'passed')
        result, proof = self.root / noisy['result']['path'], self.run / 'gates' / noisy['record']
        a.write_json(result, {**noisy['counts'], 'skipped': 1})
        value = a.read_json(proof); value['result']['sha256'] = a.digest(result.read_bytes())
        a.write_json(proof, value)
        current = g.candidate('gate-task', self.root)
        with self.assertRaisesRegex(a.ContractError, 'differs from its proof'):
            g._proofs('gate-task', current, self.root, review_required=False)
        value['counts']['skipped'] = 1
        a.write_json(proof, value)
        with self.assertRaisesRegex(a.ContractError, 'did not pass'):
            g._proofs('gate-task', current, self.root, review_required=False)

    def test_real_runner_reports_skips_whatever_tests_print(self):
        folder = self.root / 'work/runner-fixture'; folder.mkdir(parents=True)
        (folder / 'test_sample.py').write_text(
            "import unittest\n"
            "class Sample(unittest.TestCase):\n"
            "    def test_prints(self):\n        print('OK'); print('FAILED (errors=1)')\n"
            "    @unittest.skipIf(__import__('os').environ.get('FIXTURE_SKIP'), 'fixture')\n"
            "    def test_maybe_skipped(self):\n        pass\n"
            "    @unittest.expectedFailure\n"
            "    def test_expected(self):\n        raise AssertionError('always expected')\n")
        def run(**extra):
            out = folder / 'counts.json'; out.unlink(missing_ok=True)
            done = subprocess.run([sys.executable, '-I', '-B', '-c', g.RUNNER, str(out), 'discover', '-s', str(folder), '-p', 'test_sample.py'],
                                  capture_output=True, env={**os.environ, **extra}, cwd=self.root)
            return done, g._counts(out)
        done, counts = run(FIXTURE_SKIP='1')
        # unittest's own exit status is success here; only the counts show nothing was proved.
        self.assertEqual((done.returncode, counts['tests_run'], counts['skipped'], counts['expected_failures']), (0, 3, 1, 1))
        self.assertIn(b'OK (skipped=1, expected failures=1)', done.stderr)
        self.assertFalse(g._clean(counts))

    def test_failed_exit_fails(self):
        self.assertEqual(self.execute(code=1)['outcome'], 'failed')

    def test_candidate_mutated_during_test_fails(self):
        result = self.execute(mutation=lambda: (self.root / 'product.txt').write_text('changed'))
        self.assertEqual(result['outcome'], 'failed')
        self.assertFalse(result['candidate_unchanged'])

    def test_output_limit_fails(self):
        with mock.patch.object(g, 'MAX_BYTES', 500000):
            result = self.execute(b'X' * 500001)
        self.assertEqual(result['outcome'], 'failed')
        self.assertEqual(result['reason'], 'output_limit')

    def test_review_rework_blocks(self):
        self.execute(); self.review('rework')
        with self.assertRaisesRegex(a.ContractError, 'unresolved'):
            g.check_submission('gate-task', self.root)

    def test_review_inconclusive_blocks(self):
        self.execute(); self.review('inconclusive')
        with self.assertRaises(a.ContractError):
            g.check_submission('gate-task', self.root)

    def test_self_review_rejected(self):
        self.execute()
        with self.assertRaisesRegex(a.ContractError, 'independent'):
            g.assess('gate-task', {'kind': 'product', 'candidate_digest': g.candidate('gate-task', self.root)['digest'],
                'reviewer': self.profile['author'], 'verdict': 'accepted',
                'evidence': ['outputs/gate-task/artifact.txt']}, self.root)

    def test_changed_product_invalidates(self):
        auto.track('gate-task', ['runtime/fixture_shared.py'], self.root)
        self.ready()
        current = g.candidate('gate-task', self.root)
        self.assertNotIn('product.txt', {d['path'] for d in current['candidate']['dependencies']})
        for name in ('product.txt', 'runtime/fixture_shared.py'):
            file = self.root / name; original = file.read_bytes()
            file.write_text('changed')
            with self.subTest(path=name), self.assertRaises(a.ContractError):
                g.check_submission('gate-task', self.root)
            file.write_bytes(original)

    def test_existing_fixture_dependency_mutation_invalidates(self):
        self.ready()
        file = self.root / 'runtime/fixture_shared.py'
        original = file.read_bytes()
        file.write_text('VALUE = 2\n')
        with self.assertRaises(a.ContractError):
            g.check_submission('gate-task', self.root)
        file.write_bytes(original)
        file.unlink()
        current = g.candidate('gate-task', self.root)
        self.assertIn({'path': 'runtime/fixture_shared.py', 'sha256': None, 'mode': None},
                      current['candidate']['dependencies'])
        self.assertNotIn('runtime/fixture_shared.py', {e['path'] for e in current['candidate']['entries']})
        with self.assertRaises(a.ContractError):
            g.check_submission('gate-task', self.root)

    def test_unowned_runtime_dependency_invalidates(self):
        self.ready()
        (self.root / 'runtime').mkdir(exist_ok=True)
        (self.root / 'runtime/helper.py').write_text('new dependency')
        with self.assertRaises(a.ContractError):
            g.check_submission('gate-task', self.root)

    def test_environment_metadata_change_invalidates(self):
        self.ready()
        (self.root / '.venv-controls/pyvenv.cfg').write_text('different interpreter home')
        with self.assertRaises(a.ContractError):
            g.check_submission('gate-task', self.root)

    def test_timeout_is_failed_evidence(self):
        process = mock.Mock()
        process.stdout = io.BytesIO(b'Ran 1 test in 0.001s\nOK\n')
        process.wait.side_effect = [subprocess.TimeoutExpired('fixture', 10), -9]
        actual_popen = subprocess.Popen
        def dispatch(argv, **kwargs):
            if '.venv-controls' not in argv[0]:
                return actual_popen(argv, **kwargs)
            self.runner_result(argv)
            return process
        with mock.patch.object(g.subprocess, 'Popen', side_effect=dispatch):
            result = g.run_tests('gate-task', 'unit', self.root)
        self.assertEqual(result['outcome'], 'failed')
        self.assertEqual(result['reason'], 'timeout')
        process.kill.assert_called_once()

    def test_changed_result_invalidates(self):
        self.ready()
        value = a.read_json(self.run / 'result.json'); value['summary'] = 'changed'
        a.write_json(self.run / 'result.json', value)
        with self.assertRaisesRegex(a.ContractError, 'result or referenced evidence'):
            g.check_submission('gate-task', self.root)

    def test_changed_artifact_invalidates(self):
        self.ready()
        (self.root / 'outputs/gate-task/artifact.txt').write_text('changed')
        with self.assertRaises(a.ContractError):
            g.check_submission('gate-task', self.root)

    def test_changed_test_log_invalidates(self):
        execution = self.execute(); self.review()
        proof_file = self.run / 'gates' / execution['record']
        original = proof_file.read_bytes()
        proof = a.read_json(proof_file); proof['profile_digest'] = None
        a.write_json(proof_file, proof)
        with self.assertRaisesRegex(a.ContractError, 'Legacy submission profile proof is unsupported'):
            g.check_submission('gate-task', self.root)
        proof_file.write_bytes(original)
        (self.root / execution['evidence']['path']).write_text('fake passed')
        with self.assertRaisesRegex(a.ContractError, 'evidence bytes changed'):
            g.check_submission('gate-task', self.root)

    def test_rerun_tests_requires_new_review(self):
        self.ready(); self.execute()
        with self.assertRaisesRegex(a.ContractError, 'current test executions'):
            g.check_submission('gate-task', self.root)

    def test_archive_requires_reviewed_bytes(self):
        self.ready()
        file = self.root / '.agent-work/tasks/gate-task/evidence/fake.txt'
        file.parent.mkdir(exist_ok=True); file.write_text('unreviewed payload')
        auto.track('gate-task', [file.relative_to(self.root).as_posix()], self.root)
        with self.assertRaisesRegex(a.ContractError, 'exact reviewed evidence'):
            g.check_submission('gate-task', self.root)

    def test_archive_exact_reviewed_copy_allowed(self):
        self.ready()
        file = self.root / '.agent-work/tasks/gate-task/evidence/check.txt'
        file.parent.mkdir(exist_ok=True)
        shutil.copyfile(self.run / 'evidence/check.txt', file)
        auto.track('gate-task', [file.relative_to(self.root).as_posix()], self.root)
        self.assertEqual(g.check_submission('gate-task', self.root)['status'], 'passed')

    def test_missing_companion_blocks(self):
        (self.run / 'controls.json').unlink()
        with self.assertRaisesRegex(a.ContractError, 'missing or downgraded'):
            g.check_enrollment('gate-task', self.root)

    def test_changed_companion_blocks(self):
        original = a.read_json(self.run / 'controls.json')
        # A companion edited into an older shape is damage, not a legacy enrollment.
        for change in ({'submission_profile': {}}, {'schema_version': '0.2.0'}, {'schema_version': '0.3.0'}):
            a.write_json(self.run / 'controls.json', {**original, **change})
            with self.subTest(change=change), mock.patch.object(g.impact, 'capture', side_effect=AssertionError('Must reject before validation')):
                with self.assertRaisesRegex(a.ContractError, 'differs from local ledger'):
                    g.check_enrollment('gate-task', self.root)
        a.write_json(self.run / 'controls.json', original)
        taskfile = self.run / 'task.json'; task = a.read_json(taskfile)
        a.write_json(taskfile, {**task, 'submission_profile_state': None})
        with self.assertRaisesRegex(a.ContractError, 'Legacy submission profile state is unsupported'):
            g.check_enrollment('gate-task', self.root)
        a.write_json(taskfile, task)
        for obsolete in (self.run / 'submission-profile-state.json', self.run / 'gates/profile-old.json'):
            obsolete.parent.mkdir(exist_ok=True); obsolete.write_text('not parsed')
            with self.assertRaisesRegex(a.ContractError, 'Legacy submission profile state is unsupported'):
                g.check_enrollment('gate-task', self.root)
            obsolete.unlink()
        value = copy.deepcopy(original); value['mode'] = 'observe'
        a.write_json(self.run / 'controls.json', value)
        with self.assertRaises(a.ContractError):
            g.check_enrollment('gate-task', self.root)

    def test_missing_ledger_blocks(self):
        (self.root / 'runs/control-enrollments/gate-task.json').unlink()
        with self.assertRaises(a.ContractError):
            g.check_enrollment('gate-task', self.root)

    def test_config_change_blocks(self):
        profile = copy.deepcopy(self.profile); profile['enabled'] = False
        a.write_json(self.root / g.CONFIG, profile)
        with self.assertRaisesRegex(a.ContractError, 'configuration changed'):
            g.check_enrollment('gate-task', self.root)

    def test_scope_change_blocks(self):
        original = a.read_json(self.run / 'repository.json')
        for field in ('project', 'service', 'environment', 'issue'):
            with self.subTest(field=field):
                binding = copy.deepcopy(original); binding['scope'][field] = 'other'
                a.write_json(self.run / 'repository.json', binding)
                with self.assertRaises(a.ContractError):
                    g.check_enrollment('gate-task', self.root)
        a.write_json(self.run / 'repository.json', original)

    def test_explicit_deny_policy_blocks_both_actions(self):
        profile = copy.deepcopy(self.profile)
        profile['policy'] = {'submission': 'deny', 'publication': 'deny'}
        a.write_json(self.root / g.CONFIG, profile)
        a.init_task('coding', 'denied-task', 'Denied', ['Block'], self.root)
        r.bind('sample', 'denied-task', self.root, scope={**profile['selector'], 'issue': 'denied'}, new_task=True)
        with self.assertRaisesRegex(a.ContractError, 'submission policy denies'):
            g.check_submission('denied-task', self.root, {'status': 'completed'})
        with self.assertRaisesRegex(a.ContractError, 'publication policy denies'):
            g.check_commit('denied-task', self.root, 'unused')

    def test_remote_change_blocks(self):
        r.git(self.root, 'remote', 'set-url', 'origin', 'https://example.invalid/other.git')
        with self.assertRaises(a.ContractError):
            g.check_enrollment('gate-task', self.root)

    def test_partial_result_requires_integrity_only(self):
        self.assertEqual(g.check_submission('gate-task', self.root, {'status': 'partial'})['status'], 'incomplete-result')

    def test_partial_submission_checkpoint_remains_available(self):
        result = a.read_json(self.run / 'result.json')
        result.update(status='partial', limitations=['Incomplete work remains'])
        a.write_json(self.run / 'result.json', result)
        a.submit('gate-task', self.root)
        r.checkpoint('gate-task', self.root)
        self.assertFalse((self.run / 'gate-submission.json').exists())
        with self.assertRaisesRegex(a.ContractError, 'Only a completed task'):
            auto.finish('gate-task', self.root)

    def test_legacy_not_retroactively_enrolled(self):
        a.init_task('coding', 'legacy-task', 'Legacy', ['Preserve'], self.root)
        self.assertIsNone(g.check_enrollment('legacy-task', self.root))

    def test_failed_selected_enrollment_remains_pending(self):
        a.init_task('coding', 'broken-task', 'Broken', ['Fail closed'], self.root)
        binding = a.read_json(self.run / 'repository.json'); binding['task_id'] = 'broken-task'
        broken = self.root / 'runs/broken-task'
        a.write_json(broken / 'repository.json', binding)
        with self.assertRaises(a.ContractError):
            g.enroll('broken-task', self.root)
        self.assertEqual(a.read_json(broken / 'task.json')['control_enrollment'], 'pending')
        with self.assertRaises(a.ContractError):
            a.load_task('broken-task', self.root)

    def test_unselected_new_task_remains_legacy(self):
        a.init_task('coding', 'other-task', 'Other', ['Leave alone'], self.root)
        binding = a.read_json(self.run / 'repository.json'); binding['task_id'] = 'other-task'
        binding['scope']['service'] = 'other'
        a.write_json(self.root / 'runs/other-task/repository.json', binding)
        self.assertIsNone(g.enroll('other-task', self.root))
        self.assertIsNone(g.check_enrollment('other-task', self.root))

    def test_crlf_git_canonical_content(self):
        (self.root / '.gitattributes').write_text('*.txt text eol=lf\n')
        (self.root / 'product.txt').write_bytes(b'line\r\n')
        r.git(self.root, 'add', '--', '.gitattributes', 'product.txt')
        r.git(self.root, 'commit', '-q', '-m', 'CRLF fixture')
        self.assertEqual(g._blob(self.root, 'product.txt'), g._blob(self.root, 'product.txt', 'HEAD'))

    def manual_commit(self, extra=(), tamper=None):
        """Commit generated records by hand and return check_commit arguments."""
        self.ready(); a.submit('gate-task', self.root)
        submission = a.submission('gate-task', self.root)
        _, entry = r.repo('sample', self.root)
        seal = a.read_json(self.run / 'gate-submission.json')
        records = r.record_files('gate-task', self.root, self.root, entry, a.read_json(self.run / 'repository.json'),
                                 submission['task'], submission['result'], submission['snapshot'],
                                 r.git_state(self.root), a.now(), g.attachment('gate-task', self.root, seal))
        if tamper:
            tamper(records)
        for name, data in records.items():
            (self.root / name).write_bytes(data)
        paths = sorted({'product.txt', *records, *extra})
        parent = r.git(self.root, 'rev-parse', 'HEAD')
        r.git(self.root, 'add', '--', *paths)
        r.git(self.root, 'commit', '-q', '-m', 'manual candidate')
        return dict(commit=r.git(self.root, 'rev-parse', 'HEAD'), parent=parent, paths=paths, records=records,
                    task=submission['task'], result=submission['result'], seal=a.read_json(self.run / 'gate-submission.json'))

    def test_actual_commit_matches_seal(self):
        self.assertEqual(g.check_commit('gate-task', self.root, **self.manual_commit())['status'], 'passed')

    def test_generated_payload_rejected_even_if_committed(self):
        def tamper(records):
            name = '.agent-work/tasks/gate-task/spec.md'
            records[name] += b'\nUnreviewed payload\n'
        with self.assertRaisesRegex(a.ContractError, 'canonical generated'):
            g.check_commit('gate-task', self.root, **self.manual_commit(tamper=tamper))

    def test_actual_commit_extra_path_rejected(self):
        (self.root / 'unowned.txt').write_text('unowned')
        with self.assertRaisesRegex(a.ContractError, 'path set'):
            g.check_commit('gate-task', self.root, **self.manual_commit(extra=('unowned.txt',)))

    def test_unicode_and_whitespace_committed_names(self):
        name = '한글 [x] space .txt'
        (self.root / name).write_text('content\n')
        r.git(self.root, 'add', '--', name)
        r.git(self.root, 'commit', '-q', '-m', 'name fixture')
        self.assertEqual(g._blob(self.root, name), g._blob(self.root, name, 'HEAD'))


class MixedPublicationTests(GateFixture, unittest.TestCase):
    def before_initial_commit(self):
        self.remote = self.root / 'work/remote.git'
        self.remote.parent.mkdir(exist_ok=True)
        subprocess.run(['git', 'init', '-q', '--bare', str(self.remote)], check=True)
        r.git(self.root, 'remote', 'set-url', 'origin', str(self.remote))
        policy = a.read_json(self.root / '.agent-work/automation.json')
        policy['expected_url'] = str(self.remote)
        a.write_json(self.root / '.agent-work/automation.json', policy)
        (self.root / 'runtime/legacy.py').write_bytes(b'legacy = 1\r\n')
        (self.root / 'runtime/normalized.py').write_bytes(b'normalized = 1\n')
        (self.root / 'owned-legacy.txt').write_bytes(b'stored crlf\r\n')

    def after_initial_commit(self):
        r.git(self.remote, 'fetch', str(self.root), 'refs/heads/main:refs/heads/main')
        r.git(self.root, 'config', 'core.autocrlf', 'true')
        (self.root / 'runtime/normalized.py').write_bytes(b'normalized = 1\r\n')

    def test_real_publication_accepts_mixed_stored_representations(self):
        self.assertNotEqual(g._blob(self.root, 'runtime/legacy.py'), g._blob(self.root, 'runtime/legacy.py', 'HEAD'))
        self.assertEqual(g._blob(self.root, 'runtime/normalized.py'), g._blob(self.root, 'runtime/normalized.py', 'HEAD'))
        name = 'runtime/fixture_shared.py'
        auto.track('gate-task', [name, 'owned-legacy.txt'], self.root)
        (self.root / name).unlink()
        before = g.candidate('gate-task', self.root)
        tombstone = {'path': name, 'sha256': None, 'mode': None}
        self.assertIn(tombstone, before['candidate']['dependencies'])
        self.assertEqual(next(e for e in before['candidate']['entries'] if e['path'] == name),
                         {'path': name, 'state': 'deleted', 'raw_sha256': None})
        self.ready(); a.submit('gate-task', self.root)
        published = auto.finish('gate-task', self.root)
        after = g.candidate('gate-task', self.root)
        self.assertEqual(after, before)
        self.assertIn(tombstone, after['candidate']['dependencies'])
        self.assertEqual(published['phase'], 'pushed')
        self.assertEqual(published['gate']['status'], 'passed')
        self.assertEqual(auto.remote_head(self.root, published['policy']), published['commit'])
        self.assertEqual(g._blob(self.root, name, published['commit'])['state'], 'deleted')
        # An unchanged owned file stored as a CRLF blob is committed as its sealed (clean) object.
        sealed = next(e for e in before['candidate']['entries'] if e['path'] == 'owned-legacy.txt')
        self.assertEqual(g._blob(self.root, 'owned-legacy.txt', published['commit'])['oid'], sealed['oid'])
        self.assertNotEqual(g._blob(self.root, 'owned-legacy.txt', published['base_head'])['oid'], sealed['oid'])
        print('OWNED_DELETION_PUBLICATION ' + json.dumps({'before_digest': before['digest'],
              'after_digest': after['digest'], 'commit': published['commit'],
              'phase': published['phase'], 'remote_confirmed': True, 'deleted_path': name}))


class DependencyRepresentationTests(unittest.TestCase):
    def setUp(self):
        source = Path(a.__file__).resolve().parents[1]
        folder = source / 'work/gate-representation-fixtures'
        folder.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=folder)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(self.root)], check=True)
        r.git(self.root, 'config', 'user.name', 'Fixture')
        r.git(self.root, 'config', 'user.email', 'fixture@example.invalid')
        r.git(self.root, 'config', 'core.autocrlf', 'false')
        (self.root / 'runtime').mkdir()
        (self.root / 'runtime/legacy.py').write_bytes(b'value = 1\r\n')
        (self.root / 'runtime/normal.py').write_bytes(b'value = 2\n')
        r.git(self.root, 'add', '--', 'runtime')
        r.git(self.root, 'commit', '-q', '-m', 'Mixed stored bytes')
        r.git(self.root, 'config', 'core.autocrlf', 'true')
        (self.root / 'runtime/normal.py').write_bytes(b'value = 2\r\n')

    def item(self, name='runtime/legacy.py'):
        file = self.root / name
        return {'path': name, 'sha256': a.digest(file.read_bytes()) if file.exists() else None,
                'mode': g._blob(self.root, name).get('mode')}

    def test_stored_crlf_exact_raw_fallback(self):
        item = self.item()
        self.assertNotEqual(g._blob(self.root, item['path']), g._blob(self.root, item['path'], 'HEAD'))
        self.assertTrue(g._dependency_matches(self.root, item, 'HEAD'))

    def test_normal_lf_commit_crlf_worktree_uses_canonical_match(self):
        item = self.item('runtime/normal.py')
        raw = subprocess.check_output(['git', 'show', 'HEAD:runtime/normal.py'], cwd=self.root)
        self.assertNotEqual(a.digest(raw), item['sha256'])
        self.assertTrue(g._dependency_matches(self.root, item, 'HEAD'))

    def test_changed_content_is_rejected(self):
        (self.root / 'runtime/legacy.py').write_bytes(b'value = 999\r\n')
        self.assertFalse(g._dependency_matches(self.root, self.item(), 'HEAD'))

    def test_changed_pinned_bytes_are_rejected(self):
        item = self.item()
        (self.root / item['path']).write_bytes(b'value = 1\n')
        self.assertFalse(g._dependency_matches(self.root, item, 'HEAD'))

    def test_changed_mode_is_rejected(self):
        item = self.item()
        r.git(self.root, 'update-index', '--chmod=+x', '--', item['path'])
        r.git(self.root, 'commit', '-q', '-m', 'Changed mode')
        self.assertFalse(g._dependency_matches(self.root, item, 'HEAD'))

    def test_deleted_dependency_requires_committed_deletion(self):
        file = self.root / 'runtime/legacy.py'
        file.unlink()
        item = self.item()
        self.assertFalse(g._dependency_matches(self.root, item, 'HEAD'))
        r.git(self.root, 'add', '--', item['path'])
        r.git(self.root, 'commit', '-q', '-m', 'Delete dependency')
        self.assertTrue(g._dependency_matches(self.root, item, 'HEAD'))

    def test_missing_mode_binding_is_rejected(self):
        item = self.item(); item.pop('mode')
        self.assertFalse(g._dependency_matches(self.root, item, 'HEAD'))

    def test_non_regular_git_object_is_rejected(self):
        item = self.item()
        oid = r.git(self.root, 'rev-parse', 'HEAD:' + item['path'])
        r.git(self.root, 'update-index', '--cacheinfo', '120000,' + oid + ',' + item['path'])
        r.git(self.root, 'commit', '-q', '-m', 'Unsupported link object')
        with self.assertRaises(a.ContractError):
            g._dependency_matches(self.root, item, 'HEAD')

    def test_committed_entry_requires_the_sealed_object(self):
        legacy, normal = (g._reviewed_blob(self.root, name) for name in ('runtime/legacy.py', 'runtime/normal.py'))
        self.assertTrue(g._committed_entry_matches(self.root, normal, 'HEAD'))
        # A stored CRLF blob is another object; publication writes the sealed object instead.
        self.assertFalse(g._committed_entry_matches(self.root, legacy, 'HEAD'))
        r.git(self.root, 'rm', '-q', '--cached', '--', legacy['path'])
        r.git(self.root, 'add', '--', legacy['path'])
        r.git(self.root, 'commit', '-q', '-m', 'Sealed object')
        self.assertTrue(g._committed_entry_matches(self.root, legacy, 'HEAD'))

    def test_committed_entry_wrong_bytes_or_mode_rejected(self):
        name = 'runtime/normal.py'
        entry = g._reviewed_blob(self.root, name)
        original = (self.root / name).read_bytes()
        (self.root / name).write_bytes(b'value = 999\r\n')
        r.git(self.root, 'add', '--', name)
        r.git(self.root, 'commit', '-q', '-m', 'Wrong committed bytes')
        self.assertFalse(g._committed_entry_matches(self.root, entry, 'HEAD'))
        (self.root / name).write_bytes(original)
        r.git(self.root, 'add', '--', name)
        r.git(self.root, 'update-index', '--chmod=+x', '--', name)
        r.git(self.root, 'commit', '-q', '-m', 'Changed reviewed mode')
        self.assertFalse(g._committed_entry_matches(self.root, entry, 'HEAD'))


if __name__ == '__main__':
    unittest.main()
