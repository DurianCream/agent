# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: p1-submit-publish
- Repository: multi
- Module: orchestrator
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: p1-submission-publication-gates

## Objective and acceptance criteria
Implement and apply P1 cooperating submission and publication gates with tests and independent review
- Selected new tasks enforce candidate-bound submission and publication checks without silently downgrading controls
- Failures and stale or missing evidence block affected lifecycle actions with recoverable state
- Legacy tasks and P0 observations remain compatible and assurance limits are explicit
- Tests and independent review pass, specifications are saved and exact task files are pushed

## Git checkpoint
- Branch: main
- HEAD: c65bc0587efae45deeabddeb6e29f1da4c17b308

## P0 observation
- Mode: observe; executable: false; authority_verified: false
- Status: review_pending
- Record: obs-80bdd54d40f246dbb8c1f50b178015e9
- Snapshot: sha256:6e2267fd66548903ef282266eed9ef5fefa7ea6bcbad9ff8f33c88f67ecd5eb9
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
