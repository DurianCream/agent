"""Opt-in startup and task-scoped publication; no force push or history rewrite."""
from __future__ import annotations

import base64
import json
import os
import subprocess
from pathlib import Path

import agentctl as a
import repoctl as r
import secret_scan
import task_evidence


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


def _open_owners(task_id, root, binding):
    """{path: task} for files that other unfinished tasks of this repository own."""
    owners = {}
    for file in sorted(Path(root, 'runs').glob('*/publication.json')):
        folder = file.parent
        if folder.name == task_id or not (folder / 'task.json').is_file() or not (folder / 'repository.json').is_file():
            continue
        if (a.read_json(folder / 'task.json').get('state') in ('submitted', 'cancelled') or
                a.read_json(folder / 'repository.json').get('repository_uuid') != binding['repository_uuid']):
            continue
        owners.update({name: folder.name for name in a.read_json(file).get('paths', [])})
    return owners


def track(task_id, paths=None, root=a.ROOT, changed=False, yes=False):
    """Register exact owned files. changed proposes them instead: files changed since the
    baseline, minus what was already dirty and what another open task owns; yes registers them."""
    run, task, path = context(task_id, root)
    file = a.relative(run, 'publication.json', file=True)
    a.require(bool(paths) != bool(changed), 'Give either --path or --changed')
    # One repository-wide lock covers reading other tasks' ownership and saving this one's,
    # so two tasks cannot both register the same file. Transfers take the same lock.
    with a.lock(a.relative(path, '.agent-work/recovery.lock')), a.lock(run / '.publication.lock'):
        value = a.read_json(file)
        a.require(value['phase'] == 'begun', 'Cannot change a publishing/completed manifest')
        owners = _open_owners(task_id, root, a.read_json(a.relative(run, 'repository.json', file=True)))
        if changed:
            names = r.git(path, 'diff', value['base_head'], '--name-only', '-z', '--no-renames', strip=False) + \
                r.git(path, 'ls-files', '--others', '--exclude-standard', '-z', strip=False)
            skip = set(value['preexisting_dirty']) | set(owners) | set(value['paths'])
            paths = sorted(n for n in set(names.split('\0')) - {''} - skip
                           if n != AUTOMATION and not (n.startswith('.agent-work/') and n.endswith('.lock')) and
                           (not n.startswith('.agent-work/tasks/') or
                                                   n.startswith('.agent-work/tasks/' + task_id + '/evidence/')))
            if not yes:
                return {'task_id': task_id, 'registered': False, 'candidates': paths,
                        'notice': 'Nothing was registered. Check that every file is this task\'s work, then repeat with --yes.'}
        for name in paths:
            a.require(name not in owners, f'Another open task owns this file: {name} ({owners.get(name)})')
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
    return value


PHASES = ('begun', 'prepared', 'submitted', 'committed', 'indexed', 'pushed')
AUTOMATION = '.agent-work/automation.json'
MAX_BYTES = 64 * 1024 * 1024
RECORDS = ('spec.md', 'record.json', 'report.ko.md')


def publication_kind(task_id, paths, result):
    """product: completed work that owns product files. records: everything else.

    A records publication commits only the task's records, so it may follow a
    remote that advanced and leaves unfinished product in the worktree.
    """
    folder = '.agent-work/tasks/' + task_id + '/'
    product = [n for n in paths if n not in [folder + r for r in RECORDS] and not n.startswith(folder + 'evidence/')]
    return 'product' if result['status'] == 'completed' and product else 'records'


def _git(path, *args, env=None, data=None):
    """Byte-level Git call. Only temporary-index operations receive env."""
    proc = subprocess.run(['git', '--literal-pathspecs', '-C', str(path), *args], input=data, env=env,
                          capture_output=True, timeout=60)
    a.require(proc.returncode == 0, 'Git operation failed: ' + args[0])
    return proc.stdout


def _rows(raw):
    a.require(not raw or raw.endswith(b'\0'), 'Ambiguous Git listing')
    for row in filter(None, raw.split(b'\0')):
        meta, name = row.split(b'\t', 1)
        yield meta.decode('ascii').split(), name.decode('utf-8')


def _tree(path, commit, names):
    """{name: [mode, oid]} for regular blobs at exact paths in a commit."""
    entries = {}
    for meta, name in (_rows(_git(path, 'ls-tree', '-z', commit, '--', *names)) if names else ()):
        a.require(name in names and meta[1] == 'blob' and meta[0] in ('100644', '100755'),
                  'Unsupported committed object: ' + name)
        entries[name] = [meta[0], meta[2]]
    return entries


def _index(path, names):
    """{name: [mode, oid]} from the shared index; never called with a temporary index."""
    entries = {}
    for meta, name in (_rows(_git(path, 'ls-files', '--stage', '-z', '--', *names)) if names else ()):
        a.require(meta[2] == '0', 'Unresolved index conflict: ' + name)
        entries[name] = [meta[0], meta[1]]
    return entries


def _worktree(path, name, index):
    """The entry shape of control_gate._reviewed_blob, plus the bytes it describes."""
    file = a.relative(path, name)
    if not file.exists():
        return {'path': name, 'state': 'deleted', 'raw_sha256': None}, None
    a.require(file.is_file() and file.stat().st_size <= MAX_BYTES, 'Unsupported publication file: ' + name)
    data = file.read_bytes()
    oid = _git(path, 'hash-object', '--path=' + name, '--stdin', data=data).decode('ascii').strip()
    mode = index[name][0] if name in index else '100644'
    if os.name != 'nt' and r.git(path, 'config', '--get', 'core.filemode', optional=True) == 'true':
        mode = '100755' if file.stat().st_mode & 0o111 else '100644'
    a.require(mode in ('100644', '100755'), 'Unsupported publication mode: ' + name)
    return {'path': name, 'state': 'file', 'oid': oid, 'mode': mode, 'raw_sha256': a.digest(data)}, data


def _same(entry, committed):
    if entry['state'] == 'deleted':
        return committed is None
    return committed == [entry['mode'], entry['oid']]


def _record_oid(path, name, data):
    return _git(path, 'hash-object', '--path=' + name, '--stdin', data=data).decode('ascii').strip()


def _decode(files):
    return {name: base64.b64decode(data) for name, data in files.items()}


def _branch_ref(path, settings):
    return r.git(path, 'rev-parse', '--verify', '-q', 'refs/heads/' + settings['branch'], optional=True)


def verify_commit_object(task_id, root, path, value, payload):
    """Check the commit object alone: parent, exact diff, sealed content, records, scans, gate."""
    commit, parent, paths = payload['commit'], payload['parent'], payload['paths']
    a.require(r.git(path, 'rev-list', '--parents', '-n', '1', commit).split() == [commit, parent],
              'Unexpected commit parent; push stopped')
    actual = sorted(set(r.git(path, 'diff-tree', '--no-commit-id', '--name-only', '-r', '-z',
                              '--no-renames', parent, commit, strip=False).split('\0')) - {''})
    a.require(actual == paths, 'Commit contains unexpected paths; push stopped')
    records = _decode(payload['repository_files'])
    entries = payload['entries'] + ([payload['automation']] if payload['automation'] else [])
    committed = _tree(path, commit, sorted({e['path'] for e in entries} | set(records)))
    for entry in entries:
        a.require(_same(entry, committed.get(entry['path'])), 'Commit content differs from publication seal: ' + entry['path'])
    for name, data in records.items():
        a.require(committed.get(name) == ['100644', _record_oid(path, name, data)], 'Commit record differs: ' + name)
    task_evidence.validate(path, task_id, value, commit=commit)
    secret_scan.scan_commit(path, commit, parent, paths)
    return _gate(task_id, root, payload)


def _gate(task_id, root, payload, receipt=False):
    def framework(name):
        raw = payload['framework_files'].get('runs/' + task_id + '/' + name)
        return None if raw is None else json.loads(base64.b64decode(raw).decode('utf-8-sig'))
    return a.control_gate_call('check_commit', task_id, root, commit=payload['commit'], parent=payload['parent'],
                               paths=payload['paths'], records=_decode(payload['repository_files']),
                               seal=framework('gate-submission.json'), task=framework('task.json'),
                               result=framework('result.json'), receipt=receipt)


def _subject(task_id, root, run, path, value, close):
    """Current review subject: result, submission seal, owned bytes, approvals and handoffs."""
    status = a.read_json(a.relative(run, 'result.json', file=True))['status']
    a.require(close is not None or status == 'completed',
              'Only a completed task publishes without --close; close incomplete work with finish --close partial|failed|cancelled')
    submission = a.submission(task_id, root, close=close, publish=True)
    kind = publication_kind(task_id, value['paths'], submission['result'])
    recovered = set()
    if kind == 'product':  # Records never carry product, approved history or handed-over files.
        import legacy_memory
        legacy_memory.validate_publication(path, value)
        import task_recovery
        recovered = task_recovery.validate(task_id, root, value)
    return submission, sorted(recovered), kind


def _parent(task_id, path, value, settings, kind):
    """Choose the commit's parent and whether the local branch moves with it."""
    base, local, remote = value['base_head'], _branch_ref(path, settings), remote_head(path, settings)
    if kind == 'product' or remote == base:
        a.require(local == base, 'Unexpected local commits appeared during task')
        a.require(remote == base, 'Remote is ahead or diverged; reconcile separately')
        return base, 'local-update'
    # Records only: follow a remote that advanced, unless this task's records were touched there.
    if r.git(path, 'cat-file', '-e', remote + '^{commit}', optional=True) is None:
        r.git(path, 'fetch', '-q', settings['remote'], 'refs/heads/' + settings['branch'])
    a.require(r.git(path, 'merge-base', '--is-ancestor', base, remote, optional=True) is not None,
              'Remote diverged from the task base; reconcile separately')
    a.require(not _git(path, 'diff-tree', '-r', '--name-only', '-z', base, remote, '--', '.agent-work/tasks/' + task_id),
              'Task records changed on the remote since the task began')
    a.require(local in (remote, base), 'Unexpected local commits appeared during task')
    return remote, 'local-update' if local == remote else 'remote-only'


def _prepare(task_id, root, run, path, value, settings, close):
    submission, recovered, kind = _subject(task_id, root, run, path, value, close)
    parent, mode = _parent(task_id, path, value, settings, kind)
    a.require(not staged_paths(path), 'Unrelated staged changes block automatic publication')
    binding = a.read_json(a.relative(run, 'repository.json', file=True))
    _, entry = r.repo(binding['repository_id'], root)
    seal = submission['files'].get('runs/' + task_id + '/gate-submission.json')
    assessment = a.control_gate_call('attachment', task_id, root, seal=json.loads(seal.decode('utf-8'))) if seal else None
    records = r.record_files(task_id, root, path, entry, binding, submission['task'], submission['result'],
                             submission['snapshot'], r.git_state(path), a.now(), assessment)
    owned = sorted(set(value['paths']) - set(records))
    if kind == 'records':
        owned = [n for n in owned if n.startswith('.agent-work/tasks/' + task_id + '/evidence/')]
    index = _index(path, owned + [AUTOMATION])
    data, entries = {}, []
    for name in owned:
        item, data[name] = _worktree(path, name, index)
        entries.append(item)
    base = _tree(path, parent, owned + sorted(records) + [AUTOMATION])
    changed = [e for e in entries if not _same(e, base.get(e['path']))]
    automation = None
    if kind == 'product':
        automation, data[AUTOMATION] = _worktree(path, AUTOMATION, index)
        if _same(automation, base.get(AUTOMATION)):
            automation = None
        else:
            a.require(automation['raw_sha256'] == value['policy_sha256'], 'Publication policy changed since task began')
            changed.append(automation)
    changed_records = sorted(n for n, d in records.items() if base.get(n) != ['100644', _record_oid(path, n, d)])
    paths = sorted({e['path'] for e in changed} | set(changed_records))
    a.require(paths, 'No task-owned changes to publish')
    publish = a.relative(run, 'publish')
    publish.mkdir(exist_ok=True)
    temporary = a.relative(publish, 'index')
    temporary.unlink(missing_ok=True)
    env = {**os.environ, 'GIT_INDEX_FILE': str(temporary)}
    zero = '0' * len(parent)
    try:
        _git(path, 'read-tree', parent, env=env)
        info = []
        for item in changed:
            name = item['path']
            if item['state'] == 'deleted':
                info.append(f'0 {zero}\t{name}')
                continue
            oid = _git(path, 'hash-object', '-w', '--path=' + name, '--stdin', data=data[name]).decode('ascii').strip()
            a.require(oid == item['oid'], 'Sealed bytes produced another Git object: ' + name)
            info.append(f"{item['mode']} {oid}\t{name}")
        for name in changed_records:
            oid = _git(path, 'hash-object', '-w', '--path=' + name, '--stdin', data=records[name]).decode('ascii').strip()
            info.append(f'100644 {oid}\t{name}')
        _git(path, 'update-index', '-z', '--index-info', env=env, data=''.join(i + '\0' for i in info).encode('utf-8'))
        tree = _git(path, 'write-tree', env=env).decode('ascii').strip()
        message = ('Complete task ' if submission['result']['status'] == 'completed' else 'Close task ') + task_id
        commit = _git(path, 'commit-tree', tree, '-p', parent, '-m', message).decode('ascii').strip()
    finally:
        temporary.unlink(missing_ok=True)
    payload = {'schema_version': '1.0.0', 'task_id': task_id, 'kind': kind, 'mode': mode, 'close': close,
               'base': value['base_head'], 'parent': parent, 'commit': commit, 'paths': paths,
               'entries': entries, 'automation': automation, 'index_before': _index(path, paths),
               'recovered': recovered,
               'framework_files': {n: base64.b64encode(d).decode('ascii') for n, d in submission['files'].items()},
               'repository_files': {n: base64.b64encode(d).decode('ascii') for n, d in records.items()}}
    gate = verify_commit_object(task_id, root, path, value, payload)
    raw = a.json_bytes(payload)
    a.atomic_bytes(a.relative(publish, 'payload.json'), raw)
    value.update(phase='prepared', kind=kind, mode=mode, commit=commit, parent=parent, publication_paths=paths,
                 payload_sha256=a.digest(raw))
    return payload, gate


def _reverify(task_id, root, run, path, value, settings, close):
    """Common checks on every resume; saved bytes are reinstalled, never regenerated."""
    raw = a.relative(run, 'publish/payload.json', file=True).read_bytes()
    a.require(a.digest(raw) == value.get('payload_sha256'), 'Saved publication payload changed')
    payload = json.loads(raw.decode('utf-8'), object_pairs_hook=a.unique_pairs)
    a.require(payload['commit'] == value['commit'] and payload['parent'] == value['parent'] and
              payload['paths'] == value['publication_paths'] and payload['base'] == value['base_head'] and
              payload['mode'] == value['mode'] and payload['mode'] in ('local-update', 'remote-only'),
              'Saved publication payload differs from manifest')
    a.require(close in (None, payload['close']), 'Publication was prepared with another --close value')
    submission, recovered, kind = _subject(task_id, root, run, path, value, payload['close'])
    a.require(kind == payload['kind'], 'Publication kind changed after publication was prepared')
    a.require({n: base64.b64encode(d).decode('ascii') for n, d in submission['files'].items()} ==
              payload['framework_files'] and recovered == payload['recovered'],
              'Submission, seal, tests, review or evidence changed after publication was prepared')
    index = _index(path, [e['path'] for e in payload['entries']] + [AUTOMATION])
    for item in payload['entries'] + ([payload['automation']] if payload['automation'] else []):
        a.require(_worktree(path, item['path'], index)[0] == item, 'Owned file changed after publication was prepared: ' + item['path'])
    if PHASES.index(value['phase']) >= PHASES.index('submitted'):
        for name, data in _decode(payload['repository_files']).items():
            a.require(a.relative(path, name, file=True).read_bytes() == data, 'Installed task record changed: ' + name)
    a.require(remote_head(path, settings) in (payload['parent'], payload['commit']), 'Remote changed; refusing history rewrite')
    return payload, verify_commit_object(task_id, root, path, value, payload)


def _install(task_id, root, run, path, payload):
    previous = a.read_json(a.relative(run, 'task.json', file=True))['state']
    files = _decode(payload['framework_files'])
    a.install_submission(task_id, root, files)
    task = json.loads(files['runs/' + task_id + '/task.json'].decode('utf-8'))
    if previous != task['state'] == 'cancelled':
        a.event(run, 'transition', state='cancelled')
    elif previous != task['state']:
        a.event(run, 'submitted', status=task['result_status'])
    for name, data in _decode(payload['repository_files']).items():
        file = a.relative(path, name)
        if not file.is_file() or file.read_bytes() != data:
            a.atomic_bytes(file, data)
        a.require(file.read_bytes() == data, 'Installed task record differs: ' + name)


def _update_ref(path, settings, payload):
    a.require(r.git(path, 'symbolic-ref', 'HEAD') == 'refs/heads/' + settings['branch'], 'Branch changed')
    a.require(not staged_paths(path), 'Unrelated staged changes block automatic publication')
    a.require(_index(path, payload['paths']) == payload['index_before'], 'Index changed after publication was prepared')
    r.git(path, 'update-ref', '-m', 'Complete task ' + payload['task_id'], 'refs/heads/' + settings['branch'],
          payload['commit'], payload['parent'])


def _sync_index(path, payload):
    paths, commit = payload['paths'], payload['commit']
    target = _tree(path, commit, paths)
    current = _index(path, paths)
    for name in paths:
        a.require(current.get(name) in (payload['index_before'].get(name), target.get(name)),
                  'Index entry is neither the prepared nor the published state: ' + name)
    a.require(set(staged_paths(path)) <= set(paths), 'Unrelated staged changes block index synchronization')
    r.git(path, '--literal-pathspecs', 'reset', '-q', commit, '--', *paths)
    a.require(_index(path, paths) == target and not staged_paths(path), 'Index synchronization failed')


def _push(path, settings, commit):
    if remote_head(path, settings) != commit:
        r.git(path, 'push', settings['remote'], commit + ':refs/heads/' + settings['branch'])
    a.require(remote_head(path, settings) == commit, 'Remote confirmation failed')


def _publish(task_id, root, file, path, value, settings, payload):
    _push(path, settings, payload['commit'])
    gate = _gate(task_id, root, payload, receipt=True)
    value.update(phase='pushed', pushed_at=a.now())
    a.write_json(file, value)
    return gate


def finish(task_id, root=a.ROOT, close=None):
    """Publish a completed task, or with close the records of one that ends incomplete."""
    run, task, path = context(task_id, root)
    file = a.relative(run, 'publication.json', file=True)
    with a.lock(a.relative(path, '.agent-work/publication.lock')), a.lock(run / '.operation.lock'):
        value = a.read_json(file)
        settings = policy(path)
        a.require(settings == value['policy'] and a.digest(a.relative(path, AUTOMATION, file=True).read_bytes()) == value['policy_sha256'], 'Publication policy changed since task began')
        assert_destination(path, settings)
        a.require(value['phase'] in PHASES, 'Unknown publication phase')
        if value['phase'] == 'begun':
            payload, gate = _prepare(task_id, root, run, path, value, settings, close)
            a.write_json(file, value)
        else:
            payload, gate = _reverify(task_id, root, run, path, value, settings, close)
        commit, parent = payload['commit'], payload['parent']
        ref = _branch_ref(path, settings)
        if payload['mode'] == 'remote-only':
            # The remote advanced: the local branch and shared index stay at the task base.
            a.require(ref == payload['base'], 'Local branch moved during remote-only publication')
            # Read-only: nothing here touches the index, but a foreign staged change still stops publication.
            a.require(value['phase'] == 'pushed' or not staged_paths(path),
                      'Staged changes block publication; unstage them before retrying')
            if value['phase'] == 'prepared':
                _install(task_id, root, run, path, payload)
                value['phase'] = 'submitted'
                a.write_json(file, value)
            if value['phase'] == 'submitted':
                gate = _publish(task_id, root, file, path, value, settings, payload)
            a.require(value['phase'] == 'pushed' and remote_head(path, settings) == commit, 'Remote moved after publication')
            value = {**value, 'notice': 'Local branch is behind the remote; the installed task records equal the published ones.'}
            return {**value, 'gate': gate} if gate is not None else value
        if value['phase'] == 'prepared':
            a.require(ref == parent, 'Unexpected local commits appeared before publication')
            _install(task_id, root, run, path, payload)
            value['phase'] = 'submitted'
            a.write_json(file, value)
        if value['phase'] == 'submitted':
            if ref != commit:  # Equal only when update-ref succeeded before the phase was saved.
                a.require(ref == parent, 'Unexpected local commits appeared before publication')
                _update_ref(path, settings, payload)
            value['phase'] = 'committed'
            a.write_json(file, value)
        a.require(_branch_ref(path, settings) == commit, 'Local branch moved after publication commit')
        if value['phase'] == 'committed':
            _sync_index(path, payload)
            value['phase'] = 'indexed'
            a.write_json(file, value)
        if value['phase'] == 'indexed':
            # Read-only: a foreign staged change is reported, never reset.
            a.require(_index(path, payload['paths']) == _tree(path, commit, payload['paths']) and
                      not staged_paths(path), 'Index changed after publication commit; unstage it before retrying')
            gate = _publish(task_id, root, file, path, value, settings, payload)
        a.require(remote_head(path, settings) == commit, 'Remote moved after publication')
        return {**value, 'gate': gate} if gate is not None else value


def unlock(task_id, root=a.ROOT):
    """Remove locks only when their recorded owner process is gone."""
    run, _, path = context(task_id, root)
    files = [run / '.operation.lock', run / '.publication.lock'] + [
        path / '.agent-work' / name for name in ('publication.lock', 'record.lock', 'recovery.lock')]
    removed = []
    # Only unlock deletes another owner's lock, and only while holding this guard.
    # A dead owner's file cannot vanish or be replaced in between, so inspecting
    # and deleting refer to the same lock. A stale guard needs manual inspection.
    with a.lock(path / '.agent-work' / 'unlock.lock'):
        states = {file: a.lock_state(file) for file in files}
        held = [f'{file.name}: {state}' for file, state in states.items() if state in ('alive', 'incomplete')]
        a.require(not held, 'Lock owner may still be running: ' + ', '.join(held))
        for file, state in states.items():
            if state in ('dead', 'abandoned'):
                file.unlink()
                scope = 'task' if file.parent == run else 'repository'
                a.event(run, 'unlock', lock=file.name, scope=scope, owner=state)
                removed.append({'lock': file.name, 'scope': scope, 'owner': state})
    return {'task_id': task_id, 'removed': removed}


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
