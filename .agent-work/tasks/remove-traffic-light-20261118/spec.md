# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: remove-traffic-light-20261118
- Repository: multi
- Module: skill-manager
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: remove-traffic-light

## Objective and acceptance criteria
Remove the project-local traffic-light skill and its runtime, registration, documentation and tests at the user request.
- Traffic-light is absent from active project skills, runtime and usage documentation.
- Remaining project skills and repository checks pass.

## Git checkpoint
- Branch: main
- HEAD: 5ff6b7c06a2c8c42fbd470d6eae908039fb70f44

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
