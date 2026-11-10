#!/usr/bin/env python3
"""Repository-bound work records with explicit opt-in task publication."""
from __future__ import annotations

import argparse
import hashlib
import os
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import agentctl as a

ROOT = a.ROOT


SCOPE_FIELDS = ('project', 'service', 'environment', 'issue')


def _optional_observation(task_id, root, *, phase='workspace', commit=None):
    """Old no-config copies need no observer module or dependency environment."""
    profile = Path(root) / '.agent-work/observation.json'
    if not profile.exists() and not profile.is_symlink():
        return None
    safe_task = (task_id if isinstance(task_id, str) and len(task_id) <= 128
                 and re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', task_id) else 'invalid-task')
    unavailable = {'ok': False, 'task_id': safe_task, 'phase': phase,
                   'status': 'unavailable', 'mode': 'observe', 'record_id': None,
                   'snapshot_digest': None, 'decision': None, 'assessment_status': 'none',
                   'governance_recommendation': None, 'evaluator_assessment': None,
                   'executable': False, 'authority_verified': False}
    try:
        import control_integration
    except Exception:
        return {**unavailable, 'reason_codes': ['observer_module_unavailable']}
    try:
        return control_integration.invoke(task_id, phase=phase, commit=commit, root=root)
    except Exception:
        return {**unavailable, 'reason_codes': ['observer_unavailable']}


def validate_scope(value, *, complete=True):
    a.require(isinstance(value, dict) and not (set(value) - set(SCOPE_FIELDS)), 'Malformed work scope')
    if complete:
        a.require(set(value) == set(SCOPE_FIELDS), 'All four work scope fields are required')
    for key, item in value.items():
        a.identifier(item)
    return dict(value)


def scope_args(args):
    value = {key: getattr(args, key, None) for key in SCOPE_FIELDS if getattr(args, key, None) is not None}
    return validate_scope(value, complete=False) if value else None


def add_scope_args(parser):
    for key in SCOPE_FIELDS:
        parser.add_argument('--' + key)


def record_scope(record):
    # Absence is a historical legacy record; a malformed present value is never legacy.
    return validate_scope(record['scope']) if 'scope' in record else None


def saved_records(path, entry, repo_id):
    import legacy_memory as legacy
    records = []
    seen = set()
    for location in ('.agent-work/tasks', '.agent-work/legacy'):
        base = a.relative(path, location)
        if not base.exists():
            continue
        for folder in base.iterdir():
            a.require(not folder.is_symlink() and not getattr(folder, 'is_junction', lambda: False)(),
                      'Linked memory directories are not supported')
            if folder.is_dir():
                a.identifier(folder.name)
                a.require(folder.name not in seen, 'Ambiguous duplicate historical task ID')
                seen.add(folder.name)
                record = a.read_json(a.relative(base, folder.name + '/record.json', file=True))
                a.require(record['repository_uuid'] == entry['uuid'] and record['repository_id'] == repo_id
                          and record['task_id'] == folder.name, 'Saved repository/task identity mismatch')
                native = record_scope(record)
                overlay = legacy.classification(path, record, folder)
                a.require(isinstance(record['saved_at'], str) and isinstance(record['result']['status'], str),
                          'Malformed task metadata')
                record['_classification'] = overlay
                record['_effective_scope'] = native or (overlay['scope'] if overlay and overlay['status'] == 'confirmed' else None)
                records.append(record)
    return sorted(records, key=lambda item: item['saved_at'], reverse=True)


def directory(records, scope=None):
    query = validate_scope(scope, complete=False) if scope is not None else {}
    output = {}
    for item in records:
        effective = item.get('_effective_scope', record_scope(item))
        if query and (effective is None or any(effective[key] != value for key, value in query.items())):
            continue
        overlay = item.get('_classification')
        output[item['task_id']] = {'task_id': item['task_id'], 'scope': effective,
            'original_scope': record_scope(item), 'legacy_unscoped': record_scope(item) is None,
            'classification_status': overlay['status'] if overlay else 'unclassified',
            'proposed_scope': overlay.get('proposed_scope') if overlay else None,
            'unknown_fields': overlay.get('unknown_fields') if overlay else None,
            'status': item['result']['status'], 'saved_at': item['saved_at']}
    return output


def set_scope(task_id, scope, root=ROOT):
    scope = validate_scope(scope)
    run, task, _ = a.load_task(task_id, root)
    a.require(task['state'] not in ('submitted', 'cancelled'), 'Cannot scope a closed historical task')
    file = a.relative(run, 'repository.json', file=True)
    with a.lock(run / '.operation.lock'):
        binding = a.read_json(file)
        a.require('scope' not in binding or binding['scope'] == scope, 'Task scope is immutable')
        binding['scope'] = scope
        a.write_json(file, binding)
    return checkpoint(task_id, root)


def git(path, *args, optional=False, strip=True):
    p = subprocess.run(['git', '-C', str(path), *args], capture_output=True,
                       text=True, encoding='utf-8', errors='replace', timeout=30)
    if p.returncode:
        if optional:
            return None
        raise a.ContractError('Git operation failed: ' + args[0])
    return p.stdout.strip() if strip else p.stdout


def clean_remote(value):
    if not value:
        return None
    if '://' in value:
        u = urlsplit(value)
        return urlunsplit((u.scheme, u.hostname or '', u.path, '', ''))
    # SCP-style SSH remotes have a username, never store it.
    return value.split('@', 1)[-1].split('?', 1)[0].split('#', 1)[0]


def worktree_fingerprint(path):
    """Hash Git-visible contents without following links outside the checkout."""
    path = Path(path).resolve()
    names = git(path, 'ls-files', '-z', '--cached', '--others', '--exclude-standard', strip=False)
    aggregate = hashlib.sha256()
    # Include index object IDs/modes so staged-only changes are detectable too.
    staged = git(path, 'ls-files', '--stage', '-z', strip=False)
    for item in sorted(set(staged.split('\0')) - {''}):
        meta, name = item.split('\t', 1)
        if name != '.agent-work' and not name.startswith('.agent-work/'):
            aggregate.update(json.dumps(['index', meta, name], ensure_ascii=True).encode('utf-8') + b'\n')
    for name in sorted(set(names.split('\0')) - {''}):
        if name == '.agent-work' or name.startswith('.agent-work/'):
            continue
        parts = Path(name).parts
        a.require(not Path(name).is_absolute() and '..' not in parts,
                  'Unexpected Git path')
        current = path
        kind, content = 'missing', ''
        for part in parts:
            current = current / part
            if current.is_symlink() or getattr(current, 'is_junction', lambda: False)():
                kind, content = 'link', os.readlink(current)
                break
            if not current.exists():
                break
        else:
            if current.is_file():
                h = hashlib.sha256()
                with current.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        h.update(chunk)
                kind, content = 'file', h.hexdigest()
            elif current.is_dir():
                kind = 'directory'
        entry = json.dumps([name, kind, content], ensure_ascii=True, separators=(',', ':'))
        aggregate.update(entry.encode('utf-8') + b'\n')
    return aggregate.hexdigest()


def git_state(path):
    return {'branch': git(path, 'symbolic-ref', '--short', 'HEAD', optional=True),
            'head': git(path, 'rev-parse', '--verify', 'HEAD', optional=True),
            'origin': clean_remote(git(path, 'remote', 'get-url', 'origin', optional=True)),
            'status': git(path, 'status', '--porcelain=v1', '--untracked-files=normal'),
            'worktree_sha256': worktree_fingerprint(path)}


def registry(root):
    file = a.relative(root, 'runtime/repos.local.json')
    return a.read_json(file) if file.exists() else {'schema_version': '1.0.0', 'repositories': {}}


def repo(repo_id, root=ROOT):
    a.identifier(repo_id)
    entry = registry(root)['repositories'].get(repo_id)
    a.require(entry is not None, 'Repository is not registered')
    path = Path(entry['path']).resolve()
    a.require(Path(git(path, 'rev-parse', '--show-toplevel')).resolve() == path,
              'Registered path is not the exact Git root')
    identity = a.read_json(a.relative(path, '.agent-work/repository.json', file=True))
    a.require(identity['id'] == repo_id and identity['uuid'] == entry['uuid'],
              'Repository identity mismatch; register the correct checkout explicitly')
    return path, entry


def register(repo_id, path, root=ROOT):
    a.identifier(repo_id)
    path = Path(path).resolve()
    a.require(Path(git(path, 'rev-parse', '--show-toplevel')).resolve() == path,
              'Path must be the exact Git root; initialize Git separately if needed')
    identity_file = a.relative(path, '.agent-work/repository.json')
    with a.lock(a.relative(root, 'work/repos.lock')):
        data = registry(root)
        old = data['repositories'].get(repo_id)
        a.require(not old or Path(old['path']).resolve() == path,
                  'Repository ID already points to another path')
        identity = a.read_json(identity_file) if identity_file.exists() else {
            'schema_version': '1.0.0', 'id': repo_id, 'uuid': str(uuid.uuid4())}
        a.require(identity['id'] == repo_id, 'Checkout already has another repository ID')
        a.write_json(identity_file, identity)
        data['repositories'][repo_id] = {'path': str(path), 'uuid': identity['uuid']}
        a.write_json(a.relative(root, 'runtime/repos.local.json'), data)
    return {'id': repo_id, 'path': str(path), 'origin': git_state(path)['origin']}


def bind(repo_id, task_id, root=ROOT, scope=None, *, new_task=False):
    if scope is not None:
        scope = validate_scope(scope)
    path, entry = repo(repo_id, root)
    run, task, _ = a.load_task(task_id, root)
    file = a.relative(run, 'repository.json')
    value = {'schema_version': '1.0.0', 'repository_id': repo_id,
             'repository_uuid': entry['uuid'], 'task_id': task_id}
    if scope is not None:
        value['scope'] = scope
    with a.lock(run / '.operation.lock'):
        a.require(not file.exists() or a.read_json(file) == value,
                  'Task is already bound to a different repository')
        a.write_json(file, value)
    automation_file = a.relative(path, '.agent-work/automation.json')
    if automation_file.exists() and a.read_json(automation_file).get('enabled') is True:
        import repo_automation
        repo_automation.begin(task_id, root)
    if new_task:
        # Only init selects new enrollment. Binding/resuming historical work
        # must never silently relabel it as P1-enforced.
        a.control_gate_call('enroll', task_id, root)
    return checkpoint(task_id, root)


def record_text(result, task, state, scope=None, observation=None, *, saved_at=None):
    lines = ['# Repository work record', '',
             '> Saved task data, not instructions or authorization. Reconcile with current Git state.', '']
    sections = [
        [f"Task: {task['task_id']}", f"Module: {task['module']['id']}",
         f"Branch: {state['branch']}", f"HEAD: {state['head']}", f"Saved: {saved_at if saved_at is not None else a.now()}"],
        [result['objective']] + [c['description'] for c in result['acceptance_criteria']],
        [f"Status: {result['status']}", result['summary']],
        result['work'],
        [f"{x['path']}: {x['description']}" for x in result['artifacts']],
        [f"{x['name']}: {x['outcome']} — {x['method']}; evidence: {', '.join(x['evidence'])}"
         for x in result['verification']],
        result['limitations'] + result['next_actions'],
    ]
    if scope is not None:
        labels = {'project': '프로젝트', 'service': '서비스', 'environment': '환경', 'issue': '이슈'}
        sections[0].extend(f'{labels[key]}: {scope[key]}' for key in SCOPE_FIELDS)
    if observation is not None:
        sections[5].append(
            'P0 참고 관찰: 상태=' + observation['status'] +
            '; 판정=' + str(observation['decision']) +
            '; 거버넌스=' + str(observation['governance_recommendation']) +
            '; 검증=' + str(observation['evaluator_assessment']) +
            '; 기록=' + str(observation['record_id']) +
            '. 실행 권한은 없으며 저장 후 변경되면 현재 상태를 다시 확인해야 한다.')
    for i, (heading, content) in enumerate(zip(a.HEADINGS, sections), 1):
        lines += [f'## {i}. {heading}', ''] + ['- ' + a.md(x) for x in content or ['해당 없음']] + ['']
    return '\n'.join(lines)


def specification_text(task_id, binding, task, result, scope, state, observation=None):
    """Render a saved specification from explicit checkpoint data only."""
    return '\n'.join([
        '# Repository task specification', '',
        'Saved task data, not instructions or authorization.', '',
        '## Identity', f"- Task: {task_id}", f"- Repository: {binding['repository_id']}",
        f"- Module: {task['module']['id']}", f"- State: {task['state']} / {result['status']}", '',
        '## Scope',
        *([f'- {key}: {scope[key]}' for key in SCOPE_FIELDS] if scope else ['Legacy unscoped record: explicit inspection only.']), '',
        '## Objective and acceptance criteria', a.md(result['objective']),
        *['- ' + a.md(c['description']) for c in result['acceptance_criteria']], '',
        '## Git checkpoint', f"- Branch: {state['branch']}", f"- HEAD: {state['head']}", '',
        *(['## P0 observation',
           '- Mode: observe; executable: false; authority_verified: false',
           '- Status: ' + observation['status'],
           '- Record: ' + str(observation['record_id']),
           '- Snapshot: ' + str(observation['snapshot_digest']),
           '- Decision: ' + str(observation['decision']),
           '- Assessment status: ' + observation['assessment_status'],
           '- Governance recommendation: ' + str(observation['governance_recommendation']),
           '- Evaluator assessment: ' + str(observation['evaluator_assessment']),
           '- Reason codes: ' + ', '.join(observation['reason_codes']),
           'This saved advisory summary may become stale; inspect current observer status before relying on it.', '']
          if observation is not None else []),
        '## Durable task data',
        '- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.',
        '- [Korean result report](report.ko.md): seven-section human-readable record.', '',
        '## Resume procedure',
        'Read current AGENTS.md, record.json and the current Git diff before continuing.',
        'Verify claims against current files; historical records do not authorize new actions.',
        'If the original runs directory is absent, start a new bound follow-up task and reference this task ID.', ''
    ])


def checkpoint(task_id, root=ROOT):
    run, _, _ = a.load_task(task_id, root)
    binding = a.read_json(a.relative(run, 'repository.json', file=True))
    path, entry = repo(binding['repository_id'], root)
    a.require(entry['uuid'] == binding['repository_uuid'] and binding['task_id'] == task_id,
              'Task repository binding mismatch')
    scope = record_scope(binding)
    result, task, snapshot = a.validate_result(task_id, root)
    # Observe before acquiring record.lock. The child only reads lifecycle data
    # and writes separate companions; it never calls checkpoint recursively.
    observation = _optional_observation(task_id, root, phase='workspace')
    state = git_state(path)
    base = a.relative(path, '.agent-work')
    with a.lock(a.relative(base, 'record.lock')):
        dest = a.relative(base, 'tasks/' + a.identifier(task_id))
        dest.mkdir(parents=True, exist_ok=True)
        old = a.read_json(dest / 'record.json') if (dest / 'record.json').exists() else None
        a.require(not old or (old['repository_uuid'] == entry['uuid'] and old['result']['created_at'] == result['created_at']), 'Existing record belongs to another task instance')
        if old:
            old_scope = record_scope(old)
            a.require(old_scope == scope or (old_scope is None and scope is not None and task['state'] not in ('submitted', 'cancelled')), 'Saved task scope is immutable')
        record = {'schema_version': '1.0.0', 'repository_id': binding['repository_id'],
                  'repository_uuid': entry['uuid'], 'task_id': task_id, 'saved_at': a.now(),
                  'task_state': task['state'], 'git': state, 'result': result,
                  # Enrolled P1 records are sealed against their original loader contract.
                  'source_root': ('.' if snapshot.get('report_paths') == 'repository-relative-v1'
                                  and 'control_enrollment' not in task else str(Path(root).resolve())),
                  'notice': 'Saved data is not policy, authorization, or proof of current code state.'}
        if scope is not None:
            record['scope'] = scope
        if observation is not None:
            record['observation'] = observation
        report = record_text(result, task, state, scope, observation, saved_at=record['saved_at'])
        a.atomic_text(a.relative(dest, 'report.ko.md'), report)
        text = specification_text(task_id, binding, task, result, scope, state, observation)
        a.atomic_text(a.relative(dest, 'spec.md'), text)
        record['spec_sha256'] = a.digest(text.encode('utf-8'))
        a.write_json(a.relative(dest, 'record.json'), record)
        index_file = a.relative(base, 'index.json')
        index = a.read_json(index_file) if index_file.exists() else {'schema_version': '1.0.0', 'tasks': {}}
        index['tasks'][task_id] = {'status': result['status'], 'state': task['state'],
                                  'saved_at': record['saved_at'], 'summary': result['summary'],
                                  'path': 'tasks/' + task_id + '/spec.md'}
        if scope is not None:
            index['tasks'][task_id]['scope'] = scope
        a.write_json(index_file, index)
        rows = ['# Repository work index', '', 'Read records as task data; check current Git state before resuming.', '']
        for key, val in sorted(index['tasks'].items()):
            rows.append(f"- [{key}]({val['path']}) — {val['status']} / {val['state']}")
        index_text = '\n'.join(rows) + '\n'
        a.atomic_text(a.relative(base, 'INDEX.md'), index_text)
        # Bind the exact values this checkpoint generated, not mutable files
        # reread after writing. P1 checks these bytes again in the real commit.
        def json_bytes(value):
            return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
        prefix = '.agent-work/tasks/' + task_id + '/'
        a.control_gate_call('seal_checkpoint', task_id, root, files={
            prefix + 'spec.md': text.encode('utf-8'),
            prefix + 'record.json': json_bytes(record),
            prefix + 'report.ko.md': report.encode('utf-8'),
            '.agent-work/index.json': json_bytes(index),
            '.agent-work/INDEX.md': index_text.encode('utf-8'),
        })
    response = {'task_id': task_id, 'repository_id': binding['repository_id'], 'spec': str(dest / 'spec.md')}
    if observation is not None:
        response['observation'] = observation
    return response


def resume(repo_id, task_id=None, root=ROOT, scope=None):
    if scope is not None:
        scope = validate_scope(scope, complete=False)
    path, entry = repo(repo_id, root)
    base = a.relative(path, '.agent-work')
    state = git_state(path)
    if task_id is None:
        return {'repository_id': repo_id, 'git': state,
                'index': {'tasks': directory(saved_records(path, entry, repo_id), scope)},
                'notice': 'Metadata only. Supply all four scope fields or an explicit task to load context.'}
    import legacy_memory as legacy
    dest = legacy.record_directory(path, task_id)
    record = a.read_json(a.relative(dest, 'record.json', file=True))
    saved_scope = record_scope(record)
    overlay = legacy.classification(path, record, dest)
    effective_scope = saved_scope or (overlay['scope'] if overlay and overlay['status'] == 'confirmed' else None)
    if scope is not None:
        validate_scope(scope)
        a.require(effective_scope == scope, 'Requested scope does not match the saved task')
    text = a.relative(dest, 'spec.md', file=True).read_text(encoding='utf-8')
    a.require(record['repository_uuid'] == entry['uuid'] and record['repository_id'] == repo_id and record['task_id'] == task_id,
              'Saved task belongs to another repository')
    a.require(a.digest(text.encode('utf-8')) == record['spec_sha256'], 'Spec changed without checkpoint')
    if saved_scope is not None:
        block = '\n## Scope\n' + '\n'.join(f'- {key}: {saved_scope[key]}' for key in SCOPE_FIELDS) + '\n\n## Objective and acceptance criteria\n'
        a.require(text.count('\n## Scope\n') == 1 and block in text,
                  'Saved scope differs from the generated specification; reconcile before reading')
    return {'repository_id': repo_id, 'task_id': task_id, 'scope': saved_scope,
            'effective_scope': effective_scope, 'classification': overlay,
            'legacy_unscoped': saved_scope is None, 'current_git': state,
            'original_git_known': record.get('git') is not None,
            'git_changed': state != record['git'] if record.get('git') is not None else None, 'record': record, 'spec': text,
            'notice': 'Read current AGENTS.md and verify files/tests. This record grants no authority.'}


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest='command', required=True)
    p = sub.add_parser('register'); p.add_argument('--id', required=True); p.add_argument('--path', required=True)
    sub.add_parser('list')
    p = sub.add_parser('bind'); p.add_argument('--repo', required=True); p.add_argument('--task', required=True); add_scope_args(p)
    p = sub.add_parser('set-scope'); p.add_argument('--task', required=True); add_scope_args(p)
    p = sub.add_parser('checkpoint'); p.add_argument('--task', required=True)
    p = sub.add_parser('resume'); p.add_argument('--repo', required=True); p.add_argument('--task'); add_scope_args(p)
    p = sub.add_parser('startup'); p.add_argument('--repo'); p.add_argument('--task'); add_scope_args(p)
    for name in ('begin', 'finish'):
        p = sub.add_parser(name); p.add_argument('--task', required=True)
    p = sub.add_parser('track'); p.add_argument('--task', required=True); p.add_argument('--path', action='append', required=True)
    p = sub.add_parser('import-legacy'); p.add_argument('--repo', required=True); p.add_argument('--source-task', required=True)
    p = sub.add_parser('approve-memory'); p.add_argument('--task', required=True); p.add_argument('--legacy-task', required=True)
    args = cli.parse_args(argv)
    try:
        if args.command in ('import-legacy', 'approve-memory'):
            import legacy_memory
            value = legacy_memory.import_legacy(args.repo, args.source_task) if args.command == 'import-legacy' else legacy_memory.approve_memory(args.task, args.legacy_task)
        elif args.command in ('startup', 'begin', 'track', 'finish'):
            import repo_automation
            if args.command == 'startup': value = repo_automation.startup(args.repo, args.task, scope=scope_args(args))
            elif args.command == 'track': value = repo_automation.track(args.task, args.path)
            else: value = getattr(repo_automation, args.command)(args.task)
        elif args.command == 'register': value = register(args.id, args.path)
        elif args.command == 'list': value = registry(ROOT)
        elif args.command == 'bind': value = bind(args.repo, args.task, scope=validate_scope(scope_args(args)))
        elif args.command == 'set-scope': value = set_scope(args.task, scope_args(args))
        elif args.command == 'checkpoint': value = checkpoint(args.task)
        else: value = resume(args.repo, args.task, scope=scope_args(args))
        print(json.dumps({'ok': True, 'data': value}, ensure_ascii=False))
        return 0
    except (a.ContractError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
