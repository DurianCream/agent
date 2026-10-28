# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: repository-memory
- Repository: multi
- Module: knowledge-manager
- State: running / partial

## Objective and acceptance criteria
Persist repository work records and reconnect future chats
- Repository records support verified recovery in fresh processes
- Agent instructions are English and human reports are Korean
- Replace remote contents while preserving Git history

## Git checkpoint
- Branch: master
- HEAD: None

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
