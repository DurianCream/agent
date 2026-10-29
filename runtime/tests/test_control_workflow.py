"""P0 workflow tests: real policy calls, simulated local Git metadata, no targets."""
import copy
import hashlib
import json
import shutil
import stat
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE / 'runtime'))
import control_workflow as w


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.work = SOURCE / 'work'
        self.work.mkdir(exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix='workflow-test-', dir=self.work)).resolve()
        self.addCleanup(self.cleanup)
        for folder in ('core', 'modules', 'shared'):
            shutil.copytree(SOURCE / folder, self.root / folder)
        shutil.copy2(SOURCE / 'registry.json', self.root / 'registry.json')
        shutil.copy2(SOURCE / 'AGENTS.md', self.root / 'AGENTS.md')
        (self.root / 'runtime').mkdir()
        shutil.copy2(SOURCE / 'runtime/control-requirements.txt', self.root / 'runtime/control-requirements.txt')
        w.a.init_task('coding', 'sample', 'Observe a bounded workset', ['Check evidence'], self.root)
        w.a.transition('sample', 'running', self.root)
        self.run = self.root / 'runs/sample'
        self.scope = {'project': 'multi', 'service': 'agent-framework', 'environment': 'development', 'issue': 'sample-issue'}
        self.binding = {'schema_version': '1.0.0', 'repository_id': 'multi', 'repository_uuid': 'fixture-repository',
                        'task_id': 'sample', 'scope': self.scope}
        self.remote = 'https://example.invalid/fixture.git'
        self.branch = 'main'
        self.head = 'a' * 40
        self.automation = {'schema_version': '1.0.0', 'enabled': True, 'remote': 'origin', 'expected_url': self.remote, 'branch': self.branch}
        self.manifest = {'schema_version': '1.0.0', 'task_id': 'sample', 'base_head': self.head,
                         'paths': ['product.txt'], 'staged_paths': ['product.txt'], 'phase': 'begun', 'policy': self.automation}
        w.a.write_json(self.run / 'repository.json', self.binding)
        w.a.write_json(self.run / 'publication.json', self.manifest)
        w.a.write_json(self.root / 'runtime/repos.local.json', {'schema_version': '1.0.0', 'repositories': {
            'multi': {'path': str(self.root), 'uuid': 'fixture-repository'}}})
        w.a.write_json(self.root / '.agent-work/repository.json', {'id': 'multi', 'uuid': 'fixture-repository'})
        w.a.write_json(self.root / '.agent-work/automation.json', self.automation)
        (self.root / 'product.txt').write_text('candidate bytes', encoding='utf-8')
        self.profile = {'schema_version': '0.1.0', 'enabled': True, 'repository_id': 'multi',
            'selector': {'project': 'multi', 'service': 'agent-framework', 'environment': 'development'},
            'interpreter': {'windows': '.venv-controls/Scripts/python.exe', 'posix': '.venv-controls/bin/python'},
            'timeout_seconds': 30, 'max_age_seconds': 300, 'policy_path': 'shared/policies/execution-controls.observe.json',
            'target': {'data_classification': 'internal', 'risk_level': 'low', 'reversible': True}}
        self.now = datetime(2026, 10, 29, 6, 0, tzinfo=timezone.utc)
        self.git_calls = []
        self.real_git = w.r.git
        self.commit_parent = 'a' * 40
        self.commit_changed_paths = None
        self.tree_metadata = {'product.txt': ('100644', 'blob', 'c' * 40, '15')}
        self.git = mock.patch.object(w.r, 'git', side_effect=self.local_git)
        self.git.start()
        self.addCleanup(self.git.stop)

    def cleanup(self):
        if not self.root.is_relative_to(self.work.resolve()) or not self.root.name.startswith('workflow-test-'):
            raise RuntimeError('Unsafe fixture cleanup')
        def readonly_fixture_file(function, name, error_info):
            candidate = Path(name)
            if (not isinstance(error_info[1], PermissionError) or candidate.is_symlink()
                    or not candidate.resolve().is_relative_to(self.root) or not candidate.is_file()):
                raise error_info[1]
            candidate.chmod(candidate.stat().st_mode | stat.S_IWRITE)
            function(name)
        shutil.rmtree(self.root, onerror=readonly_fixture_file)

    def local_git(self, path, *args, **kwargs):
        self.git_calls.append(args)
        if args == ('rev-parse', '--show-toplevel'):
            return str(self.root)
        if args == ('symbolic-ref', '--short', 'HEAD'):
            return self.branch
        if args[0] == 'remote':
            return self.remote
        if args == ('rev-parse', 'HEAD'):
            return self.head
        if args[0] == 'cat-file':
            return 'commit'
        if args[0] == 'rev-list':
            return self.head + ' ' + self.commit_parent
        if args[0] == 'diff-tree':
            return '\0'.join(self.commit_changed_paths if self.commit_changed_paths is not None else self.manifest['staged_paths']) + '\0'
        if args[:2] == ('--literal-pathspecs', 'ls-tree'):
            names = args[args.index('--') + 1:]
            return ''.join(' '.join(self.tree_metadata[name]) + '\t' + name + '\0' for name in names if name in self.tree_metadata)
        raise AssertionError('Unexpected Git operation')

    def observe(self, phase='workspace', **kwargs):
        return w.observe('sample', phase, self.profile, self.root, now=self.now, **kwargs)

    def status(self, **kwargs):
        return w.status('sample', self.profile, self.root, now=kwargs.pop('now', self.now), **kwargs)

    def record(self, summary):
        return w.c.read_json(self.run / 'observations' / (summary['record_id'] + '.json'))

    def assessment(self, summary, role='governance', **changes):
        record = self.record(summary)
        value = {'schema_version': '0.1.0', 'task_id': 'sample', 'record_id': summary['record_id'],
                 'snapshot_digest': summary['snapshot_digest'], 'policy_digest': record['snapshot']['policy_digest'],
                 'scope': self.scope, 'role': role,
                 'reviewer': {'subject_id': role + '-person', 'host_id': 'declared-host', 'session_id': role + '-session',
                              'role': 'policy-manager' if role == 'governance' else 'evaluator'},
                 'assessment': 'proceed' if role == 'governance' else 'accepted',
                 'reason_codes': ['bounds_confirmed' if role == 'governance' else 'criteria_met'], 'governance_digest': None}
        if role == 'evaluator':
            index = w.c.read_json(self.run / 'observations/index.json')
            governance_id = index['assessments'].get(summary['record_id'], {}).get('governance')
            if governance_id:
                value['governance_digest'] = w.c.read_json(self.run / 'observations' / (governance_id + '.json'))['digest']
        value.update(changes)
        return value

    def assess(self, summary, value):
        return w.assess('sample', summary['record_id'], value, self.profile, self.root, self.now)

    def test_real_policy_invocation_and_unchanged_cache(self):
        with mock.patch.object(w.p, 'evaluate_action', wraps=w.p.evaluate_action) as call:
            first = self.observe()
            second = self.observe()
        # One new observation plus one deterministic replay to validate cache data.
        self.assertEqual(call.call_count, 2)
        self.assertEqual(first['record_id'], second['record_id'])
        self.assertEqual(first['decision'], 'allow')
        self.assertEqual(first['status'], 'review_pending')
        self.assertFalse(first['ok'])
        record = self.record(first)
        self.assertEqual(record['request']['payload']['adapter'], 'workspace.inspect')
        self.assertEqual(record['provenance']['meaning'], 'owned-workset-inspection')
        self.assertFalse(first['executable'])
        self.assertFalse(first['authority_verified'])
        self.assertNotIn('candidate bytes', json.dumps(record))
        self.assertEqual((self.root / 'product.txt').read_text(), 'candidate bytes')

    def test_deny_and_require_review_are_real_observations(self):
        for risk, expected in [('critical', 'deny'), ('high', 'require_review')]:
            self.profile['target']['risk_level'] = risk
            value = self.observe()
            self.assertEqual(value['decision'], expected)
            self.assertFalse(value['executable'])

    def test_missing_empty_and_unknown_scope_are_explicit(self):
        self.assertEqual(self.status()['status'], 'missing')
        self.manifest['paths'] = []
        w.a.write_json(self.run / 'publication.json', self.manifest)
        value = self.observe()
        self.assertEqual(value['status'], 'not_ready')
        self.assertEqual(value['reason_codes'], ['ownership_empty'])
        del self.binding['scope']['environment']
        w.a.write_json(self.run / 'repository.json', self.binding)
        self.assertEqual(self.observe()['reason_codes'], ['scope_incomplete'])

    def test_production_is_not_inferred_or_enabled(self):
        self.binding['scope']['environment'] = 'production'
        w.a.write_json(self.run / 'repository.json', self.binding)
        self.assertEqual(self.observe()['reason_codes'], ['profile_not_selected'])

    def test_content_scope_target_and_policy_changes_are_stale(self):
        self.observe()
        (self.root / 'product.txt').write_text('changed')
        self.assertEqual(self.status()['status'], 'stale')
        self.observe()
        self.binding['scope']['issue'] = 'different-issue'
        w.a.write_json(self.run / 'repository.json', self.binding)
        self.assertEqual(self.status()['status'], 'stale')
        self.observe()
        self.remote = 'https://example.invalid/different.git'
        self.assertEqual(self.status()['status'], 'stale')
        self.observe()
        path = self.root / self.profile['policy_path']
        policy = w.c.read_json(path)
        policy['budget_limits']['max_bytes'] = 999
        w.a.write_json(path, policy)
        self.assertEqual(self.status()['status'], 'stale')

    def test_age_is_explicit_and_refresh_preserves_old_record(self):
        first = self.observe()
        path = self.run / 'observations' / (first['record_id'] + '.json')
        before = path.read_bytes()
        self.assertEqual(self.status(now=self.now + timedelta(seconds=300))['reason_codes'], ['stale_age'])
        self.now += timedelta(seconds=301)
        second = self.observe()
        self.assertNotEqual(first['record_id'], second['record_id'])
        self.assertEqual(path.read_bytes(), before)

    def test_own_commit_and_managed_records_do_not_self_invalidate(self):
        first = self.observe()
        self.head = 'b' * 40
        self.manifest.update(phase='committed', commit=self.head)
        self.manifest['paths'] += ['runs/sample/evidence/check.json', '.agent-work/tasks/sample/record.json']
        w.a.write_json(self.run / 'publication.json', self.manifest)
        w.a.write_json(self.run / 'evidence/check.json', {'generated': True})
        self.assertEqual(self.status()['record_id'], first['record_id'])
        self.assertEqual(self.status()['status'], 'review_pending')

    def test_publication_requires_actual_recorded_commit(self):
        self.assertEqual(self.observe('publication')['reason_codes'], ['publication_not_ready'])
        self.head = 'b' * 40
        self.manifest.update(phase='committed', commit=self.head)
        w.a.write_json(self.run / 'publication.json', self.manifest)
        value = self.observe('publication', commit=self.head)
        self.assertEqual(value['decision'], 'allow')
        record = self.record(value)
        self.assertEqual(record['request']['payload']['parameters']['commit'], self.head)
        self.assertEqual(record['context']['authorization']['kind'], 'standing')
        self.assertNotIn('ls-remote', [args[0] for args in self.git_calls])

    def test_publication_uses_actual_staged_set_not_uncommitted_intended_outputs(self):
        self.manifest['paths'].append('outputs/sample/ignored-report.md')
        (self.root / 'outputs/sample').mkdir(parents=True, exist_ok=True)
        (self.root / 'outputs/sample/ignored-report.md').write_text('not published')
        self.head = 'b' * 40
        self.manifest.update(phase='committed', commit=self.head)
        w.a.write_json(self.run / 'publication.json', self.manifest)
        summary = self.observe('publication', commit=self.head)
        self.assertEqual(summary['decision'], 'allow')
        self.assertEqual([entry['path'] for entry in self.record(summary)['snapshot']['owned_files']], ['product.txt'])

    def test_committed_metadata_includes_managed_deleted_and_tab_unicode_paths(self):
        unusual = 'docs/한글 name\tpart.md'
        managed = '.agent-work/tasks/sample/한글 [보고서].md'
        names = [unusual, managed, 'deleted.txt']
        self.tree_metadata = {unusual: ('100644', 'blob', 'd' * 40, '7'), managed: ('100644', 'blob', 'e' * 40, '9')}
        self.commit_changed_paths = names
        self.head = 'b' * 40
        entries, size = w._committed_workset(self.root, names, self.commit_parent, self.head)
        self.assertEqual(size, 16)
        by_name = {entry['path']: entry for entry in entries}
        self.assertEqual(set(by_name), set(names))
        self.assertEqual(by_name[unusual]['git_object_id'], 'd' * 40)
        self.assertEqual(by_name['deleted.txt']['state'], 'deleted')
        self.assertIsNone(by_name['deleted.txt']['git_object_id'])

    def test_publication_changed_set_base_and_non_blob_are_checked(self):
        self.head = 'b' * 40
        self.manifest.update(phase='committed', commit=self.head)
        w.a.write_json(self.run / 'publication.json', self.manifest)
        self.commit_changed_paths = ['product.txt', 'unowned.txt']
        self.assertEqual(self.observe('publication', commit=self.head)['reason_codes'], ['publication_not_ready'])
        self.commit_changed_paths = None
        self.commit_parent = 'd' * 40
        self.assertEqual(self.observe('publication', commit=self.head)['reason_codes'], ['publication_not_ready'])
        self.commit_parent = self.manifest['base_head']
        self.tree_metadata['product.txt'] = ('160000', 'commit', 'c' * 40, '-')
        self.assertEqual(self.observe('publication', commit=self.head)['reason_codes'], ['path_unsupported'])

    def real_repository(self, baseline_path=None, crlf=False):
        git = self.real_git
        git(self.root, 'init', '--initial-branch=main')
        git(self.root, 'config', 'user.name', 'Workflow Fixture')
        git(self.root, 'config', 'user.email', 'fixture@example.invalid')
        git(self.root, 'config', 'core.autocrlf', 'true' if crlf else 'false')
        git(self.root, 'remote', 'add', 'origin', self.remote)
        if baseline_path:
            (self.root / baseline_path).write_text('old\n', encoding='utf-8')
            git(self.root, 'add', '--', baseline_path)
        git(self.root, 'commit', '--allow-empty', '-m', 'Fixture baseline')
        return git(self.root, 'rev-parse', 'HEAD')

    def real_publication(self, base, paths):
        commit = self.real_git(self.root, 'rev-parse', 'HEAD')
        self.manifest.update(base_head=base, phase='committed', commit=commit, staged_paths=paths)
        w.a.write_json(self.run / 'publication.json', self.manifest)
        return commit

    def test_real_git_assume_unchanged_cannot_substitute_worktree_bytes(self):
        base = self.real_repository()
        path = self.root / 'product.txt'
        path.write_bytes(b'one\n')
        self.real_git(self.root, 'add', '--', 'product.txt')
        self.real_git(self.root, 'commit', '-m', 'Committed one')
        commit = self.real_publication(base, ['product.txt'])
        self.real_git(self.root, 'update-index', '--assume-unchanged', 'product.txt')
        path.write_bytes(b'two\n')
        self.assertEqual(self.real_git(self.root, 'diff', '--name-only', commit, '--', 'product.txt'), '')
        original_open = Path.open

        def no_product_read(candidate, *args, **kwargs):
            if candidate == path:
                raise AssertionError('Publication must not read working file bytes')
            return original_open(candidate, *args, **kwargs)

        with mock.patch.object(w.r, 'git', wraps=self.real_git) as calls, mock.patch.object(Path, 'open', no_product_read):
            value = self.observe('publication', commit=commit)
        self.assertEqual(value['decision'], 'allow')
        snapshot = self.record(value)['snapshot']
        self.assertEqual(snapshot['content_basis'], 'git-object-metadata')
        self.assertEqual(snapshot['owned_files'], [{'path': 'product.txt', 'state': 'committed_blob',
            'git_mode': '100644', 'git_type': 'blob', 'git_object_id': hashlib.sha1(b'blob 4\0one\n').hexdigest(), 'git_size': 4}])
        self.assertEqual(path.read_bytes(), b'two\n')
        self.assertFalse(any(call.args[1:3] == ('cat-file', '-p') or 'show' in call.args[1:] for call in calls.call_args_list))

    def test_real_git_crlf_deletion_and_managed_files_use_commit_metadata(self):
        base = self.real_repository('removed.txt', crlf=True)
        path = self.root / 'product.txt'
        path.write_bytes(b'one\r\n')
        (self.root / 'removed.txt').unlink()
        managed = '.agent-work/tasks/sample/한글 [보고서].md'
        report = self.root / managed
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_bytes(b'report\n')
        paths = ['product.txt', 'removed.txt', managed]
        self.real_git(self.root, '--literal-pathspecs', 'add', '--', *paths)
        self.real_git(self.root, 'commit', '-m', 'CRLF deletion and managed metadata')
        commit = self.real_publication(base, paths)
        with mock.patch.object(w.r, 'git', wraps=self.real_git):
            value = self.observe('publication', commit=commit)
        self.assertEqual(value['decision'], 'allow')
        entries = {entry['path']: entry for entry in self.record(value)['snapshot']['owned_files']}
        self.assertEqual(set(entries), set(paths))
        self.assertEqual(entries['product.txt']['git_size'], 4)
        self.assertEqual(entries['product.txt']['git_object_id'], hashlib.sha1(b'blob 4\0one\n').hexdigest())
        self.assertEqual(entries['removed.txt']['state'], 'deleted')
        self.assertEqual(entries[managed]['state'], 'committed_blob')
        self.assertEqual(path.read_bytes(), b'one\r\n')

    def test_missing_file_marker_and_new_file_invalidate_cache(self):
        (self.root / 'product.txt').unlink()
        first = self.observe()
        self.assertEqual(self.record(first)['snapshot']['owned_files'][0]['state'], 'missing')
        (self.root / 'product.txt').write_text('new file')
        self.assertEqual(self.status()['status'], 'stale')

    def test_missing_standing_authority_yields_deny_without_new_grant(self):
        self.automation['enabled'] = False
        w.a.write_json(self.root / '.agent-work/automation.json', self.automation)
        self.head = 'b' * 40
        self.manifest.update(phase='committed', commit=self.head)
        w.a.write_json(self.run / 'publication.json', self.manifest)
        value = self.observe('publication', commit=self.head)
        self.assertEqual(value['decision'], 'deny')
        self.assertIsNone(self.record(value)['context']['authorization'])

    def test_assessments_link_exact_record_and_remain_advisory(self):
        first = self.observe()
        governance = self.assess(first, self.assessment(first))
        self.assertEqual(governance['assessment_status'], 'governance_only')
        evaluated = self.assess(first, self.assessment(first, 'evaluator'))
        self.assertEqual(evaluated['assessment_status'], 'complete')
        self.assertEqual(evaluated['status'], 'observed')
        self.assertFalse(evaluated['executable'])

    def test_evaluator_accepts_correct_deny_without_permission(self):
        self.profile['target']['risk_level'] = 'critical'
        first = self.observe()
        self.assess(first, self.assessment(first, assessment='revise'))
        reviewed = self.assess(first, self.assessment(first, 'evaluator'))
        self.assertEqual(reviewed['decision'], 'deny')
        self.assertEqual(reviewed['status'], 'review_pending')
        self.assertEqual(reviewed['assessment_status'], 'needs_followup')
        self.assertEqual(reviewed['governance_recommendation'], 'revise')
        self.assertEqual(reviewed['evaluator_assessment'], 'accepted')
        self.assertFalse(reviewed['ok'])
        self.assertFalse(reviewed['authority_verified'])

    def test_escalate_inconclusive_and_rework_are_not_success_shaped(self):
        first = self.observe()
        self.assess(first, self.assessment(first, assessment='escalate'))
        value = self.assess(first, self.assessment(first, 'evaluator', assessment='inconclusive'))
        self.assertEqual((value['status'], value['ok'], value['assessment_status']), ('review_pending', False, 'needs_followup'))
        self.assertEqual((value['governance_recommendation'], value['evaluator_assessment']), ('escalate', 'inconclusive'))
        value = self.assess(first, self.assessment(first, 'evaluator', assessment='rework'))
        self.assertEqual(value['evaluator_assessment'], 'rework')
        self.assertFalse(value['ok'])

    def test_governance_not_required_must_be_explicit_and_bounded(self):
        first = self.observe()
        self.assertEqual(self.assess(first, self.assessment(first, 'evaluator'))['reason_codes'], ['assessment_conflict'])
        value = self.assessment(first, 'evaluator', reason_codes=['criteria_met', 'governance_not_required'])
        self.assertEqual(self.assess(first, value)['assessment_status'], 'complete')
        self.profile['target']['risk_level'] = 'high'
        next_record = self.observe()
        value = self.assessment(next_record, 'evaluator', reason_codes=['criteria_met', 'governance_not_required'])
        self.assertEqual(self.assess(next_record, value)['reason_codes'], ['assessment_conflict'])

    def test_identity_conflict_and_forged_or_stale_references_rejected(self):
        first = self.observe()
        self.assess(first, self.assessment(first))
        value = self.assessment(first, 'evaluator')
        value['reviewer']['subject_id'] = 'governance-person'
        self.assertEqual(self.assess(first, value)['reason_codes'], ['assessment_conflict'])
        value = self.assessment(first, 'evaluator', snapshot_digest='sha256:' + '0' * 64)
        self.assertEqual(self.assess(first, value)['reason_codes'], ['assessment_invalid'])
        (self.root / 'product.txt').write_text('new version')
        self.assertEqual(self.assess(first, self.assessment(first, 'evaluator'))['reason_codes'], ['assessment_stale'])

    def test_publication_cannot_reuse_workspace_assessment(self):
        first = self.observe()
        self.head = 'b' * 40
        self.manifest.update(phase='committed', commit=self.head)
        w.a.write_json(self.run / 'publication.json', self.manifest)
        published = self.observe('publication', commit=self.head)
        value = self.assessment(first)
        result = w.assess('sample', published['record_id'], value, self.profile, self.root, self.now)
        self.assertEqual(result['reason_codes'], ['assessment_invalid'])

    def test_malicious_ids_and_paths_do_not_escape(self):
        self.assertEqual(w.observe('../escape', 'workspace', self.profile, self.root, now=self.now)['status'], 'error')
        self.manifest['paths'] = ['../outside']
        w.a.write_json(self.run / 'publication.json', self.manifest)
        self.assertEqual(self.observe()['reason_codes'], ['path_unsupported'])
        self.assertFalse((self.root.parent / 'escape').exists())

    def test_symlink_and_sensitive_paths_are_not_read(self):
        self.manifest['paths'] = ['.env']
        w.a.write_json(self.run / 'publication.json', self.manifest)
        self.assertEqual(self.observe()['reason_codes'], ['path_unsupported'])
        self.manifest['paths'] = ['product.txt']
        w.a.write_json(self.run / 'publication.json', self.manifest)
        original = Path.is_symlink
        with mock.patch.object(Path, 'is_symlink', lambda path: path.name == 'product.txt' or original(path)):
            self.assertEqual(self.observe()['reason_codes'], ['path_unsupported'])

    def test_limits_are_not_silently_truncated(self):
        self.manifest['paths'] = ['file-' + str(i) for i in range(w.MAX_PATHS + 1)]
        w.a.write_json(self.run / 'publication.json', self.manifest)
        self.assertEqual(self.observe()['reason_codes'], ['ownership_limit'])
        self.manifest['paths'] = ['product.txt']
        w.a.write_json(self.run / 'publication.json', self.manifest)
        with mock.patch.object(w, 'MAX_WORKSET_BYTES', 1):
            self.assertEqual(self.observe()['reason_codes'], ['workset_limit'])

    def test_oversized_companion_record_is_explicitly_not_ready(self):
        original = w._validate

        def bounded(value, kind):
            if kind == 'observation':
                raise w.c.ControlContractError('input_too_large', 'Bounded record limit reached.')
            return original(value, kind)

        with mock.patch.object(w, '_validate', side_effect=bounded):
            value = self.observe()
        self.assertEqual((value['status'], value['reason_codes']), ('not_ready', ['workset_limit']))

    def test_corrupt_record_is_error_not_success(self):
        first = self.observe()
        path = self.run / 'observations' / (first['record_id'] + '.json')
        value = w.c.read_json(path)
        value['result']['decision'] = 'deny'
        w.a.write_json(path, value)
        self.assertEqual(self.status()['reason_codes'], ['record_invalid'])

    def test_explicit_refresh_recovers_legacy_record_without_reusing_reviews(self):
        first = self.observe()
        self.assess(first, self.assessment(first))
        self.assess(first, self.assessment(first, 'evaluator'))
        directory = self.run / 'observations'
        reviews = {p.name: p.read_bytes() for p in directory.glob('asm-*.json')}
        path = directory / (first['record_id'] + '.json')
        legacy = w.c.read_json(path)
        del legacy['policy']
        w.a.write_json(path, w._seal(legacy))
        old_bytes = path.read_bytes()
        self.assertEqual(self.status()['reason_codes'], ['record_invalid'])
        self.assertEqual(self.observe()['reason_codes'], ['record_invalid'])
        self.assertEqual(w.c.read_json(directory / 'index.json')['latest']['workspace'], first['record_id'])
        fresh = self.observe(refresh=True)
        self.assertNotEqual(fresh['record_id'], first['record_id'])
        self.assertEqual((fresh['status'], fresh['assessment_status'], fresh['ok']), ('review_pending', 'none', False))
        self.assertIsNone(fresh['governance_recommendation'])
        self.assertIsNone(fresh['evaluator_assessment'])
        trace = self.record(fresh)['supersession']
        self.assertEqual(trace, {'explicit_refresh': True, 'previous_record_id': first['record_id'],
                                'previous_file_digest': 'sha256:' + hashlib.sha256(old_bytes).hexdigest(),
                                'previous_validation': 'invalid'})
        self.assertEqual(path.read_bytes(), old_bytes)
        self.assertEqual({p.name: p.read_bytes() for p in directory.glob('asm-*.json')}, reviews)
        self.assertNotIn(fresh['record_id'], w.c.read_json(directory / 'index.json')['assessments'])

    def test_explicit_refresh_handles_malformed_bytes_and_calls_real_policy(self):
        first = self.observe()
        path = self.run / 'observations' / (first['record_id'] + '.json')
        raw = b'not-json-private-marker:\xff'
        path.write_bytes(raw)
        with mock.patch.object(w.p, 'evaluate_action', wraps=w.p.evaluate_action) as actual:
            fresh = self.observe(refresh=True)
        self.assertEqual(actual.call_count, 1)
        self.assertEqual(fresh['decision'], 'allow')
        trace = self.record(fresh)['supersession']
        self.assertEqual(trace['previous_file_digest'], 'sha256:' + hashlib.sha256(raw).hexdigest())
        self.assertEqual(trace['previous_validation'], 'invalid')
        self.assertNotIn('private-marker', json.dumps(self.record(fresh)))
        self.assertEqual(path.read_bytes(), raw)

    def test_explicit_refresh_does_not_repair_symlink_or_invalid_index(self):
        first = self.observe()
        directory = self.run / 'observations'
        before_index = (directory / 'index.json').read_bytes()
        original = Path.is_symlink
        with mock.patch.object(Path, 'is_symlink', lambda path: path.name == first['record_id'] + '.json' or original(path)):
            self.assertEqual(self.observe(refresh=True)['reason_codes'], ['path_unsupported'])
        self.assertEqual((directory / 'index.json').read_bytes(), before_index)
        (directory / 'index.json').write_bytes(b'invalid-index')
        self.assertEqual(self.observe(refresh=True)['status'], 'error')
        self.assertEqual((directory / 'index.json').read_bytes(), b'invalid-index')

    def test_explicit_refresh_of_valid_record_starts_new_unreviewed_snapshot(self):
        first = self.observe()
        fresh = self.observe(refresh=True)
        self.assertNotEqual(first['record_id'], fresh['record_id'])
        self.assertEqual(first['snapshot_digest'], fresh['snapshot_digest'])
        self.assertEqual(self.record(fresh)['supersession']['previous_validation'], 'valid')
        self.assertEqual(fresh['assessment_status'], 'none')

    def test_resealed_cross_task_context_and_decision_forgery_rejected(self):
        first = self.observe()
        path = self.run / 'observations' / (first['record_id'] + '.json')
        original = w.c.read_json(path)
        for field in ('task_id', 'repository_id'):
            value = copy.deepcopy(original)
            value['request']['payload'][field] = 'other-task'
            value['context'][field] = 'other-task'
            value['context']['authorization'][field] = 'other-task'
            value['request']['digest'] = w.c.envelope_digest(value['request'])
            value['result'] = w.p.evaluate_action(value['request'], value['context'], value['policy'], now=self.now)
            w.a.write_json(path, w._seal(value))
            self.assertEqual(self.status()['reason_codes'], ['record_invalid'])
        value = copy.deepcopy(original)
        value['result']['decision'] = 'deny'
        w.a.write_json(path, w._seal(value))
        self.assertEqual(self.status()['reason_codes'], ['record_invalid'])

    def test_schema_launcher_and_dependency_identity_are_freshness_inputs(self):
        original = Path.read_bytes
        changed = {'name': None}

        def measured(path):
            data = original(path)
            return data + b'\n' if path.name == changed['name'] else data

        with mock.patch.object(Path, 'read_bytes', measured):
            for name in ('control-envelope.schema.json', 'control-observe-policy.schema.json',
                         'control-observation.schema.json', 'control_integration.py', 'control-requirements.txt'):
                changed['name'] = None
                self.observe()
                changed['name'] = name
                self.assertEqual(self.status()['status'], 'stale', name)
        record = self.record(self.observe())
        self.assertIn('python_version', record['snapshot']['runtime_identity'])
        self.assertIn('jsonschema', record['snapshot']['runtime_identity']['dependencies'])
        self.assertNotIn(str(self.root), json.dumps(record['snapshot']['runtime_identity']))

    def test_same_uuid_different_checkout_is_rejected(self):
        with mock.patch.object(w.r, 'repo', return_value=(self.root.parent / 'different-clone', {'uuid': 'fixture-repository'})):
            self.assertEqual(self.observe()['reason_codes'], ['repository_mismatch'])

    def test_policy_exception_persists_safe_error_without_rewriting_task(self):
        task_bytes = (self.run / 'task.json').read_bytes()
        with mock.patch.object(w.p, 'evaluate_action', side_effect=RuntimeError('private-marker')):
            value = self.observe()
        self.assertEqual(value['status'], 'error')
        self.assertNotIn('private-marker', json.dumps(self.record(value)))
        self.assertEqual((self.run / 'task.json').read_bytes(), task_bytes)

    def test_lock_is_preserved_and_external_verified_recovery_allows_retry(self):
        first = self.observe()
        record_path = self.run / 'observations' / (first['record_id'] + '.json')
        preserved = record_path.read_bytes()
        lock = self.run / 'observations/.workflow.lock'
        lock.write_text('unknown-or-live-owner', encoding='utf-8')
        self.assertEqual(self.observe()['reason_codes'], ['observation_locked'])
        self.assertEqual(self.status()['reason_codes'], ['observation_locked'])
        self.assertEqual(lock.read_text(), 'unknown-or-live-owner')
        self.assertEqual(record_path.read_bytes(), preserved)
        # Test operator simulates separately verified stopped-process recovery.
        # Production procedure must verify PID/liveness/path and unchanged bytes;
        # the engine itself never probes/kills a PID or removes an old lock.
        lock.unlink()
        self.assertEqual(self.observe()['record_id'], first['record_id'])
        self.assertEqual(record_path.read_bytes(), preserved)


if __name__ == '__main__':
    unittest.main()
