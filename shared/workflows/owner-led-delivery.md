# Owner-led delivery workflow

Version: 1.3.0
Status: experimental instruction workflow
Applies to: every main session and delegated role working in this repository, through the mandatory reference in root AGENTS.md.

## Purpose and authority

Keep analysis, implementation, test-environment application, actual testing, failure diagnosis, fixes, and affected retesting with one accountable specialist owner. The orchestrator manages scope, assignments, decisions, integration, and final deployment of reviewed artifacts. The evaluator independently examines the candidate and evidence.

This document defines agent behavior, not an OS sandbox, authenticated identity, automatic scheduler, or runtime permission gate. Existing user authorization, host restrictions, repository lifecycle rules, immutable task scope and snapshots, and domain-specific role instructions continue to apply. Do not expand access, deploy merely because review passed, or resume stopped work without a user request to resume. Explicit user instructions and higher-priority instructions take precedence.

## Risk tiers and routing

The main session classifies work by impact, uncertainty, and recoverability, not by file count or lines changed. Record the tier and a one-line reason in the existing task record for change work; clear explanation-only conversation needs no separate task record.

| Tier | Inclusion and exclusion | Default path |
|---|---|---|
| Light | Clear explanations; wording, links, role descriptions, or small configuration cleanup with no product behavior, permission, or security-boundary effect. Unresolved material uncertainty excludes this tier. | Answer explanations directly. For actual changes: one accountable specialist owner, one narrow independent adversarial review, and concise durable records using the existing contract. |
| Normal | Ordinary features, bugs, APIs, dependencies, behavior changes, and substantive research/design that do not meet high-risk conditions. | Brief plan, only necessary investigation/design, the same owner's implementation and relevant tests, independent adversarial review, and affected repair/re-review. |
| High risk | Authentication, credentials, permissions, OS isolation, execution/publication gates, production deployment, consequential external writes, data deletion, migrations, or recovery. | Impact and recovery plan, necessary specialist investigation, implementation and relevant real-environment verification, independent adversarial review, existing approvals and mandatory gates, and applicable post-application checks. |

A configuration file is not automatically light. Changes to namespaces, service permissions, review obligations, or publication gates require impact assessment and normal or high-risk handling. Investigate risk-concealing unknowns narrowly; unresolved high-risk conditions remain high risk. Split mixed work only at independent boundaries, never divide one security boundary to evade controls. Use existing authorization without inventing new approvals.

These are instruction-level routing rules, not automatic runtime profile selection. The separately versioned ordinary-prose-v1 capability is narrower: only previously allowlisted ordinary prose edits with independent semantic approval can select its fixed document checks. Preserve independent review for actual changes and all applicable mandatory gates at every tier. For documentation-only work, content verification can use document, path, and scenario review; existing mandatory submission/publication gates must be satisfied separately. Do not promise zero test time or measured savings without measurements.

## 1. Scope and assignment

For a task with a local run, execute `python runtime/agentctl.py workspace <task-id> --role <registered-role>` from the framework root once per newly assigned agent, including the orchestrator and evaluator. Each invocation allocates a distinct empty scratch directory. Record the role, actual agent, returned path, target checkout and exact owned product files in the task handoff. Reuse that directory when the same agent continues its assignment.

Pass the framework root, target checkout and allocated path at dispatch. The subject uses the allocated directory as its working directory, setting the tool's working-directory option when the host cannot set an initial cwd. Run repository-specific commands against the explicit checkout. The orchestrator gives concurrent writers disjoint exact paths and tracks them through the existing publication lifecycle. Sequence or reassign work before another writer touches the same file. The independent evaluator receives a separate directory and reads the candidate without editing it. Keep durable evidence in runs/<task-id>/ and deliverables in outputs/<task-id>/. Scratch directories coordinate cooperative agents and provide no OS access control.

For work requiring delegation, the orchestrator records the objective, risk tier and reason, exact repository/project/service/environment/issue, acceptance criteria, accountable specialist owner, exact file ownership, available test environment, allowed effects, and expected handoff before dispatch. Reuse suitable existing specialists and preserve the same owner through the repair loop.

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

Every change task retains the objective, tier and reason, actual files/behavior changed, decisions and reasons, checks/results/evidence (including not_run and why), review verdict and stable finding IDs with repair status, and unfinished work/next actions. Update this durable specification at meaningful implementation completion, review handoff, and repair completion; do not rewrite the whole specification after every tool call. High-risk records also retain the target environment, permissions, versions, and recovery conditions. Existing result fields and linked task evidence are sufficient; do not add duplicate empty reports or unversioned schema fields. These records must allow recovery after context compaction.

Before requesting final independent review, the owner provides:

- Exact candidate revision or file/artifact hashes and accountable author identity.
- Scope, acceptance criteria, relevant requirements and assumptions, and the test plan.
- Actual environment and relevant tool/runtime versions; fixtures, mocks, and real environment runs identified separately.
- Commands or reproducible procedures, expected and observed results, bounded evidence paths, and per-criterion passed/failed/not_run/not_applicable status with reasons.
- Test invocation counts, repeated versus distinct cases where relevant, skipped checks, and the reason for each material rerun.
- Remaining limitations, blockers, unresolved effects, and deployment/recovery instructions when deployment is in scope.

Keep credentials and private connection maps out of published evidence. Use the existing result contract and a single committed evidence/summary.json; keep raw logs, searches, test ledgers and review details in runs/<task-id>/evidence/ under the compact evidence procedure in shared/skills/submit-result/SKILL.md; this workflow does not add unversioned schema fields. A missing actual execution result cannot be replaced by a static review, a generated success label, or a fixture result.

## 4. Independent review and repair

Every review and re-review assignment includes this instruction:

> Treat the candidate as another AI's work and perform adversarial verification. Do not trust the author's completion claim; inspect actual changes and evidence. Examine relevant counterexamples, boundaries, errors, and regressions. Separate confirmed defects from unverified suspicions and do not manufacture findings. Give each finding a stable ID, location, reproduction or concrete evidence, impact, and re-verification criterion.

The evaluator must not author the principal candidate or redelegate its evaluation. It inspects the exact candidate, acceptance criteria, and relevant actual evidence. For an actual execution or deployment claim, require evidence of the applicable real environment path. Static or local tests may support preparation readiness but cannot certify that unexecuted deployment or isolation works.

Independent review does not mean blindly rerunning every author test. Reproduce only important claims whose evidence, reliability, or coverage needs independent confirmation, and satisfy any existing mandatory checks. State which findings came from source inspection, author evidence, and independent execution.

One narrow review is the default for light changes, not a limit that permits unresolved required defects. Return material defects to the same owner with the affected criterion and a concrete finding. The owner performs analysis, correction, and affected retesting, then supplies the changed evidence for focused re-review. Retain unaffected findings. Status wording alone does not restart full review; changes to factual claims, evidence, acceptance criteria, or meaning require review of those affected parts. Reused evidence must still match the relevant version, inputs, environment, and scope. Record the reason when new changes, failures, concrete concerns, environment differences, or mandatory gates require reruns. Do not create a new specialist or restart the entire review for each defect.

Final review follows the owner's evidence-ready handoff. A narrowly scoped early review is appropriate when a material design, authority, or safety uncertainty must be resolved before a consequential test; it is not a mandatory review of every command or temporary script. Missing evidence can produce an inconclusive review rather than a fabricated approval.

## 5. Orchestrator integration and final deployment

The orchestrator receives the reviewed candidate and evidence, confirms that required criteria and authorization match the intended final action, and integrates the user-facing result. It does not become the default implementation, diagnostic, or retest relay between specialists.

For authorized deployment, use the exact reviewed candidate and agreed target, perform the planned deployment readback/health checks, and preserve recovery information. Do not rerun the entire development suite solely because the artifact reached the orchestrator. A deployment failure returns to the same owner for diagnosis and correction; the orchestrator records the applied state and coordinates recovery without making unreviewed source fixes. The specialist can perform planned post-deployment tests within the same assignment and existing permissions.

An adoption review ends in a supported recommendation and evidence. Actual adoption or production deployment requires authorization covering that action; a review request alone does not provide it. Reuse authorization already granted for the exact scope and do not ask for it again unnecessarily.

Follow the existing validate/submit/checkpoint/finish lifecycle. Configuration activation, behavioral validation, live deployment, and publication are separate claims. Mark incomplete work honestly and never publish it as completed merely to end a long task.

## Delegation and ownership continuity

Main-session delegation follows the risk tiers and explanation exception defined by AGENTS.md. Do not automatically add investigation, design, or management roles to light work; reuse suitable owners, and skip a new planning call when the findings do not change the plan. A child may create another agent only with explicit parent authorization for a bounded subtask; further descendants do not inherit unlimited delegation permission. Evaluators cannot delegate their own evaluation. Use the host's actual available concurrency limit rather than a hard-coded slot count.

An authorized child contribution does not transfer the accountable owner's testing and repair responsibility. Replace an owner only for a concrete reason such as unavailability, a genuine scope change, or a user request, with a recorded handoff of candidate, evidence, unresolved items, and responsibility. Tool availability and role declarations never create new execution permissions.

## Compatibility

Version 1.3.0 applies by default to tasks started after this instruction revision. Workspace allocation is also available for an existing active task without changing its enrollment or snapshot. Existing in-progress acceptance criteria, task enrollment, historical reports, and frozen snapshots retain their original meaning; do not automatically migrate them. This procedure change follows its pre-change controls rather than exempting itself as light work. Module and skill versions/pins and affected generated adapters are maintained together; module IDs, permissions, runtime gate configuration, and result schema 1.0.0 remain unchanged. Ordinary explanation needs no artifact initialization. Actual changes still use the current init/validate/submit/checkpoint/finish lifecycle, including short records in existing fields for light changes. The optional ordinary-prose-v1 capability is captured only for new tasks from committed baseline configuration; legacy enrollments retain their full suites. Independent profile approval binds the exact candidate, impact rationale and evidence. Reuse that substantive review when sealing the executed checks and final result; do not demand a duplicate audit without changed inputs. Stale selection requires re-review or irreversible full promotion. Full promotion preserves original suites and permits reviewed profile-configuration maintenance without rewriting enrollment. Changes to gate/profile behavior still require high-risk handling. These instructions do not implement host-enforced routing or prove future agent behavior or deployment success.
