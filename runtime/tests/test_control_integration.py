"""Integration of advisory observations; no new execution authorization."""
import copy
import builtins
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE / 'runtime'))
import agentctl as a
import repoctl as r
import repo_automation as auto
import control_integration as integration


def profile():
    return json.loads((SOURCE / '.agent-work/observation.json').read_text(encoding='utf-8'))


def summary(task='integration-task', phase='workspace', *, status='observed', code='observed'):
    return {'ok': status == 'observed', 'task_id': task, 'phase': phase, 'status': status,
            'record_id': 'obs-' + 'a' * 32, 'snapshot_digest': 'sha256:' + 'b' * 64,
            'decision': 'allow', 'reason_codes': [code], 'assessment_status': 'complete' if status == 'observed' else 'none',
            'governance_recommendation': 'proceed' if status == 'observed' else None,
            'evaluator_assessment': 'accepted' if status == 'observed' else None,
            'executable': False, 'authority_verified': False}


class ScratchTest(unittest.TestCase):
    def make_scratch(self):
        self.scratch = (SOURCE / 'work').resolve()
        self.scratch.mkdir(exist_ok=True)
        self.base = Path(tempfile.mkdtemp(prefix='control-integration-', dir=self.scratch)).resolve()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        target = self.base.resolve()
        if not target.is_relative_to(self.scratch) or not target.name.startswith('control-integration-'):
            raise RuntimeError('Unsafe test cleanup')
        def remove_readonly(function, name, error):
            candidate = Path(name).resolve()
            if not candidate.is_relative_to(target):
                raise RuntimeError('Cleanup escaped verified fixture')
            os.chmod(candidate, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            function(name)
        shutil.rmtree(target, onerror=remove_readonly)


class LauncherTests(ScratchTest):
    def setUp(self):
        self.make_scratch()
        self.root = self.base / 'repo'
        self.root.mkdir()
        (self.root / '.agent-work').mkdir()
        (self.root / 'runs/integration-task').mkdir(parents=True)
        (self.root / 'runtime').mkdir()
        a.write_json(self.root / 'runtime/repos.local.json', {'repositories': {'multi': {'path': str(self.root), 'uuid': 'fixture-uuid'}}})
        (self.root / 'runtime/control_workflow.py').write_text('# fixture script', encoding='utf-8')
        self.profile = profile()
        self.save_profile()
        a.write_json(self.root / '.agent-work/repository.json', {'id': 'multi', 'uuid': 'fixture-uuid'})
        self.scope = {'project': 'multi', 'service': 'agent-framework', 'environment': 'development', 'issue': 'fixture'}
        self.binding = {'task_id': 'integration-task', 'repository_id': 'multi',
                        'repository_uuid': 'fixture-uuid', 'scope': self.scope}
        self.save_binding()
        a.write_json(self.root / 'runs/integration-task/task.json', {'task_id': 'integration-task'})
        selected = self.profile['interpreter']['windows' if os.name == 'nt' else 'posix']
        self.interpreter = self.root / selected
        self.interpreter.parent.mkdir(parents=True)
        self.interpreter.write_text('not executed by mocked tests', encoding='utf-8')

    def save_profile(self):
        a.write_json(self.root / '.agent-work/observation.json', self.profile)

    def save_binding(self):
        a.write_json(self.root / 'runs/integration-task/repository.json', self.binding)

    def invoke(self, response=None, **kwargs):
        value = summary() if response is None else response
        raw = json.dumps(value).encode()
        with mock.patch.object(integration, '_run_child', return_value=(0, raw, b'')) as runner:
            result = integration.invoke('integration-task', root=self.root, **kwargs)
        return result, runner

    def test_no_configuration_preserves_none_and_does_not_launch(self):
        (self.root / '.agent-work/observation.json').unlink()
        result, runner = self.invoke()
        self.assertIsNone(result)
        runner.assert_not_called()

    def test_overlong_task_id_is_rejected_before_profile_or_child_access(self):
        invalid_id = 'a' * 2048
        with (mock.patch.object(integration, 'load_profile') as loader,
              mock.patch.object(integration, '_run_child') as runner):
            result = integration.invoke(invalid_id, root=self.root)
        loader.assert_not_called()
        runner.assert_not_called()
        self.assertEqual(result['task_id'], 'invalid-task')
        self.assertEqual(result['reason_codes'], ['invalid_arguments'])
        self.assertNotIn(invalid_id, json.dumps(result))
        self.assertLess(len(json.dumps(result)), 700)
        self.assertTrue(integration.IDENTIFIER.fullmatch('a' * 128))
        self.assertFalse(integration.IDENTIFIER.fullmatch('a' * 129))

    def test_overlong_repository_and_selector_ids_are_bounded_profile_errors(self):
        invalid_id = 'b' * 2048
        original = copy.deepcopy(self.profile)
        for field in ('repository_id', 'project', 'service', 'environment'):
            with self.subTest(field=field):
                self.profile = copy.deepcopy(original)
                if field == 'repository_id':
                    self.profile[field] = invalid_id
                else:
                    self.profile['selector'][field] = invalid_id
                self.save_profile()
                result, runner = self.invoke()
                runner.assert_not_called()
                self.assertEqual(result['reason_codes'], ['profile_invalid'])
                self.assertNotIn(invalid_id, json.dumps(result))
                self.assertLess(len(json.dumps(result)), 700)

    def test_enabled_selected_profile_uses_fixed_environment_and_script(self):
        result, runner = self.invoke()
        args = runner.call_args.args[0]
        self.assertEqual(args[:4], [str(self.interpreter), '-I', '-B', str(self.root / 'runtime/control_workflow.py')])
        self.assertEqual(result['status'], 'observed')
        self.assertFalse(result['executable'])
        self.assertFalse(result['authority_verified'])
        self.assertEqual(result['mode'], 'observe')

    def test_selector_does_not_broaden_environment_or_service(self):
        for field in ('project', 'service', 'environment'):
            with self.subTest(field=field):
                original = self.scope[field]
                self.scope[field] = 'different'
                self.save_binding()
                result, runner = self.invoke()
                self.assertEqual(result['status'], 'not_selected')
                runner.assert_not_called()
                self.scope[field] = original
        self.save_binding()

    def test_exact_issue_is_preserved_and_not_a_selector_wildcard(self):
        self.scope['issue'] = 'another-explicit-issue'
        self.save_binding()
        result, runner = self.invoke()
        self.assertEqual(result['status'], 'observed')
        self.assertEqual(a.read_json(self.root / 'runs/integration-task/repository.json')['scope']['issue'], 'another-explicit-issue')
        self.assertNotIn('--issue', runner.call_args.args[0])

    def test_disabled_and_missing_environment_are_visible(self):
        self.profile['enabled'] = False
        self.save_profile()
        result, runner = self.invoke()
        self.assertEqual(result['status'], 'disabled')
        runner.assert_not_called()
        self.profile['enabled'] = True
        self.save_profile()
        self.interpreter.unlink()
        result, runner = self.invoke()
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['reason_codes'], ['environment_unavailable'])
        runner.assert_not_called()

    def test_profile_cannot_select_global_interpreter_or_extra_grants(self):
        for change in ({'approved': True}, {'interpreter': {'windows': 'C:/global/python.exe', 'posix': '/usr/bin/python'}}):
            with self.subTest(change=next(iter(change))):
                original = copy.deepcopy(self.profile)
                self.profile.update(change)
                self.save_profile()
                result, runner = self.invoke()
                self.assertEqual(result['status'], 'error')
                runner.assert_not_called()
                self.profile = original
        self.save_profile()

    def test_publication_requires_actual_commit_argument(self):
        result, runner = self.invoke(phase='publication')
        self.assertEqual(result['reason_codes'], ['publication_commit_required'])
        runner.assert_not_called()
        result, runner = self.invoke(summary(phase='publication'), phase='publication', commit='c' * 40)
        self.assertEqual(result['status'], 'observed')
        args = runner.call_args.args[0]
        self.assertEqual(args[args.index('--commit') + 1], 'c' * 40)

    def test_untrusted_child_output_never_leaks(self):
        marker = 'private-child-output-marker'
        malicious = summary()
        malicious['reason_codes'] = [marker]
        result, _ = self.invoke(malicious)
        self.assertEqual(result['status'], 'error')
        self.assertNotIn(marker, json.dumps(result))
        for value in (b'', marker.encode(), json.dumps({**summary(), 'private': marker}).encode()):
            with mock.patch.object(integration, '_run_child', return_value=(0, value, b'')):
                result = integration.invoke('integration-task', root=self.root)
                self.assertEqual(result['status'], 'error')
                self.assertNotIn(marker, json.dumps(result))
        with mock.patch.object(integration, '_run_child', return_value=(0, json.dumps(summary()).encode(), marker.encode())):
            result = integration.invoke('integration-task', root=self.root)
            self.assertEqual(result['reason_codes'], ['observer_stderr'])
            self.assertNotIn(marker, json.dumps(result))

    def test_child_cannot_claim_execution_authority(self):
        for field in ('executable', 'authority_verified'):
            value = summary()
            value[field] = True
            result, _ = self.invoke(value)
            self.assertEqual(result['status'], 'error')
            self.assertFalse(result['executable'])

    def test_assessment_uses_the_record_phase_without_guessing(self):
        result, runner = self.invoke(summary(phase='publication'), command='assess',
                                     record_id='obs-' + 'a' * 32, assessment_path=self.root / 'assessment.json')
        self.assertEqual(result['phase'], 'publication')
        self.assertEqual(result['status'], 'observed')
        self.assertIn('--record', runner.call_args.args[0])

    def test_explicit_refresh_is_passed_only_for_observe(self):
        result, runner = self.invoke(refresh=True)
        self.assertEqual(result['status'], 'observed')
        self.assertIn('--refresh', runner.call_args.args[0])
        for command in ('status', 'assess'):
            with self.subTest(command=command):
                result, runner = self.invoke(command=command, refresh=True)
                self.assertEqual(result['reason_codes'], ['invalid_arguments'])
                runner.assert_not_called()

    def test_binding_identity_mismatch_never_launches(self):
        self.binding['repository_uuid'] = 'different'
        self.save_binding()
        result, runner = self.invoke()
        self.assertEqual(result['reason_codes'], ['binding_invalid'])
        runner.assert_not_called()

    def test_registered_other_checkout_is_not_observed_as_framework_root(self):
        a.write_json(self.root / 'runtime/repos.local.json', {'repositories': {'multi': {
            'path': str(self.base / 'different-checkout'), 'uuid': 'fixture-uuid'}}})
        result, runner = self.invoke()
        self.assertEqual(result['reason_codes'], ['repository_mismatch'])
        self.assertEqual(result['status'], 'error')
        runner.assert_not_called()

    def test_unresolved_and_rework_verdicts_remain_visible(self):
        for governance, evaluator in [('escalate', 'inconclusive'), ('proceed', 'rework'), ('revise', 'accepted')]:
            with self.subTest(governance=governance, evaluator=evaluator):
                value = summary(status='review_pending', code='review_pending')
                value.update(assessment_status='needs_followup', governance_recommendation=governance,
                             evaluator_assessment=evaluator)
                result, _ = self.invoke(value)
                self.assertEqual(result['status'], 'review_pending')
                self.assertFalse(result['ok'])
                self.assertEqual(result['governance_recommendation'], governance)
                self.assertEqual(result['evaluator_assessment'], evaluator)

    def test_unresolved_review_cannot_be_reported_complete_success(self):
        value = summary()
        value.update(governance_recommendation='escalate', evaluator_assessment='inconclusive')
        result, _ = self.invoke(value)
        self.assertEqual(result['reason_codes'], ['observer_invalid_output'])
        self.assertFalse(result['ok'])

    def test_accepted_review_of_correct_denial_remains_valid(self):
        value = summary()
        value['decision'] = 'deny'
        result, _ = self.invoke(value)
        self.assertEqual(result['status'], 'observed')
        self.assertEqual(result['evaluator_assessment'], 'accepted')
        self.assertEqual(result['decision'], 'deny')
        self.assertFalse(result['executable'])

    def test_success_and_pending_states_require_real_record_bindings(self):
        for state in ('observed', 'review_pending'):
            for field in ('record_id', 'snapshot_digest', 'decision'):
                with self.subTest(state=state, field=field):
                    value = summary(status=state, code='observed' if state == 'observed' else 'review_pending')
                    value[field] = None
                    result, _ = self.invoke(value)
                    self.assertEqual(result['reason_codes'], ['observer_invalid_output'])

    def test_lone_escalation_is_visible_and_incomplete(self):
        value = summary(status='review_pending', code='review_pending')
        value.update(assessment_status='governance_only', governance_recommendation='escalate')
        result, _ = self.invoke(value)
        self.assertEqual(result['status'], 'review_pending')
        self.assertEqual(result['governance_recommendation'], 'escalate')
        self.assertIsNone(result['evaluator_assessment'])
        self.assertFalse(result['ok'])

    def test_impossible_verdict_status_combinations_are_rejected(self):
        values = [
            {**summary(status='review_pending', code='review_pending'), 'governance_recommendation': 'proceed'},
            {**summary(status='review_pending', code='review_pending'), 'assessment_status': 'governance_only'},
            {**summary(status='review_pending', code='review_pending'), 'assessment_status': 'needs_followup',
             'governance_recommendation': 'proceed', 'evaluator_assessment': 'accepted'},
            {**summary(status='stale', code='stale_snapshot'), 'governance_recommendation': 'proceed'},
        ]
        for value in values:
            with self.subTest(value=value['assessment_status']):
                result, _ = self.invoke(value)
                self.assertEqual(result['reason_codes'], ['observer_invalid_output'])

    def test_real_subprocess_strips_python_namespace_injection(self):
        injected = self.base / 'injected'
        injected.mkdir()
        (injected / 'injected_observer_module.py').write_text('raise RuntimeError("must not import")', encoding='utf-8')
        code = 'import os,sys,json,importlib.util;print(json.dumps({"path":os.getenv("PYTHONPATH"),"home":os.getenv("PYTHONHOME"),"isolated":sys.flags.isolated,"found":importlib.util.find_spec("injected_observer_module") is not None}))'
        with mock.patch.dict(os.environ, {'PYTHONPATH': str(injected), 'PYTHONHOME': 'invalid-home'}):
            exit_code, stdout, stderr = integration._run_child([sys.executable, '-I', '-B', '-c', code], root=self.root, timeout=10)
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, b'')
        self.assertEqual(json.loads(stdout), {'path': None, 'home': None, 'isolated': 1, 'found': False})

    def test_real_subprocess_timeout_and_output_limit(self):
        with self.assertRaises(integration.IntegrationError) as timed_out:
            integration._run_child([sys.executable, '-I', '-c', 'import time;time.sleep(5)'], root=self.root, timeout=0.2)
        self.assertEqual(str(timed_out.exception), 'observer_timeout')
        with self.assertRaises(integration.IntegrationError) as too_large:
            integration._run_child([sys.executable, '-I', '-c', 'import sys;sys.stdout.write("x"*1000000)'], root=self.root, timeout=10)
        self.assertEqual(str(too_large.exception), 'observer_output_limit')


class LifecycleHooksTests(ScratchTest):
    def setUp(self):
        self.make_scratch()
        self.root = self.base / 'repo'
        self.root.mkdir()
        for name in ('core', 'modules', 'shared'):
            shutil.copytree(SOURCE / name, self.root / name)
        for name in ('AGENTS.md', 'registry.json'):
            shutil.copyfile(SOURCE / name, self.root / name)
        (self.root / 'runtime').mkdir()
        for source in (SOURCE / 'runtime').glob('*.py'):
            shutil.copyfile(source, self.root / 'runtime' / source.name)
        shutil.copyfile(SOURCE / 'runtime/control-requirements.txt', self.root / 'runtime/control-requirements.txt')
        (self.root / '.gitignore').write_text('runs/\noutputs/\nwork/\nruntime/repos.local.json\n.venv-controls/\n', encoding='utf-8')
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(self.root)], check=True)
        r.git(self.root, 'config', 'user.name', 'Observer Test')
        r.git(self.root, 'config', 'user.email', 'observer@example.invalid')
        r.register('multi', self.root, self.root)
        self.remote = self.base / 'remote.git'
        subprocess.run(['git', 'init', '-q', '--bare', str(self.remote)], check=True)
        r.git(self.root, 'remote', 'add', 'origin', str(self.remote))
        a.write_json(self.root / '.agent-work/automation.json', {'schema_version': '1.0.0', 'enabled': True,
                     'remote': 'origin', 'expected_url': str(self.remote), 'branch': 'main'})
        r.git(self.root, 'add', '--', '.')
        r.git(self.root, 'commit', '-m', 'Fixture baseline')
        r.git(self.root, 'push', '-u', 'origin', 'main')
        a.init_task('coding', 'integration-task', 'Observe lifecycle', ['Preserve authorization'], self.root)
        self.scope = {'project': 'multi', 'service': 'agent-framework', 'environment': 'development', 'issue': 'fixture'}

    def bind(self):
        return r.bind('multi', 'integration-task', self.root, scope=self.scope)

    def complete(self):
        a.transition('integration-task', 'running', self.root)
        (self.root / 'outputs/integration-task/output.txt').write_text('fixture output', encoding='utf-8')
        (self.root / 'runs/integration-task/evidence/check.txt').write_text('fixture check passed', encoding='utf-8')
        result = a.read_json(self.root / 'runs/integration-task/result.json')
        result.update(status='completed', summary='Fixture complete', limitations=[], next_actions=[])
        result['artifacts'] = [{'path': 'outputs/integration-task/output.txt', 'description': 'Fixture', 'sha256': None}]
        result['verification'] = [{'id': 'check', 'name': 'Fixture check', 'method': 'Observed fixture', 'outcome': 'passed',
                                   'evidence': ['runs/integration-task/evidence/check.txt'], 'notes': ''}]
        result['acceptance_criteria'][0]['verification_ids'] = ['check']
        a.write_json(self.root / 'runs/integration-task/result.json', result)
        a.submit('integration-task', self.root)

    def test_no_config_checkpoint_has_legacy_return_shape(self):
        original_import = builtins.__import__
        def no_optional_module(name, *args, **kwargs):
            if name == 'control_integration':
                raise AssertionError('No-config lifecycle must not import the optional observer')
            return original_import(name, *args, **kwargs)
        with mock.patch.object(builtins, '__import__', side_effect=no_optional_module):
            result = self.bind()
            (self.root / 'legacy-owned.txt').write_text('legacy owned', encoding='utf-8')
            tracked = auto.track('integration-task', ['legacy-owned.txt'], self.root)
            self.complete()
            published = auto.finish('integration-task', self.root)
        self.assertEqual(set(result), {'task_id', 'repository_id', 'spec'})
        self.assertNotIn('observation', tracked)
        self.assertNotIn('observation', published)
        saved = a.read_json(self.root / '.agent-work/tasks/integration-task/record.json')
        self.assertNotIn('observation', saved)
        self.assertNotIn('## P0 observation', (self.root / '.agent-work/tasks/integration-task/spec.md').read_text(encoding='utf-8'))

    def test_checkpoint_and_track_hooks_run_after_conflicting_locks(self):
        a.write_json(self.root / '.agent-work/observation.json', profile())
        calls = []
        def observe(task_id, *, phase, root, **kwargs):
            self.assertFalse((root / '.agent-work/record.lock').exists())
            self.assertFalse((root / 'runs/integration-task/.publication.lock').exists())
            calls.append((task_id, phase))
            return summary(task_id, phase)
        with mock.patch.object(integration, 'invoke', side_effect=observe):
            result = self.bind()
            (self.root / 'owned.txt').write_text('owned', encoding='utf-8')
            tracked = auto.track('integration-task', ['owned.txt'], self.root)
        self.assertEqual(len(calls), 2)
        self.assertIn('observation', result)
        self.assertIn('observation', tracked)
        saved = a.read_json(self.root / '.agent-work/tasks/integration-task/record.json')
        self.assertEqual(saved['observation'], summary())
        self.assertNotIn('observation', saved['result'])
        specification = (self.root / '.agent-work/tasks/integration-task/spec.md').read_text(encoding='utf-8')
        self.assertIn('## P0 observation', specification)
        self.assertIn('obs-' + 'a' * 32, specification)

    def test_pre_push_observes_real_commit_and_never_becomes_authorization_gate(self):
        self.bind()
        (self.root / 'owned.txt').write_text('owned', encoding='utf-8')
        auto.track('integration-task', ['owned.txt'], self.root)
        self.complete()
        a.write_json(self.root / '.agent-work/observation.json', profile())
        before = r.git(self.root, 'rev-parse', 'HEAD')
        publication_calls = []
        def unavailable(task_id, *, phase, root, commit=None):
            if phase == 'publication':
                self.assertEqual(r.git(root, 'rev-parse', 'HEAD'), commit)
                self.assertNotEqual(commit, before)
                self.assertEqual(auto.remote_head(root, auto.policy(root)), before)
                publication_calls.append(commit)
            return integration._summary(task_id, phase, 'unavailable', 'environment_unavailable')
        with mock.patch.object(integration, 'invoke', side_effect=unavailable):
            result = auto.finish('integration-task', self.root)
        self.assertEqual(result['phase'], 'pushed')
        self.assertEqual(publication_calls, [result['commit']])
        self.assertEqual(result['observation']['status'], 'unavailable')
        self.assertEqual(auto.remote_head(self.root, auto.policy(self.root)), result['commit'])
        a.validate_result('integration-task', self.root)  # Sealed evidence unchanged.

    def test_selected_profile_without_optional_module_is_visible_unavailable(self):
        a.write_json(self.root / '.agent-work/observation.json', profile())
        original_import = builtins.__import__
        marker = 'private-import-error-marker'
        def missing_optional_module(name, *args, **kwargs):
            if name == 'control_integration':
                raise ImportError(marker)
            return original_import(name, *args, **kwargs)
        with mock.patch.object(builtins, '__import__', side_effect=missing_optional_module):
            result = self.bind()
        self.assertEqual(result['observation']['status'], 'unavailable')
        self.assertEqual(result['observation']['reason_codes'], ['observer_module_unavailable'])
        self.assertNotIn(marker, json.dumps(result))
        saved = a.read_json(self.root / '.agent-work/tasks/integration-task/record.json')
        self.assertEqual(saved['observation'], result['observation'])

    def test_real_observer_subprocess_and_mutable_workset_invalidation(self):
        real_python = SOURCE / '.venv-controls' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        self.assertTrue(real_python.is_file(), 'Configure .venv-controls for the integration test')
        a.write_json(self.root / '.agent-work/observation.json', profile())
        # Injection is confined to trusted test code; production profiles cannot
        # supply absolute/global interpreter paths or runner callbacks.
        with mock.patch.object(integration, '_interpreter', return_value=real_python):
            bound = self.bind()
            self.assertEqual(bound['observation']['status'], 'not_ready')
            target = self.root / 'owned.txt'
            target.write_text('first', encoding='utf-8')
            tracked = auto.track('integration-task', ['owned.txt'], self.root)
            observed = tracked['observation']
            self.assertIn(observed['status'], ('observed', 'review_pending'))
            self.assertFalse(observed['executable'])
            target.write_text('changed', encoding='utf-8')
            stale = integration.invoke('integration-task', command='status', root=self.root)
            self.assertEqual(stale['status'], 'stale')
            prior_file = self.root / 'runs/integration-task/observations' / (observed['record_id'] + '.json')
            invalid_bytes = b'{"synthetic-corruption":true}'
            prior_file.write_bytes(invalid_bytes)
            failed = integration.invoke('integration-task', root=self.root)
            self.assertEqual(failed['status'], 'error')
            refreshed = integration.invoke('integration-task', root=self.root, refresh=True)
            self.assertEqual(refreshed['status'], 'review_pending')
            self.assertNotEqual(refreshed['record_id'], observed['record_id'])
            self.assertEqual(refreshed['assessment_status'], 'none')
            self.assertEqual(prior_file.read_bytes(), invalid_bytes)
        observations = self.root / 'runs/integration-task/observations'
        self.assertTrue(any(observations.rglob('*.json')))


if __name__ == '__main__':
    unittest.main()
