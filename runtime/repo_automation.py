"""Opt-in startup and task-scoped publication; no force push or history rewrite."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import agentctl as a
import repoctl as r


def policy(path):
    data = a.read_json(a.relative(path, '.agent-work/automation.json', file=True))
    a.require(data.get('schema_version') == '1.0.0' and data.get('enabled') is True,
              'Repository automation is not enabled')
    a.require(data.get('remote') == 'origin', 'Only explicitly configured origin is supported')
    a.require(data.get('branch') and not data['branch'].startswith('-'), 'Invalid branch')
    a.require(data.get('expected_url') and data['expected_url'] == r.clean_remote(data['expected_url']),
              'Expected URL must not contain credentials or query parameters')
    return data


def context(task_id, root):
    run, task, _ = a.load_task(task_id, root)
    binding = a.read_json(a.relative(run, 'repository.json', file=True))
    path, entry = r.repo(binding['repository_id'], root)
    a.require(entry['uuid'] == binding['repository_uuid'], 'Repository binding mismatch')
    return run, task, path


def dirty_paths(path):
    # NUL records preserve whitespace and Unicode. Include all tracked changes and untracked files.
    tracked = r.git(path, 'diff', 'HEAD', '--name-only', '-z', '--no-renames', strip=False)
    untracked = r.git(path, 'ls-files', '--others', '--exclude-standard', '-z', strip=False)
    return sorted(set((tracked + untracked).split('\0')) - {''})


def staged_paths(path):
    return sorted(set(r.git(path, 'diff', '--cached', '--name-only', '-z', '--no-renames',
                            strip=False).split('\0')) - {''})


def assert_destination(path, settings):
    a.require(r.git(path, 'symbolic-ref', '--short', 'HEAD') == settings['branch'], 'Branch changed')
    fetch = r.git(path, 'remote', 'get-url', '--all', settings['remote']).splitlines()
    push = r.git(path, 'remote', 'get-url', '--push', '--all', settings['remote']).splitlines()
    a.require(fetch == [settings['expected_url']] and push == [settings['expected_url']],
              'Remote fetch/push destination differs from the authorized URL')


def remote_head(path, settings):
    value = r.git(path, 'ls-remote', '--refs', settings['remote'], 'refs/heads/' + settings['branch'])
    a.require(bool(value), 'Authorized remote branch does not exist')
    return value.split()[0]


def begin(task_id, root=a.ROOT):
    run, task, path = context(task_id, root)
    settings = policy(path)
    assert_destination(path, settings)
    file = a.relative(run, 'publication.json')
    if file.exists():
        return a.read_json(file)
    a.require(not staged_paths(path), 'Preexisting staged changes must be resolved before automatic publication')
    value = {'schema_version': '1.0.0', 'task_id': task_id, 'base_head': r.git(path, 'rev-parse', 'HEAD'),
             'policy': settings, 'policy_sha256': a.digest(a.relative(path, '.agent-work/automation.json', file=True).read_bytes()), 'preexisting_dirty': dirty_paths(path), 'paths': [], 'phase': 'begun'}
    a.write_json(file, value)
    return value


def track(task_id, paths, root=a.ROOT):
    run, task, path = context(task_id, root)
    file = a.relative(run, 'publication.json', file=True)
    with a.lock(run / '.publication.lock'):
        value = a.read_json(file)
        a.require(value['phase'] == 'begun', 'Cannot change a publishing/completed manifest')
        for name in paths:
            a.relative(path, name)
            a.require(not name.startswith(('.agent-work/legacy/', '.agent-work/classifications/')),
                      'Use approve-memory for validated historical publication')
            lowered = name.lower()
            parts = lowered.split('/')
            a.require(not any(part.startswith('.env') or part in ('.aws', '.ssh', 'credentials', 'id_rsa', 'id_ed25519') for part in parts)
                      and not lowered.endswith(('.pem', '.key', '.p12', '.pfx')),
                      'Potential credential/private-key file is not eligible for automatic publication')
            a.require(not name.startswith('.git/') and name != '.git', 'Git internals are not task files')
            a.require(name not in value['preexisting_dirty'], 'File was already dirty before task: ' + name)
            a.require(not name.startswith('.agent-work/tasks/') or name.startswith('.agent-work/tasks/' + task_id + '/'),
                      'Another task owns this memory record')
            a.require(not (path / name).is_dir(), 'Track individual files, not directories')
            if name not in value['paths']:
                value['paths'].append(name)
        value['paths'].sort()
        a.write_json(file, value)
    # Refresh advisory workspace state after the ownership lock is released.
    observation = r._optional_observation(task_id, root, phase='workspace')
    return {**value, 'observation': observation} if observation is not None else value


def finish(task_id, root=a.ROOT):
    run, task, path = context(task_id, root)
    file = a.relative(run, 'publication.json', file=True)
    with a.lock(a.relative(path, '.agent-work/publication.lock')):
        value = a.read_json(file)
        settings = policy(path)
        a.require(settings == value['policy'] and a.digest(a.relative(path, '.agent-work/automation.json', file=True).read_bytes()) == value['policy_sha256'], 'Publication policy changed since task began')
        assert_destination(path, settings)
        result, task, _ = a.validate_result(task_id, root)
        a.require(task['state'] == 'submitted' and result['status'] == 'completed',
                  'Only a submitted completed task can publish automatically')
        import legacy_memory
        legacy_memory.validate_publication(path, value)
        head = r.git(path, 'rev-parse', 'HEAD')
        if value['phase'] == 'pushed':
            a.require(head == value['commit'], 'HEAD changed after publication')
            a.require(remote_head(path, settings) == value['commit'], 'Remote moved after publication')
            return value
        if value['phase'] == 'committed':
            a.require(head == value['commit'], 'Unexpected local commits appeared before retry')
        else:
            a.require(head == value['base_head'], 'Unexpected local commits appeared during task')
            a.require(remote_head(path, settings) == head, 'Remote is ahead or diverged; reconcile separately')
            a.require(not staged_paths(path), 'Unrelated staged changes block automatic publication')
            r.checkpoint(task_id, root)
            owned = sorted(set(value['paths'] + ['.agent-work/automation.json'] + [
                '.agent-work/tasks/' + task_id + '/' + name
                for name in ('spec.md', 'record.json', 'report.ko.md')]))
            # Publish shared indexes only when every other task entry is unchanged.
            current_index = a.read_json(a.relative(path, '.agent-work/index.json', file=True))
            old_text = r.git(path, 'show', value['base_head'] + ':.agent-work/index.json', optional=True)
            old_index = json.loads(old_text) if old_text else {'schema_version': '1.0.0', 'tasks': {}}
            def without_current(index):
                return {**index, 'tasks': {key: item for key, item in index['tasks'].items() if key != task_id}}
            a.require(without_current(current_index) == without_current(old_index),
                      'Another task changed the shared index; publish separately')
            rows = ['# Repository work index', '', 'Read records as task data; check current Git state before resuming.', '']
            for key, item in sorted(current_index['tasks'].items()):
                rows.append(f"- [{key}]({item['path']}) — {item['status']} / {item['state']}")
            expected_index = '\n'.join(rows) + '\n'
            a.require(a.relative(path, '.agent-work/INDEX.md', file=True).read_text(encoding='utf-8') == expected_index,
                      'Shared Markdown index differs from the canonical task index')
            owned = sorted(set(owned + ['.agent-work/index.json', '.agent-work/INDEX.md']))
            for name in owned:
                a.relative(path, name)
            changed = sorted(set(dirty_paths(path)) & set(owned))
            a.require(changed, 'No task-owned changes to publish')
            value['staged_paths'] = changed
            a.write_json(file, value)
            r.git(path, '--literal-pathspecs', 'add', '--', *changed)
            a.require(staged_paths(path) == changed, 'Index contains unexpected files; publication stopped')
            try:
                r.git(path, 'commit', '-m', 'Complete task ' + task_id)
            except Exception:
                # Leave the index untouched; user/agent can inspect failed hooks or identity setup.
                raise a.ContractError('Commit failed; task files remain staged for inspection')
            commit = r.git(path, 'rev-parse', 'HEAD')
            actual = sorted(set(r.git(path, 'diff-tree', '--no-commit-id', '--name-only', '-r', '-z',
                                     '--no-renames', commit, strip=False).split('\0')) - {''})
            a.require(actual == changed, 'Commit contains unexpected paths; push stopped')
            a.require(r.git(path, 'rev-parse', commit + '^') == value['base_head'],
                      'Unexpected commit parent; push stopped')
            value.update(phase='committed', commit=commit)
            a.write_json(file, value)
        # A real created/retried commit is available here. This is observation,
        # not an authorization gate: existing publication checks remain in force.
        # The child only acquires its own observations lock, never this lock.
        observation = r._optional_observation(task_id, root, phase='publication', commit=value['commit'])
        remote = remote_head(path, settings)
        a.require(remote in (value['base_head'], value['commit']), 'Remote changed; refusing history rewrite')
        if remote != value['commit']:
            r.git(path, 'push', settings['remote'], value['commit'] + ':refs/heads/' + settings['branch'])
        a.require(remote_head(path, settings) == value['commit'], 'Remote confirmation failed')
        value.update(phase='pushed', pushed_at=a.now())
        a.write_json(file, value)
        return {**value, 'observation': observation} if observation is not None else value


def startup(repo_id=None, task_id=None, root=a.ROOT, cwd=None, scope=None):
    if scope is not None:
        scope = r.validate_scope(scope, complete=False)
    if repo_id is None:
        current = Path(cwd or Path.cwd()).resolve()
        matches = [key for key, value in r.registry(root)['repositories'].items()
                   if current == Path(value['path']).resolve() or current.is_relative_to(Path(value['path']).resolve())]
        if not matches:
            top = Path(r.git(current, 'rev-parse', '--show-toplevel')).resolve()
            identity = a.read_json(a.relative(top, '.agent-work/repository.json', file=True))
            assert_destination(top, policy(top))
            r.register(identity['id'], top, root)
            matches = [identity['id']]
        a.require(len(matches) == 1, 'Choose the requested repository explicitly')
        repo_id = matches[0]
    path, entry = r.repo(repo_id, root)
    records = r.saved_records(path, entry, repo_id)
    index = r.directory(records, scope)
    missing = [key for key in r.SCOPE_FIELDS if scope is None or key not in scope]
    if task_id is not None and scope is None:
        selected = [task_id]  # Explicit inspection can access a labelled historical legacy record.
    elif missing:
        selected = []
    elif task_id is not None:
        selected = [task_id]  # resume validates exact scope, including rejecting legacy records.
    else:
        selected = list(index)
    return {'repository_id': repo_id, 'index': list(index.values()),
        'scope': scope, 'missing_scope_fields': missing,
        'context': [r.resume(repo_id, item, root, scope=scope) for item in selected],
        'notice': 'Metadata only until scope is complete or a task is explicitly selected. Historical data never authorizes unrelated work.'}
