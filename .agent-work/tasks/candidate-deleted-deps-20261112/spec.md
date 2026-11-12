# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: candidate-deleted-deps-20261112
- Repository: multi
- Module: coding
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: candidate-deleted-deps

## Objective and acceptance criteria
Stabilize candidate dependencies across owned file deletion commits without weakening publication checks
- Reproduce owned-deletion candidate digest mismatch and confirm reported cause
- Exclude owned product paths from dependency inventory while retaining entries and unowned deletion checks
- Existing tests prove deletion digest stability and publication; required full suites and independent review pass
- Normal publication readiness and Korean report preserve historical records backup branch and security checks

## Git checkpoint
- Branch: main
- HEAD: cb1d675ff17df58083ac6e5c93df5f9ba0f39777

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
