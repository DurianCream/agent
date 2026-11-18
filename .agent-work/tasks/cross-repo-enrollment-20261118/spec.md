# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: cross-repo-enrollment-20261118
- Repository: multi
- Module: coding
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: cross-repo-enrollment

## Objective and acceptance criteria
Stop P1 enrollment from resolving another repository's baseline commit inside the framework checkout.
- A new task bound to a registered repository other than the framework checkout initializes without a P1 Git inspection failure and is not enrolled, while framework tasks keep baseline-config enrollment.
- Selected gate suites pass and a regression test binds a task to a second repository with an independent history.

## Git checkpoint
- Branch: main
- HEAD: 07f472c804a118fc8c6362c210a7bfab6e14b644

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
