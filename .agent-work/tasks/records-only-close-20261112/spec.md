# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: records-only-close-20261112
- Repository: multi
- Module: coding
- State: running / partial

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: records-only-close

## Objective and acceptance criteria
Enable bounded records-only publication for incomplete tasks using the smallest safe change
- Reproduce both reported conflicts in a temporary repository before changes
- Publish incomplete task records only while preserving integrity and publication boundaries
- Update existing recovery and secrets tests without adding test functions and pass mandatory suites
- Obtain independent review and publish the reviewed candidate through normal origin/main finish

## Git checkpoint
- Branch: main
- HEAD: 2af3b378edb9312c9e8ffc3e7fc007e61838ef70

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
