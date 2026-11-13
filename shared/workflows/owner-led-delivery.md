# Owner-led delivery workflow

Version: 1.4.0
Status: experimental instruction workflow
Applies to: every main session and delegated role working in this repository, through the mandatory reference in root AGENTS.md.

## Purpose and authority

One accountable specialist owner keeps analysis, implementation, test-environment application, testing, failure diagnosis, fixes and affected retesting. The orchestrator manages scope, assignments, decisions, integration and final deployment of reviewed artifacts. The evaluator independently examines the candidate and evidence.

This document defines agent behavior, not an OS sandbox, authenticated identity, scheduler or runtime permission gate. User authorization, host restrictions, repository lifecycle rules, immutable task scope and snapshots, and role instructions still apply. Do not expand access, deploy merely because review passed, or resume stopped work without a user request. Explicit user and higher-priority instructions take precedence.

## Risk tiers

Classify work by impact, uncertainty and recoverability, not file or line count. Record the tier and a one-line reason in the task record for change work; explanation-only conversation needs no task record.

| Tier | Includes | Default path |
|---|---|---|
| Light | Clear explanations; wording, links, role descriptions or small configuration cleanup with no behavior, permission or security-boundary effect. Unresolved material uncertainty excludes this tier. | Answer explanations directly. Actual changes: one owner, one narrow independent adversarial review, concise records in the existing contract. |
| Normal | Features, bugs, APIs, dependencies, behavior changes, substantive research/design below high risk. | Brief plan, necessary investigation, the owner's implementation and relevant tests, independent adversarial review, repair and affected re-review. |
| High risk | Authentication, credentials, permissions, OS isolation, execution/publication gates, production deployment, consequential external writes, data deletion, migrations, recovery. | Impact and recovery plan, necessary investigation, implementation with real-environment verification, independent adversarial review, existing approvals and mandatory gates, post-application checks. |

A configuration file is not automatically light: namespace, permission, review-obligation or publication-gate changes are normal or high risk. Investigate risk-concealing unknowns narrowly. Split mixed work only at independent boundaries, never across one security boundary. The tier routes agent effort only; it does not select runtime checks. Required checks come from the committed impact-scope selection, and every tier keeps independent review for actual changes and all applicable mandatory gates. Do not promise zero test time or savings without measurements.

## 1. Scope and assignment

Before dispatch, record the objective, tier and reason, exact repository/project/service/environment/issue, acceptance criteria, accountable owner, exact owned files, available test environment, allowed effects and expected handoff. Reuse suitable existing specialists and keep the same owner through the repair loop. Give concurrent writers disjoint exact files; sequence or reassign work before another writer touches the same file. The evaluator reads the candidate without editing it.

Workspaces are optional for a single agent. When several agents work at once, allocate one per agent with `python runtime/agentctl.py workspace <task-id> --role <registered-role>`, pass the framework root, target checkout and allocated path at dispatch, and record them in the handoff. Without a workspace, put scratch files in work/. Keep durable evidence in runs/<task-id>/ and deliverables in outputs/<task-id>/. Workspaces provide no OS access control.

Set a task-proportionate budget, a check-in point and stop conditions before substantial work, such as a missing required environment, an exhausted budget, an unexpected consequential effect, or repeated failure without a new diagnostic hypothesis. Never invent measured token usage. A budget boundary triggers a scope decision, not a completion claim or an endless retry.

For infrastructure adoption R&D, infrastructure owns the PoC and experiments; oss-rnd may own a bounded source, alternatives or license investigation. Otherwise choose the owner from the registry. Advisory or documentation work needs relevant evidence and review, not a fabricated deployment stage.

Answer status and clarification questions without turning them into new work. Honor an explicit pause or stop and preserve the current state.

## 2. Owner's implementation and testing loop

1. Inspect the target, relevant sources, constraints and existing evidence within scope.
2. Define the smallest meaningful normal path and its expected result. For executable or infrastructure work, exercise it early in the required test environment. If that environment is unavailable, record execution as not_run and complete only useful authorized preparation.
3. Implement and apply the candidate to the authorized test environment. This belongs to the owner, must not silently target production, and must not use new credentials or permissions.
4. Run the required and risk-relevant checks: normal behavior first, then meaningful failure, boundary, resource and recovery cases. Configuration-only work can use structural checks and scenario walkthroughs; these do not establish live behavior.
5. On failure, the same owner captures bounded diagnostics, separates an implementation defect from an environment blocker or valid R&D finding, fixes the defect and reruns affected checks.
6. Repeat or broaden testing only for a new change, failure, concrete concern or mandatory gate, and record why. Reuse unaffected evidence tied to unchanged inputs and environment. Do not count reruns as extra coverage or skipped cases as passed.
7. When access, tooling or an external decision blocks testing, report the exact blocker and test status. The orchestrator resolves scope or access; it does not take over debugging unless the user explicitly reallocates it.

R&D does not have to make the proposed technology pass. A supported finding that it is unsuitable, too costly or inconclusive is valid when the research criteria are met. Keep failed experiments as evidence and never weaken criteria to manufacture adoption.

## 3. Evidence handoff

Every change task records the objective, tier and reason, actual changes, decisions, checks with results and evidence (including not_run and why), review verdict with stable finding IDs and repair status, and unfinished work. Update it at implementation completion, review handoff and repair completion, not after every tool call. High-risk records also keep the target environment, permissions, versions and recovery conditions. The records must allow recovery after context compaction.

Before final review, the owner provides the exact candidate revision or hashes and author; scope, criteria, assumptions and test plan; environment and tool versions, with fixtures, mocks and real runs identified separately; commands, expected and observed results, evidence paths and per-criterion status; invocation counts and the reason for each material rerun; and remaining limitations, blockers and deployment/recovery instructions when in scope.

Keep credentials and private connection maps out of published evidence. Use the existing result contract and the compact evidence procedure in shared/skills/submit-result/SKILL.md. A static review, generated success label or fixture result never replaces a missing actual execution result.

## 4. Independent review and repair

Every review and re-review assignment includes this instruction:

> Treat the candidate as another AI's work and perform adversarial verification. Do not trust the author's completion claim; inspect actual changes and evidence. Examine relevant counterexamples, boundaries, errors, and regressions. Separate confirmed defects from unverified suspicions and do not manufacture findings. Give each finding a stable ID, location, reproduction or concrete evidence, impact, and re-verification criterion.

The evaluator must not author the candidate or redelegate its evaluation. It inspects the exact candidate, criteria and actual evidence; an execution or deployment claim needs evidence from the applicable real environment. Static or local tests may show readiness but cannot certify unexecuted deployment or isolation. It reproduces only claims whose evidence or coverage needs independent confirmation, satisfies mandatory checks, and states which findings came from inspection, author evidence and independent execution.

Return material defects to the same owner with the affected criterion and finding; the owner fixes, retests the affected part and supplies changed evidence for focused re-review. Keep unaffected findings. Status wording alone does not restart review; changed facts, evidence, criteria or meaning require review of those parts. One narrow review is the light-tier default, not a cap on required repair. An early narrow review fits a material design, authority or safety uncertainty before a consequential test. Missing evidence yields an inconclusive review, not an approval.

## 5. Integration and final deployment

The orchestrator confirms that required criteria and authorization match the intended final action and integrates the user-facing result. It is not an implementation or retest relay between specialists.

For authorized deployment, use the exact reviewed candidate and target, perform the planned readback and health checks, and keep recovery information. Do not rerun the whole development suite because the artifact reached the orchestrator. A deployment failure returns to the same owner. An adoption review ends in a supported recommendation; actual adoption or production deployment needs authorization covering that action. Reuse authorization already granted for the exact scope.

Follow the publication lifecycle in shared/workflows/harness-delivery.md#publication. Configuration activation, behavioral validation, live deployment and publication are separate claims. Mark incomplete work honestly and close it through that section instead of publishing it as completed.

## 6. Delegation

Do not automatically add investigation, design or management roles to light work. A child may create another agent only with explicit parent authorization for a bounded subtask; descendants do not inherit unlimited delegation. Evaluators never delegate their evaluation. Use the host's actual concurrency limit. A child's contribution does not move the owner's testing and repair responsibility. Replace an owner only for a concrete reason, such as unavailability, a real scope change or a user request, with a recorded handoff of candidate, evidence, open items and responsibility. Tool availability and role declarations never create execution permissions.

## Compatibility

Version 1.4.0 applies to tasks started after this revision. Existing in-progress criteria, enrollments, historical reports and frozen snapshots keep their original meaning and are not migrated. Module IDs, permissions, runtime gate configuration and result schema 1.0.0 are unchanged. These instructions do not implement host-enforced routing or prove agent behavior or deployment success.
