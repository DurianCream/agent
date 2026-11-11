# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: oss-execution-safety-20261111
- Repository: multi
- Module: skill-manager
- State: queued / partial

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: oss-execution-safety

## Objective and acceptance criteria
Publish the exact preserved seven-file OSS execution safety candidate under fresh enrollment, preserving all historical records and excluded files.
- Restored seven-file candidate matches all preservation SHA256 hashes exactly.
- Fresh sync\_codex check, doctor ok true, independent evaluation and mandatory P1 pass with zero errors and candidate\_unchanged true.
- Commit and push only owned candidate and permitted new-task records; exclude historical tasks, backup, unrelated adapters, infrastructure and runtime p2 files.

## Git checkpoint
- Branch: main
- HEAD: 4a4770f9508da2a00e5271d321a15a9e5e3a6036

## P0 observation
- Mode: observe; executable: false; authority_verified: false
- Status: not_ready
- Record: obs-fdd44337a86e4909ad867fce1569850b
- Snapshot: None
- Decision: None
- Assessment status: none
- Governance recommendation: None
- Evaluator assessment: None
- Reason codes: ownership_empty
This saved advisory summary may become stale; inspect current observer status before relying on it.

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.

## Accountable specialist assignment

Owner: /root/candidate_owner (skill-manager). Coordinator: /root (orchestrator).
Scope: repository multi; project multi; service agent-framework; environment development; issue oss-execution-safety.
Risk: high, because the preserved candidate changes execution-safety instructions and will pass publication gates.
Workspace: work/agents/oss-execution-safety-20261111/skill-manager/instance-yjoiokvn. Target checkout: framework root.
Owned product files: modules/oss-rnd/instructions.md; modules/oss-rnd/module.json; shared/skills/oss-research/SKILL.md; shared/skills/skills.json; .codex/agents/oss-rnd.toml; .agents/skills/oss-research/SKILL.md; runtime/native-map.json.
Allowed effects: apply the preserved patch exactly and write only this task's evidence/result/spec; no content repair, normalization, adapter regeneration, historical record edits, or publication by the specialist.
Acceptance: all seven raw SHA256 values match the preservation manifest; fresh sync check and doctor pass; fresh mandatory P1 suites report zero errors and candidate_unchanged=true; an independent evaluator reviews new evidence before publication by the coordinator.
Environment: existing local Windows checkout and Python runtime; no external test deployment.
Budget/checkpoints: restoration and hash comparison; fresh checks; evidence-ready handoff. Stop immediately at any blocked step and report, without bypass.
Recovery: preserved patch and file copies remain in the excluded oss-execution-safety-20261110-rerun backup directory; do not alter or publish that directory.
