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
        (self.root / '.gitignore').write_text('runs/\noutputs/\n.venv-controls/\nwork/\n')
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

    def execute(self, text=b'Ran 1 test in 0.001s\n\nOK\n', code=0, mutation=None):
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
            return Process() if '.venv-controls' in argv[0] else actual_popen(argv, **kwargs)
        with mock.patch.object(g.subprocess, 'Popen', side_effect=dispatch):
            return g.run_tests('gate-task', 'unit', self.root)

    def review(self, verdict='accepted', extra=()):
        return g.assess('gate-task', {'candidate_digest': g.candidate('gate-task', self.root)['digest'],
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
        g.check_submission('gate-task', self.root, persist=True)
        self.assertTrue((self.run / 'gate-submission.json').is_file())

    def test_missing_tests_blocks(self):
        with self.assertRaisesRegex(a.ContractError, 'test evidence missing'):
            g.check_submission('gate-task', self.root)

    def test_missing_review_blocks(self):
        self.execute()
        with self.assertRaisesRegex(a.ContractError, 'review missing'):
            g.check_submission('gate-task', self.root)

    def test_zero_tests_fail(self):
        self.assertEqual(self.execute(b'Ran 0 tests in 0.001s\nOK\n')['outcome'], 'failed')

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
            g.assess('gate-task', {'candidate_digest': g.candidate('gate-task', self.root)['digest'],
                'reviewer': self.profile['author'], 'verdict': 'accepted',
                'evidence': ['outputs/gate-task/artifact.txt']}, self.root)

    def test_changed_product_invalidates(self):
        self.ready()
        (self.root / 'product.txt').write_text('changed')
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
            return process if '.venv-controls' in argv[0] else actual_popen(argv, **kwargs)
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
        value = a.read_json(self.run / 'controls.json'); value['mode'] = 'observe'
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
            g.check_publication('denied-task', self.root, 'unused')

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
        self.assertFalse((self.run / 'gate-checkpoint.json').exists())
        with self.assertRaisesRegex(a.ContractError, 'submitted completed task'):
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

    def test_actual_commit_with_canonical_generated_records(self):
        self.ready(); a.submit('gate-task', self.root); r.checkpoint('gate-task', self.root)
        publication = a.read_json(self.run / 'publication.json')
        paths = sorted({'product.txt'} | g._managed('gate-task'))
        r.git(self.root, 'add', '--', *paths)
        r.git(self.root, 'commit', '-q', '-m', 'generated candidate')
        commit = r.git(self.root, 'rev-parse', 'HEAD')
        publication.update(phase='committed', commit=commit, staged_paths=paths)
        a.write_json(self.run / 'publication.json', publication)
        self.assertEqual(g.check_publication('gate-task', self.root, commit, publication)['status'], 'passed')

    def test_generated_payload_rejected_even_if_committed(self):
        self.ready(); a.submit('gate-task', self.root); r.checkpoint('gate-task', self.root)
        file = self.root / '.agent-work/tasks/gate-task/spec.md'
        file.write_text(file.read_text(encoding='utf-8') + '\nUnreviewed payload\n', encoding='utf-8')
        publication = a.read_json(self.run / 'publication.json')
        paths = sorted({'product.txt'} | g._managed('gate-task'))
        r.git(self.root, 'add', '--', *paths)
        r.git(self.root, 'commit', '-q', '-m', 'tampered generated candidate')
        commit = r.git(self.root, 'rev-parse', 'HEAD')
        publication.update(phase='committed', commit=commit, staged_paths=paths)
        a.write_json(self.run / 'publication.json', publication)
        with self.assertRaisesRegex(a.ContractError, 'canonical generated'):
            g.check_publication('gate-task', self.root, commit, publication)

    def test_generated_json_payload_rejected_by_checkpoint_receipt(self):
        self.ready(); a.submit('gate-task', self.root); r.checkpoint('gate-task', self.root)
        file = self.root / '.agent-work/tasks/gate-task/record.json'
        value = a.read_json(file); value['git']['status'] = 'UNREVIEWED PAYLOAD'
        a.write_json(file, value)
        publication = a.read_json(self.run / 'publication.json')
        paths = sorted({'product.txt'} | g._managed('gate-task'))
        r.git(self.root, 'add', '--', *paths)
        r.git(self.root, 'commit', '-q', '-m', 'tampered JSON checkpoint')
        commit = r.git(self.root, 'rev-parse', 'HEAD')
        publication.update(phase='committed', commit=commit, staged_paths=paths)
        a.write_json(self.run / 'publication.json', publication)
        with self.assertRaisesRegex(a.ContractError, 'differ from lifecycle checkpoint'):
            g.check_publication('gate-task', self.root, commit, publication)

    def test_unicode_and_whitespace_committed_names(self):
        name = '한글 [x] space .txt'
        (self.root / name).write_text('content\n')
        r.git(self.root, 'add', '--', name)
        r.git(self.root, 'commit', '-q', '-m', 'name fixture')
        self.assertEqual(g._blob(self.root, name), g._blob(self.root, name, 'HEAD'))

    def test_actual_commit_matches_seal(self):
        self.ready()
        a.submit('gate-task', self.root)
        r.checkpoint('gate-task', self.root)
        publication = a.read_json(self.run / 'publication.json')
        paths = sorted({'product.txt'} | g._managed('gate-task'))
        r.git(self.root, 'add', '--', *paths)
        r.git(self.root, 'commit', '-q', '-m', 'candidate')
        commit = r.git(self.root, 'rev-parse', 'HEAD')
        publication.update(phase='committed', commit=commit, staged_paths=paths)
        a.write_json(self.run / 'publication.json', publication)
        self.assertEqual(g.check_publication('gate-task', self.root, commit, publication)['status'], 'passed')

    def test_actual_commit_extra_path_rejected(self):
        self.ready(); a.submit('gate-task', self.root)
        (self.root / 'unowned.txt').write_text('unowned')
        r.git(self.root, 'add', '--', 'product.txt', 'unowned.txt')
        r.git(self.root, 'commit', '-q', '-m', 'unexpected')
        commit = r.git(self.root, 'rev-parse', 'HEAD')
        publication = a.read_json(self.run / 'publication.json')
        publication.update(phase='committed', commit=commit, staged_paths=['product.txt', 'unowned.txt'])
        a.write_json(self.run / 'publication.json', publication)
        with self.assertRaisesRegex(a.ContractError, 'path set'):
            g.check_publication('gate-task', self.root, commit, publication)


class MixedPublicationTests(GateFixture, unittest.TestCase):
    def before_initial_commit(self):
        (self.root / 'runtime/legacy.py').write_bytes(b'legacy = 1\r\n')
        (self.root / 'runtime/normalized.py').write_bytes(b'normalized = 1\n')

    def after_initial_commit(self):
        r.git(self.root, 'config', 'core.autocrlf', 'true')
        (self.root / 'runtime/normalized.py').write_bytes(b'normalized = 1\r\n')

    def test_real_publication_accepts_mixed_stored_representations(self):
        self.assertNotEqual(g._blob(self.root, 'runtime/legacy.py'), g._blob(self.root, 'runtime/legacy.py', 'HEAD'))
        self.assertEqual(g._blob(self.root, 'runtime/normalized.py'), g._blob(self.root, 'runtime/normalized.py', 'HEAD'))
        GateTests.test_actual_commit_with_canonical_generated_records(self)


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

    def test_reviewed_owned_historic_crlf_and_normal_content(self):
        for name in ('runtime/legacy.py', 'runtime/normal.py'):
            with self.subTest(name=name):
                entry = g._reviewed_blob(self.root, name)
                self.assertTrue(g._reviewed_blob_matches(self.root, entry, 'HEAD'))

    def test_reviewed_changed_historic_crlf_commit(self):
        name = 'runtime/legacy.py'
        (self.root / name).write_bytes(b'value = 7\r\n')
        entry = g._reviewed_blob(self.root, name)
        r.git(self.root, 'add', '--', name)
        r.git(self.root, 'commit', '-q', '-m', 'Changed historical CRLF')
        self.assertNotEqual(entry['oid'], g._blob(self.root, name, 'HEAD')['oid'])
        self.assertTrue(g._reviewed_blob_matches(self.root, entry, 'HEAD'))

    def test_reviewed_owned_wrong_committed_bytes_rejected(self):
        name = 'runtime/legacy.py'
        entry = g._reviewed_blob(self.root, name)
        original = (self.root / name).read_bytes()
        (self.root / name).write_bytes(b'value = 999\r\n')
        r.git(self.root, 'add', '--', name)
        r.git(self.root, 'commit', '-q', '-m', 'Wrong committed bytes')
        (self.root / name).write_bytes(original)
        self.assertFalse(g._reviewed_blob_matches(self.root, entry, 'HEAD'))

    def test_reviewed_owned_postreview_raw_change_rejected(self):
        name = 'runtime/normal.py'
        entry = g._reviewed_blob(self.root, name)
        (self.root / name).write_bytes(b'value = 2\n')
        self.assertEqual(entry['oid'], g._blob(self.root, name)['oid'])
        self.assertFalse(g._reviewed_blob_matches(self.root, entry, 'HEAD'))

    def test_reviewed_owned_mode_change_rejected(self):
        name = 'runtime/legacy.py'
        entry = g._reviewed_blob(self.root, name)
        r.git(self.root, 'update-index', '--chmod=+x', '--', name)
        r.git(self.root, 'commit', '-q', '-m', 'Changed reviewed mode')
        self.assertFalse(g._reviewed_blob_matches(self.root, entry, 'HEAD'))


if __name__ == '__main__':
    unittest.main()
