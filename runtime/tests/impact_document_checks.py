"""Fast structural checks; independent semantic review remains mandatory."""
import os
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agentctl as a
import control_gate as g
import sync_codex

# Outside the gate there is no task to check; the gate itself counts any skip as a failure.
needs_task = unittest.skipUnless('AGENT_SUBMISSION_TASK' in os.environ,
                                 'needs a gate task; run through control_gate.py run-tests')


class ImpactDocumentChecks(unittest.TestCase):
    def test_adapter_consistency(self):
        result = sync_codex.synchronize(write=False)
        self.assertTrue(result['ok'], result)

    def test_registry(self):
        result = a.doctor()
        self.assertGreater(result['modules'], 0)

    @needs_task
    def test_result_contract(self):
        task_id = a.identifier(os.environ['AGENT_SUBMISSION_TASK'])
        run, task, _ = a.load_task(task_id)
        result = a.read_json(run / 'result.json')
        a.validate_named(result, 'result', run / 'snapshot/files')
        self.assertEqual(result['task_id'], task_id)
        self.assertEqual(result['module'], task['module'])
        self.assertEqual(result['objective'], task['objective'])
        self.assertEqual([{k: c[k] for k in ('id', 'description', 'required')} for c in result['acceptance_criteria']], task['criteria'])

    @needs_task
    def test_document_integrity(self):
        task = a.identifier(os.environ['AGENT_SUBMISSION_TASK'])
        current = g.candidate(task)
        for item in current['candidate']['entries']:
            if item['path'].endswith(('.md', '.txt', '.json', '.toml')):
                self.assertEqual(item['state'], 'file')
                raw = a.relative(a.ROOT, item['path'], file=True).read_bytes()
                self.assertLessEqual(len(raw), g.MAX_BYTES)
                self.assertNotIn('\x00', raw.decode('utf-8-sig'))
                self.assertFalse(any(line.startswith(('<<<<<<< ', '=======', '>>>>>>> ')) for line in raw.decode('utf-8-sig').splitlines()))
