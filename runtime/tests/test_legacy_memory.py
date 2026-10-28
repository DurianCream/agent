import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agentctl as a
import repoctl as r
import repo_automation as auto
import legacy_memory as legacy
import test_repoctl as memory_fixtures
import test_repo_automation as automation_fixtures

SCOPE = {'project': 'project-a', 'service': 'vpn', 'environment': 'production', 'issue': 'incident-one'}


def sidecar(path, task_id, status='confirmed'):
    folder = legacy.record_directory(path, task_id)
    record = a.read_json(folder / 'record.json')
    value = {'schema_version': '1.0.0', 'repository_id': record['repository_id'],
             'repository_uuid': record['repository_uuid'], 'task_id': task_id,
             'source': {'record_sha256': a.digest((folder / 'record.json').read_bytes()),
                        'spec_sha256': a.digest((folder / 'spec.md').read_bytes())},
             'status': status, 'rationale': 'Reviewed original task inputs.',
             'evidence': ['Original objective and acceptance criteria inspected.']}
    if status == 'confirmed': value['scope'] = SCOPE
    else:
        value['proposed_scope'] = {'service': 'vpn'}
        value['unknown_fields'] = ['project', 'environment', 'issue']
    a.write_json(path / '.agent-work/classifications' / (task_id + '.json'), value)
    return value


class ClassificationTests(unittest.TestCase):
    def setUp(self): memory_fixtures.RepositoryMemoryTests.setUp(self)

    def test_confirmed_overlay_preserves_originals_and_routes(self):
        r.bind('sample', 'sample-task', self.root)
        folder = self.path / '.agent-work/tasks/sample-task'
        before = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
        sidecar(self.path, 'sample-task')
        data = auto.startup('sample', root=self.root, scope=SCOPE)
        self.assertEqual(len(data['context']), 1)
        self.assertIsNone(data['context'][0]['scope'])
        self.assertEqual(data['context'][0]['effective_scope'], SCOPE)
        self.assertEqual(data['context'][0]['classification']['status'], 'confirmed')
        self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()})

    def test_uncertain_metadata_only_and_no_scope_assumption(self):
        r.bind('sample', 'sample-task', self.root)
        sidecar(self.path, 'sample-task', 'needs-review')
        self.assertEqual(auto.startup('sample', root=self.root, scope=SCOPE)['context'], [])
        data = auto.startup('sample', root=self.root)
        self.assertEqual(data['context'], [])
        self.assertEqual(data['index'][0]['classification_status'], 'needs-review')
        self.assertIn('environment', data['index'][0]['unknown_fields'])

    def test_native_scope_override_rejected(self):
        r.bind('sample', 'sample-task', self.root, scope=SCOPE)
        sidecar(self.path, 'sample-task')
        with self.assertRaises(a.ContractError): auto.startup('sample', root=self.root, scope=SCOPE)
        with self.assertRaises(a.ContractError): r.resume('sample', 'sample-task', self.root)

    def test_import_preserves_published_report_bytes(self):
        report = self.root / 'outputs/sample-task/result.md'
        content = '# 원본 보고서\r\n본문\r\n'.encode('utf-8')
        report.write_bytes(content)
        (self.root / 'runs/sample-task/result.md').write_text('fallback must not win', encoding='utf-8')
        legacy.import_legacy('sample', 'sample-task', self.root)
        copied = self.path / '.agent-work/legacy/sample-task/source/result.md'
        self.assertEqual(copied.read_bytes(), content)
        self.assertEqual(report.read_bytes(), content)

    def test_evolved_artifacts_do_not_rewrite_or_block_historical_import(self):
        a.transition('sample-task', 'running', self.root)
        artifact = self.root / 'outputs/sample-task/artifact.txt'; artifact.write_text('old content')
        evidence = self.root / 'runs/sample-task/evidence/check.txt'; evidence.write_text('old verification')
        file = self.root / 'runs/sample-task/result.json'
        result = a.read_json(file)
        result.update(status='completed', limitations=[], next_actions=[])
        result['artifacts'] = [{'path': 'outputs/sample-task/artifact.txt', 'description': 'Historical artifact', 'sha256': None}]
        result['verification'] = [{'id': 'old-check', 'name': 'Old check', 'method': 'Historical test', 'outcome': 'passed',
                                  'evidence': ['runs/sample-task/evidence/check.txt'], 'notes': ''}]
        result['acceptance_criteria'][0]['verification_ids'] = ['old-check']
        a.write_json(file, result)
        a.submit('sample-task', self.root)
        original = file.read_bytes()
        artifact.write_text('later revision'); evidence.write_text('later evidence')
        legacy.import_legacy('sample', 'sample-task', self.root)
        copied = self.path / '.agent-work/legacy/sample-task/source/result.json'
        self.assertEqual(copied.read_bytes(), original)
        imported = a.read_json(self.path / '.agent-work/legacy/sample-task/record.json')
        self.assertEqual(imported['result']['status'], 'completed')
        self.assertIn('not reverified', imported['source_validation'])

    def test_stale_overlay_and_import_source_fail_closed(self):
        legacy.import_legacy('sample', 'sample-task', self.root)
        sidecar(self.path, 'sample-task')
        folder = self.path / '.agent-work/legacy/sample-task'
        file = folder / 'record.json'; file.write_bytes(file.read_bytes() + b'\n')
        with self.assertRaises(a.ContractError): auto.startup('sample', root=self.root, scope=SCOPE)
        sidecar(self.path, 'sample-task')
        source = folder / 'source/result.json'; source.write_bytes(source.read_bytes() + b'\n')
        with self.assertRaises(a.ContractError): r.resume('sample', 'sample-task', self.root)


class LegacyPublicationTests(unittest.TestCase):
    def setUp(self): automation_fixtures.AutomationTests.setUp(self)

    def test_declared_import_publish_and_autocrlf_clone(self):
        automation_fixtures.AutomationTests.bind(self)
        a.init_task('coding', 'old-task', 'Historical work', ['Preserve history'], self.root)
        source = self.root / 'runs/old-task/result.json'
        source.write_bytes(source.read_bytes().replace(b'\n', b'\r\n'))
        original = source.read_bytes()
        imported = legacy.import_legacy('sample', 'old-task', self.root)
        sidecar(self.path, 'old-task')
        attrs = self.path / '.agent-work/.gitattributes'
        attrs.write_text('tasks/** -text\nlegacy/** -text\nclassifications/** -text\n', encoding='utf-8')
        auto.track('auto-task', ['.agent-work/.gitattributes'], self.root)
        with self.assertRaises(a.ContractError):
            auto.track('auto-task', ['.agent-work/classifications/old-task.json'], self.root)
        approved = legacy.approve_memory('auto-task', 'old-task', self.root)
        self.assertIn('.agent-work/legacy/old-task/source/result.json', approved['files'])
        (self.path / '.agent-work/legacy/old-task/source/raw.log').write_text('must not publish')
        automation_fixtures.AutomationTests.complete(self)
        auto.finish('auto-task', self.root)
        clone = self.base / 'historical-clone'
        subprocess.run(['git', '-c', 'core.autocrlf=true', 'clone', '-q', '-b', 'main',
                        str(self.remote), str(clone)], check=True)
        self.assertEqual((clone / '.agent-work/legacy/old-task/source/result.json').read_bytes(), original)
        self.assertFalse((clone / '.agent-work/legacy/old-task/source/raw.log').exists())
        self.assertEqual(source.read_bytes(), original)
        fresh_root = self.base / 'fresh-memory-root'; fresh_root.mkdir()
        loaded = auto.startup(root=fresh_root, cwd=clone, scope=SCOPE)
        self.assertEqual(loaded['context'][0]['task_id'], 'old-task')
        self.assertIsNone(loaded['context'][0]['git_changed'])
        self.assertFalse(loaded['context'][0]['original_git_known'])

    def test_changed_approved_sidecar_blocks_publication(self):
        automation_fixtures.AutomationTests.bind(self)
        a.init_task('coding', 'old-task', 'Historical work', ['Preserve'], self.root)
        legacy.import_legacy('sample', 'old-task', self.root)
        sidecar(self.path, 'old-task')
        legacy.approve_memory('auto-task', 'old-task', self.root)
        file = self.path / '.agent-work/classifications/old-task.json'
        value = a.read_json(file); value['rationale'] = 'Changed after approval'
        a.write_json(file, value)
        automation_fixtures.AutomationTests.complete(self)
        with self.assertRaises(a.ContractError): auto.finish('auto-task', self.root)
        self.assertEqual(auto.staged_paths(self.path), [])


if __name__ == '__main__': unittest.main()
