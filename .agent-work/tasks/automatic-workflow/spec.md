# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: automatic-workflow
- Repository: multi
- Module: orchestrator
- State: submitted / completed

## Objective and acceptance criteria
Automatically load repository memory and publish completed work
- Startup reads saved work without a user reminder
- Completed work is saved committed and pushed to the authorized remote
- Unrelated changes and remote conflicts are protected

## Git checkpoint
- Branch: main
- HEAD: 9b62de06849bd096c82188b2a719feac1cadbee6

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
