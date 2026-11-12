# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: profile-capture-off-20261112
- Repository: multi
- Module: coding
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: profile-capture-off

## Objective and acceptance criteria
Disable profile capture for new enrollments while retaining historical profile validation
- Requested impact rules added without changing PROTECTED
- New enrollment has impact\_tests and no submission\_profile; configuration removed and historical verification retained
- Existing tests prove absent key without adding test functions; mandatory suites and independent review pass
- Normal current-task submission and origin/main publication with Korean evidence report

## Git checkpoint
- Branch: main
- HEAD: 0eb9fafcd009e574165ca26e77f50271df7b2762

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
