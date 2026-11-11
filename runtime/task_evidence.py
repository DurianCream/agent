"""Bounded task records, enabled only by the task's committed publication baseline."""
import json
import re

import agentctl as a
import repoctl as r

CONFIG = '.agent-work/evidence-policy.json'
POLICY = {'schema_version': '1.0.0', 'format': 'summary-v1',
          'file_bytes': 65536, 'task_bytes': 262144}
FILES = ('spec.md', 'record.json', 'report.ko.md', 'evidence/summary.json')


def enabled(root, publication):
    raw = r.git(root, 'show', publication['base_head'] + ':' + CONFIG, optional=True)
    if raw is None:
        return False
    a.require(json.loads(raw, object_pairs_hook=a.unique_pairs) == POLICY,
              'Unsupported committed task evidence policy')
    return True


def summary(root, task_id, data):
    value = json.loads(data.decode('utf-8'), object_pairs_hook=a.unique_pairs)
    a.require(type(value) is dict and set(value) == {'checks'} and
              type(value['checks']) is list and 0 < len(value['checks']) <= 64,
              'Evidence summary requires only checks (1..64)')
    seen = set()
    for check in value['checks']:
        a.require(type(check) is dict and set(check) == {'id', 'result', 'command', 'metrics', 'evidence'},
                  'Invalid evidence summary check fields')
        a.identifier(check['id'])
        a.require(check['id'] not in seen, 'Duplicate evidence summary check')
        seen.add(check['id'])
        a.require(check['result'] in ('passed', 'failed', 'not_run', 'not_applicable') and
                  type(check['command']) is str and 0 < len(check['command']) <= 1024,
                  'Invalid evidence summary result or command')
        metrics = check['metrics']
        a.require(type(metrics) is dict and len(metrics) <= 16 and
                  all(type(k) is str and 0 < len(k) <= 64 and type(v) in (int, float) and
                      abs(v) < 1e100 for k, v in metrics.items()), 'Summary metrics must be bounded numbers')
        a.require(type(check['evidence']) is list and 0 < len(check['evidence']) <= 32,
                  'Summary raw evidence references required')
        for item in check['evidence']:
            a.require(type(item) is dict and set(item) == {'path', 'sha256'} and
                      type(item['path']) is str and item['path'].startswith('runs/' + task_id + '/evidence/') and
                      type(item['sha256']) is str and re.fullmatch('[0-9a-f]{64}', item['sha256']),
                      'Invalid summary raw evidence path or SHA-256')
            file = a.relative(root, item['path'], file=True)
            evidence_root = a.relative(root, 'runs/' + task_id + '/evidence')
            a.require(file.resolve().is_relative_to(evidence_root.resolve()), 'Raw evidence escaped task directory')
            a.require(a.digest(file.read_bytes()) == item['sha256'], 'Raw evidence SHA-256 mismatch: ' + item['path'])
    return value


def validate(root, task_id, publication, *, commit=None):
    if not enabled(root, publication):
        return
    prefix = '.agent-work/tasks/' + task_id + '/'
    expected = {prefix + name for name in FILES}
    a.require(prefix + 'evidence/summary.json' in publication['paths'], 'Track the committed evidence/summary.json')
    if commit:
        names = set(filter(None, r.git(root, 'ls-tree', '-r', '--name-only', '-z', commit, '--', prefix, strip=False).split('\0')))
    else:
        folder = a.relative(root, prefix.rstrip('/'))
        names = {p.relative_to(root).as_posix() for p in folder.rglob('*') if p.is_file() or p.is_symlink()}
        names.update(p for p in publication['paths'] if p.startswith(prefix))
    a.require(names == expected, 'Task records must contain exactly four files; unexpected=' +
              str(sorted(names - expected)) + '; missing=' + str(sorted(expected - names)))
    contents, total = {}, 0
    for name in sorted(names):
        if commit:
            size = int(r.git(root, 'cat-file', '-s', commit + ':' + name))
        else:
            size = a.relative(root, name, file=True).stat().st_size
        a.require(size <= POLICY['file_bytes'], f'Task record exceeds 65536 bytes: {name} ({size})')
        total += size
        contents[name] = (r.git(root, 'show', commit + ':' + name, strip=False).encode('utf-8')
                          if commit else a.relative(root, name, file=True).read_bytes())
    a.require(total <= POLICY['task_bytes'], f'Task records exceed 262144 bytes: {task_id} ({total}); files={sorted(names)}')
    summary(root, task_id, contents[prefix + 'evidence/summary.json'])
