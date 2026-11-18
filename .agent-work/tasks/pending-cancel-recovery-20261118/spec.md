# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: pending-cancel-recovery-20261118
- Repository: multi
- Module: coding
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: pending-cancel-recovery

## Objective and acceptance criteria
Support auditable cancellation only for provably failed unstarted external repository enrollment
- Close the requested unstarted external task as cancelled through the supported CLI and maintain all other safeguards
- Prove refusal for invalid candidates and retain existing lifecycle behavior

## Git checkpoint
- Branch: main
- HEAD: 1d28a0c3bf7583375a63f3b2743b0d0dadb17f2f

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
