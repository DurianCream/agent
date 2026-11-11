# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: repository-lf-20261111
- Repository: multi
- Module: coding
- State: submitted / partial

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: repository-lf-normalization

## Objective and acceptance criteria
Normalize repository text line endings to LF without semantic changes or historical hash edits
- Preserve existing attributes and establish repository-wide LF policy
- Prove normalization changes only line endings and preserve historical hash fields
- sync\_codex check and doctor pass with clean adapter status
- Full P1 suites and independent evaluator accept exact candidate

## Git checkpoint
- Branch: main
- HEAD: 51376aadcd9f60f712200cdff56c8f939b4897b7

## P0 observation
- Mode: observe; executable: false; authority_verified: false
- Status: review_pending
- Record: obs-5a9aa43f9a334d139aabcd72c28b3ead
- Snapshot: sha256:0a34cd1e240d089679454ec331ef06de777af18ef6c80ae5b4dbf6cfaff4db95
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
