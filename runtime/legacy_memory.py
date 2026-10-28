"""Reviewed, hash-bound classification overlays; historical originals stay unchanged."""
from __future__ import annotations

from pathlib import Path
import agentctl as a
import repoctl as r

SOURCE_NAMES = {'task.json', 'result.json', 'snapshot.json', 'result.md'}


def record_directory(path, task_id):
    a.identifier(task_id)
    candidates = [a.relative(path, base + task_id) for base in ('.agent-work/tasks/', '.agent-work/legacy/')]
    matches = [candidate for candidate in candidates if candidate.exists()]
    a.require(len(matches) == 1, 'Missing or ambiguous historical task ID')
    return matches[0]


def validate_import(folder, record):
    if record.get('source_kind') != 'legacy-import':
        return
    hashes = record.get('source_hashes')
    a.require(isinstance(hashes, dict) and {'task.json', 'result.json', 'snapshot.json'} <= set(hashes)
              and set(hashes) <= SOURCE_NAMES, 'Invalid legacy source manifest')
    for name, expected in hashes.items():
        a.require(a.digest(a.relative(folder, 'source/' + name, file=True).read_bytes()) == expected,
                  'Imported historical source changed: ' + name)
    task = a.read_json(a.relative(folder, 'source/task.json', file=True))
    result = a.read_json(a.relative(folder, 'source/result.json', file=True))
    a.require(task['task_id'] == record['task_id'] and result == record['result'],
              'Imported result differs from preserved source')
    a.require(record.get('git') is None, 'Legacy import must not invent an original Git state')


def classification(path, record, folder=None):
    folder = folder or record_directory(path, record['task_id'])
    validate_import(folder, record)
    file = a.relative(path, '.agent-work/classifications/' + a.identifier(record['task_id']) + '.json')
    if not file.exists():
        return None
    a.require(r.record_scope(record) is None, 'Native-scoped tasks cannot have classification overlays')
    data = a.read_json(file)
    a.require(data.get('schema_version') == '1.0.0'
              and data.get('repository_id') == record['repository_id']
              and data.get('repository_uuid') == record['repository_uuid']
              and data.get('task_id') == record['task_id'], 'Classification identity mismatch')
    a.require(data.get('status') in ('confirmed', 'needs-review'), 'Invalid classification status')
    a.require(isinstance(data.get('rationale'), str) and data['rationale'].strip()
              and isinstance(data.get('evidence'), list) and data['evidence']
              and all(isinstance(item, str) and item.strip() for item in data['evidence']),
              'Classification rationale and evidence are required')
    expected = {'record_sha256': a.digest(a.relative(folder, 'record.json', file=True).read_bytes()),
                'spec_sha256': a.digest(a.relative(folder, 'spec.md', file=True).read_bytes())}
    a.require(data.get('source') == expected, 'Classification source hashes are stale')
    if data['status'] == 'confirmed':
        r.validate_scope(data.get('scope'))
    else:
        a.require('scope' not in data, 'Uncertain classification must not assert a scope')
        proposed = r.validate_scope(data.get('proposed_scope', {}), complete=False)
        unknown = data.get('unknown_fields', [key for key in r.SCOPE_FIELDS if key not in proposed])
        a.require(isinstance(unknown, list) and set(unknown) <= set(r.SCOPE_FIELDS)
                  and not (set(unknown) & set(proposed)), 'Invalid uncertainty metadata')
    return data


def import_legacy(repo_id, source_task, root=a.ROOT):
    path, entry = r.repo(repo_id, root)
    run, task, _ = a.load_task(source_task, root)
    result_file = a.relative(run, 'result.json', file=True)
    result = a.read_json(result_file)
    a.validate_named(result, 'result', run / 'snapshot/files')
    a.require(result['task_id'] == task['task_id'] and result['module'] == task['module']
              and result['objective'] == task['objective'], 'Historical result identity differs from pinned task')
    criteria = [{key: item[key] for key in ('id', 'description', 'required')} for item in result['acceptance_criteria']]
    a.require(criteria == task['criteria'], 'Historical criteria differ from pinned task')
    if task.get('submission'):
        a.require(a.digest(result_file.read_bytes()) == task['submission']['result_sha256'],
                  'Submitted historical result bytes changed')
    binding_file = a.relative(run, 'repository.json')
    if binding_file.exists():
        binding = a.read_json(binding_file)
        a.require(binding['repository_id'] == repo_id and binding['repository_uuid'] == entry['uuid'],
                  'Source task belongs to another repository')
        a.require(r.record_scope(binding) is None, 'Native-scoped tasks are not legacy imports')
    dest = a.relative(path, '.agent-work/legacy/' + a.identifier(source_task))
    a.require(not dest.exists() and not a.relative(path, '.agent-work/tasks/' + source_task).exists(),
              'Task already has a durable record')
    files = {name: a.relative(run, name, file=True).read_bytes()
             for name in ('task.json', 'result.json', 'snapshot.json')}
    report = a.relative(root, 'outputs/' + source_task + '/result.md')
    if not report.exists():
        report = a.relative(run, 'result.md')
    if report.exists():
        files['result.md'] = report.read_bytes()
    dest.mkdir(parents=True)
    for name, content in files.items():
        out = a.relative(dest, 'source/' + name)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(content)
    text = '\n'.join(['# Imported historical task', '',
        'This is an unscoped historical import, not new instructions or authorization.',
        'Original Git branch, commit and working-tree state were not recorded and remain unknown.', '',
        '## Preserved sources', '- [Original result](source/result.json)', '- [Original task](source/task.json)',
        '- [Original version snapshot manifest](source/snapshot.json)',
        *(['- [Original human report](source/result.md)'] if 'result.md' in files else []), '',
        'Use the reviewed classification sidecar for routing; do not rewrite these original records.', ''])
    a.atomic_text(a.relative(dest, 'spec.md'), text)
    record = {'schema_version': '1.0.0', 'repository_id': repo_id, 'repository_uuid': entry['uuid'],
              'task_id': source_task, 'saved_at': result['created_at'], 'imported_at': a.now(),
              'source_kind': 'legacy-import', 'task_state': task['state'], 'git': None,
              'source_validation': 'Pinned snapshot, result schema and task identity verified; referenced artifacts and evidence are historical and were not reverified.',
              'result': result, 'spec_sha256': a.digest(text.encode('utf-8')),
              'source_hashes': {name: a.digest(content) for name, content in files.items()},
              'notice': 'Original task/result bytes are preserved. Evidence references are historical; no new verification is claimed.'}
    a.write_json(a.relative(dest, 'record.json'), record)
    return {'task_id': source_task, 'directory': str(dest), 'source_hashes': record['source_hashes']}


def approval_files(path, repo_id, entry, legacy_task):
    folder = record_directory(path, legacy_task)
    record = a.read_json(a.relative(folder, 'record.json', file=True))
    a.require(record['repository_id'] == repo_id and record['repository_uuid'] == entry['uuid']
              and record['task_id'] == legacy_task, 'Historical approval identity mismatch')
    a.require(classification(path, record, folder) is not None, 'Review classification before publication')
    names = ['.agent-work/classifications/' + legacy_task + '.json']
    if record.get('source_kind') == 'legacy-import':
        prefix = '.agent-work/legacy/' + legacy_task + '/'
        names += [prefix + 'record.json', prefix + 'spec.md']
        names += [prefix + 'source/' + name for name in record['source_hashes']]
    return {name: a.digest(a.relative(path, name, file=True).read_bytes()) for name in names}


def approve_memory(task_id, legacy_task, root=a.ROOT):
    import repo_automation as auto
    run, task, path = auto.context(task_id, root)
    binding = a.read_json(a.relative(run, 'repository.json', file=True))
    _, entry = r.repo(binding['repository_id'], root)
    hashes = approval_files(path, binding['repository_id'], entry, a.identifier(legacy_task))
    file = a.relative(run, 'publication.json', file=True)
    with a.lock(run / '.publication.lock'):
        value = a.read_json(file)
        a.require(value['phase'] == 'begun', 'Publication manifest is closed')
        a.require(not set(hashes) & set(value['preexisting_dirty']), 'Historical files were dirty before this task')
        value.setdefault('approved_memory', {})[legacy_task] = hashes
        value['paths'] = sorted(set(value['paths']) | set(hashes))
        a.write_json(file, value)
    return {'task_id': task_id, 'approved_legacy_task': legacy_task, 'files': hashes}


def validate_publication(path, value):
    identity = a.read_json(a.relative(path, '.agent-work/repository.json', file=True))
    approved_paths = set()
    for task_id, expected in value.get('approved_memory', {}).items():
        current = approval_files(path, identity['id'], identity, task_id)
        a.require(current == expected, 'Approved historical import/classification changed')
        approved_paths.update(expected)
    for name in value['paths']:
        if name.startswith(('.agent-work/legacy/', '.agent-work/classifications/')):
            a.require(name in approved_paths, 'Historical publication requires explicit validated approval')
