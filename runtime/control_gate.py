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
import submission_profile as sp
import impact_tests as impact

VERSION = '0.1.0'
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
    value = {'schema_version': VERSION, 'mode': 'enforce', 'assurance': 'local-cooperating-cli',
             'task_id': task_id, 'binding': binding, 'base_head': publication['base_head'],
             'publication_policy': publication['policy'], 'publication_policy_sha256': publication['policy_sha256'],
             'config': profile, 'config_sha256': a.digest(config.read_bytes()),
             'created_at': _now(), 'nonce': uuid.uuid4().hex}
    capability = sp.capture(root, publication['base_head'])
    if capability is not None:
        value['schema_version'] = sp.ENROLLMENT_VERSION
        value['submission_profile'] = capability
    impact_capability = impact.capture(root, publication['base_head'])
    if impact_capability is not None:
        value['schema_version'] = impact.ENROLLMENT_VERSION
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
    companion = a.relative(run, 'controls.json')
    ledger = a.relative(root, 'runs/control-enrollments/' + task_id + '.json')
    if not (companion.exists() or ledger.exists() or 'control_enrollment' in task):
        return None
    a.require(companion.is_file() and ledger.is_file() and 'control_enrollment' in task,
              'P1 enrollment is missing or downgraded')
    value, stored = _read(companion), _read(ledger)
    a.require(stored == {'digest': _hash(value), 'enrollment': value} and
              task['control_enrollment'] == _hash(value), 'P1 enrollment differs from local ledger')
    expected_keys = {'schema_version', 'mode', 'assurance', 'task_id', 'binding', 'base_head',
                     'publication_policy', 'publication_policy_sha256', 'config', 'config_sha256',
                     'created_at', 'nonce'}
    if value.get('schema_version') == impact.ENROLLMENT_VERSION:
        expected_keys.add('impact_tests')
        a.require(value['impact_tests'] == impact.capture(root, value['base_head']), 'Impact capture differs from baseline')
    if value.get('schema_version') == sp.ENROLLMENT_VERSION or (value.get('schema_version') == impact.ENROLLMENT_VERSION and 'submission_profile' in value):
        expected_keys.add('submission_profile')
        sp.validate_capture(value, root)
    a.require(set(value) == expected_keys, 'Invalid P1 enrollment fields')
    a.require(value['schema_version'] in (VERSION, sp.ENROLLMENT_VERSION, impact.ENROLLMENT_VERSION) and value['mode'] == 'enforce' and
              value['assurance'] == 'local-cooperating-cli' and value['task_id'] == task_id,
              'Invalid P1 enrollment')
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


def _managed(task_id):
    return {'.agent-work/index.json', '.agent-work/INDEX.md', *[
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


def _reviewed_blob_matches(root, item, commit):
    # Recheck both raw bytes and Git representation; never accept a changed
    # candidate just because one earlier representation still exists in Git.
    if _reviewed_blob(root, item['path']) != item:
        return False
    committed = _blob(root, item['path'], commit)
    if committed['state'] != item['state']:
        return False
    if item['state'] == 'deleted':
        return item['raw_sha256'] is None
    if committed['mode'] != item['mode']:
        return False
    return (committed['oid'] == item['oid'] or
            _committed_raw_matches(root, committed, item['raw_sha256']))


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
    _, _, publication = _context(task_id, root)
    import task_recovery
    task_recovery.validate(task_id, root, publication)
    paths = publication['paths']
    a.require(type(paths) is list and len(paths) <= 512 and len(set(paths)) == len(paths),
              'Invalid P1 owned path set')
    for name in paths:
        a.relative(root, name)
        a.require(not name.startswith(('runs/', 'outputs/', '.git/')), 'P1 publication path unsupported')
    product = sorted(name for name in paths if name not in _managed(task_id) and not _evidence_path(name, task_id))
    a.require(product, 'P1 candidate has no reviewed product files')
    dependencies = []
    index_modes = {}
    for row in filter(None, _git(root, 'ls-files', '--stage', '-z', raw=True).split('\0')):
        metadata, name = row.split('\t', 1)
        mode, _, stage = metadata.split()
        a.require(stage == '0', 'P1 unresolved index conflict')
        index_modes[name] = mode
    native_modes = os.name != 'nt' and _git(root, 'config', '--get', 'core.filemode', optional=True) == 'true'
    source_names = set(filter(None, _git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z', raw=True).split('\0')))
    if 'submission_profile' in enrollment:
        source_names.update(filter(None, _git(root, 'ls-tree', '-r', '--name-only', '-z', enrollment['base_head'], raw=True).split('\0')))
    for name in sorted(source_names):
        if ('submission_profile' in enrollment and sp.protected(name)) or name.startswith(('runtime/', 'shared/', 'core/', 'modules/', '.codex/', '.agents/')) or name in ('registry.json', 'AGENTS.md', '.gitattributes', '.gitignore'):
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
    state = sp._state(task_id, root)
    return impact.select(current, enrollment, root, forced=bool(state and state[1]['profile'] == 'full'))


def run_tests(task_id, suite_id, root=a.ROOT):
    root = Path(root).resolve()
    before = candidate(task_id, root)
    enrollment = check_enrollment(task_id, root)
    suites, profile_proof = sp.effective(task_id, before, enrollment, root)
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
    if profile_proof is not None:
        value['profile_digest'] = profile_proof['sha256']
    if 'impact_tests' in enrollment:
        value['impact_selection'] = impact_selection(task_id, before, enrollment, root)
    record = _append(run, 'test', value)
    return {'record': record, **value}


def assess(task_id, value, root=a.ROOT):
    root = Path(root).resolve()
    current = candidate(task_id, root)
    enrollment = check_enrollment(task_id, root)
    required_fields = {'candidate_digest', 'reviewer', 'verdict', 'evidence'}
    if 'impact_tests' in enrollment:
        required_fields |= {'impact_digest', 'impact_review'}
        selection = impact_selection(task_id, current, enrollment, root)
        a.require(value.get('impact_digest') == _hash(selection), 'Impact review selection is stale')
        review = value.get('impact_review')
        a.require(type(review) is dict and set(review) == {e['path'] for e in current['candidate']['entries']} and all(type(v) is str and len(v) >= 10 for v in review.values()), 'Independent impact review must cover every owned path')
    a.require(type(value) is dict and set(value) == required_fields,
              'Invalid P1 assessment fields')
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
    record = {'kind': 'review', 'task_id': task_id, 'candidate_digest': current['digest'],
              'reviewer': value['reviewer'], 'verdict': value['verdict'], 'evidence': items,
              'tests': _proofs(task_id, current, root, review_required=False),
              'result_digest': _hash(_result_subject(_read(a.relative(_run(task_id, root), 'result.json', file=True)), root)),
              'created_at': _now(), 'identity_authenticated': False}
    if 'impact_tests' in enrollment:
        record.update(impact_digest=value['impact_digest'], impact_review=value['impact_review'])
    name = _append(_run(task_id, root), 'review', record)
    return {'record': name, **record}


def _evidence_valid(root, item):
    file = a.relative(root, item['path'], file=True)
    a.require(a.digest(file.read_bytes()) == item['sha256'], 'P1 evidence bytes changed')


def _proofs(task_id, current, root, review_required=True):
    run = _run(task_id, root)
    enrollment = check_enrollment(task_id, root)
    records = []
    for file in sorted(_records(run).glob('*.json')):
        value = _read(a.relative(run, 'gates/' + file.name, file=True))
        if value.get('candidate_digest') == current['digest']:
            a.require(value.get('task_id') == task_id, 'P1 evidence task mismatch')
            records.append((file.name, value))
    suites, profile_proof = sp.effective(task_id, current, enrollment, root)
    selected = [profile_proof] if profile_proof is not None else []
    for suite in suites:
        matching = [(n, v) for n, v in records if v.get('kind') == 'test' and v.get('suite_id') == suite['id']]
        a.require(matching, 'P1 mandatory test evidence missing: ' + suite['id'])
        name, proof = max(matching, key=lambda row: (row[1]['created_at'], row[0]))
        a.require(proof.get('profile_digest') == (profile_proof['sha256'] if profile_proof else None),
                  'P1 test profile approval changed')
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
    if 'impact_tests' in enrollment:
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


def check_submission(task_id, root=a.ROOT, result=None, persist=False):
    root = Path(root).resolve()
    enrollment = check_enrollment(task_id, root)
    if enrollment is None:
        return None
    run = _run(task_id, root)
    if result is None:
        result = _read(a.relative(run, 'result.json', file=True))
    if result['status'] != 'completed':
        response = {'mode': 'enforce', 'status': 'incomplete-result', 'assurance': 'local-cooperating-cli'}
        task = _read(run / 'task.json')
        file = run / 'incomplete-candidate.json'
        anchor = task.get('submission', {}).get('incomplete_candidate_sha256')
        if anchor is not None:
            a.require(file.is_file() and a.digest(file.read_bytes()) == anchor, 'Incomplete candidate differs from source submission anchor')
            saved = _read(file)
            a.require(saved['candidate']['digest'] == _hash(saved['candidate']['candidate']), 'Incomplete candidate digest mismatch')
            response['incomplete_candidate_sha256'] = anchor
        elif persist and result['status'] == 'partial' and task['state'] == 'running':
            incomplete = _incomplete_candidate(task_id, root, enrollment)
            if incomplete is not None:
                saved = {'candidate': incomplete, 'result_sha256': a.digest((json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8'))}
                if file.exists():
                    a.require(_read(file) == saved, 'Incomplete candidate changed after submission attempt')
                else:
                    a.write_json(file, saved)
                response['incomplete_candidate_sha256'] = a.digest(file.read_bytes())
        return response
    a.require(enrollment['config']['policy']['submission'] == 'allow', 'P1 submission policy denies action')
    current = candidate(task_id, root)
    proofs = _proofs(task_id, current, root)
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
    seal = {'schema_version': VERSION, 'task_id': task_id, 'candidate': current, 'proofs': proofs,
            'subject': _result_subject(result, root), 'record_entries': record_entries,
            'owned_paths': sorted(publication['paths'])}
    file = a.relative(run, 'gate-submission.json')
    task = _read(a.relative(run, 'task.json', file=True))
    if task['state'] == 'submitted':
        a.require(file.exists() and _read(file) == seal, 'P1 submitted gate seal changed')
    elif persist:
        a.write_json(file, seal)
    return {'mode': 'enforce', 'status': 'passed', 'candidate_digest': current['digest'],
            'seal_digest': _hash(seal), 'assurance': 'local-cooperating-cli'}


def _check_generated(task_id, root, enrollment, actual):
    import repoctl as r
    a.require(_managed(task_id) <= set(actual), 'P1 commit omits required generated task records')
    run = _run(task_id, root)
    task = _read(a.relative(run, 'task.json', file=True))
    result = _read(a.relative(run, 'result.json', file=True))
    binding = enrollment['binding']
    folder = '.agent-work/tasks/' + task_id + '/'
    record = _read(a.relative(root, folder + 'record.json', file=True))
    keys = {'schema_version', 'repository_id', 'repository_uuid', 'task_id', 'saved_at',
            'task_state', 'git', 'result', 'source_root', 'notice', 'scope', 'spec_sha256'}
    a.require(set(record) == keys and record['schema_version'] == '1.0.0',
              'P1 generated record fields changed')
    a.require(all(record[k] == binding[k] for k in ('repository_id', 'repository_uuid', 'task_id', 'scope')) and
              record['task_state'] == task['state'] and record['result'] == result and
              record['source_root'] == str(root.resolve()) and
              record['notice'] == 'Saved data is not policy, authorization, or proof of current code state.',
              'P1 generated record does not derive from submitted task')
    state = record['git']
    a.require(set(state) == {'branch', 'head', 'origin', 'status', 'worktree_sha256'} and
              state['head'] == enrollment['base_head'] and state['branch'] == enrollment['publication_policy']['branch'] and
              state['origin'] == enrollment['publication_policy']['expected_url'], 'P1 generated Git checkpoint mismatch')
    datetime.fromisoformat(record['saved_at'])
    expected_spec = r.specification_text(task_id, binding, task, result, binding['scope'], state)
    spec = a.relative(root, folder + 'spec.md', file=True).read_text(encoding='utf-8')
    a.require(spec == expected_spec and record['spec_sha256'] == a.digest(spec.encode('utf-8')),
              'P1 specification is not the canonical generated record')
    expected_report = r.record_text(result, task, state, binding['scope'], saved_at=record['saved_at'])
    a.require(a.relative(root, folder + 'report.ko.md', file=True).read_text(encoding='utf-8') == expected_report,
              'P1 report is not the canonical generated record')
    index = _read(a.relative(root, '.agent-work/index.json', file=True))
    expected_item = {'status': result['status'], 'state': task['state'], 'saved_at': record['saved_at'],
                     'summary': result['summary'], 'path': 'tasks/' + task_id + '/spec.md', 'scope': binding['scope']}
    a.require(index['tasks'][task_id] == expected_item, 'P1 index entry is not derived from submitted task')
    baseline_text = _git(root, 'show', enrollment['base_head'] + ':.agent-work/index.json', optional=True)
    baseline = json.loads(baseline_text) if baseline_text else {'schema_version': '1.0.0', 'tasks': {}}
    import task_recovery
    _, _, publication = _context(task_id, root)
    task_recovery.check_index(task_id, root, publication, index, baseline)
    rows = ['# Repository work index', '', 'Read records as task data; check current Git state before resuming.', '']
    rows.extend(f"- [{key}]({item['path']}) — {item['status']} / {item['state']}" for key, item in sorted(index['tasks'].items()))
    a.require(a.relative(root, '.agent-work/INDEX.md', file=True).read_text(encoding='utf-8') == '\n'.join(rows) + '\n',
              'P1 Markdown index is not canonical')
    prepared = _read(a.relative(run, 'gate-checkpoint.json', file=True))
    seal = _read(a.relative(run, 'gate-submission.json', file=True))
    a.require(prepared['task_id'] == task_id and prepared['seal_digest'] == _hash(seal) and
              set(prepared['files']) == _managed(task_id), 'P1 checkpoint is not bound to submission')
    for name, expected in prepared['files'].items():
        a.require(a.digest(a.relative(root, name, file=True).read_bytes()) == expected,
                  'P1 generated bytes differ from lifecycle checkpoint')


def seal_checkpoint(task_id, root=a.ROOT, files=None):
    """Capture the lifecycle generator's bytes, not arbitrary later file contents.

    This is a local cooperating callback, not an authenticated attestation.
    """
    root = Path(root).resolve()
    enrollment = check_enrollment(task_id, root)
    if enrollment is None:
        return None
    run = _run(task_id, root)
    task = _read(a.relative(run, 'task.json', file=True))
    if task['state'] != 'submitted':
        return None
    if _read(a.relative(run, 'result.json', file=True))['status'] != 'completed':
        return None
    a.require(type(files) is dict and set(files) == _managed(task_id) and
              all(type(value) is bytes and len(value) <= 2 * 1024 * 1024 for value in files.values()),
              'P1 invalid lifecycle checkpoint payload')
    seal = _read(a.relative(run, 'gate-submission.json', file=True))
    value = {'task_id': task_id, 'seal_digest': _hash(seal),
             'files': {name: a.digest(data) for name, data in sorted(files.items())}}
    a.write_json(a.relative(run, 'gate-checkpoint.json'), value)
    return {'status': 'prepared', 'assurance': 'local-cooperating-cli'}


def check_publication(task_id, root=a.ROOT, commit=None, publication=None):
    root = Path(root).resolve()
    enrollment = check_enrollment(task_id, root)
    if enrollment is None:
        return None
    a.require(enrollment['config']['policy']['publication'] == 'allow', 'P1 publication policy denies action')
    run = _run(task_id, root)
    task = _read(a.relative(run, 'task.json', file=True))
    a.require(task['state'] == 'submitted', 'P1 publication requires submission')
    check_submission(task_id, root)
    seal = _read(a.relative(run, 'gate-submission.json', file=True))
    if publication is None:
        _, _, publication = _context(task_id, root)
    a.require(commit and publication.get('commit') == commit and publication['phase'] in ('committed', 'pushed'),
              'P1 publication requires recorded real commit')
    a.require(_git(root, 'rev-parse', 'HEAD') == commit and
              _git(root, 'rev-list', '--parents', '-n', '1', commit).split() == [commit, enrollment['base_head']],
              'P1 commit or parent mismatch')
    actual = sorted(filter(None, _git(root, 'diff-tree', '--no-commit-id', '--name-only', '-r', '-z', '--no-renames', commit, raw=True).split('\0')))
    a.require(actual == sorted(publication['staged_paths']) and set(actual) <= set(seal['owned_paths']) | _managed(task_id) | {'.agent-work/automation.json'},
              'P1 commit path set differs from submitted ownership')
    _check_generated(task_id, root, enrollment, actual)
    for item in seal['candidate']['candidate']['entries'] + seal['record_entries']:
        a.require(_reviewed_blob_matches(root, item, commit), 'P1 commit content differs from submitted candidate')
    for item in seal['candidate']['candidate']['dependencies']:
        a.require(_dependency_matches(root, item, commit),
                  'P1 committed dependency differs from tested source')
    # Generated records are checked against current canonical lifecycle outputs,
    # separately from reviewed product files and sealed evidence archives.
    for name in actual:
        if name in _managed(task_id) or name == '.agent-work/automation.json':
            a.require(_reviewed_blob_matches(root, _reviewed_blob(root, name), commit), 'P1 generated record differs from commit')
    receipt = {'schema_version': VERSION, 'task_id': task_id, 'commit': commit,
               'seal_digest': _hash(seal), 'candidate_digest': seal['candidate']['digest'],
               'status': 'passed', 'assurance': 'local-cooperating-cli', 'checked_at': a.now()}
    _append(run, 'publication', receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('candidate', 'run-tests', 'assess', 'status', 'select-profile', 'promote-full', 'select-tests'))
    parser.add_argument('--task', required=True)
    parser.add_argument('--suite')
    parser.add_argument('--input')
    parser.add_argument('--reason')
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
        elif args.command == 'select-profile':
            value = sp.select(args.task, _read(a.relative(a.ROOT, args.input, file=True)))
        elif args.command == 'promote-full':
            value = sp.promote(args.task, args.reason)
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
