# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: p2-reviewed-release-20261103
- Repository: multi
- Module: orchestrator
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: p2-host-credential-isolation

## Objective and acceptance criteria
Release independently reviewed frozen P2 artifacts and previously approved owner-led workflow sources with explicit provenance from preserved predecessor tasks
- Initialize on the verified authorized remote main baseline before materializing any candidate files and preserve predecessor history and pending commit
- Include only explicitly owned frozen P2 artifacts and approved owner-led workflow sources with provenance and no secrets private maps or unrelated task records
- Required tests and independent review cover the exact integrated release candidate and actual execution claims are supported by applicable evidence
- Validate submit and finish through configured publication gates with verified authorized non-force remote commit

## Git checkpoint
- Branch: main
- HEAD: b0ad3079baa1d0bd10a8959fbd0aa1a0256e1f5c

## P0 observation
- Mode: observe; executable: false; authority_verified: false
- Status: review_pending
- Record: obs-882c6b02bb93424bb89502b036b4d11b
- Snapshot: sha256:63d81965474051723736f4ddeeef94802828666b01b286d0b5da1c85fa0f6324
- Decision: allow
- Assessment status: none
- Governance recommendation: None
- Evaluator assessment: None
- Reason codes: review_pending
This saved advisory summary may become stale; inspect current observer status before relying on it.

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
