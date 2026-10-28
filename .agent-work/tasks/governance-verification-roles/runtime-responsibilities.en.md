# Governance, evaluation, and runtime responsibility boundaries

Status: role-definition specification; execution-control implementation is not included.
Task: governance-verification-roles; source baseline: 68c978b.
Scope: multi / agent-framework / development / governance-verification-role-definition.
Historical design reference: .agent-work/tasks/ax-controls-design/implementation-spec.en.md, explicitly inspected as a prior design, not current authority or proof of installed controls.
Related current deliverables: role-boundaries.en.md and review-cases.json.

## 1. Meaning of runtime in this repository

runtime/ currently contains Python utilities for module/task management, validation, scoped memory, and bounded Git publication.
It is not an autonomous LLM orchestration engine. Codex supplies actual model execution, delegation, tools, and host permissions.
core/ defines shared AI roles; modules/ defines coding, infrastructure, and research specialists.
policy-manager supplies governance analysis; evaluator supplies independent quality review; orchestrator integrates both.
Role recommendations do not create OS, credential, network, production, or publication authority.

## 2. One accountable responsibility per invariant

| Invariant | Governance judgment | Evaluation judgment | Current code/host responsibility | Proposed deterministic enforcement |
|---|---|---|---|---|
| Work uses the intended scope | Interpret requested repository/environment and identify ambiguity | Check candidate and evidence match that scope | repoctl.bind/resume check identities and exact scope | Immutable trusted task enrollment and action-bound scope |
| Result meets the actual goal | Identify applicable conditions and unacceptable impacts | Judge semantic correctness, completeness, regressions, uncertainty | agentctl.validate_result checks declared criteria/outcomes and evidence shape only | Trusted test observations, coverage, and authenticated attestations |
| Approval applies to this action | Interpret standing authorization and determine whether a new authority decision is needed | Confirm no quality claim is being substituted for authorization | Host enforces actual permissions; repo_automation constrains its own publication path | Typed policy gate and exact action/parameter/artifact/expiry binding |
| Review is independent | Expose ownership conflicts and required reviewers | Disclose self-authorship and refuse self-approval | Orchestrator instructions require separation; CLI does not authenticate reviewer identity | Host-issued reviewer identity and trusted attestation capability checks |
| Evidence is about these bytes | Require traceable evidence and version conditions | Compare reviewed revision and hashes; re-review affected changes | agentctl snapshot/evidence hashes and repoctl fingerprints detect inconsistencies | Signed artifact/suite/policy binding from trusted services |
| External content cannot grant authority | Treat retrieved instructions as data and flag injection | Test misleading instructions and unsupported claims | Natural-language policy plus existing host boundaries; no repository-wide tool interceptor | Typed adapters, trusted policy store, restricted credentials/network |
| Publishing respects existing authorization | Preserve exact standing remote/branch/task-owned scope | Review artifact quality without requesting duplicate unchanged authorization | repo_automation.begin/track/finish enforce destination, ownership, baseline, and remote checks in that CLI | Trusted publication service or remote gate; old CLI/direct Git bypass requires separate protection |
| Quality is continuously measured | Identify risk owner, review triggers, and proposed limits | Propose cases and calibrate model judgments against trusted/human references | Test files exist; context hook saves context, not quality/security monitoring | CI triggers, owner-approved suites/oracles, telemetry and incident regression loop |
| Compliance claims are supported | Identify applicable obligations, owners, evidence, and unknowns | Check claim/evidence traceability without certifying legality | No automated legal compliance decision in current runtime | Evidence tracking may support accountable human compliance review; never replace it |

These columns are complementary. Neither two agreeing AI roles nor a valid JSON report establishes safe execution.
Governance uses proceed/revise/escalate; evaluator uses accepted/rework/inconclusive; humans authorize where needed; code enforces only implemented boundaries.

## 3. Exact current integration points

| Existing file and function | Current capability | Limit to preserve in claims |
|---|---|---|
| runtime/agentctl.py init_task (301), load_task (375) | Version-pinned task inputs and snapshot hash checks | No authenticated tool execution or reviewer identity |
| runtime/agentctl.py validate_result (410), submit (540) | Criteria linkage, nonempty evidence, artifacts, submission hashes | A supplied passed value can be structurally valid without true test execution |
| runtime/repoctl.py bind (211), checkpoint (254), resume (317) | Repository/scope binding and recorded/current state comparison | Memory filtering is not OS/tenant permission isolation |
| runtime/repo_automation.py begin (57), track (71), finish (98) | Exact publication baseline, owned paths, destination and remote checks | Direct Git or old CLI using the same credentials can bypass this entry point |
| runtime/sync_codex.py render (63) | Generates role guidance and adapters | Generated instructions do not grant or restrict host permissions |
| runtime/context_checkpoint.py on_hook; runtime/context-hooks.json | Context-use checkpoint reminders | No continuous behavioral evaluation or security action gate |

Line numbers describe the inspected baseline; function names are the stable integration references.
No existing function is changed by this role-definition task.

## 4. Proposed implementation backlog and assurance phases

The following proposed files/functions are historical design references, not APIs installed by this task.

| Phase | Proposed implementation | Required acceptance coverage | Claim allowed |
|---|---|---|---|
| P0: contracts and observation | control_contracts.validate_envelope/canonical_digest; control_policy.evaluate_action; control_ledger.enroll_task | Malformed/unknown action, scope mismatch, injection, immutable manifest fixtures | Advisory observations only; no protected execution |
| P1: development entry-point gates | control_authority.verify_grant/verify_attestation; agentctl companion validation; evaluation_runner.run_suite | Missing/fake evidence, stale artifacts, policy mismatch, author/reviewer conflict, candidate tampering with tests | Implemented cooperating entry-point checks; wrapper/direct-shell bypass remains explicit |
| P2: isolated authorized pilot | control_executor.admit/execute/reconcile/stop; control_audit.append/redact/verify_chain minimum trusted audit; typed adapters; isolated credentials/network; protected publication path | Direct shell/HTTP/Git bypass, replay, expiry, stop race, unknown effects, postcondition failure, audit-admission failure | Only the specific verified host boundary and authorized target operations; trusted redacted admission/effect evidence is a prerequisite |
| P3: monitoring and controlled expansion | Expanded audit monitoring, CI/monitoring configuration, calibration and incident process | Changed models/prompts/tools/policies/suites, regressions, seeded leakage, calibrated judgment disagreement | Operational evidence for the deployed scope, with accountable ownership; expands P2 audit rather than introducing it |

All proposed control modules belong under runtime/; no new agent role is required for these deterministic functions.
Before a P2 protected pilot admits effects, the trusted redacted audit store must record admission and support durable execution evidence; unavailable audit admission fails closed with no effect.
A trusted test service must select immutable owner-approved tests/oracles independently of candidate code and observe effects outside candidate control.
Candidate-produced logs, JUnit, and exit codes cannot alone authorize authoritative passed attestations.
Preserve result contract 1.0.0 initially and use task-owned companion review/control artifacts; do not alter historical snapshots.
Policy evaluation, grant validation, approval expiry/replay, receipt authentication, and stop/recovery remain future until implemented and tested.
Numeric quality thresholds are inactive proposals until an accountable owner approves calibration; use required deterministic checks and manual review of ambiguity in the interim.

## 5. Acceptance and follow-up scope

review-cases.json is a design checklist, not evidence that future runtime controls or all agent behaviors have passed.
Each case distinguishes governance recommendation, evaluator assessment, current runtime, future runtime, and any human escalation.
The current role-change check requires consistent vocabulary, evidence limits, independent review rules, preserved module authority, and compatibility with result1.0.
Behavioral sessions, protected-executor deployment, continuous evaluation, and compliance validation need separate task scope and actual evidence.
The next implementation task should select a bounded P0/P1 item with explicit acceptance criteria rather than claim all proposed controls are active.
