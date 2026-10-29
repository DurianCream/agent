"""P0 workflow observations and declared reviews; never an execution gate."""
from __future__ import annotations

import sys
from pathlib import Path
sys.dont_write_bytecode = True
# The launcher uses isolated Python (-I). Only this fixed code directory is added.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager, ExitStack

import agentctl as a
import repoctl as r
import control_contracts as c
import control_policy as p

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / 'shared/schemas/control-workflow.schema.json'
MAX_PATHS = 128
MAX_WORKSET_BYTES = 64 * 1024 * 1024
REASONS = frozenset(('observed', 'observation_missing', 'scope_incomplete', 'profile_not_selected',
    'invalid_profile', 'binding_missing', 'repository_mismatch', 'manifest_missing', 'ownership_empty',
    'ownership_limit', 'path_unsupported', 'workset_limit', 'publication_not_ready', 'policy_invalid',
    'dependency_unavailable', 'input_invalid', 'record_invalid', 'assessment_invalid', 'assessment_stale',
    'assessment_conflict', 'stale_snapshot', 'stale_age', 'review_pending', 'observation_locked', 'workflow_internal'))


class WorkflowError(ValueError):
    def __init__(self, code, status='error'):
        self.code = code if code in REASONS else 'workflow_internal'
        self.status = status
        super().__init__(self.code)


def _fail(code, status='error'):
    raise WorkflowError(code, status) from None


def _now(now=None):
    value = datetime.now(timezone.utc) if now is None else now
    if not isinstance(value, datetime) or value.tzinfo is None:
        _fail('input_invalid')
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _time(value):
    return value.isoformat(timespec='seconds').replace('+00:00', 'Z')


def _parse_time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _safe(root, name, file=False):
    try:
        return a.relative(root, name, file=file)
    except a.ContractError:
        _fail('path_unsupported', 'not_ready')


def _validate(value, kind):
    schema = c.read_json(SCHEMA_PATH)
    schema['oneOf'] = [{'$ref': '#/$defs/' + kind}]
    return c.validate_schema_data(value, schema)


def _requirements(root):
    try:
        path = _safe(root, 'runtime/control-requirements.txt', True)
        installed = {}
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line or line.startswith('#'):
                continue
            name, version = line.split('==')
            installed[name] = importlib.metadata.version(name)
            if installed[name] != version:
                _fail('dependency_unavailable')
        return installed
    except (OSError, ValueError, importlib.metadata.PackageNotFoundError):
        _fail('dependency_unavailable')


def _run(task_id, root):
    try:
        a.identifier(task_id)
        path = _safe(root, 'runs/' + task_id)
        if not path.is_dir():
            _fail('binding_missing', 'not_ready')
        return path
    except a.ContractError:
        _fail('input_invalid')


def _profile(profile):
    try:
        value = _validate(profile, 'profile')
        if not value['enabled']:
            _fail('profile_not_selected', 'not_ready')
        if value['selector'] != {'project': 'multi', 'service': 'agent-framework', 'environment': 'development'}:
            _fail('profile_not_selected', 'not_ready')
        return value
    except c.ControlContractError as error:
        if error.code in ('dependency_missing', 'dependency_incompatible'):
            _fail('dependency_unavailable')
        _fail('invalid_profile', 'not_ready')


def _excluded(name, task_id):
    # Generated task records and this task's evidence can include observation copies.
    return (name.startswith('.agent-work/tasks/' + task_id + '/')
            or name in ('.agent-work/index.json', '.agent-work/INDEX.md')
            or name.startswith('runs/' + task_id + '/')
            or name in ('outputs/' + task_id + '/result.json', 'outputs/' + task_id + '/result.md'))


def _workset(repo, paths, task_id):
    if type(paths) is not list or any(type(name) is not str for name in paths):
        _fail('manifest_missing', 'not_ready')
    for name in paths:
        _safe(repo, name)  # Even excluded generated paths must be canonical.
    names = sorted(set(name for name in paths if not _excluded(name, task_id)))
    if not names:
        _fail('ownership_empty', 'not_ready')
    if len(names) > MAX_PATHS:
        _fail('ownership_limit', 'not_ready')
    output, total = [], 0
    for name in names:
        if name.startswith('.git/') or name == '.git':
            _fail('path_unsupported', 'not_ready')
        lower = name.lower()
        if (any(part.startswith('.env') or part in ('.aws', '.ssh', 'credentials', 'id_rsa', 'id_ed25519') for part in lower.split('/'))
                or lower.endswith(('.pem', '.key', '.p12', '.pfx'))):
            _fail('path_unsupported', 'not_ready')
        path = _safe(repo, name)
        if not path.exists():
            output.append({'path': name, 'state': 'missing', 'digest': None, 'size': 0})
            continue
        if not path.is_file():
            _fail('path_unsupported', 'not_ready')
        before = path.stat()
        if before.st_size + total > MAX_WORKSET_BYTES:
            _fail('workset_limit', 'not_ready')
        value = hashlib.sha256()
        read = 0
        # O_NOFOLLOW is available on POSIX; path-component link checks also apply
        # on Windows. These reads are observation, not an OS security boundary.
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, 'rb') as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                _fail('path_unsupported', 'not_ready')
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                read += len(chunk)
                if total + read > MAX_WORKSET_BYTES:
                    _fail('workset_limit', 'not_ready')
                value.update(chunk)
            after = os.fstat(stream.fileno())
        _safe(repo, name)  # Detect replaced link components after the bounded read.
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            _fail('stale_snapshot', 'not_ready')
        total += read
        output.append({'path': name, 'state': 'file', 'digest': 'sha256:' + value.hexdigest(), 'size': read})
    return output, total


def _committed_workset(repo, paths, base, commit):
    """Describe the complete committed change set without reading any blob bytes."""
    if type(paths) is not list or any(type(name) is not str for name in paths) or len(paths) != len(set(paths)):
        _fail('manifest_missing', 'not_ready')
    names = sorted(paths)
    if not names:
        _fail('ownership_empty', 'not_ready')
    if len(names) > MAX_PATHS:
        _fail('ownership_limit', 'not_ready')
    for name in names:
        # Syntactic only: immutable Git paths are not resolved in the worktree.
        if (not name or name.startswith('/') or '\\' in name or ':' in name or '\0' in name
                or any(part in ('', '.', '..') for part in name.split('/'))
                or name == '.git' or name.startswith('.git/')):
            _fail('path_unsupported', 'not_ready')
    parents = r.git(repo, 'rev-list', '--parents', '-n', '1', commit).split()
    if parents != [commit, base]:
        _fail('publication_not_ready', 'not_ready')
    changed = r.git(repo, 'diff-tree', '--no-commit-id', '--name-only', '-r', '-z', '--no-renames',
                    base, commit, strip=False).split('\0')
    if set(changed) - {''} != set(names):
        _fail('publication_not_ready', 'not_ready')
    raw = r.git(repo, '--literal-pathspecs', 'ls-tree', '-r', '-l', '-z', commit, '--', *names, strip=False)
    objects, total = {}, 0
    for item in raw.split('\0'):
        if not item:
            continue
        try:
            metadata, name = item.split('\t', 1)
            mode, kind, object_id, size_text = metadata.split()
        except ValueError:
            _fail('publication_not_ready', 'not_ready')
        if (name not in names or name in objects or kind != 'blob' or mode not in ('100644', '100755', '120000')
                or not re.fullmatch('[a-f0-9]{40}', object_id) or not re.fullmatch('[0-9]+', size_text)):
            _fail('path_unsupported', 'not_ready')
        size = int(size_text)
        total += size
        if total > MAX_WORKSET_BYTES:
            _fail('workset_limit', 'not_ready')
        objects[name] = {'path': name, 'state': 'committed_blob', 'git_mode': mode,
                         'git_type': kind, 'git_object_id': object_id, 'git_size': size}
    # Absence means deletion only because names already equal the actual changed
    # set from the verified parent/base, not because a working file is missing.
    entries = [objects.get(name, {'path': name, 'state': 'deleted', 'git_mode': None,
                                  'git_type': None, 'git_object_id': None, 'git_size': None}) for name in names]
    return entries, total


def _prepare(task_id, phase, profile, root, commit=None):
    if phase not in ('workspace', 'publication'):
        _fail('input_invalid')
    dependencies = _requirements(root)
    profile = _profile(profile)
    run = _run(task_id, root)
    try:
        _, task, _ = a.load_task(task_id, root)
        binding = c.read_json(_safe(run, 'repository.json', True))
    except (c.ControlContractError, a.ContractError):
        _fail('binding_missing', 'not_ready')
    if binding.get('task_id') != task_id:
        _fail('repository_mismatch')
    try:
        scope = r.validate_scope(binding.get('scope'))
    except a.ContractError:
        _fail('scope_incomplete', 'not_ready')
    if any(scope.get(k) != v for k, v in profile['selector'].items()) or binding.get('repository_id') != profile['repository_id']:
        _fail('profile_not_selected', 'not_ready')
    # repo() uses only fixed local Git reads and checks registered root and UUID.
    try:
        repo, entry = r.repo(binding['repository_id'], root)
        if entry['uuid'] != binding['repository_uuid'] or repo.resolve() != root.resolve():
            _fail('repository_mismatch')
        manifest = c.read_json(_safe(run, 'publication.json', True))
    except a.ContractError:
        _fail('repository_mismatch')
    except c.ControlContractError:
        _fail('manifest_missing', 'not_ready')
    if manifest.get('task_id') != task_id or not re.fullmatch('[a-f0-9]{40}', manifest.get('base_head', '')):
        _fail('manifest_missing', 'not_ready')
    if phase == 'publication' and (manifest.get('phase') not in ('committed', 'pushed') or not commit):
        _fail('publication_not_ready', 'not_ready')
    actual_commit = None
    if phase == 'publication':
        actual_commit = commit
        if (not isinstance(actual_commit, str) or not re.fullmatch('[a-f0-9]{40}', actual_commit)
                or manifest.get('commit') != actual_commit or r.git(repo, 'rev-parse', 'HEAD') != actual_commit
                or r.git(repo, 'cat-file', '-t', actual_commit) != 'commit'):
            _fail('publication_not_ready', 'not_ready')
        entries, total = _committed_workset(repo, manifest.get('staged_paths'), manifest['base_head'], actual_commit)
    else:
        entries, total = _workset(repo, manifest.get('paths'), task_id)
    branch = r.git(repo, 'symbolic-ref', '--short', 'HEAD')
    remotes = {name: r.git(repo, 'remote', 'get-url', *flags, '--all', 'origin').splitlines()
               for name, flags in [('fetch', ()), ('push', ('--push',))]}
    if any(len(urls) != 1 or r.clean_remote(urls[0]) != urls[0] for urls in remotes.values()):
        _fail('repository_mismatch')
    def redact_local(url):
        return url if url.startswith('https://') else 'non-https-sha256:' + hashlib.sha256(url.encode('utf-8')).hexdigest()
    target = {'branch': branch, 'fetch_url': redact_local(remotes['fetch'][0]), 'push_url': redact_local(remotes['push'][0])}
    automation = c.read_json(_safe(repo, '.agent-work/automation.json', True))
    if (set(automation) != {'schema_version', 'enabled', 'remote', 'expected_url', 'branch'}
            or automation.get('schema_version') != '1.0.0' or automation.get('remote') != 'origin'
            or type(automation.get('enabled')) is not bool or not isinstance(automation.get('branch'), str)):
        _fail('manifest_missing', 'not_ready')
    expected = automation.get('expected_url')
    if not isinstance(expected, str) or r.clean_remote(expected) != expected:
        _fail('repository_mismatch')
    policy = c.read_json(_safe(root, profile['policy_path'], True))
    try:
        c.validate_schema_data(policy, c.read_json(p.INPUT_SCHEMA))
        if policy.get('document_type') != 'observe_policy':
            _fail('policy_invalid')
    except c.ControlContractError:
        _fail('policy_invalid')
    policy_digest = c.canonical_digest(policy)
    if phase == 'publication':
        if not all(url.startswith('https://') for url in (expected, remotes['fetch'][0], remotes['push'][0])):
            _fail('path_unsupported', 'not_ready')
    automation = {**automation, 'expected_url': redact_local(expected)}
    code_files = [Path(__file__), Path(c.__file__), Path(p.__file__), ROOT / 'runtime/control_integration.py', SCHEMA_PATH,
                  c.SCHEMA_PATH, p.INPUT_SCHEMA, p.OUTPUT_SCHEMA, _safe(root, 'runtime/control-requirements.txt', True)]
    implementation = [{'name': path.name, 'digest': 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()} for path in code_files]
    snapshot = {'task_id': task_id, 'repository_id': binding['repository_id'], 'repository_uuid': binding['repository_uuid'],
                'scope': scope, 'base_head': manifest['base_head'], 'phase': phase, 'commit': actual_commit,
                'content_basis': 'git-object-metadata' if phase == 'publication' else 'working-tree-bytes',
                'owned_files': entries, 'target': target, 'declared_target': profile['target'],
                'authorization_setting': automation, 'policy_digest': policy_digest,
                'policy_ref': {'id': policy['id'], 'version': policy['version'], 'digest': policy_digest},
                'requester': {'subject_id': 'module-' + task['module']['id'], 'host_id': 'declared-local-host',
                              'session_id': task_id, 'role': task['module']['id']},
                'lifetime_seconds': min(profile['max_age_seconds'], policy['max_request_lifetime_seconds']),
                'request_budget': {'timeout_seconds': min(30, profile['max_age_seconds'], policy['max_request_lifetime_seconds']),
                                   'max_attempts': 1, 'max_bytes': total, 'max_cost_microunits': 0, 'max_actions': 1},
                'profile_digest': c.canonical_digest(profile), 'implementation_digest': c.canonical_digest(implementation),
                'runtime_identity': {'implementation': sys.implementation.name,
                                     'python_version': '.'.join(str(item) for item in sys.version_info[:3]),
                                     'virtual_environment': sys.prefix != sys.base_prefix, 'dependencies': dependencies}}
    # Validate bounds before saving; never truncate a workset to make it fit.
    try:
        snapshot_digest = c.canonical_digest(snapshot)
    except c.ControlContractError:
        _fail('workset_limit', 'not_ready')
    return {'run': run, 'repo': repo, 'task': task, 'binding': binding, 'manifest': manifest, 'profile': profile,
            'policy': policy, 'snapshot': snapshot, 'snapshot_digest': snapshot_digest, 'bytes': total}


def _store(run):
    directory = _safe(run, 'observations')
    directory.mkdir(exist_ok=True)
    return directory


def _index(directory):
    path = _safe(directory, 'index.json')
    return _validate(c.read_json(path), 'index') if path.exists() else {'schema_version': '0.1.0', 'latest': {}, 'assessments': {}}


@contextmanager
def _workflow_lock(directory):
    """Never auto-delete unknown/live/dead owner files after a killed child."""
    path = _safe(directory, '.workflow.lock')
    if path.exists():
        _fail('observation_locked', 'not_ready')
    with ExitStack() as stack:
        try:
            stack.enter_context(a.lock(path))
        except a.ContractError:
            _fail('observation_locked', 'not_ready')
        yield


def _seal(value):
    value['digest'] = c.canonical_digest({key: val for key, val in value.items() if key != 'digest'})
    return value


def _immutable(directory, name, value):
    path = _safe(directory, name)
    # Exclusive create never replaces historical records. Index is published
    # only after flush; a crash can leave an unindexed incomplete record.
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def _load_record(directory, record_id, assessment=False):
    pattern = 'asm-[a-f0-9]{32}' if assessment else 'obs-[a-f0-9]{32}'
    if not isinstance(record_id, str) or not re.fullmatch(pattern, record_id):
        _fail('record_invalid')
    try:
        value = c.read_json(_safe(directory, record_id + '.json', True))
        kind = 'assessment_record' if assessment else ('observation' if value.get('record_type') == 'workflow_observation' else 'error_record')
        _validate(value, kind)
        if (value['input']['task_id'] if assessment else value['task_id']) != directory.parent.name:
            _fail('record_invalid')
        if value['digest'] != c.canonical_digest({k: v for k, v in value.items() if k != 'digest'}):
            _fail('record_invalid')
        if assessment and value['assessment_id'] != record_id or not assessment and value['record_id'] != record_id:
            _fail('record_invalid')
        if kind == 'observation':
            c.validate_envelope(value['request'])
            c.validate_schema_data(value['context'], c.read_json(p.INPUT_SCHEMA))
            c.validate_schema_data(value['result'], c.read_json(p.OUTPUT_SCHEMA))
            c.validate_schema_data(value['policy'], c.read_json(p.INPUT_SCHEMA))
            if (value['snapshot_digest'] != c.canonical_digest(value['snapshot'])
                    or value['result']['request_digest'] != value['request']['digest']
                    or value['result']['context_digest'] != c.canonical_digest(value['context'])
                    or value['result']['policy_digest'] != value['snapshot']['policy_digest']
                    or value['context']['scope'] != value['snapshot']['scope']
                    or value['request']['payload']['scope'] != value['snapshot']['scope']
                    or value['task_id'] != value['snapshot']['task_id'] or value['phase'] != value['snapshot']['phase']
                    or value['policy'].get('document_type') != 'observe_policy'
                    or c.canonical_digest(value['policy']) != value['snapshot']['policy_digest']
                    or value['snapshot']['policy_ref'] != {'id': value['policy']['id'], 'version': value['policy']['version'],
                                                          'digest': value['snapshot']['policy_digest']}):
                _fail('record_invalid')
            expected_request, expected_context, expected_expiry = _inputs({'snapshot': value['snapshot']}, _parse_time(value['created_at']))
            for field in ('request_id', 'nonce', 'idempotency_key'):
                expected_request['payload'][field] = value['request']['payload'][field]
            expected_request['digest'] = c.envelope_digest(expected_request)
            if (value['request'] != expected_request or value['context'] != expected_context
                    or value['expires_at'] != _time(expected_expiry)
                    or value['result'] != p.evaluate_action(value['request'], value['context'], value['policy'],
                                                          now=_parse_time(value['created_at']))):
                _fail('record_invalid')
        return value
    except (c.ControlContractError, KeyError, TypeError, OSError):
        _fail('record_invalid')


def _summary(task_id, phase, status, reason, record=None, assessment='none', governance=None, evaluator=None):
    return {'ok': status == 'observed', 'task_id': task_id, 'phase': phase,
            'status': status, 'record_id': record.get('record_id') if record else None,
            'snapshot_digest': record.get('snapshot_digest') if record else None,
            'decision': record.get('result', {}).get('decision') if record else None,
            'reason_codes': [reason if reason in REASONS else 'workflow_internal'],
            'assessment_status': assessment, 'governance_recommendation': governance, 'evaluator_assessment': evaluator,
            'executable': False, 'authority_verified': False}


def _reviews(record, index, directory):
    refs = index['assessments'].get(record['record_id'], {})
    if not refs:
        return 'none', None, None
    governance = _load_record(directory, refs['governance'], True) if 'governance' in refs else None
    evaluator = _load_record(directory, refs['evaluator'], True) if 'evaluator' in refs else None
    if (governance and governance['input']['role'] != 'governance') or (evaluator and evaluator['input']['role'] != 'evaluator'):
        _fail('assessment_conflict')
    for review in (governance, evaluator):
        if review and any(review['input'][key] != expected for key, expected in (
                ('record_id', record['record_id']), ('task_id', record['task_id']),
                ('snapshot_digest', record['snapshot_digest']), ('policy_digest', record['snapshot']['policy_digest']),
                ('scope', record['snapshot']['scope']))):
            _fail('assessment_conflict')
    if evaluator:
        actor = record['request']['payload']['requester']
        if any(evaluator['input']['reviewer'][field] == actor[field] for field in ('subject_id', 'session_id')):
            return 'conflict', governance['input']['assessment'] if governance else None, evaluator['input']['assessment']
        if governance:
            if (evaluator['input']['governance_digest'] != governance['digest']
                    or any(evaluator['input']['reviewer'][field] == governance['input']['reviewer'][field]
                           for field in ('subject_id', 'session_id'))):
                return 'conflict', governance['input']['assessment'], evaluator['input']['assessment']
        elif not (evaluator['input']['governance_digest'] is None and 'governance_not_required' in evaluator['input']['reason_codes']
                  and record['result']['decision'] == 'allow' and record['result']['risk'] in ('low', 'medium')):
            return 'conflict', None, evaluator['input']['assessment']
        recommendation = governance['input']['assessment'] if governance else 'not_required'
        assessment = evaluator['input']['assessment']
        status = 'complete' if recommendation in ('proceed', 'not_required') and assessment == 'accepted' else 'needs_followup'
        return status, recommendation, assessment
    return ('governance_only', governance['input']['assessment'], None) if governance else ('conflict', None, None)


def _current(record, prepared, moment, index, directory):
    task_id, phase = record['task_id'], record['phase']
    if task_id != prepared['snapshot']['task_id'] or phase != prepared['snapshot']['phase']:
        _fail('record_invalid')
    if record['record_type'] == 'workflow_error':
        return _summary(task_id, phase, record['status'], record['reason_code'], record)
    if record['snapshot_digest'] != prepared['snapshot_digest']:
        return _summary(task_id, phase, 'stale', 'stale_snapshot', record)
    if moment >= _parse_time(record['expires_at']) or moment < _parse_time(record['created_at']):
        return _summary(task_id, phase, 'stale', 'stale_age', record)
    reviews, governance, evaluator = _reviews(record, index, directory)
    if reviews == 'complete':
        return _summary(task_id, phase, 'observed', 'observed', record, reviews, governance, evaluator)
    return _summary(task_id, phase, 'review_pending', 'review_pending', record, reviews, governance, evaluator)


def _inputs(prepared, moment):
    snapshot = prepared['snapshot']
    scope, task_id = snapshot['scope'], snapshot['task_id']
    actor = snapshot['requester']
    paths = [entry['path'] for entry in snapshot['owned_files']]
    workset_digest = c.canonical_digest(snapshot['owned_files'])
    phase = snapshot['phase']
    ttl = snapshot['lifetime_seconds']
    expiry = moment + timedelta(seconds=ttl)
    target_id = 'repository-' + snapshot['repository_id']
    publication = None
    artifacts = []
    if phase == 'publication':
        publication = {'remote': 'origin', 'remote_url': snapshot['target']['push_url'], 'branch': snapshot['target']['branch'],
                       'commit': snapshot['commit'], 'owned_manifest_digest': workset_digest}
        artifacts = [{'id': 'owned-workset', 'digest': workset_digest, 'media_type': 'application/json'}]
        params = publication
    else:
        params = {'paths': paths}
    adapter = 'repo.publish' if phase == 'publication' else 'workspace.inspect'
    setting = snapshot['authorization_setting']
    auth_publication = ({**publication, 'remote_url': setting['expected_url'], 'branch': setting['branch']}
                        if publication else None)
    authority = {'kind': 'standing' if publication else 'task', 'repository_id': snapshot['repository_id'],
                 'task_id': task_id, 'scope': scope, 'subject_id': actor['subject_id'], 'target_id': target_id,
                 'adapters': [adapter], 'paths': paths, 'artifact_digests': [workset_digest] if publication else [],
                 'publication': auth_publication, 'expires_at': None}
    if publication and setting.get('enabled') is not True:
        authority = None
    context = {'document_type': 'observe_context', 'schema_version': '0.1.0', 'repository_id': snapshot['repository_id'],
               'task_id': task_id, 'scope': scope, 'requester': actor,
               'target': {'id': target_id, 'environment': scope['environment'], **snapshot['declared_target'],
                          'allowed_operations': [], 'resource_ids': []}, 'authorization': authority}
    request = {'record_type': 'action_request', 'schema_version': '0.1.0', 'payload': {
        'request_id': str(uuid.uuid4()), 'task_id': task_id, 'repository_id': snapshot['repository_id'], 'scope': scope,
        'requester': actor, 'adapter': adapter, 'parameters': params, 'artifacts': artifacts,
        'policy_ref': snapshot['policy_ref'],
        'issued_at': _time(moment), 'expires_at': _time(expiry), 'nonce': uuid.uuid4().hex, 'idempotency_key': str(uuid.uuid4()),
        'budget': snapshot['request_budget']}, 'signature': None}
    request['digest'] = c.envelope_digest(request)
    return request, context, expiry


def _supersession(directory, record_id, prepared, moment, index):
    """Bounded recovery trace, not approval of the old record's contents."""
    trace = {'explicit_refresh': True, 'previous_record_id': record_id,
             'previous_file_digest': None, 'previous_validation': 'missing'}
    if record_id is None:
        return trace
    if not re.fullmatch('obs-[a-f0-9]{32}', record_id):
        _fail('record_invalid')
    path = _safe(directory, record_id + '.json')
    if not path.exists():
        return trace
    if not path.is_file():
        _fail('record_invalid')
    with path.open('rb') as stream:
        data = stream.read(c.MAX_INPUT_BYTES + 1)
    if len(data) > c.MAX_INPUT_BYTES:
        trace['previous_validation'] = 'oversized'
        return trace
    trace['previous_file_digest'] = 'sha256:' + hashlib.sha256(data).hexdigest()
    try:
        previous = _load_record(directory, record_id)
        state = _current(previous, prepared, moment, index, directory)['status']
        trace['previous_validation'] = 'stale' if state == 'stale' else ('error' if previous['record_type'] == 'workflow_error' else 'valid')
    except WorkflowError as error:
        if error.code == 'path_unsupported':
            raise
        trace['previous_validation'] = 'invalid'
    return trace


def observe(task_id, phase, profile, root=ROOT, commit=None, now=None, refresh=False):
    root, moment = Path(root).resolve(), _now(now)
    try:
        prepared = _prepare(task_id, phase, profile, root, commit)
        directory = _store(prepared['run'])
        with _workflow_lock(directory):
            index = _index(directory)
            supersession = _supersession(directory, index['latest'].get(phase), prepared, moment, index) if refresh else None
            if phase in index['latest'] and not refresh:
                previous_id = index['latest'][phase]
                try:
                    previous = _load_record(directory, previous_id)
                except WorkflowError as error:
                    # Keep invalid history and its latest pointer visible until
                    # an explicit refresh requests a newly measured observation.
                    return _summary(task_id, phase, error.status, error.code, {'record_id': previous_id})
                current = _current(previous, prepared, moment, index, directory)
                if previous['record_type'] == 'workflow_error' and previous['reason_code'] == 'record_invalid':
                    return current
                if current['status'] in ('observed', 'review_pending'):
                    return current
            request, context, expiry = _inputs(prepared, moment)
            result = p.evaluate_action(request, context, prepared['policy'], now=moment)
            if result['reason_codes'][0] in ('invalid_request', 'invalid_context', 'invalid_policy', 'unsupported_record_type'):
                _fail('input_invalid')
            # Reject an unstable measurement; there is no target mutation to roll back.
            if _prepare(task_id, phase, profile, root, commit)['snapshot_digest'] != prepared['snapshot_digest']:
                _fail('stale_snapshot', 'not_ready')
            record = _seal({'record_type': 'workflow_observation', 'schema_version': '0.1.0',
                'record_id': 'obs-' + uuid.uuid4().hex, 'task_id': task_id, 'phase': phase,
                'created_at': _time(moment), 'expires_at': _time(expiry),
                'snapshot': prepared['snapshot'], 'snapshot_digest': prepared['snapshot_digest'],
                'request': request, 'context': context, 'policy': prepared['policy'], 'result': result,
                'provenance': {'invocation': 'control_policy.evaluate_action',
                    'meaning': 'actual-commit-publication-observation' if phase == 'publication' else 'owned-workset-inspection',
                    'authorization_source': ('missing' if context['authorization'] is None else
                        'declared-repository-automation-setting' if phase == 'publication' else 'declared-task-binding-and-owned-paths'),
                    'identity_authenticated': False, 'input_contents_stored': False},
                'executable': False, 'authority_verified': False})
            if supersession is not None:
                record['supersession'] = supersession
                _seal(record)
            _validate(record, 'observation')
            _immutable(directory, record['record_id'] + '.json', record)
            index['latest'][phase] = record['record_id']
            a.write_json(_safe(directory, 'index.json'), _validate(index, 'index'))
            return _current(record, prepared, moment, index, directory)
    except Exception as error:
        # A failed explicit recovery must not hide or replace the prior pointer.
        return _failure(task_id, phase, root, moment, error, persist=not refresh)


def _failure(task_id, phase, root, moment, error, persist=False):
    if isinstance(error, WorkflowError):
        code, state = error.code, error.status
    elif isinstance(error, c.ControlContractError) and error.code in ('dependency_missing', 'dependency_incompatible'):
        code, state = 'dependency_unavailable', 'error'
    elif isinstance(error, c.ControlContractError) and error.code in ('input_too_large', 'input_depth', 'input_nodes'):
        code, state = 'workset_limit', 'not_ready'
    else:
        code, state = 'workflow_internal', 'error'
    record = None
    if persist and phase in ('workspace', 'publication'):
        try:
            directory = _store(_run(task_id, root))
            with _workflow_lock(directory):
                index = _index(directory)
                record = _seal({'record_type': 'workflow_error', 'schema_version': '0.1.0',
                    'record_id': 'obs-' + uuid.uuid4().hex, 'task_id': task_id, 'phase': phase,
                    'created_at': _time(moment), 'status': state, 'reason_code': code,
                    'executable': False, 'authority_verified': False})
                _validate(record, 'error_record')
                _immutable(directory, record['record_id'] + '.json', record)
                index['latest'][phase] = record['record_id']
                a.write_json(_safe(directory, 'index.json'), _validate(index, 'index'))
        except Exception:
            pass  # No raw diagnostics, and never rewrite a broken record/index.
    return _summary(task_id if isinstance(task_id, str) and re.fullmatch('[a-z0-9-]{1,128}', task_id) else 'invalid-task',
                    phase if phase in ('workspace', 'publication') else 'workspace', state, code, record)


def status(task_id, profile, root=ROOT, now=None, phase='workspace'):
    root, moment = Path(root).resolve(), _now(now)
    try:
        run = _run(task_id, root)
        directory = _safe(run, 'observations')
        if not directory.exists():
            return _summary(task_id, phase, 'missing', 'observation_missing')
        if _safe(directory, '.workflow.lock').exists():
            _fail('observation_locked', 'not_ready')
        index = _index(directory)
        if phase not in index['latest']:
            return _summary(task_id, phase, 'missing', 'observation_missing')
        record = _load_record(directory, index['latest'][phase])
        commit = record.get('snapshot', {}).get('commit')
        prepared = _prepare(task_id, phase, profile, root, commit)
        return _current(record, prepared, moment, index, directory)
    except Exception as error:
        return _failure(task_id, phase, root, moment, error)


def assess(task_id, record_id, assessment, profile, root=ROOT, now=None):
    root, moment = Path(root).resolve(), _now(now)
    phase = 'workspace'
    try:
        value = _validate(assessment, 'assessment_input')
        directory = _safe(_run(task_id, root), 'observations')
        with _workflow_lock(directory):
            index = _index(directory)
            record = _load_record(directory, record_id)
            phase = record['phase']
            if record['record_type'] != 'workflow_observation' or index['latest'].get(phase) != record_id:
                _fail('assessment_stale')
            prepared = _prepare(task_id, phase, profile, root, record['snapshot']['commit'])
            current = _current(record, prepared, moment, index, directory)
            if current['status'] not in ('observed', 'review_pending'):
                _fail('assessment_stale')
            expected = {'task_id': task_id, 'record_id': record_id, 'snapshot_digest': record['snapshot_digest'],
                        'policy_digest': record['snapshot']['policy_digest'], 'scope': record['snapshot']['scope']}
            if any(value[key] != item for key, item in expected.items()):
                _fail('assessment_invalid')
            refs = index['assessments'].get(record_id, {})
            if value['role'] == 'evaluator':
                governance = _load_record(directory, refs['governance'], True) if 'governance' in refs else None
                actor = record['request']['payload']['requester']
                if any(value['reviewer'][field] == actor[field] for field in ('subject_id', 'session_id')):
                    _fail('assessment_conflict')
                if governance:
                    if (value['governance_digest'] != governance['digest']
                            or any(value['reviewer'][field] == governance['input']['reviewer'][field]
                                   for field in ('subject_id', 'session_id'))):
                        _fail('assessment_conflict')
                elif not (value['governance_digest'] is None and 'governance_not_required' in value['reason_codes']
                          and record['result']['decision'] == 'allow' and record['result']['risk'] in ('low', 'medium')):
                    _fail('assessment_conflict')
            stored = _seal({'record_type': 'workflow_assessment', 'schema_version': '0.1.0',
                'assessment_id': 'asm-' + uuid.uuid4().hex, 'created_at': _time(moment), 'input': value,
                'identity_authenticated': False, 'executable': False, 'authority_verified': False})
            _validate(stored, 'assessment_record')
            _immutable(directory, stored['assessment_id'] + '.json', stored)
            index['assessments'].setdefault(record_id, {})[value['role']] = stored['assessment_id']
            a.write_json(_safe(directory, 'index.json'), _validate(index, 'index'))
            return _current(record, prepared, moment, index, directory)
    except Exception as error:
        if isinstance(error, c.ControlContractError):
            error = WorkflowError('assessment_invalid')
        return _failure(task_id, phase, root, moment, error)


class _Arguments(argparse.ArgumentParser):
    def error(self, message):
        _fail('input_invalid')


def main(argv=None):
    try:
        parser = _Arguments(description=__doc__)
        commands = parser.add_subparsers(dest='command', required=True, parser_class=_Arguments)
        for command in ('observe', 'status', 'assess'):
            sub = commands.add_parser(command)
            sub.add_argument('--task', required=True)
            sub.add_argument('--root', default=str(ROOT))
            sub.add_argument('--profile', required=True)
            if command != 'assess':
                sub.add_argument('--phase', choices=('workspace', 'publication'), default='workspace')
            if command == 'observe':
                sub.add_argument('--commit')
                sub.add_argument('--refresh', action='store_true')
            if command == 'assess':
                sub.add_argument('--record', required=True)
                sub.add_argument('--input', required=True)
        args = parser.parse_args(argv)
        profile = c.read_json(args.profile)
        if args.command == 'observe':
            result = observe(args.task, args.phase, profile, args.root, args.commit, refresh=args.refresh)
        elif args.command == 'status':
            result = status(args.task, profile, args.root, phase=args.phase)
        else:
            result = assess(args.task, args.record, c.read_json(args.input), profile, args.root)
        print(json.dumps(result, sort_keys=True, separators=(',', ':')))
        return 0 if result['status'] in ('observed', 'review_pending') else 2
    except Exception as error:
        result = _failure('invalid-task', 'workspace', ROOT, _now(), error)
        print(json.dumps(result, sort_keys=True, separators=(',', ':')))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
