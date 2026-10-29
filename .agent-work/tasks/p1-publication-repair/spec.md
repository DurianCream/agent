# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: p1-publication-repair
- Repository: multi
- Module: orchestrator
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: p1-publication-representation-repair

## Objective and acceptance criteria
Repair mixed Git line-ending publication comparison without changing sealed prior tasks and verify actual gated publication
- Exact raw and valid canonical representations pass while changed content and modes fail
- Prior blocked commit and submitted records remain preserved and recovery is documented
- Focused tests and independent review pass and the repaired gate verifies real publication

## Git checkpoint
- Branch: main
- HEAD: 01fbaaf717add7ecffc7a8b8d331163d90e16f79

## P0 observation
- Mode: observe; executable: false; authority_verified: false
- Status: review_pending
- Record: obs-97e60252fdca46b186dc8d33632578cc
- Snapshot: sha256:e4e1fe0acf536ca2002b6618f25dc4f5df9b993e95bb0a9ad2873c9bcf5d9db7
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
