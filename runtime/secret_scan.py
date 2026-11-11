"""Small, fail-closed publication scan of Git blobs; never emit matched text.

This is a minimum pattern check, not comprehensive secret discovery. No scanner
configuration, inline suppression or environment variable can exempt a finding.
"""
from __future__ import annotations

import codecs
import json
import re
import subprocess

import agentctl as a

ALLOWLIST = '.agent-work/secret-scan-allowlist.json'
MAX_BYTES = 16 * 1024 * 1024
PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r'-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----',
    r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    r'\bAIza[0-9A-Za-z_-]{35}\b',
    r'\b(?:AccountKey|SharedAccessKey|password|passwd|token|api[_-]?key|client[_-]?secret)\s*["\']?\s*[:=]\s*(?:"[^"\r\n]+"|\'[^\'\r\n]+\'|[^\s"\'<>;,}]+)',
    r'\bFAKE-CANARY(?:[-_][A-Za-z0-9]+)+\b',
))


def _fail(name=None, line=0):
    # JSON quoting keeps unusual filenames from becoming extra log lines.
    location = '' if name is None else ': ' + json.dumps(name, ensure_ascii=True) + ':' + str(line)
    raise a.ContractError('Secret scan blocked' + location)


def _git(path, *args, input_bytes=None):
    try:
        result = subprocess.run(['git', '-C', str(path), *args], capture_output=True, input=input_bytes,
                                timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        _fail()
    if result.returncode:
        _fail()
    return result.stdout


def _blobs(path, tree, names):
    """Batch only the selected blobs, retaining a per-blob allocation bound."""
    names = sorted(set(names))
    if not names:
        return
    raw = _git(path, '--literal-pathspecs', 'ls-tree', '-z', tree, '--', *names)
    entries = {}
    try:
        if raw and not raw.endswith(b'\0'):
            _fail()
        for row in filter(None, raw.split(b'\0')):
            meta, actual = row.split(b'\t', 1)
            name = actual.decode('utf-8')
            mode, kind, oid = meta.split()
            if (name not in names or name in entries or kind != b'blob' or
                    mode not in (b'100644', b'100755', b'120000') or
                    not re.fullmatch(rb'[0-9a-f]{40,64}', oid)):
                _fail(name if name in names else None)
            entries[name] = oid
        if not entries:
            return
        requests = b''.join(oid + b'\n' for oid in entries.values())
        metadata = _git(path, 'cat-file', '--batch-check', input_bytes=requests).splitlines()
        if len(metadata) != len(entries):
            _fail()
        batch = []
        total = 0
        for (name, oid), row in zip(entries.items(), metadata):
            reported, kind, size_bytes = row.split()
            size = int(size_bytes)
            if reported != oid or kind != b'blob' or not 0 <= size <= MAX_BYTES:
                _fail(name)
            # One batch has at most one blob limit of content. Large selections
            # are partitioned instead of reading the whole repository into RAM.
            if batch and total + size > MAX_BYTES:
                yield from _contents(path, batch)
                batch, total = [], 0
            batch.append((name, oid, size))
            total += size
        if batch:
            yield from _contents(path, batch)
    except a.ContractError:
        raise
    except (ValueError, UnicodeError):
        _fail()


def _contents(path, batch):
    raw = _git(path, 'cat-file', '--batch', input_bytes=b''.join(oid + b'\n' for _, oid, _ in batch))
    offset = 0
    for name, oid, size in batch:
        newline = raw.find(b'\n', offset)
        if newline < 0 or raw[offset:newline] != oid + b' blob ' + str(size).encode('ascii'):
            _fail(name)
        start = newline + 1
        end = start + size
        if raw[end:end + 1] != b'\n':
            _fail(name)
        yield name, raw[start:end]
        offset = end + 1
    if offset != len(raw):
        _fail()


def _allowlist(raw):
    if raw is None:
        return set()  # Existing repositories start with no exemptions.
    try:
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError()
                result[key] = value
            return result
        data = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
        if type(data) is not dict or set(data) != {'schema_version', 'paths'} or data['schema_version'] != '1.0.0' or type(data['paths']) is not list:
            _fail(ALLOWLIST)
        paths = data['paths']
        for name in paths:
            if (type(name) is not str or not name or name == ALLOWLIST or
                    any(c in name for c in '\\:*?[]\r\n\0') or
                    any(part in ('', '.', '..') for part in name.split('/')) or
                    name.split('/')[0].lower() == '.git'):
                _fail(ALLOWLIST)
        if len(paths) != len(set(paths)):
            _fail(ALLOWLIST)
        return set(paths)
    except (ValueError, UnicodeError):
        _fail(ALLOWLIST)


def _text(raw, name):
    # BOM-aware Unicode; byte-preserving fallback still finds ASCII secrets in
    # non-UTF-8 text/binaries. Ambiguous NUL-containing encodings fail closed.
    try:
        if raw.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
            return raw.decode('utf-32')
        if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            return raw.decode('utf-16')
        if b'\0' in raw:
            _fail(name)
        return raw.decode('utf-8-sig', errors='surrogateescape')
    except UnicodeError:
        _fail(name)


def scan_tree(path, tree, names):
    """Scan full new blob contents of only exact changed publication paths."""
    if not re.fullmatch(r'[0-9a-f]{40,64}', tree):
        _fail()
    # Policy must be read before content decisions, always from this snapshot.
    names = sorted(set(names))
    findings = []
    def inspect(name, raw):
        if name in allowed:
            return
        for number, line in enumerate(_text(raw, name).splitlines(), 1):
            if any(pattern.search(line) for pattern in PATTERNS):
                findings.append((name, number))
    policy_blobs = list(_blobs(path, tree, [ALLOWLIST]))
    allowed = _allowlist(policy_blobs[0][1] if policy_blobs else None)
    for name, raw in _blobs(path, tree, [name for name in names if name not in allowed]):
        inspect(name, raw)
    if findings:
        raise a.ContractError('Secret scan blocked: ' + ', '.join(
            json.dumps(name, ensure_ascii=True) + ':' + str(line) for name, line in findings))


def scan_index(path, names):
    tree = _git(path, 'write-tree').decode('ascii').strip()
    scan_tree(path, tree, names)


def scan_commit(path, commit, parent, expected):
    if not all(re.fullmatch(r'[0-9a-f]{40,64}', value) for value in (commit, parent)):
        _fail()
    try:
        actual_parent = _git(path, 'rev-parse', commit + '^').decode('ascii').strip()
        names = _git(path, 'diff-tree', '--no-commit-id', '--name-only', '-r', '-z',
                     '--no-renames', parent, commit).decode('utf-8').split('\0')
        names = sorted(set(names) - {''})
    except UnicodeError:
        _fail()
    if actual_parent != parent or names != sorted(set(expected)):
        _fail()
    scan_tree(path, commit, names)
