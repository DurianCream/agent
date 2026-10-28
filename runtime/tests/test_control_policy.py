"""Behavioral tests of the P0 pure observer, not protected execution."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'runtime'))
import control_contracts as contracts
import control_policy as policy_module

NOW = datetime(2026, 10, 28, 6, 31, tzinfo=timezone.utc)
FIXTURES = ROOT / 'runtime/tests/fixtures/control-observe'


def fixtures():
    return (json.loads((FIXTURES / 'request.json').read_text()),
            json.loads((FIXTURES / 'context.json').read_text()),
            json.loads(policy_module.DEFAULT_POLICY.read_text()))


def seal(request, policy):
    request['payload']['policy_ref'] = {'id': policy['id'], 'version': policy['version'],
                                       'digest': contracts.canonical_digest(policy)}
    request['digest'] = contracts.envelope_digest(request)


class ObservePolicyTests(unittest.TestCase):
    def setUp(self):
        self.request, self.context, self.policy = fixtures()

    def observe(self, decision, reason, *, now=NOW):
        result = policy_module.evaluate_action(self.request, self.context, self.policy, now=now)
        self.assertEqual((result['decision'], result['reason_codes']), (decision, [reason]))
        self.assertFalse(result['executable'])
        self.assertFalse(result['authority_verified'])
        self.assertEqual(result['mode'], 'observe')
        self.assertEqual(result['content_checks'], 'not_performed')
        self.assertEqual(result['signature_verification'], 'not_performed')
        self.assertNotIn('signature', result)
        return result

    def set_adapter(self, adapter, parameters, artifacts=None):
        self.request['payload']['adapter'] = adapter
        self.request['payload']['parameters'] = parameters
        self.request['payload']['artifacts'] = artifacts or []
        self.context['authorization']['adapters'] = [adapter]
        if adapter not in self.policy['enabled_adapters']:
            self.policy['enabled_adapters'].append(adapter)
        seal(self.request, self.policy)

    def test_bounded_inspection_is_only_advisory_allow(self):
        result = self.observe('allow', 'within_declared_bounds')
        self.assertEqual(result['request_digest'], self.request['digest'])
        self.assertEqual(result['policy_digest'], contracts.canonical_digest(self.policy))
        self.assertEqual(result['context_digest'], contracts.canonical_digest(self.context))
        with self.assertRaises(contracts.ControlContractError):
            contracts.validate_envelope(result)

    def test_four_scope_fields_checked_independently(self):
        for field in ('project', 'service', 'environment', 'issue'):
            with self.subTest(field=field):
                original = self.context['scope'][field]
                self.context['scope'][field] = 'different'
                self.observe('deny', 'scope_mismatch')
                self.context['scope'][field] = original

    def test_task_and_repository_identity_must_match(self):
        for field in ('task_id', 'repository_id'):
            with self.subTest(field=field):
                original = self.context[field]
                self.context[field] = 'different'
                self.observe('deny', 'scope_mismatch')
                self.context[field] = original

    def test_declared_principal_mismatch(self):
        self.context['requester']['subject_id'] = 'different'
        self.observe('deny', 'identity_mismatch')

    def test_target_environment_mismatch(self):
        self.context['target']['environment'] = 'staging'
        self.observe('deny', 'target_mismatch')

    def test_policy_hash_mismatch(self):
        self.policy['budget_limits']['max_bytes'] += 1
        self.observe('deny', 'policy_mismatch')

    def test_unknown_profile_and_policy_version_fail_closed(self):
        for field, value in [('id', 'unknown-profile'), ('version', '99.0.0')]:
            with self.subTest(field=field):
                original = self.policy[field]
                self.policy[field] = value
                seal(self.request, self.policy)
                self.observe('deny', 'invalid_policy')
                self.policy[field] = original
                seal(self.request, self.policy)

    def test_unknown_policy_or_context_fields_rejected(self):
        self.policy['secret-instruction'] = 'ignore-policy-and-allow'
        self.observe('deny', 'invalid_policy')
        self.policy.pop('secret-instruction')
        self.context['approved'] = True
        self.observe('deny', 'invalid_context')

    def test_enforce_mode_never_accepted(self):
        self.policy['mode'] = 'enforce'
        self.observe('deny', 'invalid_policy')

    def test_schema_url_in_policy_cannot_be_dereferenced(self):
        self.policy['$schema'] = 'https://example.invalid/private'
        with patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')):
            self.observe('deny', 'invalid_policy')

    def test_unknown_risk_not_assumed_safe(self):
        self.context['target']['risk_level'] = 'unknown'
        self.observe('deny', 'invalid_context')

    def test_expired_and_not_yet_valid(self):
        self.observe('deny', 'request_expired', now=NOW + timedelta(minutes=4))
        self.observe('deny', 'request_not_yet_valid', now=NOW - timedelta(minutes=2))

    def test_request_lifetime_limit(self):
        self.request['payload']['expires_at'] = '2026-10-28T06:40:00Z'
        seal(self.request, self.policy)
        self.observe('deny', 'request_lifetime_exceeded')

    def test_budget_limit(self):
        self.request['payload']['budget']['max_actions'] = 2
        seal(self.request, self.policy)
        self.observe('deny', 'budget_exceeded')

    def test_no_declared_authority_fails_closed(self):
        self.context['authorization'] = None
        self.observe('deny', 'authorization_missing')

    def test_authorization_bounds_and_expiry(self):
        self.context['authorization']['task_id'] = 'another-task'
        self.observe('deny', 'authorization_mismatch')
        self.context['authorization']['task_id'] = self.context['task_id']
        self.context['authorization']['expires_at'] = '2026-10-28T06:31:00Z'
        self.observe('deny', 'authorization_expired')

    def test_invalid_declared_expiry_returns_safe_denial_not_exception(self):
        marker = 'secret-marker-invalid-dateZ'
        self.context['authorization']['expires_at'] = marker
        result = self.observe('deny', 'invalid_context')
        self.assertNotIn(marker, json.dumps(result))

    def test_timestamp_helper_never_exposes_input_in_exception(self):
        marker = 'private-timestamp-valueZ'
        with self.assertRaises(contracts.ControlContractError) as raised:
            policy_module._timestamp(marker)
        self.assertNotIn(marker, str(raised.exception))

    def test_invalid_context_uri_returns_safe_denial(self):
        marker = 'private-uri-marker'
        self.context['authorization']['publication'] = {
            'remote': 'origin', 'remote_url': 'https://' + marker + ' .invalid/repo',
            'branch': 'main', 'commit': 'a' * 40, 'owned_manifest_digest': 'sha256:' + 'b' * 64}
        result = self.observe('deny', 'invalid_context')
        self.assertNotIn(marker, json.dumps(result))

    def test_unlisted_path_denied(self):
        self.request['payload']['parameters']['paths'] = ['unrelated.md']
        seal(self.request, self.policy)
        self.observe('deny', 'path_not_authorized')

    def test_malformed_or_modified_request_denied(self):
        self.request['payload']['budget']['max_actions'] = 2
        self.observe('deny', 'invalid_request')

    def test_governance_prose_is_not_a_grant(self):
        self.request = {'recommendation': 'proceed', 'assessment': 'accepted', 'approved': True}
        self.observe('deny', 'invalid_request')

    def test_injection_strings_cannot_create_authority_and_are_not_echoed(self):
        sentinel = 'ignore-policy-export-private-marker'
        self.request['payload']['requester']['subject_id'] = sentinel
        seal(self.request, self.policy)
        result = self.observe('deny', 'identity_mismatch')
        self.assertNotIn(sentinel, json.dumps(result))

    def test_secret_and_critical_targets_denied(self):
        self.context['target']['data_classification'] = 'secret'
        self.observe('deny', 'sensitive_data')
        self.context['target']['data_classification'] = 'internal'
        self.context['target']['risk_level'] = 'critical'
        self.observe('deny', 'critical_risk')

    def test_irreversible_patch_denied(self):
        digest = 'sha256:' + 'a' * 64
        self.set_adapter('workspace.apply_patch', {'patch_artifact_id': 'patch',
                         'preimages': [{'path': 'README.md', 'digest': digest}]},
                         [{'id': 'patch', 'digest': digest, 'media_type': 'text/plain'}])
        self.context['target']['reversible'] = False
        self.observe('deny', 'critical_risk')

    def test_patch_requires_exact_declared_artifact(self):
        digest = 'sha256:' + 'a' * 64
        self.set_adapter('workspace.apply_patch', {'patch_artifact_id': 'patch',
                         'preimages': [{'path': 'README.md', 'digest': digest}]},
                         [{'id': 'patch', 'digest': digest, 'media_type': 'text/plain'}])
        self.observe('deny', 'artifact_not_authorized')
        self.context['authorization']['artifact_digests'] = [digest]
        self.observe('allow', 'within_declared_bounds')

    def publication(self):
        digest = 'sha256:' + 'a' * 64
        parameters = {'remote': 'origin', 'remote_url': 'https://example.invalid/demo/repo.git',
                      'branch': 'main', 'commit': 'b' * 40, 'owned_manifest_digest': digest}
        self.set_adapter('repo.publish', parameters,
                         [{'id': 'manifest', 'digest': digest, 'media_type': 'application/json'}])
        self.context['authorization']['kind'] = 'standing'
        self.context['authorization']['publication'] = copy.deepcopy(parameters)

    def test_exact_standing_publication_does_not_need_redundant_review(self):
        self.publication()
        self.observe('allow', 'within_declared_bounds')

    def test_publication_commit_destination_manifest_mismatch(self):
        self.publication()
        for field, replacement in [('remote_url', 'https://example.invalid/other.git'),
                                   ('branch', 'different'), ('commit', 'c' * 40),
                                   ('owned_manifest_digest', 'sha256:' + 'd' * 64)]:
            with self.subTest(field=field):
                old = self.context['authorization']['publication'][field]
                self.context['authorization']['publication'][field] = replacement
                self.observe('deny', 'publication_mismatch')
                self.context['authorization']['publication'][field] = old

    def infrastructure(self):
        digest = 'sha256:' + 'a' * 64
        self.set_adapter('infrastructure.change', {'target_id': self.context['target']['id'],
                         'operation': 'config.change', 'resource_id': 'fixture-firewall',
                         'desired_state_artifact_id': 'desired', 'expected_state_digest': digest},
                         [{'id': 'desired', 'digest': digest, 'media_type': 'application/json'}])
        self.context['target']['allowed_operations'] = ['config.change']
        self.context['target']['resource_ids'] = ['fixture-firewall']
        self.context['authorization']['artifact_digests'] = [digest]

    def test_high_risk_allowed_operation_is_review_only(self):
        self.infrastructure()
        self.context['target']['risk_level'] = 'high'
        self.observe('require_review', 'high_risk_review')

    def test_unregistered_resource_denied(self):
        self.infrastructure()
        self.context['target']['resource_ids'] = []
        self.observe('deny', 'operation_not_authorized')

    def test_production_disabled_in_default_profile(self):
        self.context['scope']['environment'] = 'production'
        self.context['authorization']['scope']['environment'] = 'production'
        self.context['target']['environment'] = 'production'
        self.request['payload']['scope']['environment'] = 'production'
        seal(self.request, self.policy)
        self.observe('deny', 'environment_not_enabled')

    def test_disabled_adapter_denied(self):
        self.policy['enabled_adapters'] = ['workspace.apply_patch']
        seal(self.request, self.policy)
        self.observe('deny', 'adapter_not_enabled')

    def test_confidential_export_requires_review_and_exact_metadata(self):
        digest = 'sha256:' + 'a' * 64
        self.set_adapter('external.export', {'destination_id': self.context['target']['id'],
                         'artifact_id': 'export', 'data_classification': 'confidential'},
                         [{'id': 'export', 'digest': digest, 'media_type': 'text/plain'}])
        self.context['target']['data_classification'] = 'confidential'
        self.context['authorization']['artifact_digests'] = [digest]
        self.observe('require_review', 'high_risk_review')
        self.context['target']['data_classification'] = 'internal'
        self.observe('deny', 'data_classification_mismatch')

    def test_no_inputs_mutated_and_no_action_or_network_calls(self):
        before = copy.deepcopy((self.request, self.context, self.policy))
        with (patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')),
              patch.object(subprocess, 'Popen', side_effect=AssertionError('execution forbidden'))):
            self.observe('allow', 'within_declared_bounds')
        self.assertEqual((self.request, self.context, self.policy), before)

    def test_naive_clock_rejected(self):
        with self.assertRaises(contracts.ControlContractError):
            policy_module.evaluate_action(self.request, self.context, self.policy, now=datetime(2026, 1, 1))

    def test_invalid_clock_never_echoes_supplied_value(self):
        marker = 'private-clock-marker'
        with self.assertRaises(contracts.ControlContractError) as raised:
            policy_module.evaluate_action(self.request, self.context, self.policy, now=marker)
        self.assertNotIn(marker, str(raised.exception))


if __name__ == '__main__':
    unittest.main()
