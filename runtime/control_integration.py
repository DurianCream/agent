"""Stdlib-only launcher for optional advisory P0 workflow observations.

This invokes only the fixed repository observer in a configured local environment.
It does not authorize, block, or execute a business action or Git publication.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = '.agent-work/observation.json'
SCRIPT_PATH = 'runtime/control_workflow.py'
MAX_JSON_BYTES = 16384
MAX_CHILD_BYTES = 65536
IDENTIFIER = re.compile(r'(?=.{1,128}\Z)[a-z0-9]+(?:-[a-z0-9]+)*\Z')
DIGEST = re.compile(r'^sha256:[a-f0-9]{64}$')
RECORD_ID = re.compile(r'^obs-[a-f0-9]{32}$')
SCOPES = ('project', 'service', 'environment', 'issue')
STATUSES = {'missing', 'not_ready', 'error', 'stale', 'review_pending', 'observed'}
SUMMARY_FIELDS = {'ok', 'task_id', 'phase', 'status', 'record_id', 'snapshot_digest',
                  'decision', 'reason_codes', 'assessment_status', 'governance_recommendation',
                  'evaluator_assessment', 'executable', 'authority_verified'}
# These codes are output vocabulary, never raw child errors or user text.
WORKFLOW_REASONS = {
    'observed', 'observation_missing', 'scope_incomplete', 'profile_not_selected',
    'invalid_profile', 'binding_missing', 'repository_mismatch', 'manifest_missing',
    'ownership_empty', 'ownership_limit', 'path_unsupported', 'workset_limit',
    'publication_not_ready', 'policy_invalid', 'dependency_unavailable', 'input_invalid',
    'record_invalid', 'assessment_invalid', 'assessment_stale', 'assessment_conflict',
    'stale_snapshot', 'stale_age', 'review_pending', 'workflow_internal', 'observation_locked',
}


class IntegrationError(Exception):
    pass


def _summary(task_id, phase, status, code):
    return {'ok': False, 'task_id': task_id, 'phase': phase, 'status': status,
            'mode': 'observe', 'reason_codes': [code], 'record_id': None,
            'snapshot_digest': None, 'decision': None, 'assessment_status': 'none',
            'governance_recommendation': None, 'evaluator_assessment': None,
            'executable': False, 'authority_verified': False}


def _pairs(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise IntegrationError('invalid_json')
        data[key] = value
    return data


def _json_bytes(raw):
    if len(raw) > MAX_JSON_BYTES:
        raise IntegrationError('oversized_json')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(IntegrationError('invalid_json')))
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise IntegrationError('invalid_json') from None


def _read(path):
    with path.open('rb') as stream:
        return _json_bytes(stream.read(MAX_JSON_BYTES + 1))


def _relative(root, name, *, must_exist=True):
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or any(part in ('', '.', '..') for part in name.split('/'))):
        raise IntegrationError('unsafe_path')
    target = root.joinpath(*name.split('/'))
    # A repository-local virtual environment must use copies, not a link to an
    # arbitrary external executable. The profile cannot select a global Python.
    if not target.resolve().is_relative_to(root.resolve()):
        raise IntegrationError('unsafe_path')
    if must_exist and not target.is_file():
        raise IntegrationError('missing_file')
    return target


def load_profile(root=ROOT):
    root = Path(root).resolve()
    path = _relative(root, PROFILE_PATH, must_exist=False)
    if not path.exists():
        return None
    profile = _read(path)
    required = {'schema_version', 'enabled', 'repository_id', 'selector', 'interpreter',
                'timeout_seconds', 'max_age_seconds', 'policy_path', 'target'}
    if not isinstance(profile, dict) or set(profile) != required:
        raise IntegrationError('profile_invalid')
    if profile['schema_version'] != '0.1.0' or type(profile['enabled']) is not bool:
        raise IntegrationError('profile_invalid')
    if not isinstance(profile['repository_id'], str) or not IDENTIFIER.fullmatch(profile['repository_id']):
        raise IntegrationError('profile_invalid')
    selector = profile['selector']
    if not isinstance(selector, dict) or set(selector) != {'project', 'service', 'environment'}:
        raise IntegrationError('profile_invalid')
    if any(not isinstance(value, str) or not IDENTIFIER.fullmatch(value) for value in selector.values()):
        raise IntegrationError('profile_invalid')
    if profile['interpreter'] != {'windows': '.venv-controls/Scripts/python.exe', 'posix': '.venv-controls/bin/python'}:
        raise IntegrationError('profile_invalid')
    if type(profile['timeout_seconds']) is not int or not 1 <= profile['timeout_seconds'] <= 60:
        raise IntegrationError('profile_invalid')
    if type(profile['max_age_seconds']) is not int or not 30 <= profile['max_age_seconds'] <= 3600:
        raise IntegrationError('profile_invalid')
    if profile['policy_path'] != 'shared/policies/execution-controls.observe.json':
        raise IntegrationError('profile_invalid')
    if profile['target'] != {'data_classification': 'internal', 'risk_level': 'low', 'reversible': True}:
        raise IntegrationError('profile_invalid')
    return profile


def _binding(task_id, profile, root):
    binding = _read(_relative(root, f'runs/{task_id}/repository.json'))
    task = _read(_relative(root, f'runs/{task_id}/task.json'))
    if (not isinstance(binding, dict) or binding.get('task_id') != task_id
            or not isinstance(task, dict) or task.get('task_id') != task_id):
        raise IntegrationError('binding_invalid')
    scope = binding.get('scope')
    if (not isinstance(scope, dict) or set(scope) != set(SCOPES)
            or any(not isinstance(value, str) or not IDENTIFIER.fullmatch(value) for value in scope.values())):
        raise IntegrationError('binding_invalid')
    if binding.get('repository_id') != profile['repository_id']:
        return False
    registry = _read(_relative(root, 'runtime/repos.local.json'))
    repositories = registry.get('repositories') if isinstance(registry, dict) else None
    entry = repositories.get(binding['repository_id']) if isinstance(repositories, dict) else None
    if not isinstance(entry, dict) or entry.get('uuid') != binding.get('repository_uuid'):
        raise IntegrationError('binding_invalid')
    try:
        registered_root = Path(entry['path']).resolve()
    except (OSError, TypeError, ValueError, KeyError):
        raise IntegrationError('binding_invalid') from None
    if registered_root != root:
        raise IntegrationError('repository_mismatch')
    identity = _read(_relative(root, '.agent-work/repository.json'))
    if (identity.get('id') != binding['repository_id']
            or identity.get('uuid') != binding.get('repository_uuid')):
        raise IntegrationError('binding_invalid')
    return all(scope[key] == expected for key, expected in profile['selector'].items())


def _interpreter(profile, root):
    try:
        return _relative(root, profile['interpreter']['windows' if os.name == 'nt' else 'posix'])
    except IntegrationError:
        raise IntegrationError('environment_unavailable') from None


def _run_child(arguments, *, root, timeout):
    """Capture at most two bounded streams, kill on timeout/overflow, shell=False."""
    environment = {key: value for key, value in os.environ.items()
                   if key.upper() not in ('PYTHONPATH', 'PYTHONHOME')}
    environment.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
    process = subprocess.Popen(arguments, cwd=root, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
                               env=environment,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    chunks = [bytearray(), bytearray()]
    overflow = threading.Event()
    read_error = threading.Event()

    def consume(stream, index):
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                available = MAX_CHILD_BYTES - len(chunks[index])
                if len(chunk) > available:
                    overflow.set()
                    try:
                        process.kill()
                    except OSError:
                        pass
                    break
                chunks[index].extend(chunk)
        except (OSError, ValueError):
            read_error.set()
        finally:
            stream.close()

    threads = [threading.Thread(target=consume, args=(stream, number), daemon=True)
               for number, stream in enumerate((process.stdout, process.stderr))]
    for thread in threads:
        thread.start()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        for thread in threads:
            thread.join(timeout=1)
        raise IntegrationError('observer_timeout') from None
    for thread in threads:
        thread.join(timeout=1)
    if overflow.is_set() or any(thread.is_alive() for thread in threads):
        raise IntegrationError('observer_output_limit')
    if read_error.is_set():
        raise IntegrationError('observer_failed')
    return process.returncode, bytes(chunks[0]), bytes(chunks[1])


def _checked_summary(raw, task_id, phase, return_code, root):
    if not raw:
        raise IntegrationError('observer_empty_output')
    try:
        data = _json_bytes(raw)
    except IntegrationError:
        raise IntegrationError('observer_invalid_output') from None
    if not isinstance(data, dict) or set(data) != SUMMARY_FIELDS:
        raise IntegrationError('observer_invalid_output')
    if (type(data['ok']) is not bool or data['task_id'] != task_id
            or data['phase'] not in ('workspace', 'publication') or (phase is not None and data['phase'] != phase)
            or data['status'] not in STATUSES or data['executable'] is not False
            or data['authority_verified'] is not False):
        raise IntegrationError('observer_invalid_output')
    if data['record_id'] is not None and (not isinstance(data['record_id'], str) or not RECORD_ID.fullmatch(data['record_id'])):
        raise IntegrationError('observer_invalid_output')
    if data['snapshot_digest'] is not None and (not isinstance(data['snapshot_digest'], str) or not DIGEST.fullmatch(data['snapshot_digest'])):
        raise IntegrationError('observer_invalid_output')
    if data['decision'] not in (None, 'allow', 'deny', 'require_review') or data['assessment_status'] not in ('none', 'governance_only', 'complete', 'conflict', 'needs_followup'):
        raise IntegrationError('observer_invalid_output')
    governance = data['governance_recommendation']
    evaluator = data['evaluator_assessment']
    if (governance not in (None, 'proceed', 'revise', 'escalate', 'not_required')
            or evaluator not in (None, 'accepted', 'rework', 'inconclusive')):
        raise IntegrationError('observer_invalid_output')
    if data['status'] == 'observed':
        if (data['ok'] is not True or data['assessment_status'] != 'complete'
                or governance not in ('proceed', 'not_required') or evaluator != 'accepted'):
            raise IntegrationError('observer_invalid_output')
    elif data['ok'] is not False:
        raise IntegrationError('observer_invalid_output')
    if data['status'] == 'review_pending' and data['assessment_status'] == 'complete':
        raise IntegrationError('observer_invalid_output')
    if data['status'] in ('observed', 'review_pending'):
        if data['record_id'] is None or data['snapshot_digest'] is None or data['decision'] is None:
            raise IntegrationError('observer_invalid_output')
    if data['status'] == 'review_pending':
        assessment = data['assessment_status']
        if assessment == 'none' and (governance is not None or evaluator is not None):
            raise IntegrationError('observer_invalid_output')
        if assessment == 'governance_only' and (governance is None or evaluator is not None):
            raise IntegrationError('observer_invalid_output')
        if assessment == 'needs_followup' and not (governance in ('revise', 'escalate') or evaluator in ('rework', 'inconclusive')):
            raise IntegrationError('observer_invalid_output')
    if data['status'] not in ('observed', 'review_pending') and (
            data['assessment_status'] != 'none' or governance is not None or evaluator is not None):
        raise IntegrationError('observer_invalid_output')
    reasons = data['reason_codes']
    if (not isinstance(reasons, list) or not 1 <= len(reasons) <= 16
            or any(not isinstance(code, str) or code not in WORKFLOW_REASONS for code in reasons)):
        raise IntegrationError('observer_invalid_output')
    if return_code and data['ok']:
        raise IntegrationError('observer_failed')
    return {**data, 'mode': 'observe'}


def invoke(task_id, *, command='observe', phase='workspace', commit=None,
           record_id=None, assessment_path=None, root=ROOT, refresh=False):
    """Return a sanitized advisory summary, or None when configuration is absent."""
    try:
        root = Path(root).resolve()
    except (OSError, ValueError, TypeError):
        return _summary('invalid-task', 'workspace', 'error', 'invalid_root')
    if (not isinstance(task_id, str) or not IDENTIFIER.fullmatch(task_id)
            or command not in ('observe', 'status', 'assess') or phase not in ('workspace', 'publication')
            or type(refresh) is not bool or (refresh and command != 'observe')):
        return _summary('invalid-task', 'workspace', 'error', 'invalid_arguments')
    try:
        profile = load_profile(root)
        if profile is None:
            return None
        if not profile['enabled']:
            return _summary(task_id, phase, 'disabled', 'observations_disabled')
        if not _binding(task_id, profile, root):
            return _summary(task_id, phase, 'not_selected', 'selector_mismatch')
        interpreter = _interpreter(profile, root)
        script = _relative(root, SCRIPT_PATH)
        arguments = [str(interpreter), '-I', '-B', str(script), command, '--task', task_id,
                     '--profile', str(_relative(root, PROFILE_PATH)), '--root', str(root)]
        if command in ('observe', 'status'):
            arguments += ['--phase', phase]
        if refresh:
            arguments += ['--refresh']
        if command == 'observe' and phase == 'publication':
            if not isinstance(commit, str) or not re.fullmatch('[a-f0-9]{40}', commit):
                return _summary(task_id, phase, 'error', 'publication_commit_required')
            arguments += ['--commit', commit]
        elif commit is not None:
            return _summary(task_id, phase, 'error', 'invalid_arguments')
        if command == 'assess':
            if not isinstance(record_id, str) or not RECORD_ID.fullmatch(record_id) or assessment_path is None:
                return _summary(task_id, phase, 'error', 'invalid_arguments')
            arguments += ['--record', record_id, '--input', str(Path(assessment_path))]
        return_code, stdout, stderr = _run_child(arguments, root=root, timeout=profile['timeout_seconds'])
        if stderr:
            return _summary(task_id, phase, 'error', 'observer_stderr')
        return _checked_summary(stdout, task_id, None if command == 'assess' else phase, return_code, root)
    except IntegrationError as error:
        allowed = {'observer_timeout', 'observer_output_limit', 'observer_empty_output',
                   'observer_invalid_output', 'observer_failed', 'profile_invalid', 'binding_invalid',
                   'environment_unavailable', 'repository_mismatch'}
        code = str(error) if str(error) in allowed else 'observer_unavailable'
        return _summary(task_id, phase, 'unavailable' if code in ('observer_unavailable', 'environment_unavailable') else 'error', code)
    except Exception:
        return _summary(task_id, phase, 'error', 'observer_internal_error')


class _Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise IntegrationError('invalid_arguments')


def main(argv=None):
    try:
        parser = _Arguments(description=__doc__)
        parser.add_argument('command', choices=('observe', 'status', 'assess'))
        parser.add_argument('--task', required=True)
        parser.add_argument('--phase', choices=('workspace', 'publication'), default='workspace')
        parser.add_argument('--commit')
        parser.add_argument('--record')
        parser.add_argument('--input')
        parser.add_argument('--refresh', action='store_true', help='Append a new unreviewed observation while preserving prior history; observe only.')
        parser.add_argument('--root', default=str(ROOT))
        args = parser.parse_args(argv)
        summary = invoke(args.task, command=args.command, phase=args.phase, commit=args.commit,
                         record_id=args.record, assessment_path=args.input, root=args.root, refresh=args.refresh)
        if summary is None:
            summary = _summary(args.task, args.phase, 'not_configured', 'observation_not_configured')
    except (IntegrationError, ValueError):
        summary = _summary('invalid-task', 'workspace', 'error', 'invalid_arguments')
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary['status'] not in ('error', 'unavailable') else 2


if __name__ == '__main__':
    raise SystemExit(main())
