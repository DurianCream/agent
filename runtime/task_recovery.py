"""Hash-bound transfer of unfinished product files to a successor task.

The source keeps and publishes its own records (finish --close); a transfer is
bound to the source's immutable submission anchor, not to its publication phase.
"""
from __future__ import annotations
from pathlib import Path
import agentctl as a
import repo_automation as auto


def anchor(source, root):
    """The submitted partial result and sealed file identities that never change after submission."""
    import control_gate as g
    run, task, path = auto.context(source, root)
    a.require(task['state'] == 'submitted' and task.get('result_status') == 'partial',
              'Only submitted partial candidates can transfer')
    submission = task['submission']
    a.require(a.digest(a.relative(run, 'result.json', file=True).read_bytes()) == submission['result_sha256'],
              'Submitted source result was changed')
    saved_file = a.relative(run, 'incomplete-candidate.json', file=True)
    a.require(submission.get('incomplete_candidate_sha256') == a.digest(saved_file.read_bytes()),
              'Source candidate has no matching submission anchor')
    saved = a.read_json(saved_file)
    a.require(saved['candidate']['digest'] == g._hash(saved['candidate']['candidate']), 'Source candidate digest mismatch')
    a.require(saved['result_sha256'] == submission['result_sha256'], 'Source candidate is not bound to submitted result')
    a.require(saved['candidate']['candidate']['task_id'] == source, 'Source candidate identity mismatch')
    value = {'result_sha256': submission['result_sha256'],
             'incomplete_candidate_sha256': submission['incomplete_candidate_sha256']}
    return run, path, value, {e['path']: e for e in saved['candidate']['candidate']['entries']}


def prepare(task_id, source, paths, root=a.ROOT):
    import control_gate as g
    a.require(task_id != source, 'Transfer requires a distinct successor')
    run, task, path = auto.context(task_id, root)
    oldrun, oldpath, bound, bypath = anchor(source, root)
    a.require(path == oldpath and task['state'] == 'running', 'Transfer requires running successor in same repository')
    binding, oldbinding = a.read_json(run / 'repository.json'), a.read_json(oldrun / 'repository.json')
    a.require(all(binding[k] == oldbinding[k] for k in ('repository_id', 'repository_uuid', 'scope')), 'Transfer scope must exactly match')
    a.require(g.check_enrollment(task_id, root) is not None, 'Transfer requires independently gated successor')
    owned = a.read_json(oldrun / 'publication.json')['paths']
    a.require(paths and len(paths) == len(set(paths)), 'Transfer requires unique exact paths')
    entries = []
    for name in paths:
        a.relative(path, name)
        a.require(not name.startswith(('.agent-work/', 'runs/', 'outputs/', '.git/')) and name in owned and name in bypath, 'Transfer path is not original owned product')
        a.require(g._reviewed_blob(path, name) == bypath[name], 'Transfer file differs from original candidate: ' + name)
        entries.append(bypath[name])
    record = {'schema_version': '1.1.0', 'kind': 'transfer', 'source': source, 'successor': task_id,
              'binding': binding, 'anchor': bound, 'entries': entries}
    with a.lock(a.relative(path, '.agent-work/recovery.lock')):
        value = a.read_json(run / 'publication.json')
        a.require(value['phase'] == 'begun' and not value.get('recovery'), 'Transfer manifest is already prepared/closed')
        for other in Path(root, 'runs').glob('*/publication.json'):
            recovery = a.read_json(other).get('recovery')
            a.require(not recovery or recovery['source'] != source or not set(paths) & {e['path'] for e in recovery['entries']}, 'Source ownership already transferred')
        value['recovery'] = record
        value['paths'] = sorted(set(value['paths']) | set(paths))
        a.write_json(run / 'publication.json', value)
    return record


def validate(task_id, root, publication):
    recovery = publication.get('recovery')
    if recovery is None:
        return set()
    a.require(recovery.get('kind') == 'transfer' and 'anchor' in recovery,
              'Unsupported recovery manifest; close this task as records and start a new one')
    run, _, _ = auto.context(task_id, root)
    a.require(recovery['successor'] == task_id and recovery['binding'] == a.read_json(run / 'repository.json'), 'Transfer identity changed')
    a.require(anchor(recovery['source'], root)[2] == recovery['anchor'], 'Source submission changed after transfer')
    # Original file identities are checked at handoff. Later implementation is
    # permitted, but must pass the successor's own tests and independent seal.
    a.require({e['path'] for e in recovery['entries']} <= set(publication['paths']), 'Transferred ownership missing')
    return {recovery['source']}
