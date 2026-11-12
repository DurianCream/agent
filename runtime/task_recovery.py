"""Additive, hash-bound handoffs and closed-record-only publication preparation."""
from __future__ import annotations
import json
import uuid
from pathlib import Path
import agentctl as a
import repoctl as r
import repo_automation as auto


def closed(source, root):
    run, task, path = auto.context(source, root)
    a.require(task['state'] in ('submitted', 'cancelled'), 'Source task must be closed incomplete or cancelled')
    result, _, _ = a.validate_result(source, root)
    a.require(task['state'] == 'cancelled' or (task['state'] == 'submitted' and result['status'] in ('partial', 'failed')), 'Source task must be closed incomplete or cancelled')
    publication = a.read_json(run / 'publication.json')
    a.require(publication['phase'] == 'begun', 'Source already publishing or published')
    return run, task, path, publication


def source_records(source, root):
    run, task, path, publication = closed(source, root)
    prefix = '.agent-work/tasks/' + source + '/'
    names = [prefix + name for name in ('spec.md', 'record.json', 'report.ko.md')]
    hashes = {name: a.digest(a.relative(path, name, file=True).read_bytes()) for name in names}
    record = a.read_json(path / (prefix + 'record.json'))
    binding = a.read_json(run / 'repository.json')
    a.require(all(record[k] == binding[k] for k in ('repository_id', 'repository_uuid', 'task_id', 'scope')), 'Source record identity mismatch')
    a.require(record['spec_sha256'] == hashes[prefix + 'spec.md'], 'Source specification changed without checkpoint')
    # Historical records are never regenerated, even if cancellation occurred later.
    index = r.generated_index(path)['tasks'].get(source)
    expected = {'status': record['result']['status'], 'state': record['task_state'], 'saved_at': record['saved_at'],
                'summary': record['result']['summary'], 'path': 'tasks/' + source + '/spec.md', 'scope': record['scope']}
    a.require(index == expected, 'Source index does not match preserved record')
    return hashes, index


def receipt_paths(source, target, receipt_id):
    return ['.agent-work/tasks/' + task + '/recovery/' + receipt_id + '.json' for task in (source, target)]


def prepare(task_id, source, paths=None, root=a.ROOT):
    import control_gate as g
    a.require(task_id != source, 'Recovery requires a distinct successor')
    run, task, path = auto.context(task_id, root)
    oldrun, oldtask, oldpath, oldpub = closed(source, root)
    a.require(path == oldpath and task['state'] == 'running', 'Recovery requires running successor in same repository')
    binding, oldbinding = a.read_json(run / 'repository.json'), a.read_json(oldrun / 'repository.json')
    a.require(all(binding[k] == oldbinding[k] for k in ('repository_id', 'repository_uuid', 'scope')), 'Recovery scope must exactly match')
    a.require(g.check_enrollment(task_id, root) is not None, 'Recovery requires independently gated successor')
    hashes, index = source_records(source, root)
    mode = 'transfer' if paths is not None else 'records-only'
    entries = []
    if mode == 'transfer':
        a.require(oldtask['state'] == 'submitted' and a.read_json(oldrun / 'result.json')['status'] == 'partial', 'Only submitted partial candidates can transfer')
        saved_file = a.relative(oldrun, 'incomplete-candidate.json', file=True)
        a.require(oldtask['submission'].get('incomplete_candidate_sha256') == a.digest(saved_file.read_bytes()), 'Source candidate has no matching submission anchor')
        saved = a.read_json(saved_file)
        a.require(saved['candidate']['digest'] == g._hash(saved['candidate']['candidate']), 'Source candidate digest mismatch')
        a.require(saved['result_sha256'] == oldtask['submission']['result_sha256'], 'Source candidate is not bound to submitted result')
        a.require(saved['candidate']['candidate']['task_id'] == source, 'Source candidate identity mismatch')
        bypath = {e['path']:e for e in saved['candidate']['candidate']['entries']}
        a.require(paths and len(paths) == len(set(paths)), 'Transfer requires unique exact paths')
        for name in paths:
            a.relative(path, name)
            a.require(not name.startswith(('.agent-work/', 'runs/', 'outputs/', '.git/')) and name in oldpub['paths'] and name in bypath, 'Transfer path is not original owned product')
            a.require(g._reviewed_blob(path, name) == bypath[name], 'Transfer file differs from original candidate: ' + name)
            entries.append(bypath[name])
    receipt_id = uuid.uuid4().hex
    receipt = {'schema_version':'1.0.0', 'kind':mode, 'source':source, 'successor':task_id,
               'binding':binding, 'source_state':oldtask['state'], 'source_result_status':a.read_json(oldrun/'result.json')['status'], 'source_task_sha256':a.digest((oldrun/'task.json').read_bytes()),
               'source_records':hashes, 'source_index':index, 'entries':entries}
    names = receipt_paths(source, task_id, receipt_id)
    with a.lock(a.relative(path, '.agent-work/recovery.lock')):
        value = a.read_json(run / 'publication.json')
        a.require(value['phase'] == 'begun' and not value.get('recovery'), 'Recovery manifest is already prepared/closed')
        if mode == 'records-only':
            a.require(not value['paths'], 'Records-only publication cannot include product files')
        for other in Path(root, 'runs').glob('*/publication.json'):
            other_value = a.read_json(other)
            recovery = other_value.get('recovery')
            a.require(not recovery or recovery['source'] != source or not set(paths or []) & {e['path'] for e in recovery['entries']}, 'Source ownership already transferred')
        for name in names:
            file = a.relative(path, name)
            file.parent.mkdir(parents=True, exist_ok=True)
            with file.open('x', encoding='utf-8') as stream:
                json.dump(receipt, stream, ensure_ascii=False, indent=2); stream.write('\n')
        record = {**receipt, 'receipts':{name:a.digest((path/name).read_bytes()) for name in names}}
        value['recovery'] = record
        value['paths'] = sorted(set(value['paths']) | set(hashes) | set(names) | set(paths or []))
        a.write_json(run / 'publication.json', value)
    return record


def validate(task_id, root, publication):
    recovery = publication.get('recovery')
    if recovery is None:
        return set()
    import control_gate as g
    run, task, path = auto.context(task_id, root)
    source = recovery['source']
    oldrun, oldtask, _, _ = closed(source, root)
    a.require(recovery['successor'] == task_id and recovery['binding'] == a.read_json(run/'repository.json'), 'Recovery identity changed')
    a.require(a.digest((oldrun/'task.json').read_bytes()) == recovery['source_task_sha256'] and recovery['source_state'] == oldtask['state'] and recovery['source_result_status'] == a.read_json(oldrun/'result.json')['status'], 'Source lifecycle changed after recovery')
    hashes, index = source_records(source, root)
    a.require(hashes == recovery['source_records'] and index == recovery['source_index'], 'Recovered source records changed')
    expected = {k:v for k,v in recovery.items() if k != 'receipts'}
    a.require(len(recovery['receipts']) == 2, 'Both recovery receipts required')
    for name, digest in recovery['receipts'].items():
        a.require(name.startswith(('.agent-work/tasks/'+source+'/recovery/', '.agent-work/tasks/'+task_id+'/recovery/')) and name.endswith('.json'), 'Invalid recovery receipt path')
        file = a.relative(path, name, file=True)
        a.require(a.digest(file.read_bytes()) == digest and a.read_json(file) == expected, 'Recovery receipt changed')
    allowed = set(hashes) | set(recovery['receipts'])
    a.require(allowed <= set(publication['paths']), 'Recovery manifest omits records')
    if recovery['kind'] == 'records-only':
        a.require(not recovery['entries'] and all(name in allowed or name in g._managed(task_id) or g._evidence_path(name, task_id) for name in publication['paths']), 'Records-only publication contains product files')
    else:
        a.require(recovery['kind'] == 'transfer', 'Invalid recovery kind')
        # Original candidate hashes are checked at handoff. Subsequent implementation is
        # permitted, but must pass the successor candidate tests and independent seal.
        a.require({e['path'] for e in recovery['entries']} <= set(publication['paths']), 'Transferred ownership missing')
    return {source}
