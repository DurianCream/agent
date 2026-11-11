import copy
import json
import unittest
from unittest import mock

from test_control_gate import GateFixture, a, auto, g, r
import task_evidence as e


class EvidenceTests(GateFixture, unittest.TestCase):
    def before_initial_commit(self):
        a.write_json(self.root / e.CONFIG, e.POLICY)

    def prepare(self):
        self.publication = a.read_json(self.run / 'publication.json')
        raw = self.run / 'evidence/check.txt'
        self.value = {'checks': [{'id': 'check', 'result': 'passed', 'command': 'fixture',
            'metrics': {'tests': 1}, 'evidence': [{'path': 'runs/gate-task/evidence/check.txt',
                'sha256': a.digest(raw.read_bytes())}]}]}
        self.summary_path = '.agent-work/tasks/gate-task/evidence/summary.json'
        a.write_json(self.root / self.summary_path, self.value)
        a.write_json(self.run / 'evidence/summary.json', self.value)
        auto.track('gate-task', [self.summary_path], self.root)
        self.publication = a.read_json(self.run / 'publication.json')

    def test_reviewed_summary_and_committed_hash_validation(self):
        self.prepare()
        self.execute()
        self.review(extra=('runs/gate-task/evidence/summary.json',))
        self.assertEqual(g.check_submission('gate-task', self.root)['status'], 'passed')
        r.git(self.root, 'add', '--', '.agent-work/tasks/gate-task')
        r.git(self.root, 'commit', '-q', '-m', 'records')
        e.validate(self.root, 'gate-task', self.publication, commit='HEAD')
        (self.run / 'evidence/check.txt').write_text('changed')
        with self.assertRaisesRegex(a.ContractError, 'SHA-256 mismatch'):
            e.validate(self.root, 'gate-task', self.publication, commit='HEAD')

    def test_record_size_boundaries_and_exact_file_set(self):
        self.prepare()
        spec = self.root / '.agent-work/tasks/gate-task/spec.md'
        spec.write_bytes(b'x' * 65536)
        e.validate(self.root, 'gate-task', self.publication)
        spec.write_bytes(b'x' * 65537)
        with self.assertRaisesRegex(a.ContractError, 'spec.md.*65537'):
            e.validate(self.root, 'gate-task', self.publication)
        spec.write_bytes(b'x')
        with mock.patch.dict(e.POLICY, task_bytes=1), mock.patch.object(e, 'enabled', return_value=True):
            with self.assertRaisesRegex(a.ContractError, 'Task records exceed'):
                e.validate(self.root, 'gate-task', self.publication)
        extra = self.root / '.agent-work/tasks/gate-task/evidence/raw.log'
        extra.write_text('raw')
        with self.assertRaisesRegex(a.ContractError, 'raw.log'):
            e.validate(self.root, 'gate-task', self.publication)

    def test_summary_shape_paths_hash_and_baseline_compatibility(self):
        self.prepare()
        cases = []
        for field, value in [('payload', 'raw'), ('metrics', {'log': 'raw'}), ('command', 'x' * 1025)]:
            bad = copy.deepcopy(self.value); bad['checks'][0][field] = value; cases.append(bad)
        for path in ('runs/other/evidence/x', 'runs/gate-task/evidence/../result.json'):
            bad = copy.deepcopy(self.value); bad['checks'][0]['evidence'][0]['path'] = path; cases.append(bad)
        bad = copy.deepcopy(self.value); bad['checks'][0]['evidence'][0]['sha256'] = '0' * 64; cases.append(bad)
        for bad in cases:
            with self.subTest(value=bad), self.assertRaises(a.ContractError):
                e.summary(self.root, 'gate-task', json.dumps(bad).encode())
        # Deleting/changing live policy cannot disable a task's committed baseline.
        (self.root / e.CONFIG).unlink()
        self.assertTrue(e.enabled(self.root, self.publication))
        r.git(self.root, 'add', '--', e.CONFIG)
        r.git(self.root, 'commit', '-q', '-m', 'legacy baseline without policy')
        legacy = {**self.publication, 'base_head': r.git(self.root, 'rev-parse', 'HEAD')}
        a.write_json(self.root / e.CONFIG, e.POLICY)
        self.assertFalse(e.enabled(self.root, legacy))
        e.validate(self.root, 'absent-legacy-task', legacy)
