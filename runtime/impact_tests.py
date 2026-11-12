"""Explicit, baseline-pinned impact selection; never infer dependencies from imports."""
from __future__ import annotations
import fnmatch
import json
import subprocess
from pathlib import Path
import agentctl as a

VERSION = '1.0.0'
ENROLLMENT_VERSION = '0.3.0'
CONFIG = '.agent-work/impact-tests.json'
# Protected paths always add the gate's required suites to their mapped suites.
# Agent instruction documents (AGENTS.md, shared/workflows) are mapped to the
# document suite instead: the gate suites do not exercise their text.
PROTECTED = ('.agent-work/gates.json', CONFIG, 'shared/schemas/*',
             'runtime/secret_scan.py', '.agent-work/secret-scan-allowlist.json',
             'runtime/control_gate.py', 'runtime/impact_tests.py',
             'runtime/agentctl.py', 'runtime/repoctl.py',
             'runtime/repo_automation.py', 'runtime/task_recovery.py', 'runtime/legacy_memory.py',
             'runtime/task_evidence.py', '.agent-work/evidence-policy.json')

def gate():
    import control_gate
    return control_gate

def configuration(value):
    a.require(type(value) is dict and set(value) == {'schema_version', 'rules', 'suites', 'periodic_full'}, 'Invalid impact configuration')
    a.require(value['schema_version'] == VERSION and value['periodic_full'] == 'manual-before-release', 'Invalid impact version or periodic policy')
    a.require(type(value['rules']) is list and 0 < len(value['rules']) <= 128, 'Invalid impact rules')
    ids = set()
    for suite in value['suites']:
        a.require(type(suite) is dict and set(suite) == {'id', 'argv'}, 'Invalid impact suite')
        a.identifier(suite['id'])
        a.require(suite['id'] not in ids and suite['argv'][:3] == ['@project-python', '-m', 'unittest'] and all(type(x) is str and x and '\0' not in x for x in suite['argv']), 'Invalid impact suite command')
        ids.add(suite['id'])
    for rule in value['rules']:
        a.require(type(rule) is dict and set(rule) == {'path', 'suites', 'reason'}, 'Invalid impact rule')
        a.require(type(rule['path']) is str and rule['path'] and not rule['path'].startswith('/') and '..' not in rule['path'] and '\\' not in rule['path'], 'Invalid impact path')
        a.require(rule['suites'] and set(rule['suites']) <= ids and type(rule['reason']) is str and len(rule['reason']) >= 10, 'Invalid impact rule suites/reason')
    return value

def capture(root, base):
    g = gate()
    blob = g._blob(root, CONFIG, base)
    if blob['state'] == 'deleted':
        return None
    a.require(blob.get('mode') == '100644', 'Impact policy must be nonexecutable')
    raw = g._git(root, 'show', base + ':' + CONFIG, raw=True).encode('utf-8')
    value = configuration(json.loads(raw.decode('utf-8-sig'), object_pairs_hook=a.unique_pairs))
    return {'config': value, 'baseline_blob': blob, 'baseline_sha256': a.digest(raw)}

def changed_dependencies(current, enrollment, root, owned):
    """Batch exact baseline bytes; retain Git-clean fallback for CRLF representations."""
    g = gate()
    baseline = {}
    for row in filter(None, g._git(root, 'ls-tree', '-r', '-z', enrollment['base_head'], raw=True).split('\0')):
        meta, name = row.split('\t', 1)
        mode, kind, oid = meta.split()
        baseline[name] = (mode, kind, oid)
    dependencies = [d for d in current['candidate']['dependencies'] if d['path'] not in owned]
    oids = sorted({baseline[d['path']][2] for d in dependencies if d['path'] in baseline and baseline[d['path']][1] == 'blob'})
    hashes = {}
    if oids:
        proc = subprocess.run(['git', 'cat-file', '--batch'], cwd=root,
            input=('\n'.join(oids) + '\n').encode('ascii'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        a.require(proc.returncode == 0 and len(proc.stdout) <= g.MAX_BYTES, 'Impact baseline exceeds bounds or cannot be read')
        offset = 0
        for oid in oids:
            end = proc.stdout.find(b'\n', offset)
            a.require(end >= offset, 'Invalid impact baseline object header')
            header = proc.stdout[offset:end].decode('ascii').split()
            a.require(len(header) == 3 and header[:2] == [oid, 'blob'], 'Invalid impact baseline object')
            size = int(header[2]); offset = end + 1
            a.require(0 <= size <= g.MAX_BYTES and proc.stdout[offset + size:offset + size + 1] == b'\n', 'Invalid impact baseline size')
            hashes[oid] = a.digest(proc.stdout[offset:offset + size]); offset += size + 1
        a.require(offset == len(proc.stdout), 'Trailing impact baseline bytes')
    for item in dependencies:
        original = baseline.get(item['path'])
        if original and original[1] == 'blob' and item.get('mode') == original[0] and item['sha256'] == hashes[original[2]]:
            continue
        if not g._dependency_matches(root, item, enrollment['base_head']):
            yield item['path']


META = set('*?[')

def _discover(suite):
    """Return (argv without the pattern, pattern) for a unittest discover suite."""
    argv = suite['argv']
    if 'discover' not in argv or '-p' not in argv or argv.index('-p') + 1 >= len(argv):
        return None
    i = argv.index('-p') + 1
    return tuple(argv[:i] + argv[i + 1:]), argv[i]

def _covers(broad, narrow):
    """Sound, deliberately narrow test that every file `narrow` collects, `broad` also collects."""
    if broad == narrow:
        return True
    if not META & set(narrow):
        return fnmatch.fnmatchcase(narrow, broad)
    # Only a single-star literal pattern A*B is compared against another
    # pattern, and never against one with a character class.
    if '[' in narrow or broad.count('*') != 1 or META & (set(broad) - {'*'}):
        return False
    head, tail = broad.split('*')
    first = min(narrow.index(c) for c in META if c in narrow)
    last = max(narrow.rindex(c) for c in META if c in narrow)
    return narrow[:first].startswith(head) and narrow[last + 1:].endswith(tail)

def _merge(suites):
    """Keep order; drop a suite another listed suite with the same command already collects."""
    for suite in suites:
        a.require(all(other['argv'] == suite['argv'] for other in suites if other['id'] == suite['id']),
                  'Suite id names different commands: ' + suite['id'])
    kept = []
    for index, suite in enumerate(suites):
        if any(s['id'] == suite['id'] for s in kept):
            continue
        mine = _discover(suite)
        def redundant(other_index, other):
            theirs = _discover(other)
            if other_index == index or not mine or not theirs or theirs[0] != mine[0]:
                return False
            if not _covers(theirs[1], mine[1]):
                return False
            # Equal coverage keeps the earlier suite.
            return not _covers(mine[1], theirs[1]) or other_index < index
        if any(redundant(j, other) for j, other in enumerate(suites)):
            continue
        kept.append(suite)
    return kept

def select(current, enrollment, root):
    g = gate()
    required = enrollment['config']['required_suites']
    captured = enrollment.get('impact_tests')
    if captured is None:
        return {'mode': 'full', 'suites': required, 'reasons': [{'path': '*', 'reason': 'legacy enrollment'}]}
    config = captured['config']
    # Fallback runs required gate suites plus every configured suite; the
    # configured catch-all discover suite also collects newly added test files.
    full = _merge(list(required) + list(config['suites']))
    reasons, ids, fallback, protected = [], set(), False, False
    if g._blob(root, CONFIG) != captured['baseline_blob']:
        fallback = True
        reasons.append({'path': CONFIG, 'reason': 'mapping changed'})
    entries = current['candidate']['entries']
    for item in entries:
        name = item['path']
        baseline = g._blob(root, name, enrollment['base_head'])
        matches = [r for r in config['rules'] if fnmatch.fnmatchcase(name, r['path'])]
        mapped = sorted({s for r in matches for s in r['suites']})
        new = baseline['state'] != 'file'
        guarded = False
        if item['state'] != 'file' or (not new and item.get('mode') != baseline.get('mode')):
            reason, chosen = 'deleted or mode-changed file', None
        elif new and (item.get('mode') != '100644' or name.startswith('runtime/tests/')):
            # A new test module can change what a discover pattern collects.
            reason, chosen = 'new executable or test file', None
        elif any(fnmatch.fnmatchcase(name, p) for p in PROTECTED):
            protected = guarded = True
            reason, chosen = 'protected path: required suites plus mapped suites', mapped
        elif not matches:
            reason, chosen = 'unmapped path', None
        else:
            chosen = mapped
            reason = ('new file; ' if new else '') + '; '.join(r['reason'] for r in matches)
        if chosen is None:
            fallback = True
        else:
            ids.update(chosen)
        listed = [s['id'] for s in required] if guarded else []
        reasons.append({'path': name, 'reason': reason,
                        'suites': [s['id'] for s in full] if chosen is None else listed + chosen})
    # Any changed dependency outside ownership is uncertain: do not skip its tests.
    owned = {e['path'] for e in entries}
    for name in changed_dependencies(current, enrollment, root, owned):
        fallback = True
        reasons.append({'path': name, 'reason': 'changed unowned dependency'})
    if fallback:
        suites = full
    else:
        suites = _merge((list(required) if protected else []) + [s for s in config['suites'] if s['id'] in ids])
    a.require(suites, 'Impact selection cannot be empty')
    return {'mode': 'full' if fallback else 'impact', 'suites': suites, 'reasons': reasons,
            'mapping_sha256': captured['baseline_sha256']}
