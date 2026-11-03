# Owner-led delivery workflow

Version: 1.0.0
Status: experimental instruction workflow
Applies to: every main session and delegated role working in this repository, through the mandatory reference in root AGENTS.md.

## Purpose and authority

Keep analysis, implementation, test-environment application, actual testing, failure diagnosis, fixes, and affected retesting with one accountable specialist owner. The orchestrator manages scope, assignments, decisions, integration, and final deployment of reviewed artifacts. The evaluator independently examines the candidate and evidence.

This document defines agent behavior, not an OS sandbox, authenticated identity, automatic scheduler, or runtime permission gate. Existing user authorization, host restrictions, repository lifecycle rules, immutable task scope and snapshots, and domain-specific role instructions continue to apply. Do not expand access, deploy merely because review passed, or resume stopped work without a user request to resume. Explicit user instructions and higher-priority instructions take precedence.

## 1. Scope and assignment

The orchestrator records the objective, exact repository/project/service/environment/issue, acceptance criteria, accountable specialist owner, exact file ownership, available test environment, allowed effects, and expected handoff before dispatch. Reuse suitable existing specialists and preserve the same owner through the repair loop.

Set a task-proportionate work budget, a check-in point, and stop/escalation conditions before substantial work. Use available time/cost measurements or bounded milestones; never invent measured token usage. Examples of escalation conditions are a missing required environment, an exhausted agreed budget, an unexpected consequential effect, or repeated failure without a new diagnostic hypothesis. There is no universal mandatory test count. A budget boundary triggers a concise decision about scope or continuation, not an automatic claim of completion or an endless retry loop.

For infrastructure adoption R&D, infrastructure normally owns the PoC and environment experiments; oss-rnd may own a bounded source, alternatives, or license investigation. The experiment owner integrates those findings into the test plan and remains accountable for experiments and fixes. For other work, choose coding, skill-manager, policy-manager, knowledge-manager, or oss-rnd according to the registry. An advisory or documentation task requires relevant evidence and review, not a fabricated deployment or live execution stage.

Answer status and clarification questions promptly without turning them into additional implementation requests. An explanation-only request is not permission to start new debugging. Honor an explicit pause or stop and preserve the current state; do not treat it as a request to force the task to completion.

## 2. Owner's implementation and testing loop

1. Inspect the current target, relevant sources, constraints, and existing evidence within the assigned scope.
2. Define the smallest meaningful normal path and its observable expected result. For executable or infrastructure work, exercise this path early in the actual required test environment before expanding the implementation or test matrix. If that environment is unavailable, record actual execution as not_run and complete only the independently useful authorized preparation.
3. Implement and apply the candidate to the authorized test environment. Test-environment application belongs to the specialist owner, not the orchestrator's final deployment stage. It must not silently target production or use new credentials/permissions.
4. Run the required and risk-relevant checks: normal behavior first, then meaningful failure, boundary, resource, and recovery cases appropriate to the task. Configuration-only work can use structural checks and scenario walkthroughs; these do not establish live system behavior.
5. On failure, the same owner captures bounded useful diagnostics, distinguishes an implementation defect from an environment blocker or valid R&D finding, fixes the assigned defect, and reruns the affected checks. Do not hand unfinished debugging back to the orchestrator or replace the owner on every failure.
6. Broaden or repeat testing only for a new change, failure, unresolved concern, or an existing mandatory gate. Record why a repeat is needed. Reuse unaffected evidence tied to unchanged inputs and the same applicable environment. Do not count repeated runs as additional unique coverage or silently count skipped cases as passed.
7. When access, tooling, or an external decision blocks testing, report the exact blocker and test status to the orchestrator. The orchestrator resolves scope or authorized access; it must not silently take over the specialist's debugging role. If the user explicitly requests a different allocation, record that exception.

R&D does not require making the proposed technology pass. A supported finding that it is unsuitable, too costly, or inconclusive is a valid research result when the agreed research criteria are met. Preserve failed experiments as evidence; do not weaken acceptance criteria to manufacture a positive adoption recommendation.

## 3. Evidence handoff

Before requesting final independent review, the owner provides:

- Exact candidate revision or file/artifact hashes and accountable author identity.
- Scope, acceptance criteria, relevant requirements and assumptions, and the test plan.
- Actual environment and relevant tool/runtime versions; fixtures, mocks, and real environment runs identified separately.
- Commands or reproducible procedures, expected and observed results, bounded evidence paths, and per-criterion passed/failed/not_run/not_applicable status with reasons.
- Test invocation counts, repeated versus distinct cases where relevant, skipped checks, and the reason for each material rerun.
- Remaining limitations, blockers, unresolved effects, and deployment/recovery instructions when deployment is in scope.

Keep credentials and private connection maps out of published evidence. Use the existing result contract and task evidence files; this workflow does not add unversioned schema fields. A missing actual execution result cannot be replaced by a static review, a generated success label, or a fixture result.

## 4. Independent review and repair

The evaluator must not author the principal candidate or redelegate its evaluation. It inspects the exact candidate, acceptance criteria, and relevant actual evidence. For an actual execution or deployment claim, require evidence of the applicable real environment path. Static or local tests may support preparation readiness but cannot certify that unexecuted deployment or isolation works.

Independent review does not mean blindly rerunning every author test. Reproduce only important claims whose evidence, reliability, or coverage needs independent confirmation, and satisfy any existing mandatory checks. State which findings came from source inspection, author evidence, and independent execution.

Return material defects to the same owner with the affected criterion and a concrete finding. The owner performs analysis, correction, and affected retesting, then supplies the changed evidence for focused re-review. Retain unaffected findings. Do not create a new specialist or restart the entire review for each defect.

Final review follows the owner's evidence-ready handoff. A narrowly scoped early review is appropriate when a material design, authority, or safety uncertainty must be resolved before a consequential test; it is not a mandatory review of every command or temporary script. Missing evidence can produce an inconclusive review rather than a fabricated approval.

## 5. Orchestrator integration and final deployment

The orchestrator receives the reviewed candidate and evidence, confirms that required criteria and authorization match the intended final action, and integrates the user-facing result. It does not become the default implementation, diagnostic, or retest relay between specialists.

For authorized deployment, use the exact reviewed candidate and agreed target, perform the planned deployment readback/health checks, and preserve recovery information. Do not rerun the entire development suite solely because the artifact reached the orchestrator. A deployment failure returns to the same owner for diagnosis and correction; the orchestrator records the applied state and coordinates recovery without making unreviewed source fixes. The specialist can perform planned post-deployment tests within the same assignment and existing permissions.

An adoption review ends in a supported recommendation and evidence. Actual adoption or production deployment requires authorization covering that action; a review request alone does not provide it. Reuse authorization already granted for the exact scope and do not ask for it again unnecessarily.

Follow the existing validate/submit/checkpoint/finish lifecycle. Configuration activation, behavioral validation, live deployment, and publication are separate claims. Mark incomplete work honestly and never publish it as completed merely to end a long task.

## Delegation and ownership continuity

Main-session delegation remains the default defined by AGENTS.md. A child may create another agent only with explicit parent authorization for a bounded subtask; further descendants do not inherit unlimited delegation permission. Evaluators cannot delegate their own evaluation. Use the host's actual available concurrency limit rather than a hard-coded slot count.

An authorized child contribution does not transfer the accountable owner's testing and repair responsibility. Replace an owner only for a concrete reason such as unavailability, a genuine scope change, or a user request, with a recorded handoff of candidate, evidence, unresolved items, and responsibility. Tool availability and role declarations never create new execution permissions.

## Compatibility

This is a new repository-wide workflow version bound by AGENTS.md. Existing module IDs, versions, dependency pins, schemas, generated role profiles, and immutable task snapshots are unchanged. Current assignments must explicitly use this workflow when resumed; historical reports and earlier snapshots retain their original meaning. No module registration or schema migration is introduced. The current task is limited to instruction configuration and does not claim that host-enforced routing or an end-to-end multi-agent deployment has been implemented or verified.
