# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: profile-removal-20261112b
- Repository: multi
- Module: coding
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: profile-removal-reapply

## Objective and acceptance criteria
Reapply reviewed profile removal product changes while retaining owned-deletion candidate stability fix
- Own enrollment has no submission\_profile and zero profile state files exist
- Only approved backup product changes reapplied with candidate-dependency fix preserved and historical records untouched
- Required full tests and independent evaluation pass with no new test functions
- Normal publication readiness and Korean comparison workflow fail-closed metrics report verified

## Git checkpoint
- Branch: main
- HEAD: 2eaadfc7b73648cf8787c8312b6764b73c4d6bd5

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
