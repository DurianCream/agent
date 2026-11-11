# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: compact-evidence-20261111
- Repository: multi
- Module: coding
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: compact-task-evidence

## Objective and acceptance criteria
Reduce committed task evidence to a bounded summary, preserving historical records and raw local evidence
- New tasks publish only spec.md record.json report.ko.md and evidence/summary.json with verified raw evidence hashes
- Publication rejects oversized committed records with named files and documented limits
- Instructions versions adapters and at most three added tests are updated and independently reviewed
- Historical records stay unchanged and reviewed changes are committed and pushed

## Git checkpoint
- Branch: main
- HEAD: bb65946c093e0370a129efa180c364481cb0100b

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
