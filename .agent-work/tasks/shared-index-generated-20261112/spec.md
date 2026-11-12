# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: shared-index-generated-20261112
- Repository: multi
- Module: coding
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: shared-index-generated

## Objective and acceptance criteria
Generate shared task index from records without publication deadlocks
- Deterministic generated index, preserved publication security, required tests and independent review, normal origin/main publication

## Git checkpoint
- Branch: main
- HEAD: 38ca357dd1488e903925be4f29c6b5f51c9fc055

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
