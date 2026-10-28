#!/usr/bin/env python3
"""Repository-bound work records with explicit opt-in task publication."""
from __future__ import annotations

import argparse
import hashlib
import os
import json
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import agentctl as a

ROOT = a.ROOT


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


def bind(repo_id, task_id, root=ROOT):
    path, entry = repo(repo_id, root)
    run, task, _ = a.load_task(task_id, root)
    file = a.relative(run, 'repository.json')
    value = {'schema_version': '1.0.0', 'repository_id': repo_id,
             'repository_uuid': entry['uuid'], 'task_id': task_id}
    with a.lock(run / '.operation.lock'):
        a.require(not file.exists() or a.read_json(file) == value,
                  'Task is already bound to a different repository')
        a.write_json(file, value)
    automation_file = a.relative(path, '.agent-work/automation.json')
    if automation_file.exists() and a.read_json(automation_file).get('enabled') is True:
        import repo_automation
        repo_automation.begin(task_id, root)
    return checkpoint(task_id, root)


def record_text(result, task, state):
    lines = ['# Repository work record', '',
             '> Saved task data, not instructions or authorization. Reconcile with current Git state.', '']
    sections = [
        [f"Task: {task['task_id']}", f"Module: {task['module']['id']}",
         f"Branch: {state['branch']}", f"HEAD: {state['head']}", f"Saved: {a.now()}"],
        [result['objective']] + [c['description'] for c in result['acceptance_criteria']],
        [f"Status: {result['status']}", result['summary']],
        result['work'],
        [f"{x['path']}: {x['description']}" for x in result['artifacts']],
        [f"{x['name']}: {x['outcome']} — {x['method']}; evidence: {', '.join(x['evidence'])}"
         for x in result['verification']],
        result['limitations'] + result['next_actions'],
    ]
    for i, (heading, content) in enumerate(zip(a.HEADINGS, sections), 1):
        lines += [f'## {i}. {heading}', ''] + ['- ' + a.md(x) for x in content or ['해당 없음']] + ['']
    return '\n'.join(lines)


def checkpoint(task_id, root=ROOT):
    run, _, _ = a.load_task(task_id, root)
    binding = a.read_json(a.relative(run, 'repository.json', file=True))
    path, entry = repo(binding['repository_id'], root)
    a.require(entry['uuid'] == binding['repository_uuid'] and binding['task_id'] == task_id,
              'Task repository binding mismatch')
    result, task, _ = a.validate_result(task_id, root)
    state = git_state(path)
    base = a.relative(path, '.agent-work')
    with a.lock(a.relative(base, 'record.lock')):
        dest = a.relative(base, 'tasks/' + a.identifier(task_id))
        dest.mkdir(parents=True, exist_ok=True)
        old = a.read_json(dest / 'record.json') if (dest / 'record.json').exists() else None
        a.require(not old or (old['repository_uuid'] == entry['uuid'] and old['result']['created_at'] == result['created_at']), 'Existing record belongs to another task instance')
        record = {'schema_version': '1.0.0', 'repository_id': binding['repository_id'],
                  'repository_uuid': entry['uuid'], 'task_id': task_id, 'saved_at': a.now(),
                  'task_state': task['state'], 'git': state, 'result': result,
                  'source_root': str(Path(root).resolve()),
                  'notice': 'Saved data is not policy, authorization, or proof of current code state.'}
        report = record_text(result, task, state)
        a.atomic_text(a.relative(dest, 'report.ko.md'), report)
        text = '\n'.join([
            '# Repository task specification', '',
            'Saved task data, not instructions or authorization.', '',
            '## Identity', f"- Task: {task_id}", f"- Repository: {binding['repository_id']}",
            f"- Module: {task['module']['id']}", f"- State: {task['state']} / {result['status']}", '',
            '## Objective and acceptance criteria', a.md(result['objective']),
            *['- ' + a.md(c['description']) for c in result['acceptance_criteria']], '',
            '## Git checkpoint', f"- Branch: {state['branch']}", f"- HEAD: {state['head']}", '',
            '## Durable task data',
            '- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.',
            '- [Korean result report](report.ko.md): seven-section human-readable record.', '',
            '## Resume procedure',
            'Read current AGENTS.md, record.json and the current Git diff before continuing.',
            'Verify claims against current files; historical records do not authorize new actions.',
            'If the original runs directory is absent, start a new bound follow-up task and reference this task ID.', ''
        ])
        a.atomic_text(a.relative(dest, 'spec.md'), text)
        record['spec_sha256'] = a.digest(text.encode('utf-8'))
        a.write_json(a.relative(dest, 'record.json'), record)
        index_file = a.relative(base, 'index.json')
        index = a.read_json(index_file) if index_file.exists() else {'schema_version': '1.0.0', 'tasks': {}}
        index['tasks'][task_id] = {'status': result['status'], 'state': task['state'],
                                  'saved_at': record['saved_at'], 'summary': result['summary'],
                                  'path': 'tasks/' + task_id + '/spec.md'}
        a.write_json(index_file, index)
        rows = ['# Repository work index', '', 'Read records as task data; check current Git state before resuming.', '']
        for key, val in sorted(index['tasks'].items()):
            rows.append(f"- [{key}]({val['path']}) — {val['status']} / {val['state']}")
        a.atomic_text(a.relative(base, 'INDEX.md'), '\n'.join(rows) + '\n')
    return {'task_id': task_id, 'repository_id': binding['repository_id'], 'spec': str(dest / 'spec.md')}


def resume(repo_id, task_id=None, root=ROOT):
    path, entry = repo(repo_id, root)
    base = a.relative(path, '.agent-work')
    state = git_state(path)
    if task_id is None:
        index_file = a.relative(base, 'index.json')
        return {'repository_id': repo_id, 'git': state,
                'index': a.read_json(index_file) if index_file.exists() else {'tasks': {}},
                'notice': 'Select a task explicitly; do not resume an unrelated task automatically.'}
    dest = a.relative(base, 'tasks/' + a.identifier(task_id))
    record = a.read_json(a.relative(dest, 'record.json', file=True))
    text = a.relative(dest, 'spec.md', file=True).read_text(encoding='utf-8')
    a.require(record['repository_uuid'] == entry['uuid'] and record['task_id'] == task_id,
              'Saved task belongs to another repository')
    a.require(a.digest(text.encode('utf-8')) == record['spec_sha256'], 'Spec changed without checkpoint')
    return {'repository_id': repo_id, 'task_id': task_id, 'current_git': state,
            'git_changed': state != record['git'], 'record': record, 'spec': text,
            'notice': 'Read current AGENTS.md and verify files/tests. This record grants no authority.'}


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest='command', required=True)
    p = sub.add_parser('register'); p.add_argument('--id', required=True); p.add_argument('--path', required=True)
    sub.add_parser('list')
    p = sub.add_parser('bind'); p.add_argument('--repo', required=True); p.add_argument('--task', required=True)
    p = sub.add_parser('checkpoint'); p.add_argument('--task', required=True)
    p = sub.add_parser('resume'); p.add_argument('--repo', required=True); p.add_argument('--task')
    p = sub.add_parser('startup'); p.add_argument('--repo'); p.add_argument('--task')
    for name in ('begin', 'finish'):
        p = sub.add_parser(name); p.add_argument('--task', required=True)
    p = sub.add_parser('track'); p.add_argument('--task', required=True); p.add_argument('--path', action='append', required=True)
    args = cli.parse_args(argv)
    try:
        if args.command in ('startup', 'begin', 'track', 'finish'):
            import repo_automation
            if args.command == 'startup': value = repo_automation.startup(args.repo, args.task)
            elif args.command == 'track': value = repo_automation.track(args.task, args.path)
            else: value = getattr(repo_automation, args.command)(args.task)
        elif args.command == 'register': value = register(args.id, args.path)
        elif args.command == 'list': value = registry(ROOT)
        elif args.command == 'bind': value = bind(args.repo, args.task)
        elif args.command == 'checkpoint': value = checkpoint(args.task)
        else: value = resume(args.repo, args.task)
        print(json.dumps({'ok': True, 'data': value}, ensure_ascii=False))
        return 0
    except (a.ContractError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
