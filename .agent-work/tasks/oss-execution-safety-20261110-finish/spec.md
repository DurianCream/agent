# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: oss-execution-safety-20261110-finish
- Repository: multi
- Module: policy-manager
- State: waiting / partial

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: oss-execution-safety

## Objective and acceptance criteria
Complete oss-execution-safety-20261110: regenerate adapters, independent review, full P1, scoped publication
- Adapters regenerated and check plus doctor report ok true
- Independent evaluator accepts exact candidate and all mandatory P1 suites pass with zero errors and candidate\_unchanged true
- Publish only original task source changes, affected adapters and bounded task records; exclude unrelated adapters infrastructure and runtime p2

## Git checkpoint
- Branch: main
- HEAD: 4a4770f9508da2a00e5271d321a15a9e5e3a6036

## P0 observation
- Mode: observe; executable: false; authority_verified: false
- Status: review_pending
- Record: obs-2094cb9023eb4bbc973602d51ce1cfbb
- Snapshot: sha256:d793d644a120ee7d6463004e05c592b411fab5b45e23f25fe28c3d90be929ba6
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
