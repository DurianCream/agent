"""Versioned, opt-in prose profile for cooperating local CLIs, not an authority boundary."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import agentctl as a

VERSION = '0.1.0'
ENROLLMENT_VERSION = '0.2.0'
CONFIG = '.agent-work/submission-profiles.json'
PROFILE = 'ordinary-prose-v1'
SUITE = {'id': 'light-document-integrity', 'argv': ['@project-python', '-m', 'unittest',
         'discover', '-s', 'runtime/tests', '-p', 'light_document_checks.py', '-v']}
NAME = re.compile(r'docs/prose/[a-z0-9]+(?:-[a-z0-9]+)*\.txt\Z')
MAX_DOCUMENT = 32768


def gate():
    import control_gate
    return control_gate


def configuration(value):
    a.require(type(value) is dict and set(value) == {'schema_version', 'profile', 'paths'},
              'Invalid submission profile configuration fields')
    a.require(value['schema_version'] == VERSION and value['profile'] == PROFILE,
              'Unsupported submission profile version')
    paths = value['paths']
    a.require(type(paths) is list and len(paths) <= 128 and
              all(type(p) is str and NAME.fullmatch(p) for p in paths) and
              len(paths) == len(set(paths)), 'Invalid ordinary prose allowlist')
    return value


def committed_bytes(root, oid):
    g = gate()
    size = int(g._git(root, 'cat-file', '-s', oid))
    a.require(0 < size <= MAX_DOCUMENT, 'Profile baseline size unsupported')
    result = subprocess.run(['git', 'cat-file', 'blob', oid], cwd=root,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    a.require(result.returncode == 0 and len(result.stdout) == size, 'Profile baseline unreadable')
    return result.stdout


def capture(root, base):
    """Only committed baseline policy enables a new capability; never live candidate policy."""
    g = gate()
    blob = g._blob(root, CONFIG, base)
    if blob['state'] == 'deleted':
        return None
    a.require(blob.get('mode') == '100644', 'Profile configuration must be nonexecutable')
    raw = committed_bytes(root, blob['oid'])
    value = configuration(json.loads(raw.decode('utf-8-sig'), object_pairs_hook=a.unique_pairs))
    return {'schema_version': VERSION, 'config': value, 'baseline_blob': blob,
            'baseline_sha256': a.digest(raw)}


def validate_capture(enrollment, root):
    a.require(enrollment.get('submission_profile') == capture(root, enrollment['base_head']),
              'Captured submission profile differs from baseline')
    a.require(enrollment.get('submission_profile') is not None, 'Missing captured submission profile')


def protected(name):
    # Unknown source/configuration is protected, not inferred safe by extension.
    # Durable records are data and still use existing exact publication checks.
    if name.startswith(('.agent-work/tasks/', '.agent-work/classifications/', '.agent-work/legacy/')):
        return False
    return True


def unchanged_controls(current, enrollment, root):
    g = gate()
    documents(current, enrollment, root)
    approved = {item['path'] for item in current['candidate']['entries']}
    # Compare baseline/current union even for assume-unchanged/skip-worktree files.
    # Batch-read objects; differing raw representations use the established
    # Git-clean/raw fallback rather than treating Git diff as a content oracle.
    baseline, total = {}, 0
    for row in filter(None, g._git(root, 'ls-tree', '-r', '-l', '-z', enrollment['base_head'], raw=True).split('\0')):
        meta, name = row.split('\t', 1)
        if protected(name):
            mode, kind, oid, size = meta.split()
            a.require(kind == 'blob' and mode in ('100644', '100755'), 'Unsupported control baseline')
            total += int(size)
            a.require(total <= g.MAX_BYTES and len(baseline) < 4096, 'Light control baseline exceeds bounds')
            baseline[name] = (mode, oid)
    dependencies = current['candidate']['dependencies']
    a.require({item['path'] for item in dependencies} == set(baseline),
              'Light profile requires unchanged control dependency set')
    oids = sorted({item[1] for item in baseline.values()})
    process = subprocess.run(['git', 'cat-file', '--batch'], cwd=root,
        input=('\n'.join(oids) + '\n').encode('ascii'), stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=30)
    a.require(process.returncode == 0, 'Control baseline unreadable')
    raw, offset, hashes = process.stdout, 0, {}
    for oid in oids:
        end = raw.find(b'\n', offset)
        a.require(end >= offset, 'Invalid baseline object header')
        header = raw[offset:end].decode('ascii').split()
        a.require(len(header) == 3 and header[:2] == [oid, 'blob'], 'Invalid baseline object')
        size = int(header[2]); offset = end + 1
        a.require(0 <= size <= g.MAX_BYTES and len(raw) > offset + size and raw[offset + size:offset + size + 1] == b'\n',
                  'Invalid baseline object size')
        hashes[oid] = a.digest(raw[offset:offset + size]); offset += size + 1
    a.require(offset == len(raw), 'Trailing baseline object data')
    for item in dependencies:
        if item['path'] in approved:
            continue
        mode, oid = baseline[item['path']]
        a.require(item['sha256'] is not None and item['mode'] == mode and
                  (item['sha256'] == hashes[oid] or g._dependency_matches(root, item, enrollment['base_head'])),
                  'Light profile requires unchanged control dependencies: ' + item['path'])
    captured = enrollment['submission_profile']
    a.require(g._blob(root, CONFIG) == captured['baseline_blob'] and
              a.read_json(a.relative(root, CONFIG, file=True)) == captured['config'],
              'Light profile configuration changed; promote to full')


def prose(raw):
    a.require(0 < len(raw) <= MAX_DOCUMENT, 'Ordinary prose size unsupported')
    try:
        value = raw.decode('utf-8')
    except UnicodeError as error:
        raise a.ContractError('Ordinary prose must be UTF-8') from error
    a.require(all(c in '\r\n\t' or c.isprintable() for c in value), 'Non-text prose content')
    a.require(not any(c in value for c in '`<>{}=$\\') and
              not re.search(r'(?im)^\s*(?:#!|---|\[|\w+\s*[:=])', value),
              'Structured or executable-looking content requires full profile')
    # This deliberately conservative screening is necessary, not semantic proof.
    a.require(not re.search(r'(?i)\b(?:policy|permission|credential|instruction|execute|command|password|sudo|chmod|powershell|python|bash|gate|agent)\b|권한|정책|명령|자격|실행|비밀번호|지침', value),
              'Control-related prose requires full profile')


def documents(current, enrollment, root):
    g = gate()
    paths = enrollment['submission_profile']['config']['paths']
    entries = current['candidate']['entries']
    a.require(entries, 'Light profile requires owned documents')
    for item in entries:
        name = item['path']
        a.require(name in paths and NAME.fullmatch(name), 'Product path is not opted-in ordinary prose: ' + name)
        baseline = g._blob(root, name, enrollment['base_head'])
        a.require(item['state'] == baseline['state'] == 'file' and
                  item.get('mode') == baseline.get('mode') == '100644',
                  'Light profile supports existing nonexecutable files only')
        prose(committed_bytes(root, baseline['oid']))
        prose(a.relative(root, name, file=True).read_bytes())


def _state(task_id, root):
    g = gate()
    run = g._run(task_id, root)
    task = g._read(a.relative(run, 'task.json', file=True))
    file = a.relative(run, 'submission-profile-state.json')
    marker = task.get('submission_profile_state')
    existing = list(g._records(run).glob('profile-*.json'))
    if marker is None and not file.exists() and not existing:
        return None
    a.require(marker is not None and file.is_file(), 'Submission profile state missing')
    state = g._read(file)
    a.require(set(state) == {'schema_version', 'task_id', 'record', 'sha256'} and
              state['schema_version'] == VERSION and state['task_id'] == task_id and
              marker == g._hash(state), 'Submission profile state mismatch')
    name = state['record']
    a.require(type(name) is str and re.fullmatch(r'profile-[a-f0-9]{32}\.json', name), 'Invalid profile record path')
    recordfile = a.relative(run, 'gates/' + name, file=True)
    a.require(a.digest(recordfile.read_bytes()) == state['sha256'], 'Submission profile record changed')
    record = g._read(recordfile)
    a.require(record.get('schema_version') == VERSION and record.get('task_id') == task_id and
              record.get('kind') == 'profile' and record.get('profile') in ('full', PROFILE),
              'Invalid submission profile record')
    return state, record


def _save(task_id, root, record):
    g = gate()
    run = g._run(task_id, root)
    name = g._append(run, 'profile', record)
    state = {'schema_version': VERSION, 'task_id': task_id, 'record': name,
             'sha256': a.digest((run / 'gates' / name).read_bytes())}
    a.write_json(run / 'submission-profile-state.json', state)
    task = g._read(run / 'task.json')
    task['submission_profile_state'] = g._hash(state)
    a.write_json(run / 'task.json', task)
    return {'record': name, **record}


def _independent(reviewer, enrollment):
    g = gate()
    g._identity(reviewer)
    a.require(all(reviewer[k] != enrollment['config']['author'][k] for k in ('subject', 'session')),
              'Profile reviewer is not declared independent')


def select(task_id, value, root=a.ROOT):
    g = gate()
    root = Path(root).resolve()
    enrollment = g.check_enrollment(task_id, root)
    a.require(enrollment and 'submission_profile' in enrollment and 'impact_tests' not in enrollment, 'Task has no light capability; original full suites apply')
    run = g._run(task_id, root)
    with a.lock(run / '.submission-profile.lock'):
        a.require(g._read(run / 'task.json')['state'] == 'running', 'Profile selection requires running task')
        state = _state(task_id, root)
        a.require(state is None or state[1]['profile'] != 'full', 'Full promotion is irreversible')
        current = g.candidate(task_id, root)
        a.require(type(value) is dict and set(value) == {'candidate_digest', 'reviewer', 'reason', 'impact', 'evidence'},
                  'Invalid profile selection fields')
        _independent(value['reviewer'], enrollment)
        a.require(value['candidate_digest'] == current['digest'], 'Profile candidate is stale')
        a.require(type(value['reason']) is str and 10 <= len(value['reason']) <= 4096, 'Profile reason required')
        impact = value['impact']
        a.require(type(impact) is dict and set(impact) == {e['path'] for e in current['candidate']['entries']},
                  'Semantic review must cover exact owned file set')
        for item in impact.values():
            a.require(type(item) is dict and set(item) == {'ordinary_prose', 'no_behavior_change', 'uncertainty', 'rationale'} and
                      item['ordinary_prose'] is True and item['no_behavior_change'] is True and item['uncertainty'] == 'none' and
                      type(item['rationale']) is str and 10 <= len(item['rationale']) <= 4096,
                      'Independent semantic low-impact approval required')
        documents(current, enrollment, root)
        unchanged_controls(current, enrollment, root)
        evidence = value['evidence']
        a.require(type(evidence) is list and 0 < len(evidence) <= 64, 'Profile review evidence required')
        items = []
        for name in evidence:
            a.require(type(name) is str and name.startswith(('runs/' + task_id + '/evidence/', 'outputs/' + task_id + '/')),
                      'Profile evidence must belong to task')
            file = a.relative(root, name, file=True)
            a.require(0 < file.stat().st_size <= g.MAX_BYTES, 'Invalid profile evidence size')
            items.append({'path': name, 'sha256': a.digest(file.read_bytes())})
        return _save(task_id, root, {**value, 'schema_version': VERSION, 'kind': 'profile', 'task_id': task_id,
            'profile': PROFILE, 'risk_tier': 'light', 'enrollment_digest': g._hash(enrollment),
            'evidence': items, 'created_at': g._now(), 'identity_authenticated': False})


def promote(task_id, reason, root=a.ROOT):
    g = gate()
    root = Path(root).resolve()
    enrollment = g.check_enrollment(task_id, root)
    a.require(enrollment and ('submission_profile' in enrollment or 'impact_tests' in enrollment), 'Task has no profile capability')
    run = g._run(task_id, root)
    with a.lock(run / '.submission-profile.lock'):
        a.require(g._read(run / 'task.json')['state'] == 'running', 'Promotion requires running task')
        state = _state(task_id, root)
        a.require(state is None or state[1]['profile'] != 'full', 'Task already promoted to full')
        a.require(type(reason) is str and 10 <= len(reason) <= 4096, 'Promotion reason required')
        return _save(task_id, root, {'schema_version': VERSION, 'kind': 'profile', 'task_id': task_id,
            'profile': 'full', 'reason': reason, 'candidate_digest': g.candidate(task_id, root)['digest'],
            'enrollment_digest': g._hash(enrollment), 'evidence': [], 'created_at': g._now()})


def effective(task_id, current, enrollment, root):
    g = gate()
    if 'impact_tests' in enrollment:
        state = _state(task_id, root)
        a.require(state is None or state[1]['profile'] == 'full', 'Impact capability cannot mix prose selection')
        if state:
            a.require(state[1]['enrollment_digest'] == g._hash(enrollment), 'Impact promotion enrollment replay rejected')
        selection = g.impact_selection(task_id, current, enrollment, root)
        proof = ({'path': 'runs/' + task_id + '/gates/' + state[0]['record'], 'sha256': state[0]['sha256']} if state else None)
        return selection['suites'], proof
    if 'submission_profile' not in enrollment:
        a.require(_state(task_id, root) is None, 'Legacy enrollment cannot select a profile')
        return enrollment['config']['required_suites'], None
    state = _state(task_id, root)
    if state is None:
        return enrollment['config']['required_suites'], None
    pointer, record = state
    a.require(record['enrollment_digest'] == g._hash(enrollment), 'Profile enrollment replay rejected')
    if record['profile'] == PROFILE:
        a.require(record['candidate_digest'] == current['digest'], 'Light selection stale; re-review or promote to full')
        _independent(record['reviewer'], enrollment)
        for item in record['evidence']:
            g._evidence_valid(root, item)
        documents(current, enrollment, root)
        unchanged_controls(current, enrollment, root)
        suites = [SUITE]
    else:
        suites = enrollment['config']['required_suites']
    return suites, {'path': 'runs/' + task_id + '/gates/' + pointer['record'], 'sha256': pointer['sha256']}
