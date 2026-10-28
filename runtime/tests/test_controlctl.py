"""Subprocess and in-process checks of the non-executing P0 CLI."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'runtime'))
import control_contracts as contracts
import controlctl


class ControlCLITests(unittest.TestCase):
    def setUp(self):
        self.scratch = (ROOT / 'work').resolve()
        self.scratch.mkdir(exist_ok=True)
        self.directory = Path(tempfile.mkdtemp(prefix='control-cli-', dir=self.scratch)).resolve()
        self.addCleanup(self.cleanup)
        fixture = ROOT / 'runtime/tests/fixtures/control-observe'
        self.request = json.loads((fixture / 'request.json').read_text())
        self.context = json.loads((fixture / 'context.json').read_text())
        now = datetime.now(timezone.utc).replace(microsecond=0)
        self.request['payload']['issued_at'] = (now - timedelta(seconds=1)).isoformat().replace('+00:00', 'Z')
        self.request['payload']['expires_at'] = (now + timedelta(seconds=59)).isoformat().replace('+00:00', 'Z')
        self.request['digest'] = contracts.envelope_digest(self.request)
        self.input_path = self.directory / 'request.json'
        self.context_path = self.directory / 'context.json'
        self.save()

    def cleanup(self):
        target = self.directory.resolve()
        if not target.is_relative_to(self.scratch) or not target.name.startswith('control-cli-'):
            raise RuntimeError('Unsafe test cleanup path')
        shutil.rmtree(target)

    def save(self):
        self.input_path.write_text(json.dumps(self.request), encoding='utf-8')
        self.context_path.write_text(json.dumps(self.context), encoding='utf-8')

    def invoke(self, *arguments):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            exit_code = controlctl.main(list(arguments))
        return exit_code, json.loads(out.getvalue()), out.getvalue() + err.getvalue()

    def test_validate_does_not_echo_envelope_or_assert_authenticity(self):
        code, result, text = self.invoke('validate', '--input', str(self.input_path))
        self.assertEqual(code, 0)
        self.assertTrue(result['ok'])
        self.assertFalse(result['executable'])
        self.assertEqual(result['authenticity'], 'not_verified')
        self.assertNotIn('fixture-author', text)
        self.assertNotIn('README.md', text)

    def test_missing_lazy_dependency_has_safe_actionable_diagnostic(self):
        original_import = contracts.importlib.import_module
        marker = 'private-dependency-exception-detail'
        def missing_jcs(name, *args, **kwargs):
            if name == 'rfc8785':
                raise ImportError(marker)
            return original_import(name, *args, **kwargs)
        with patch.object(contracts.importlib, 'import_module', side_effect=missing_jcs):
            code, result, text = self.invoke('validate', '--input', str(self.input_path))
        self.assertEqual(code, 2)
        self.assertEqual(result['code'], 'dependency_unavailable')
        self.assertIn('runtime/control-requirements.txt', result['install_hint'])
        self.assertIn('No automatic installation', result['install_hint'])
        self.assertFalse(result['executable'])
        self.assertNotIn(marker, text)
        self.assertNotIn(str(self.input_path), text)

    def test_observe_returns_nonexecutable_allow(self):
        code, result, text = self.invoke('observe', '--input', str(self.input_path), '--context', str(self.context_path))
        self.assertEqual(code, 0)
        self.assertEqual(result['decision'], 'allow')
        self.assertFalse(result['executable'])
        self.assertFalse(result['authority_verified'])
        self.assertNotIn('fixture-author', text)

    def test_valid_denial_has_zero_exit_and_stable_reason(self):
        self.context['authorization'] = None
        self.save()
        code, result, _ = self.invoke('observe', '--input', str(self.input_path), '--context', str(self.context_path))
        self.assertEqual(code, 0)
        self.assertEqual(result['decision'], 'deny')
        self.assertEqual(result['reason_codes'], ['authorization_missing'])

    def test_enforce_and_unknown_arguments_rejected_without_echo(self):
        for arguments in [('enforce', '--secret-marker', 'private-argument-value'),
                          ('observe', '--input', str(self.input_path), '--context', str(self.context_path), '--enforce', 'private-argument-value')]:
            with self.subTest(arguments=arguments[0]):
                code, result, text = self.invoke(*arguments)
                self.assertEqual(code, 2)
                self.assertEqual(result['code'], 'invalid_arguments')
                self.assertNotIn('private-argument-value', text)
                self.assertNotIn(str(self.input_path), text)

    def test_malformed_request_and_missing_file_are_sanitized(self):
        marker = 'private-json-value-should-never-appear'
        self.input_path.write_text('{"x":"' + marker + '","x":1}', encoding='utf-8')
        code, _, text = self.invoke('validate', '--input', str(self.input_path))
        self.assertEqual(code, 2)
        self.assertNotIn(marker, text)
        self.assertNotIn(str(self.input_path), text)
        code, _, text = self.invoke('validate', '--input', str(self.directory / marker))
        self.assertEqual(code, 2)
        self.assertNotIn(marker, text)

    def test_invalid_context_never_echoes_supplied_secrets(self):
        marker = 'private-context-secret'
        self.context['approval'] = {'secret': marker, 'recommendation': 'proceed'}
        self.save()
        code, result, text = self.invoke('observe', '--input', str(self.input_path), '--context', str(self.context_path))
        self.assertEqual(code, 2)
        self.assertEqual(result['reason_codes'], ['invalid_context'])
        self.assertNotIn(marker, text)

    def test_invalid_context_timestamp_is_sanitized(self):
        marker = 'private-invalid-context-timestampZ'
        self.context['authorization']['expires_at'] = marker
        self.save()
        code, result, text = self.invoke('observe', '--input', str(self.input_path), '--context', str(self.context_path))
        self.assertEqual(code, 2)
        self.assertEqual(result['reason_codes'], ['invalid_context'])
        self.assertNotIn(marker, text)

    def test_missing_policy_fails_closed_without_path(self):
        code, result, text = self.invoke('observe', '--input', str(self.input_path), '--context', str(self.context_path),
                                         '--policy', str(self.directory / 'private-policy-path'))
        self.assertEqual(code, 2)
        self.assertFalse(result['executable'])
        self.assertNotIn('private-policy-path', text)

    def test_real_process_has_no_target_side_effects_or_artifact_reads(self):
        # The target path is only declared data. Even a registered local target
        # must not be dereferenced by an observation.
        target = self.directory / 'do-not-touch.txt'
        target.write_text('synthetic-private-payload', encoding='utf-8')
        target_name = target.relative_to(ROOT).as_posix()
        self.request['payload']['parameters']['paths'] = [target_name]
        self.request['digest'] = contracts.envelope_digest(self.request)
        self.context['authorization']['paths'] = [target_name]
        self.save()
        original_open = Path.open
        def guarded_open(path, *args, **kwargs):
            if path.resolve() == target:
                raise AssertionError('Observation must not open action targets')
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'open', guarded_open):
            code, observed, _ = self.invoke('observe', '--input', str(self.input_path), '--context', str(self.context_path))
            self.assertEqual(code, 0)
            self.assertEqual(observed['decision'], 'allow')
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.directory.iterdir()}
        process = subprocess.run([sys.executable, str(ROOT / 'runtime/controlctl.py'), 'observe',
                                  '--input', str(self.input_path), '--context', str(self.context_path)],
                                 cwd=ROOT, capture_output=True, text=True, encoding='utf-8', env=os.environ.copy())
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertFalse(result['executable'])
        self.assertNotIn('synthetic-private-payload', process.stdout + process.stderr)
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.directory.iterdir()}
        self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
