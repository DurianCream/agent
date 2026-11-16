# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: gate-bypass-fixes-20261116
- Repository: multi
- Module: coding
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: gate-bypass-fixes

## Objective and acceptance criteria
Block two P1 gate bypasses: product publication by a task whose scope skipped enrollment, and unowned automation.json changes in product commits.
- check\_commit refuses product publication from an unenrolled task in a gated repository, while records-only and incomplete closures still pass.
- Product commits may change only owned paths; .agent-work/automation.json is no longer implicitly allowed.
- Selected gate suites pass and a regression test covers the new refusal.

## Git checkpoint
- Branch: main
- HEAD: f139fa784d2fa2e889091d4cd9ba44511ed5de05

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
