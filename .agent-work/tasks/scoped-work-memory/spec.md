# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: scoped-work-memory
- Repository: multi
- Module: coding
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: scoped-work-memory

## Objective and acceptance criteria
Isolate work memory by project service environment and issue
- Startup returns full records only for the exact selected scope
- Different projects services environments issues and legacy records do not leak into context
- Scoped records survive fresh process and clone and publish safely

## Git checkpoint
- Branch: main
- HEAD: c5c1aa1bf345d846a62766dfb50cac0f7b82928c

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
