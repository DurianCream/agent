# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: repository-lf-retry-20261111
- Repository: multi
- Module: coding
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: repository-lf-normalization

## Objective and acceptance criteria
Normalize repository text to LF without content or historical hash changes; preserve candidate on failure
- Global LF attributes preserve existing rules; binary and Windows script decisions evidenced
- Renormalization contains only CRLF-to-LF byte changes excluding authorized attributes and current task records
- Historic records unchanged; sync\_codex check and doctor pass; adapters clean
- Full P1 1800-second suite and independent evaluator accept exact LF candidate

## Git checkpoint
- Branch: main
- HEAD: c3808fa0375ab6b0756a52ab97ded877a45e5b05

## P0 observation
- Mode: observe; executable: false; authority_verified: false
- Status: review_pending
- Record: obs-82d709685f4f450991810e4fcd1960de
- Snapshot: sha256:eb460083702dd9eebcdaa5fe05abf4216385c4961576f19354bf70d3f74229e4
- Decision: allow
- Assessment status: none
- Governance recommendation: None
- Evaluator assessment: None
- Reason codes: review_pending
This saved advisory summary may become stale; inspect current observer status before relying on it.

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
