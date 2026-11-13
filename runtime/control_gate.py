"""P1 cooperating local CLI gates. No authenticated identity or isolation boundary."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import agentctl as a
import impact_tests as impact

VERSION = '0.1.0'
ENROLLMENT = '0.4.0'
# Older enrollments stay loadable so their tasks can be closed as records, never published as product.
LEGACY_ENROLLMENTS = ('0.1.0', '0.2.0', '0.3.0')
CONFIG = '.agent-work/gates.json'
MAX_BYTES = 64 * 1024 * 1024


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def _hash(value):
    return a.digest(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                               allow_nan=False).encode('utf-8'))


def _read(path):
    a.require(path.stat().st_size <= 2 * 1024 * 1024, 'P1 record exceeds limit')
    return a.read_json(path)


def _run(task_id, root):
    return a.relative(root, 'runs/' + a.identifier(task_id))


def _git(root, *args, data=None, raw=False, optional=False):
    proc = subprocess.run(['git', '--literal-pathspecs', *args], cwd=root, input=data,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    if proc.returncode != 0 and optional:
        return None
    a.require(proc.returncode == 0, 'P1 Git inspection failed')
    value = proc.stdout.decode('utf-8')
    return value if raw else value.strip()


def _profile(value):
    keys = {'schema_version', 'enabled', 'repository_id', 'selector', 'required_suites',
            'timeout_seconds', 'policy', 'author'}
    a.require(type(value) is dict and set(value) == keys, 'Invalid P1 configuration fields')
    a.require(value['schema_version'] == VERSION and type(value['enabled']) is bool,
              'Invalid P1 configuration version')
    a.identifier(value['repository_id'])
    a.require(set(value['selector']) == {'project', 'service', 'environment'}, 'Invalid P1 selector')
    for item in value['selector'].values():
        a.identifier(item)
    a.require(type(value['timeout_seconds']) is int and 1 <= value['timeout_seconds'] <= 1800,
              'Invalid P1 test timeout')
    a.require(value['policy'] in ({'submission': 'allow', 'publication': 'allow'},
        {'submission': 'deny', 'publication': 'deny'}, {'submission': 'allow', 'publication': 'deny'}),
        'Invalid P1 lifecycle policy')
    _identity(value['author'])
    suites = value['required_suites']
    a.require(type(suites) is list and 0 < len(suites) <= 32, 'P1 mandatory suites required')
    seen = set()
    for suite in suites:
        a.require(type(suite) is dict and set(suite) == {'id', 'argv'}, 'Invalid P1 suite')
        a.identifier(suite['id'])
        a.require(suite['id'] not in seen, 'Duplicate P1 suite')
        seen.add(suite['id'])
        argv = suite['argv']
        a.require(type(argv) is list and 2 <= len(argv) <= 128 and
                  all(type(s) is str and 0 < len(s) <= 1024 and '\0' not in s for s in argv),
                  'Invalid P1 suite command')
        a.require(argv[0] == '@project-python' and argv[1:3] == ['-m', 'unittest'],
                  'P1 suites require the project Python unittest runner')
    return value


def _identity(value):
    a.require(type(value) is dict and set(value) == {'subject', 'session'} and
              all(type(v) is str and 0 < len(v) <= 128 for v in value.values()),
              'Invalid declared P1 identity')


def _context(task_id, root):
    import repoctl as r
    run = _run(task_id, root)
    binding = _read(a.relative(run, 'repository.json', file=True))
    path, entry = r.repo(binding['repository_id'], root)
    a.require(path.resolve() == Path(root).resolve(), 'P1 requires the registered framework checkout')
    a.require(entry['uuid'] == binding['repository_uuid'] and binding['task_id'] == task_id,
              'P1 repository binding mismatch')
    r.validate_scope(binding['scope'], complete=True)
    publication = _read(a.relative(run, 'publication.json', file=True))
    a.require(publication['task_id'] == task_id, 'P1 publication task mismatch')
    return run, binding, publication


def enroll(task_id, root=a.ROOT):
    """Called only by new bound task initialization, never by resume/begin."""
    root = Path(root).resolve()
    config = a.relative(root, CONFIG)
    if not config.exists():
        return None
    run = _run(task_id, root)
    taskfile = a.relative(run, 'task.json', file=True)
    task = _read(taskfile)
    try:
        profile = _profile(_read(config))
    except Exception:
        task['control_enrollment'] = 'pending'
        a.write_json(taskfile, task)
        raise
    if not profile['enabled']:
        return None
    binding = _read(a.relative(run, 'repository.json', file=True))
    if (binding['repository_id'] != profile['repository_id'] or
        any(binding['scope'][k] != v for k, v in profile['selector'].items())):
        return None
    a.require(task['state'] == 'queued', 'P1 enrollment requires a new queued task')
    companion = a.relative(run, 'controls.json')
    ledger = a.relative(root, 'runs/control-enrollments/' + task_id + '.json')
    a.require(not companion.exists() and not ledger.exists() and 'control_enrollment' not in task,
              'P1 enrollment already exists')
    task['control_enrollment'] = 'pending'
    a.write_json(taskfile, task)
    a.require(len(task_id) <= 128, 'P1 task ID exceeds limit')
    run, binding, publication = _context(task_id, root)
    value = {'schema_version': ENROLLMENT, 'mode': 'enforce', 'assurance': 'local-cooperating-cli',
             'task_id': task_id, 'binding': binding, 'base_head': publication['base_head'],
             'publication_policy': publication['policy'], 'publication_policy_sha256': publication['policy_sha256'],
             'config': profile, 'config_sha256': a.digest(config.read_bytes()),
             'created_at': _now(), 'nonce': uuid.uuid4().hex}
    impact_capability = impact.capture(root, publication['base_head'])
    if impact_capability is not None:
        value['impact_tests'] = impact_capability
    digest = _hash(value)
    a.write_json(companion, value)
    a.write_json(ledger, {'digest': digest, 'enrollment': value})
    task['control_enrollment'] = digest
    a.write_json(taskfile, task)
    return {'mode': 'enforce', 'assurance': value['assurance'], 'enrollment_digest': digest}


def check_enrollment(task_id, root=a.ROOT):
    root = Path(root).resolve()
    run = _run(task_id, root)
    task = _read(a.relative(run, 'task.json', file=True))
    obsolete = ('submission_profile_state' in task or
                a.relative(run, 'submission-profile-state.json').exists() or
                any(a.relative(run, 'gates').glob('profile-*.json')))
    companion = a.relative(run, 'controls.json')
    ledger = a.relative(root, 'runs/control-enrollments/' + task_id + '.json')
    if not (companion.exists() or ledger.exists() or 'control_enrollment' in task):
        a.require(not obsolete, 'Legacy submission profile state is unsupported; start a new task')
        return None
    a.require(companion.is_file() and ledger.is_file() and 'control_enrollment' in task,
              'P1 enrollment is missing or downgraded')
    value = _read(companion)
    stored = _read(ledger)
    a.require(type(value) is dict and stored == {'digest': _hash(value), 'enrollment': value} and
              task['control_enrollment'] == _hash(value), 'P1 enrollment differs from local ledger')
    expected_keys = {'schema_version', 'mode', 'assurance', 'task_id', 'binding', 'base_head',
                     'publication_policy', 'publication_policy_sha256', 'config', 'config_sha256',
                     'created_at', 'nonce'}
    legacy = value.get('schema_version') in LEGACY_ENROLLMENTS
    optional = {'impact_tests', 'submission_profile'} if legacy else {'impact_tests'}
    a.require(expected_keys <= set(value) <= expected_keys | optional, 'Invalid P1 enrollment fields')
    a.require((legacy or value['schema_version'] == ENROLLMENT) and value['mode'] == 'enforce' and
              value['assurance'] == 'local-cooperating-cli' and value['task_id'] == task_id,
              'Invalid P1 enrollment')
    if legacy:
        # Intact by its own ledger. Its configuration and removed profile rules are frozen
        # history; only the declared author is still used, to keep the closing review independent.
        _identity(value['config']['author'])
    else:
        a.require(not obsolete, 'Legacy submission profile state is unsupported; start a new task')
        if 'impact_tests' in value:
            a.require(value['impact_tests'] == impact.capture(root, value['base_head']), 'Impact capture differs from baseline')
        _profile(value['config'])
        config = a.relative(root, CONFIG, file=True)
        a.require(a.digest(config.read_bytes()) == value['config_sha256'] and
                  _read(config) == value['config'], 'P1 configuration changed after enrollment')
    _, binding, publication = _context(task_id, root)
    a.require(binding == value['binding'] and publication['base_head'] == value['base_head'] and
              publication['policy'] == value['publication_policy'] and
              publication['policy_sha256'] == value['publication_policy_sha256'],
              'P1 enrollment scope, baseline or destination changed')
    import repo_automation as auto
    settings = auto.policy(root)
    a.require(settings == value['publication_policy'] and
              a.digest(a.relative(root, '.agent-work/automation.json', file=True).read_bytes()) == value['publication_policy_sha256'],
              'P1 standing publication policy changed')
    auto.assert_destination(root, settings)
    return value


def _legacy(enrollment):
    return enrollment['schema_version'] != ENROLLMENT


def _kind(task_id, root, result):
    import repo_automation as auto
    _, _, publication = _context(task_id, root)
    return auto.publication_kind(task_id, publication['paths'], result)


def _subject(task_id, root, result, enrollment):
    """What a review binds: the tested candidate, or the identity of an incomplete closure.

    Incomplete work runs no tests and publishes no product, so its review is bound
    to the task identity here and to the exact result through result_digest.
    """
    if result['status'] == 'completed':
        return candidate(task_id, root)
    _, binding, publication = _context(task_id, root)
    value = {'schema_version': VERSION, 'kind': 'incomplete-records', 'task_id': task_id,
             'enrollment_digest': _hash(enrollment), 'binding': binding, 'base_head': publication['base_head']}
    return {'digest': _hash(value), 'candidate': value}


def _managed(task_id):
    return {*[
        '.agent-work/tasks/' + task_id + '/' + name for name in ('spec.md', 'record.json', 'report.ko.md')]}


def _evidence_path(name, task_id):
    return name.startswith('.agent-work/tasks/' + task_id + '/evidence/')


def _blob(root, name, commit=None):
    file = a.relative(root, name)
    if commit is not None:
        line = _git(root, 'ls-tree', '-z', commit, '--', name, raw=True)
        if not line:
            return {'path': name, 'state': 'deleted'}
        a.require(line.endswith('\0') and line.count('\0') == 1, 'P1 ambiguous committed path')
        meta, actual = line[:-1].split('\t', 1)
        mode, kind, oid = meta.split()
        a.require(actual == name and kind == 'blob' and mode in ('100644', '100755'),
                  'P1 unsupported committed object')
        return {'path': name, 'state': 'file', 'oid': oid, 'mode': mode}
    if not file.exists():
        return {'path': name, 'state': 'deleted'}
    a.require(file.is_file() and file.stat().st_size <= MAX_BYTES, 'P1 candidate file unsupported')
    content = file.read_bytes()
    a.require(len(content) <= MAX_BYTES, 'P1 candidate size limit')
    oid = _git(root, 'hash-object', '--path=' + name, '--stdin', data=content)
    staged = _git(root, 'ls-files', '--stage', '-z', '--', name, raw=True)
    mode = staged.split()[0] if staged else '100644'
    if os.name != 'nt' and _git(root, 'config', '--get', 'core.filemode') == 'true':
        mode = '100755' if file.stat().st_mode & 0o111 else '100644'
    a.require(mode in ('100644', '100755'), 'P1 unsupported candidate mode')
    return {'path': name, 'state': 'file', 'oid': oid, 'mode': mode}


def _environment(root):
    names = {'.venv-controls/Scripts/python.exe' if os.name == 'nt' else '.venv-controls/bin/python',
             '.venv-controls/pyvenv.cfg'}
    environment = a.relative(root, '.venv-controls')
    for metadata in environment.rglob('*.dist-info/METADATA'):
        names.add(metadata.relative_to(root).as_posix())
    output = []
    for name in sorted(names):
        file = a.relative(root, name, file=True)
        a.require(file.stat().st_size <= MAX_BYTES, 'P1 environment metadata too large')
        output.append({'path': name, 'sha256': a.digest(file.read_bytes())})
    return output


def _reviewed_blob(root, name):
    entry = _blob(root, name)
    entry['raw_sha256'] = (a.digest(a.relative(root, name, file=True).read_bytes())
                           if entry['state'] == 'file' else None)
    return entry


def _committed_raw_matches(root, committed, expected):
    size = int(_git(root, 'cat-file', '-s', committed['oid']))
    a.require(0 <= size <= MAX_BYTES, 'P1 committed object exceeds size limit')
    process = subprocess.run(['git', 'cat-file', 'blob', committed['oid']], cwd=root,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    a.require(process.returncode == 0 and len(process.stdout) == size,
              'P1 committed object could not be read exactly')
    return a.digest(process.stdout) == expected


def _dependency_matches(root, item, commit):
    """Match reviewed bytes or their Git-clean representation, preserving mode.

    Existing CRLF blobs can remain in an index after autocrlf is enabled. Their
    raw bytes were tested even though a new clean-filter pass yields another OID.
    Do not rewrite the index or relax either the reviewed SHA or object checks.
    """
    current = _blob(root, item['path'])
    committed = _blob(root, item['path'], commit)
    if item['sha256'] is None:
        return item.get('mode') is None and current['state'] == committed['state'] == 'deleted'
    if current['state'] != 'file' or committed['state'] != 'file':
        return False
    if item.get('mode') not in ('100644', '100755') or current['mode'] != item['mode'] or committed['mode'] != item['mode']:
        return False
    source = a.relative(root, item['path'], file=True)
    if a.digest(source.read_bytes()) != item['sha256']:
        return False
    if committed == current:
        return True
    return _committed_raw_matches(root, committed, item['sha256'])


def candidate(task_id, root=a.ROOT):
    root = Path(root).resolve()
    enrollment = check_enrollment(task_id, root)
    a.require(enrollment is not None, 'Task is not P1 enrolled')
    a.require(not _legacy(enrollment), 'Legacy enrollment can only be closed as incomplete records; start a new task')
    _, _, publication = _context(task_id, root)
    import task_recovery
    task_recovery.validate(task_id, root, publication)
    paths = publication['paths']
    a.require(type(paths) is list and len(paths) <= 512 and len(set(paths)) == len(paths),
              'Invalid P1 owned path set')
    for name in paths:
        a.relative(root, name)
        a.require(not name.startswith(('runs/', 'outputs/', '.git/')), 'P1 publication path unsupported')
    # No product is a records publication: the candidate still binds environment and dependencies.
    product = sorted(name for name in paths if name not in _managed(task_id) and not _evidence_path(name, task_id))
    dependencies = []
    index_modes = {}
    for row in filter(None, _git(root, 'ls-files', '--stage', '-z', raw=True).split('\0')):
        metadata, name = row.split('\t', 1)
        mode, _, stage = metadata.split()
        a.require(stage == '0', 'P1 unresolved index conflict')
        index_modes[name] = mode
    native_modes = os.name != 'nt' and _git(root, 'config', '--get', 'core.filemode', optional=True) == 'true'
    source_names = set(filter(None, _git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z', raw=True).split('\0')))
    # Owned deletions must remain in the inventory after Git removes their index entries.
    source_names.update(product)
    for name in sorted(source_names):
        if name.startswith(('runtime/', 'shared/', 'core/', 'modules/', '.codex/', '.agents/')) or name in ('registry.json', 'AGENTS.md', '.gitattributes', '.gitignore'):
            safe = a.relative(root, name)
            if not safe.exists():
                dependencies.append({'path': name, 'sha256': None, 'mode': None})
            else:
                a.require(safe.is_file() and safe.stat().st_size <= MAX_BYTES, 'P1 dependency unsupported')
                mode = ('100755' if safe.stat().st_mode & 0o111 else '100644') if native_modes else index_modes.get(name, '100644')
                a.require(mode in ('100644', '100755'), 'P1 unsupported dependency mode')
                dependencies.append({'path': name, 'sha256': a.digest(safe.read_bytes()), 'mode': mode})
    value = {'schema_version': VERSION, 'task_id': task_id, 'enrollment_digest': _hash(enrollment),
             'binding': enrollment['binding'], 'base_head': enrollment['base_head'],
             'environment': _environment(root),
             'dependencies': dependencies, 'entries': [_reviewed_blob(root, name) for name in product]}
    return {'digest': _hash(value), 'candidate': value}


def _records(run):
    directory = a.relative(run, 'gates')
    directory.mkdir(exist_ok=True)
    return directory


def _append(run, prefix, value):
    directory = _records(run)
    name = prefix + '-' + uuid.uuid4().hex + '.json'
    file = a.relative(directory, name)
    with file.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return name


def impact_selection(task_id, current, enrollment, root):
    return impact.select(current, enrollment, root)


def run_tests(task_id, suite_id, root=a.ROOT):
    root = Path(root).resolve()
    before = candidate(task_id, root)
    enrollment = check_enrollment(task_id, root)
    suites = impact_selection(task_id, before, enrollment, root)['suites']
    suite = next((s for s in suites if s['id'] == suite_id), None)
    a.require(suite is not None, 'Unknown mandatory P1 suite')
    executable = a.relative(root, '.venv-controls/Scripts/python.exe' if os.name == 'nt'
                            else '.venv-controls/bin/python', file=True)
    run = _run(task_id, root)
    argv = [str(executable), '-I', '-B', *suite['argv'][1:]]
    # The child is local candidate code, not a sandbox or trusted runner.
    env = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP'):
        env.pop(key, None)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['AGENT_SUBMISSION_TASK'] = task_id
    log = a.relative(run, 'evidence/gate-test-' + uuid.uuid4().hex + '.log')
    code, reason = None, None
    with log.open('wb') as output:
        proc = subprocess.Popen(argv, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        overflow = threading.Event()
        def drain():
            total = 0
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                permitted = min(len(chunk), MAX_BYTES - total)
                if permitted:
                    output.write(chunk[:permitted])
                    total += permitted
                if permitted < len(chunk):
                    overflow.set()
                    proc.kill()
                    break
        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        try:
            code = proc.wait(timeout=enrollment['config']['timeout_seconds'])
        except subprocess.TimeoutExpired:
            reason = 'timeout'
            proc.kill()
            proc.wait(timeout=10)
        reader.join(timeout=5)
        if reader.is_alive():
            reason = 'output_pipe_unclosed'
        elif overflow.is_set():
            reason = 'output_limit'
        if not reader.is_alive():
            proc.stdout.close()
    after = candidate(task_id, root)
    a.require(log.stat().st_size <= MAX_BYTES, 'P1 test output exceeds limit')
    log_bytes = log.read_bytes()
    counts = re.findall(rb'^Ran ([0-9]+) tests? in ', log_bytes, re.MULTILINE)
    count = int(counts[-1]) if counts else 0
    value = {'kind': 'test', 'task_id': task_id, 'candidate_digest': before['digest'],
             'suite_id': suite_id, 'suite_digest': _hash(suite), 'created_at': _now(),
             'outcome': 'passed' if code == 0 and reason is None and count > 0 and before == after else 'failed',
             'tests_run': count,
             'exit_code': code, 'reason': reason, 'candidate_unchanged': before == after,
             'evidence': {'path': log.relative_to(root).as_posix(), 'sha256': a.digest(log_bytes)},
             'assurance': 'local-executed-untrusted-candidate'}
    if 'impact_tests' in enrollment:
        value['impact_selection'] = impact_selection(task_id, before, enrollment, root)
    record = _append(run, 'test', value)
    return {'record': record, **value}


def assess(task_id, value, root=a.ROOT):
    root = Path(root).resolve()
    enrollment = check_enrollment(task_id, root)
    a.require(enrollment is not None, 'Task is not P1 enrolled')
    result = _read(a.relative(_run(task_id, root), 'result.json', file=True))
    kind, tested = _kind(task_id, root, result), result['status'] == 'completed'
    current = _subject(task_id, root, result, enrollment)
    required_fields = {'kind', 'candidate_digest', 'reviewer', 'verdict', 'evidence'}
    if tested and 'impact_tests' in enrollment:
        required_fields |= {'impact_digest', 'impact_review'}
        selection = impact_selection(task_id, current, enrollment, root)
        a.require(value.get('impact_digest') == _hash(selection), 'Impact review selection is stale')
        review = value.get('impact_review')
        a.require(type(review) is dict and set(review) == {e['path'] for e in current['candidate']['entries']} and all(type(v) is str and len(v) >= 10 for v in review.values()), 'Independent impact review must cover every owned path')
    a.require(type(value) is dict and set(value) == required_fields,
              'Invalid P1 assessment fields')
    a.require(value['kind'] == kind, 'P1 assessment kind differs from the publication kind: ' + kind)
    _identity(value['reviewer'])
    author = enrollment['config']['author']
    a.require(all(value['reviewer'][k] != author[k] for k in ('subject', 'session')),
              'P1 reviewer is not declared independent from author')
    a.require(value['candidate_digest'] == current['digest'], 'P1 assessment candidate is stale')
    a.require(value['verdict'] in ('accepted', 'rework', 'inconclusive'), 'Invalid P1 review verdict')
    evidence = value['evidence']
    a.require(type(evidence) is list and 0 < len(evidence) <= 64, 'P1 review evidence required')
    items = []
    for name in evidence:
        a.require(name.startswith(('runs/' + task_id + '/evidence/', 'outputs/' + task_id + '/')),
                  'P1 assessment evidence must belong to task')
        file = a.relative(root, name, file=True)
        a.require(0 < file.stat().st_size <= MAX_BYTES, 'Invalid P1 assessment evidence size')
        items.append({'path': name, 'sha256': a.digest(file.read_bytes())})
    record = {'kind': 'review', 'publication_kind': kind, 'task_id': task_id, 'candidate_digest': current['digest'],
              'reviewer': value['reviewer'], 'verdict': value['verdict'], 'evidence': items,
              'tests': _proofs(task_id, current, root, review_required=False, tested=tested),
              'result_digest': _hash(_result_subject(result, root)),
              'created_at': _now(), 'identity_authenticated': False}
    if tested and 'impact_tests' in enrollment:
        record.update(impact_digest=value['impact_digest'], impact_review=value['impact_review'])
    name = _append(_run(task_id, root), 'review', record)
    return {'record': name, **record}


def _evidence_valid(root, item):
    file = a.relative(root, item['path'], file=True)
    a.require(a.digest(file.read_bytes()) == item['sha256'], 'P1 evidence bytes changed')


def _proofs(task_id, current, root, review_required=True, kind='product', tested=True):
    """Passing executions of every selected suite, then the accepted review of this kind.

    An incomplete closure (tested=False) selects no suite; its review is still required.
    """
    run = _run(task_id, root)
    enrollment = check_enrollment(task_id, root)
    records = []
    for file in sorted(_records(run).glob('*.json')):
        value = _read(a.relative(run, 'gates/' + file.name, file=True))
        if value.get('candidate_digest') == current['digest']:
            a.require(value.get('task_id') == task_id, 'P1 evidence task mismatch')
            records.append((file.name, value))
    suites = impact_selection(task_id, current, enrollment, root)['suites'] if tested else []
    selected = []
    for suite in suites:
        matching = [(n, v) for n, v in records if v.get('kind') == 'test' and v.get('suite_id') == suite['id']]
        a.require(matching, 'P1 mandatory test evidence missing: ' + suite['id'])
        name, proof = max(matching, key=lambda row: (row[1]['created_at'], row[0]))
        a.require('profile_digest' not in proof, 'Legacy submission profile proof is unsupported')
        a.require(proof['suite_digest'] == _hash(suite) and proof['outcome'] == 'passed' and
                  proof['exit_code'] == 0 and type(proof.get('tests_run')) is int and proof['tests_run'] > 0 and
                  proof['candidate_unchanged'] is True,
                  'P1 mandatory test did not pass')
        if 'impact_tests' in enrollment:
            a.require(proof.get('impact_selection') == impact_selection(task_id, current, enrollment, root), 'P1 impact selection changed')
        _evidence_valid(root, proof['evidence'])
        selected.append({'path': 'runs/' + task_id + '/gates/' + name, 'sha256': a.digest((run / 'gates' / name).read_bytes())})
    if not review_required:
        return selected
    reviews = [(n, v) for n, v in records if v.get('kind') == 'review']
    a.require(reviews, 'P1 independent review missing')
    name, review = max(reviews, key=lambda row: (row[1]['created_at'], row[0]))
    _identity(review['reviewer'])
    a.require(review['verdict'] == 'accepted' and all(review['reviewer'][k] != enrollment['config']['author'][k]
              for k in ('subject', 'session')), 'P1 review is unresolved or not independent')
    a.require(review.get('publication_kind') == kind, 'P1 review is for another publication kind')
    if tested and 'impact_tests' in enrollment:
        a.require(review.get('impact_digest') == _hash(impact_selection(task_id, current, enrollment, root)), 'P1 impact review changed')
    a.require(review.get('tests') == selected, 'P1 review does not cover current test executions')
    a.require(review['evidence'], 'P1 review evidence missing')
    for item in review['evidence']:
        _evidence_valid(root, item)
    selected.append({'path': 'runs/' + task_id + '/gates/' + name, 'sha256': a.digest((run / 'gates' / name).read_bytes())})
    return selected


def _result_subject(result, root):
    value = copy.deepcopy(result)
    for item in value['artifacts']:
        item['sha256'] = a.digest(a.relative(root, item['path'], file=True).read_bytes())
    evidence = sorted({name for check in value['verification'] for name in check['evidence']})
    return {'result': value, 'evidence': [{'path': name, 'sha256': a.digest(a.relative(root, name, file=True).read_bytes())}
                                         for name in evidence]}


def _incomplete_candidate(task_id, root, enrollment):
    """Seal only transferable file identity; incomplete work needs no test runner."""
    _, binding, publication = _context(task_id, root)
    paths = publication['paths']
    a.require(type(paths) is list and len(paths) <= 512 and len(paths) == len(set(paths)), 'Invalid incomplete owned path set')
    product = sorted(name for name in paths if name not in _managed(task_id) and not _evidence_path(name, task_id))
    if not product:
        return None
    for name in product:
        a.relative(root, name)
        a.require(not name.startswith(('runs/', 'outputs/', '.git/')), 'Incomplete publication path unsupported')
    value = {'schema_version': VERSION, 'kind': 'incomplete-file-candidate', 'task_id': task_id,
             'enrollment_digest': _hash(enrollment), 'binding': binding, 'base_head': publication['base_head'],
             'entries': [_reviewed_blob(root, name) for name in product]}
    return {'digest': _hash(value), 'candidate': value}


def check_submission(task_id, root=a.ROOT, result=None, persist=False, publish=False, cancel=False):
    """Seal a submission. Incomplete results need a review only when they are published.

    cancel closes without a transfer anchor: product files are neither read nor required.
    """
    root = Path(root).resolve()
    enrollment = check_enrollment(task_id, root)
    if enrollment is None:
        return None
    run = _run(task_id, root)
    if result is None:
        result = _read(a.relative(run, 'result.json', file=True))
    completed = result['status'] == 'completed'
    response = {'mode': 'enforce', 'status': 'incomplete-result', 'assurance': 'local-cooperating-cli'}
    files = {}
    if completed:
        a.require(enrollment['config']['policy']['submission'] == 'allow', 'P1 submission policy denies action')
    else:
        task = _read(run / 'task.json')
        file = run / 'incomplete-candidate.json'
        anchor = task.get('submission', {}).get('incomplete_candidate_sha256')
        if anchor is not None:
            a.require(file.is_file() and a.digest(file.read_bytes()) == anchor, 'Incomplete candidate differs from source submission anchor')
            saved = _read(file)
            a.require(saved['candidate']['digest'] == _hash(saved['candidate']['candidate']), 'Incomplete candidate digest mismatch')
            files['incomplete-candidate.json'] = saved
            response['incomplete_candidate_sha256'] = anchor
        elif persist and not cancel and result['status'] == 'partial' and task['state'] == 'running':
            incomplete = _incomplete_candidate(task_id, root, enrollment)
            if incomplete is not None:
                saved = {'candidate': incomplete, 'result_sha256': a.digest(a.json_bytes(result))}
                a.require(not file.exists() or _read(file) == saved, 'Incomplete candidate changed after submission attempt')
                files['incomplete-candidate.json'] = saved
                response['incomplete_candidate_sha256'] = a.digest(a.json_bytes(saved))
        if not publish:
            if persist and files:
                response['files'] = files
            return response
    kind = _kind(task_id, root, result)
    current = _subject(task_id, root, result, enrollment)
    proofs = _proofs(task_id, current, root, kind=kind, tested=completed)
    review_record = _read(a.relative(root, proofs[-1]['path'], file=True))
    a.require(review_record.get('result_digest') == _hash(_result_subject(result, root)),
              'P1 result or referenced evidence changed after review')
    reviewed_hashes = {p['sha256'] for p in proofs}
    for proof in proofs:
        item = _read(a.relative(root, proof['path'], file=True))
        evidence = item['evidence'] if type(item['evidence']) is list else [item['evidence']]
        reviewed_hashes.update(e['sha256'] for e in evidence)
    for artifact in result['artifacts']:
        a.require(a.digest(a.relative(root, artifact['path'], file=True).read_bytes()) in reviewed_hashes,
                  'P1 artifact was not bound by review evidence')
    _, _, publication = _context(task_id, root)
    import task_evidence
    task_evidence.validate(root, task_id, publication)
    record_entries = [_reviewed_blob(root, name) for name in sorted(publication['paths']) if _evidence_path(name, task_id)]
    for item in record_entries:
        a.require(item['state'] == 'file' and a.digest(a.relative(root, item['path'], file=True).read_bytes()) in reviewed_hashes,
                  'P1 archive is not an exact reviewed evidence copy')
    seal = {'schema_version': VERSION, 'task_id': task_id, 'publication_kind': kind, 'candidate': current,
            'proofs': proofs, 'subject': _result_subject(result, root), 'record_entries': record_entries,
            'owned_paths': sorted(publication['paths'])}
    file = a.relative(run, 'gate-submission.json')
    task = _read(a.relative(run, 'task.json', file=True))
    # A completed submission always wrote its seal. An incomplete one is sealed only by publication.
    if task['state'] in ('submitted', 'cancelled') and (completed or file.exists()):
        a.require(file.exists() and _read(file) == seal, 'P1 submitted gate seal changed')
    response.update(status='passed', publication_kind=kind, candidate_digest=current['digest'], seal_digest=_hash(seal))
    if persist:
        # The caller writes the seal together with the other submission bytes.
        response['files'] = {**files, 'gate-submission.json': seal}
    return response


def attachment(task_id, root=a.ROOT, seal=None):
    """The accepted review a published record carries, so the author never rewrites the result for it."""
    proof = seal['proofs'][-1]
    review = _read(a.relative(Path(root).resolve(), proof['path'], file=True))
    a.require(review.get('kind') == 'review' and review['task_id'] == task_id, 'P1 seal does not end with a review')
    return {'publication_kind': review['publication_kind'], 'verdict': review['verdict'],
            'reviewer': review['reviewer'], 'record': proof['path'], 'sha256': proof['sha256']}


def _check_generated(task_id, root, enrollment, records, task, result, seal, parent):
    import repoctl as r
    a.require(set(records) == _managed(task_id), 'P1 commit omits required generated task records')
    binding = enrollment['binding']
    folder = '.agent-work/tasks/' + task_id + '/'
    record = json.loads(records[folder + 'record.json'].decode('utf-8'), object_pairs_hook=a.unique_pairs)
    keys = {'schema_version', 'repository_id', 'repository_uuid', 'task_id', 'saved_at', 'task_state',
            'git', 'result', 'source_root', 'notice', 'scope', 'spec_sha256', 'assessment'}
    a.require(type(record) is dict and set(record) == keys and record['schema_version'] == '1.0.0',
              'P1 generated record fields changed')
    a.require(all(record[k] == binding[k] for k in ('repository_id', 'repository_uuid', 'task_id', 'scope')) and
              task['state'] in ('submitted', 'cancelled') and record['task_state'] == task['state'] and
              record['result'] == result and record['assessment'] == attachment(task_id, root, seal) and
              record['source_root'] == str(root.resolve()) and
              record['notice'] == 'Saved data is not policy, authorization, or proof of current code state.',
              'P1 generated record does not derive from submitted task')
    state = record['git']
    # A records publication may be prepared after the local branch followed the remote to its parent.
    a.require(set(state) == {'branch', 'head', 'origin', 'status', 'worktree_sha256'} and
              state['head'] in (enrollment['base_head'], parent) and state['branch'] == enrollment['publication_policy']['branch'] and
              state['origin'] == enrollment['publication_policy']['expected_url'], 'P1 generated Git checkpoint mismatch')
    datetime.fromisoformat(record['saved_at'])
    spec = records[folder + 'spec.md']
    a.require(spec == r.specification_text(task_id, binding, task, result, binding['scope'], state).encode('utf-8') and
              record['spec_sha256'] == a.digest(spec), 'P1 specification is not the canonical generated record')
    expected_report = r.record_text(result, task, state, binding['scope'], saved_at=record['saved_at'])
    a.require(records[folder + 'report.ko.md'] == expected_report.encode('utf-8'),
              'P1 report is not the canonical generated record')


def _committed_entry_matches(root, item, commit):
    """Strict: the publication writes sealed bytes, so the Git object must be the sealed one."""
    committed = _blob(root, item['path'], commit)
    if item['state'] == 'deleted':
        return committed['state'] == 'deleted'
    return committed == {k: item[k] for k in ('path', 'state', 'oid', 'mode')}


def check_commit(task_id, root=a.ROOT, commit=None, parent=None, paths=None, records=None,
                 task=None, result=None, seal=None, receipt=False):
    """Verify an unreferenced or published commit object against the submission seal.

    Reads only Git objects and the sealed submission; HEAD, the shared index and
    the worktree are never consulted for committed content.
    """
    root = Path(root).resolve()
    enrollment = check_enrollment(task_id, root)
    if enrollment is None:
        return None
    a.require(enrollment['config']['policy']['publication'] == 'allow', 'P1 publication policy denies action')
    a.require(type(seal) is dict and type(records) is dict and type(paths) is list, 'P1 publication payload missing')
    fresh = check_submission(task_id, root, result=result, publish=True)
    a.require(fresh is not None and fresh['status'] == 'passed' and fresh['seal_digest'] == _hash(seal),
              'P1 seal differs from current submission state')
    product = seal['publication_kind'] == 'product'
    base = enrollment['base_head']
    if product:
        a.require(parent == base, 'P1 commit or parent mismatch')
        allowed = set(seal['owned_paths']) | {'.agent-work/automation.json'}
    else:
        # Records may follow a remote that advanced, but only if nobody touched this task's records.
        a.require(_git(root, 'merge-base', '--is-ancestor', base, parent, optional=True) is not None and
                  not _git(root, 'diff-tree', '-r', '--name-only', '-z', base, parent, '--',
                           '.agent-work/tasks/' + task_id, raw=True),
                  'P1 records parent is not an untouched descendant of the task base')
        allowed = {name for name in seal['owned_paths'] if _evidence_path(name, task_id)}
    a.require(_git(root, 'rev-list', '--parents', '-n', '1', commit).split() == [commit, parent],
              'P1 commit or parent mismatch')
    actual = sorted(filter(None, _git(root, 'diff-tree', '--no-commit-id', '--name-only', '-r', '-z',
                                      '--no-renames', parent, commit, raw=True).split('\0')))
    a.require(actual == sorted(paths) and _managed(task_id) <= set(actual) and
              set(actual) <= allowed | _managed(task_id),
              'P1 commit path set differs from submitted ownership')
    _check_generated(task_id, root, enrollment, records, task, result, seal, parent)
    for name, data in records.items():
        oid = _git(root, 'hash-object', '--path=' + name, '--stdin', data=data)
        a.require(_blob(root, name, commit) == {'path': name, 'state': 'file', 'oid': oid, 'mode': '100644'},
                  'P1 generated record differs from commit')
    # Unfinished or absent product stays in the worktree: a records commit binds records only.
    for item in seal['record_entries'] + (seal['candidate']['candidate']['entries'] if product else []):
        a.require(_committed_entry_matches(root, item, commit), 'P1 commit content differs from submitted candidate')
    for item in seal['candidate']['candidate']['dependencies'] if product else []:
        a.require(_dependency_matches(root, item, commit),
                  'P1 committed dependency differs from tested source')
    value = {'schema_version': VERSION, 'task_id': task_id, 'commit': commit,
             'seal_digest': _hash(seal), 'candidate_digest': seal['candidate']['digest'],
             'status': 'passed', 'assurance': 'local-cooperating-cli', 'checked_at': a.now()}
    if receipt:
        _append(_run(task_id, root), 'publication', value)
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('candidate', 'run-tests', 'assess', 'status', 'select-tests'))
    parser.add_argument('--task', required=True)
    parser.add_argument('--suite')
    parser.add_argument('--input')
    args = parser.parse_args(argv)
    try:
        a.load_task(args.task)
        if args.command == 'candidate':
            value = candidate(args.task)
        elif args.command == 'select-tests':
            value = impact_selection(args.task, candidate(args.task), check_enrollment(args.task), a.ROOT)
            value = {**value, 'digest': _hash(value)}
        elif args.command == 'run-tests':
            value = run_tests(args.task, args.suite)
        elif args.command == 'assess':
            value = assess(args.task, _read(a.relative(a.ROOT, args.input, file=True)))
        else:
            value = check_submission(args.task)
        print(json.dumps({'ok': True, 'data': value}, ensure_ascii=False))
        return 0 if not isinstance(value, dict) or value.get('outcome') != 'failed' else 2
    except (a.ContractError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
