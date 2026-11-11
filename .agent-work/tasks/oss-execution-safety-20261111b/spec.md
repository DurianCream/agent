# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: oss-execution-safety-20261111b
- Repository: multi
- Module: skill-manager
- State: queued / partial

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: oss-execution-safety

## Objective and acceptance criteria
Verify and publish the preserved seven-file OSS execution safety change, preserving excluded historical records and files.
- Each of the seven restored files matches its backup Git blob hash using git hash-object --path for the backup and git hash-object for the candidate; runtime/native-map.json complies with eol=lf.
- Fresh sync\_codex --check and doctor return success with doctor ok true.
- Fresh mandatory P1 suites pass with zero errors and candidate\_unchanged true, and independent adversarial evaluator accepts the exact candidate.
- Publication scope is restricted to the seven owned files and permitted new-task records, excluding historical tasks, backup, unrelated adapters, modules/infrastructure and runtime/p2 files.

## Git checkpoint
- Branch: main
- HEAD: 4a4770f9508da2a00e5271d321a15a9e5e3a6036

## P0 observation
- Mode: observe; executable: false; authority_verified: false
- Status: not_ready
- Record: obs-2fde09f3cf2540f580dcda167f490f7a
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

## Accountable assignment
Owner: /root/candidate_owner (skill-manager); coordinator: /root.
Risk: high because execution-safety instructions and publication are involved.
Scope: multi / multi / agent-framework / development / oss-execution-safety.
Workspace: work/agents/oss-execution-safety-20261111b/skill-manager/instance-ua47obj4. Target: framework root.
Owned candidate: modules/oss-rnd/instructions.md, modules/oss-rnd/module.json, shared/skills/oss-research/SKILL.md, shared/skills/skills.json, .codex/agents/oss-rnd.toml, .agents/skills/oss-research/SKILL.md, runtime/native-map.json.
Acceptance: seven backup/candidate Git blob hashes match; native-map uses LF; fresh sync check and doctor succeed; fresh p1-regression has zero errors and unchanged candidate; independent review accepts exact candidate; publication remains bounded.
Budget milestones: exact patch restoration/blob comparison; fresh checks; evidence-ready handoff. Stop on any blocker without bypass. No candidate normalization, unrelated edits, history changes, delegation, or specialist publication.
Environment: current Windows checkout and configured project Python; local cooperating checks do not establish OS isolation.
Context: previous task oss-execution-safety-20261111 was cancelled by the coordinator because its immutable raw-byte acceptance criterion was mistaken. This task has fresh enrollment and evidence; prior records and backup remain immutable and excluded.
Recovery: retain excluded backup and report any failure; do not alter the seven-file content or repair a failed gate without renewed direction.
