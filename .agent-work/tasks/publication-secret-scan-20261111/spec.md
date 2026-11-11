# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: publication-secret-scan-20261111
- Repository: multi
- Module: coding
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: publication-secret-scan

## Objective and acceptance criteria
Block secrets in exact task publication files before commit and push for normal and records-only publication
- Scan only publication change files and document scanner selection
- Block secret findings without printing or storing secret values; report only file and line
- Provide one explicit file-level allowlist
- Test fake canary blocked and clean changes passed for both publication paths and retries without weakening P1
- Add concise Korean P1 guide and register new tests in impact-tests mapping; exclude unrelated edits
- Pass mandatory tests and independent adversarial review then publish task-owned files

## Git checkpoint
- Branch: main
- HEAD: 7d3caccd3d71896ec7c28aeccc653aa76ac9f3d2

## P0 observation
- Mode: observe; executable: false; authority_verified: false
- Status: review_pending
- Record: obs-e12dc0ed3c93434386ff16359e4160b1
- Snapshot: sha256:7b5f64de5cfaddbac6264ef2cec3d87454147f5ad4889d9092350cd64c2db7d2
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
