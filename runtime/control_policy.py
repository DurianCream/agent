"""P0 policy observation. Declared inputs never grant authority or execute actions."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

if __package__:
    from . import control_contracts as contracts
else:
    import control_contracts as contracts

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / 'shared/policies/execution-controls.observe.json'
INPUT_SCHEMA = ROOT / 'shared/schemas/control-observe-policy.schema.json'
OUTPUT_SCHEMA = ROOT / 'shared/schemas/control-observation.schema.json'
LEVELS = ('low', 'medium', 'high', 'critical')
BASE_RISK = {'workspace.inspect': 'low', 'workspace.apply_patch': 'low',
             'repo.publish': 'medium', 'infrastructure.change': 'medium',
             'external.export': 'medium'}


def _timestamp(text: str) -> datetime:
    try:
        if not isinstance(text, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z', text):
            raise ValueError
        return datetime.fromisoformat(text.replace('Z', '+00:00'))
    except (ValueError, TypeError, AttributeError):
        raise contracts.ControlContractError('invalid_timestamp', 'Timestamp is invalid.') from None


def _validate_input(value: Any, kind: str, schema: dict) -> dict:
    validated = contracts.validate_schema_data(value, schema)
    if validated['document_type'] != kind:
        raise contracts.ControlContractError('invalid_context', 'Observation input kind is invalid.')
    return validated


def evaluate_action(request: Any, context: Any, policy: Any = None, *,
                    now: datetime | None = None) -> dict:
    """Return a non-executable observation using only supplied declared data.

    No signatures, authorizations, artifact contents, filesystem targets, or remote
    systems are authenticated or inspected. Policy/context hashes identify the
    declared inputs; they do not establish trust. ``now`` is a test seam, never a
    CLI option. Validation failures produce bounded reason codes, not raw values.
    """
    moment = datetime.now(timezone.utc) if now is None else now
    if not isinstance(moment, datetime) or moment.tzinfo is None:
        raise contracts.ControlContractError('invalid_clock', 'An aware clock is required.')
    try:
        moment = moment.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        raise contracts.ControlContractError('invalid_clock', 'An aware clock is required.') from None
    observed_at = moment.isoformat(timespec='seconds').replace('+00:00', 'Z')
    hashes = {'request_digest': None, 'policy_digest': None, 'context_digest': None}
    risk = None

    def result(decision: str, code: str) -> dict:
        value = {'record_type': 'policy_observation', 'schema_version': '0.1.0',
                 'mode': 'observe', 'decision': decision, 'risk': risk,
                 'reason_codes': [code], 'observed_at': observed_at, **hashes,
                 'executable': False, 'authority_verified': False,
                 'content_checks': 'not_performed', 'signature_verification': 'not_performed'}
        # Output schema is a fixed local implementation asset, never an input URL.
        return contracts.validate_schema_data(value, contracts.read_json(OUTPUT_SCHEMA))

    try:
        checked = contracts.validate_envelope(request)['envelope']
    except contracts.ControlContractError:
        return result('deny', 'invalid_request')
    if checked['record_type'] != 'action_request':
        return result('deny', 'unsupported_record_type')
    hashes['request_digest'] = checked['digest']
    payload = checked['payload']
    try:
        schema = contracts.read_json(INPUT_SCHEMA)
        selected = contracts.read_json(DEFAULT_POLICY) if policy is None else policy
        selected = _validate_input(selected, 'observe_policy', schema)
        hashes['policy_digest'] = contracts.canonical_digest(selected)
    except (contracts.ControlContractError, OSError):
        return result('deny', 'invalid_policy')
    try:
        declared = _validate_input(context, 'observe_context', schema)
        hashes['context_digest'] = contracts.canonical_digest(declared)
    except contracts.ControlContractError:
        return result('deny', 'invalid_context')

    adapter = payload['adapter']
    parameters = payload['parameters']
    target = declared['target']
    risk = max((BASE_RISK[adapter], target['risk_level']), key=LEVELS.index)
    if target['environment'] == 'production' or target['data_classification'] in ('confidential', 'restricted'):
        risk = max(risk, 'high', key=LEVELS.index)
    if target['data_classification'] == 'secret':
        risk = 'critical'
        return result('deny', 'sensitive_data')
    if adapter in ('workspace.apply_patch', 'infrastructure.change') and not target['reversible']:
        risk = 'critical'
    if risk == 'critical':
        return result('deny', 'critical_risk')
    if payload['policy_ref'] != {'id': selected['id'], 'version': selected['version'],
                                  'digest': hashes['policy_digest']}:
        return result('deny', 'policy_mismatch')
    if (payload['scope'] != declared['scope'] or payload['task_id'] != declared['task_id']
            or payload['repository_id'] != declared['repository_id']):
        return result('deny', 'scope_mismatch')
    if payload['requester'] != declared['requester']:
        return result('deny', 'identity_mismatch')
    if target['environment'] != payload['scope']['environment']:
        return result('deny', 'target_mismatch')
    if target['environment'] not in selected['allowed_environments']:
        return result('deny', 'environment_not_enabled')
    if adapter not in selected['enabled_adapters']:
        return result('deny', 'adapter_not_enabled')
    try:
        issued = _timestamp(payload['issued_at'])
        expires = _timestamp(payload['expires_at'])
    except contracts.ControlContractError:
        return result('deny', 'invalid_request')
    if moment >= expires:
        return result('deny', 'request_expired')
    if moment < issued:
        return result('deny', 'request_not_yet_valid')
    if (expires - issued).total_seconds() > selected['max_request_lifetime_seconds']:
        return result('deny', 'request_lifetime_exceeded')
    if any(payload['budget'][key] > limit for key, limit in selected['budget_limits'].items()):
        return result('deny', 'budget_exceeded')
    authority = declared['authorization']
    if authority is None:
        return result('deny', 'authorization_missing')
    if (authority['repository_id'] != payload['repository_id']
            or authority['task_id'] != payload['task_id'] or authority['scope'] != payload['scope']
            or authority['subject_id'] != payload['requester']['subject_id']
            or authority['target_id'] != target['id'] or adapter not in authority['adapters']):
        return result('deny', 'authorization_mismatch')
    if authority['expires_at'] is not None:
        try:
            authority_expiry = _timestamp(authority['expires_at'])
        except contracts.ControlContractError:
            return result('deny', 'invalid_context')
        if moment >= authority_expiry:
            return result('deny', 'authorization_expired')
    artifacts = {entry['id']: entry['digest'] for entry in payload['artifacts']}
    if adapter == 'workspace.inspect':
        if any(path not in authority['paths'] for path in parameters['paths']):
            return result('deny', 'path_not_authorized')
    elif adapter == 'workspace.apply_patch':
        if any(item['path'] not in authority['paths'] for item in parameters['preimages']):
            return result('deny', 'path_not_authorized')
        if artifacts.get(parameters['patch_artifact_id']) not in authority['artifact_digests']:
            return result('deny', 'artifact_not_authorized')
    elif adapter == 'repo.publish':
        publication = authority['publication']
        if publication is None or any(parameters[key] != publication[key] for key in publication):
            return result('deny', 'publication_mismatch')
        if parameters['owned_manifest_digest'] not in artifacts.values():
            return result('deny', 'artifact_not_authorized')
    elif adapter == 'infrastructure.change':
        if parameters['target_id'] != target['id']:
            return result('deny', 'target_mismatch')
        if (parameters['operation'] not in target['allowed_operations']
                or parameters['resource_id'] not in target['resource_ids']):
            return result('deny', 'operation_not_authorized')
        if artifacts.get(parameters['desired_state_artifact_id']) not in authority['artifact_digests']:
            return result('deny', 'artifact_not_authorized')
    elif adapter == 'external.export':
        if parameters['destination_id'] != target['id']:
            return result('deny', 'target_mismatch')
        if parameters['data_classification'] != target['data_classification']:
            return result('deny', 'data_classification_mismatch')
        if artifacts.get(parameters['artifact_id']) not in authority['artifact_digests']:
            return result('deny', 'artifact_not_authorized')
    if risk == 'high':
        return result('require_review', 'high_risk_review')
    return result('allow', 'within_declared_bounds')
