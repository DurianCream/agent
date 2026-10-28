"""Validate design fixtures, not execution safety or signatures.

Requires jsonschema 4.26.0. Example:
  python verify_design.py --dependency-path ../../work/ax-controls-design/vendor
Optional --evidence writes a small JSON evidence summary.
This program does not execute fixture actions, verify Ed25519, or install controls.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import sys
from datetime import datetime, timezone

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--dependency-path')
parser.add_argument('--directory', default=str(Path(__file__).resolve().parent))
parser.add_argument('--evidence')
args = parser.parse_args()
if args.dependency_path:
    sys.path.insert(0, str(Path(args.dependency_path).resolve()))
from jsonschema import Draft202012Validator, FormatChecker

directory = Path(args.directory).resolve()
checks = []


def check(name, predicate, detail=''):
    checks.append({'id': name, 'outcome': 'passed' if predicate else 'failed', 'detail': detail})


def unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate JSON key: ' + key)
        obj[key] = value
    return obj


def load(name):
    return json.loads((directory / name).read_text(encoding='utf-8'), object_pairs_hook=unique_pairs)


def fixture_digest(value):
    # Restricted fixture subset only: ASCII keys/text, booleans, safe integers.
    text = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    if not text.isascii():
        raise ValueError('fixture digest helper supports ASCII fixtures only; use full JCS for general data')
    return 'sha256:' + hashlib.sha256(text.encode()).hexdigest()


schema = load('contracts.schema.json')
examples = load('examples.json')
matrix = load('control-matrix.json')
Draft202012Validator.check_schema(schema)
check('draft-2020-12-meta-schema', True)
formats = FormatChecker()


@formats.checks('date-time', raises=(ValueError, TypeError))
def utc_datetime(value):
    if not isinstance(value, str):
        return True
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z', value):
        return False
    datetime.fromisoformat(value.replace('Z', '+00:00'))
    return True


validator = Draft202012Validator(schema, format_checker=formats)
records = examples['records']
for number, record in enumerate(records):
    errors = list(validator.iter_errors(record))
    check(f'fixture-{number + 1}-shape', not errors,
          '; '.join(error.message for error in errors)[:1500])
    preimage = {key: record[key] for key in ('record_type', 'schema_version', 'payload')}
    check(f'fixture-{number + 1}-digest', fixture_digest(preimage) == record['digest'])

by_digest = {record['digest']: record for record in records}
by_type = {}
for record in records:
    by_type.setdefault(record['record_type'], []).append(record)
expected = {'action_request', 'policy_decision', 'action_approval', 'execution_receipt',
            'evaluation_attestation', 'task_control_manifest'}
check('all-six-contract-types', set(by_type) == expected)
check('unique-record-digests', len(by_digest) == len(records))

for number, record in enumerate(records):
    payload = record['payload']
    for field, expected_type in [('request_digest', 'action_request'),
                                 ('decision_digest', 'policy_decision'),
                                 ('review_target_digest', 'policy_decision')]:
        if payload.get(field) is not None:
            referenced = by_digest.get(payload[field])
            check(f'fixture-{number + 1}-{field}', referenced is not None and referenced['record_type'] == expected_type)
    for approval_digest in payload.get('approval_digests', []):
        referenced = by_digest.get(approval_digest)
        check(f'fixture-{number + 1}-approval-reference', referenced is not None and referenced['record_type'] == 'action_approval')

request = by_type['action_request'][0]
negative_mutators = {
    'extra-envelope-key': lambda item: item.update(unexpected=True),
    'missing-version': lambda item: item.pop('schema_version'),
    'unsupported-version': lambda item: item.update(schema_version='99.0.0'),
    'unknown-record-type': lambda item: item.update(record_type='unrestricted_shell'),
    'wrong-payload-type': lambda item: item.update(payload=[]),
    'malformed-digest': lambda item: item.update(digest='not-a-digest'),
    'extra-action-property': lambda item: item['payload'].update(unrestricted_shell='fixture-only'),
    'invalid-time': lambda item: item['payload'].update(issued_at='2026-99-99T25:99:99Z'),
}
for name, mutate in negative_mutators.items():
    candidate = copy.deepcopy(request)
    mutate(candidate)
    check('negative-' + name, not validator.is_valid(candidate), 'Shape rejection only; no action executed.')

manifest = by_type['task_control_manifest'][0]
check('schema-reference-current', manifest['payload']['schema_ref']['digest'] ==
      'sha256:' + hashlib.sha256((directory / 'contracts.schema.json').read_bytes()).hexdigest())
check('synthetic-warning', 'SYNTHETIC' in examples['warning'] and 'placeholder' in examples['warning'])

controls = matrix['controls']
check('unique-control-ids', len({item['id'] for item in controls}) == len(controls))
required = {'id', 'threat', 'rule', 'technical_enforcement', 'owner', 'evidence', 'tests', 'stage', 'failure_behavior'}
for item in controls:
    check('control-' + item['id'], required.issubset(item) and bool(item['tests']) and bool(item['evidence'])
          and bool(item['owner'].get('human_accountable')) and item['stage'] in matrix['phases'])

for name in ('design.ko.md', 'implementation-spec.en.md', 'risk-policy.en.md'):
    text = (directory / name).read_text(encoding='utf-8')
    for phase in ('P0', 'P1', 'P2', 'P3'):
        check(name + '-' + phase, phase in text)
    for target in re.findall(r'\]\(([^)]+)\)', text):
        if not target.startswith(('https://', 'http://', '#')):
            check(name + '-link-' + target, (directory / target.split('#')[0]).is_file())

check('seven-korean-sections', len(re.findall(r'^## [1-7]\. ', (directory / 'design.ko.md').read_text(encoding='utf-8'), re.M)) == 7)
result = {
    'kind': 'design_structure_verification',
    'checked_at': datetime.now(timezone.utc).isoformat(),
    'jsonschema_version': importlib.metadata.version('jsonschema'),
    'outcome': 'passed' if all(item['outcome'] == 'passed' for item in checks) else 'failed',
    'checks': checks,
    'counts': {'envelopes': len(records), 'controls': len(controls),
               'planned_policy_scenarios': sum(len(item['tests']) for item in controls),
               'negative_shape_fixtures': len(negative_mutators)},
    'files': {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
              for name in ['design.ko.md', 'implementation-spec.en.md', 'risk-policy.en.md',
                           'contracts.schema.json', 'examples.json', 'control-matrix.json', 'verify_design.py']},
    'not_run': ['runtime execution and security tests', 'Ed25519 signature verification',
                'full RFC8785 canonicalization conformance', 'production isolation/CI/monitor deployment',
                'regulatory compliance audit'],
    'limitations': ['Fixture signatures and outcomes are synthetic and never constitute authorization.',
                    'Digest checks cover only the restricted ASCII fixture subset; this is not a production JCS implementation.',
                    'Semantic authority and real enforcement are assessed by independent design review, not established by schema validation.'],
}
if args.evidence:
    target = Path(args.evidence)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'outcome': result['outcome'], 'counts': result['counts'], 'checks': len(checks),
                  'failed': [item for item in checks if item['outcome'] == 'failed']}))
sys.exit(0 if result['outcome'] == 'passed' else 1)
