import os
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agentctl as a
import control_gate as g
import submission_profile as p


class DocumentChecks(unittest.TestCase):
    def setUp(self):
        self.task = a.identifier(os.environ['AGENT_SUBMISSION_TASK'])
        self.enrollment = g.check_enrollment(self.task)
        self.current = g.candidate(self.task)

    def test_approval_and_evidence(self):
        suites, proof = p.effective(self.task, self.current, self.enrollment, a.ROOT)
        self.assertEqual(suites, [p.SUITE])
        self.assertIsNotNone(proof)

    def test_document_integrity(self):
        p.documents(self.current, self.enrollment, a.ROOT)

    def test_control_dependencies_unchanged(self):
        p.unchanged_controls(self.current, self.enrollment, a.ROOT)
