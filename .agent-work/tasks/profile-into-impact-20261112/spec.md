# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: profile-into-impact-20261112
- Repository: multi
- Module: coding
- State: running / partial

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: profile-into-impact

## Objective and acceptance criteria
Merge lightweight profile into impact selection, stopping if historical verification depends on it
- Preserve historical verification and protected full suites
- If compatible implement removal with full tests independent review and normal publication

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
