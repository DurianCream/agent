"""Lifecycle boundary regressions; local bare remotes never contact a service."""
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import agentctl as a
import repoctl as r
import repo_automation as auto
import test_repo_automation as automation_tests


class GateIntegrationTests(unittest.TestCase):
    setUp = automation_tests.AutomationTests.setUp
    bind = automation_tests.AutomationTests.bind
    complete = automation_tests.AutomationTests.complete
    own_file = automation_tests.AutomationTests.own_file

    def fake_gate(self):
        gate = types.SimpleNamespace(**{name: mock.Mock(return_value=None) for name in
            ('enroll', 'check_enrollment', 'check_submission', 'check_publication', 'seal_checkpoint')})
        patch = mock.patch.dict(sys.modules, {'control_gate': gate})
        patch.start()
        self.addCleanup(patch.stop)
        return gate

    def test_new_binding_enrolls_after_publication_baseline(self):
        gate = self.fake_gate()
        def enrolled(task_id, root):
            self.assertTrue((root / 'runs/auto-task/publication.json').is_file())
            self.assertTrue((root / 'runs/auto-task/repository.json').is_file())
        gate.enroll.side_effect = enrolled
        r.bind('sample', 'auto-task', self.root,
               scope={'project': 'test-project', 'service': 'test-service',
                      'environment': 'test', 'issue': 'publish'}, new_task=True)
        gate.enroll.assert_called_once_with('auto-task', root=self.root)

    def test_legacy_binding_does_not_enroll(self):
        gate = self.fake_gate()
        self.bind()
        gate.enroll.assert_not_called()

    def test_failed_configured_enrollment_retains_pending_marker(self):
        gate = self.fake_gate()
        a.write_json(self.root / '.agent-work/gates.json', {'enabled': True})
        gate.enroll.side_effect = a.ContractError('Malformed selected configuration')
        with self.assertRaisesRegex(a.ContractError, 'Malformed selected configuration'):
            a.control_gate_call('enroll', 'auto-task', self.root)
        self.assertEqual(a.read_json(self.root / 'runs/auto-task/task.json')['control_enrollment'], 'pending')

    def test_checkpoint_rendering_uses_explicit_saved_timestamp(self):
        self.bind()
        folder = self.path / '.agent-work/tasks/auto-task'
        record = a.read_json(folder / 'record.json')
        run, task, _ = a.load_task('auto-task', self.root)
        binding = a.read_json(run / 'repository.json')
        self.assertEqual((folder / 'spec.md').read_text(encoding='utf-8'),
            r.specification_text('auto-task', binding, task, record['result'],
                record['scope'], record['git']))
        with mock.patch.object(a, 'now', side_effect=AssertionError('Renderer must be pure')):
            self.assertEqual((folder / 'report.ko.md').read_text(encoding='utf-8'),
                r.record_text(record['result'], task, record['git'], record['scope'],
                    saved_at=record['saved_at']))

    def test_checkpoint_seal_receives_generated_bytes_not_file_reread(self):
        gate = self.fake_gate()
        original = a.atomic_text
        def tamper_after_write(file, text):
            original(file, text)
            if file.name == 'spec.md':
                file.write_text(text + 'unreviewed addition', encoding='utf-8')
        with mock.patch.object(a, 'atomic_text', side_effect=tamper_after_write):
            self.bind()
        files = gate.seal_checkpoint.call_args.kwargs['files']
        self.assertEqual(len(files), 5)
        self.assertTrue(all(type(value) is bytes for value in files.values()))
        name = '.agent-work/tasks/auto-task/spec.md'
        self.assertNotEqual(files[name], (self.path / name).read_bytes())
        self.assertNotIn(b'unreviewed addition', files[name])
        for name, expected in files.items():
            if not name.endswith('/spec.md'):
                self.assertEqual(expected, (self.path / name).read_bytes())

    def test_load_rejects_enrollment_failure(self):
        gate = self.fake_gate()
        gate.check_enrollment.side_effect = a.ContractError('Enrollment changed')
        with self.assertRaisesRegex(a.ContractError, 'Enrollment changed'):
            a.load_task('auto-task', self.root)

    def test_missing_gate_module_keeps_legacy_readable(self):
        with mock.patch.dict(sys.modules, {'control_gate': None}):
            a.load_task('auto-task', self.root)

    def test_missing_gate_module_blocks_each_enrollment_signal(self):
        run = self.root / 'runs/auto-task'
        for name in ('marker', 'controls', 'ledger'):
            with self.subTest(signal=name):
                task = a.read_json(run / 'task.json')
                if name == 'marker':
                    task['control_enrollment'] = 'pinned'
                    a.write_json(run / 'task.json', task)
                    target = None
                else:
                    target = (run / 'controls.json' if name == 'controls' else
                              self.root / 'runs/control-enrollments/auto-task.json')
                    a.write_json(target, {})
                with mock.patch.dict(sys.modules, {'control_gate': None}):
                    with self.assertRaisesRegex(a.ContractError, 'module unavailable'):
                        a.load_task('auto-task', self.root)
                if target:
                    target.unlink()
                else:
                    task.pop('control_enrollment')
                    a.write_json(run / 'task.json', task)

    def test_missing_gate_module_blocks_configured_init(self):
        a.write_json(self.root / '.agent-work/gates.json', {'enabled': True})
        with mock.patch.dict(sys.modules, {'control_gate': None}):
            with self.assertRaisesRegex(a.ContractError, 'module unavailable'):
                a.control_gate_call('enroll', 'auto-task', self.root)
            self.assertEqual(a.read_json(self.root / 'runs/auto-task/task.json')['control_enrollment'], 'pending')
            with self.assertRaisesRegex(a.ContractError, 'module unavailable'):
                a.load_task('auto-task', self.root)

    def test_failed_submission_gate_writes_no_published_result(self):
        gate = self.fake_gate()
        self.bind()
        a.transition('auto-task', 'running', self.root)
        gate.check_submission.side_effect = a.ContractError('Review missing')
        with self.assertRaisesRegex(a.ContractError, 'Review missing'):
            a.submit('auto-task', self.root)
        self.assertFalse((self.root / 'outputs/auto-task/result.json').exists())
        self.assertEqual(a.read_json(self.root / 'runs/auto-task/task.json')['state'], 'running')

    def test_unknown_gate_exception_is_blocking_and_sanitized(self):
        gate = self.fake_gate()
        gate.check_submission.side_effect = RuntimeError('private content')
        with self.assertRaisesRegex(a.ContractError, '^P1 gate check failed: RuntimeError$'):
            a.validate_result('auto-task', self.root)

    def test_submission_persists_gate_only_after_sealed_validation(self):
        gate = self.fake_gate()
        self.bind()
        def check(task_id, root, result, persist=False):
            if persist:
                self.assertIsNotNone(result['artifacts'][0]['sha256'])
                self.assertFalse((root / 'outputs/auto-task/result.json').exists())
        gate.check_submission.side_effect = check
        self.complete()
        calls = gate.check_submission.call_args_list
        self.assertEqual(sum(call.kwargs.get('persist', False) for call in calls), 1)
        a.validate_result('auto-task', self.root)
        self.assertFalse(gate.check_submission.call_args.kwargs.get('persist', False))

    def test_publication_gate_blocks_push_and_retry_reuses_commit(self):
        gate = self.fake_gate()
        self.bind(); self.own_file(); self.complete()
        baseline = r.git(self.path, 'rev-parse', 'HEAD')
        gate.check_publication.side_effect = a.ContractError('Candidate changed')
        with self.assertRaisesRegex(a.ContractError, 'Candidate changed'):
            auto.finish('auto-task', self.root)
        saved = a.read_json(self.root / 'runs/auto-task/publication.json')
        self.assertEqual(saved['phase'], 'committed')
        self.assertEqual(auto.remote_head(self.path, saved['policy']), baseline)
        self.assertEqual(r.git(self.path, 'rev-parse', 'HEAD'), saved['commit'])
        args = gate.check_publication.call_args.kwargs
        self.assertEqual(args['commit'], saved['commit'])
        self.assertEqual(args['publication']['staged_paths'], saved['staged_paths'])
        gate.check_publication.side_effect = None
        gate.check_publication.return_value = {'status': 'passed', 'assurance': 'cooperating-cli'}
        completed = auto.finish('auto-task', self.root)
        self.assertEqual(completed['commit'], saved['commit'])
        self.assertEqual(completed['gate']['status'], 'passed')
        self.assertEqual(auto.remote_head(self.path, saved['policy']), saved['commit'])

    def test_new_lifecycle_records_only_include_gate_metadata(self):
        gate = self.fake_gate()
        self.bind()
        self.own_file()
        tracked = auto.track('auto-task', ['owned [literal].txt'], self.root)
        checkpoint = r.checkpoint('auto-task', self.root)
        self.complete()
        published = auto.finish('auto-task', self.root)
        folder = self.path / '.agent-work/tasks/auto-task'
        for value in (tracked, checkpoint, published, a.read_json(folder / 'record.json')):
            self.assertNotIn('observation', value)
        self.assertFalse((self.root / 'runs/auto-task/observations').exists())
        self.assertEqual(published['phase'], 'pushed')
        self.assertEqual(auto.remote_head(self.path, published['policy']), published['commit'])
        gate.seal_checkpoint.assert_called()
        gate.check_submission.assert_called()
        gate.check_publication.assert_called_once()

    def test_resume_preserves_historical_extra_metadata_and_specification(self):
        self.bind()
        folder = self.path / '.agent-work/tasks/auto-task'
        record = a.read_json(folder / 'record.json')
        # Simulate a saved historical extension; resuming must not re-render it.
        record['observation'] = {'status': 'review_pending', 'decision': 'allow'}
        specification = (folder / 'spec.md').read_text(encoding='utf-8')
        specification += '\n## Historical advisory summary\nSaved unchanged.\n'
        (folder / 'spec.md').write_text(specification, encoding='utf-8')
        record['spec_sha256'] = a.digest(specification.encode('utf-8'))
        a.write_json(folder / 'record.json', record)
        before = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
        resumed = r.resume('sample', 'auto-task', self.root, scope=record['scope'])
        self.assertEqual(resumed['record'], record)
        self.assertEqual(resumed['spec'], specification)
        self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()})


if __name__ == '__main__':
    unittest.main()
