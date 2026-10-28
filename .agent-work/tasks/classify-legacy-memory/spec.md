# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: classify-legacy-memory
- Repository: multi
- Module: knowledge-manager
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: legacy-memory-classification

## Objective and acceptance criteria
Classify legacy work records without changing historical originals
- Every registered legacy record has an evidence-based classification or explicit uncertainty
- Historical originals remain byte-for-byte unchanged
- Confirmed classifications load only in their exact scope and publish successfully

## Git checkpoint
- Branch: main
- HEAD: ab6d33eb23b16f9f4cf75ca897e1c19f63590f50

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
