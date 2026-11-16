# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: gate-config-baseline-20261116
- Repository: multi
- Module: coding
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: gate-config-baseline

## Objective and acceptance criteria
Enroll P1 gates from the gate configuration committed at the task baseline, not from uncommitted worktree bytes.
- Enrollment uses .agent-work/gates.json from the publication base commit; an uncommitted edit, addition or deletion of the worktree copy cannot weaken, activate or disable enrollment and fails closed when it differs.
- Selected gate suites pass and regression tests cover modified and deleted worktree configuration.

## Git checkpoint
- Branch: main
- HEAD: 4f59bc7c10c665e033f1cec33f2c44fcdba6c858

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
