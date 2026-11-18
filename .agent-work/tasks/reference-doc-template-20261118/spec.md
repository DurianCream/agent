# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: reference-doc-template-20261118
- Repository: multi
- Module: coding
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: reference-doc-template

## Objective and acceptance criteria
Make infra-docs deliverables reusable reference documents by default through a Korean template, an AGENTS.md rule and an evaluator check.
- A Korean reference-document template defines the section structure, what each section contains, and what must stay out (dates, actors, task narrative, test-result tables).
- AGENTS.md requires infra-docs docs/\<topic\>/ deliverables to follow the template, keeps test results in task records, and tells the evaluator to check template conformance.
- Selected gate suites pass.

## Git checkpoint
- Branch: main
- HEAD: ec88753ebaef46d1a85712f9d8e6366a078eff06

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
