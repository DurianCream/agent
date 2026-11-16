# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: open-task-status-20261116
- Repository: multi
- Module: coding
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: open-task-status

## Objective and acceptance criteria
Add a read-only open-tasks command and exercise the publication lifecycle.
- List open tasks bound to the repository in task ID order with the requested metadata and per-task read errors without writes.
- Add one test to an existing test file and one or two Korean usage lines.

## Git checkpoint
- Branch: main
- HEAD: b9c86bd1cf89a88562ef021ab85c4f73da9a5b12

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
