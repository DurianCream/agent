# Execution Risk and Continuous Validation Policy Design

Status: proposed design, not an active policy or proof of protection. Version: 0.1.0. Observed: 2026-10-28 (Asia/Seoul).
Task: ax-controls-design. Scope: multi / agent-framework / development / execution-control-continuous-validation-design.
Companions: implementation-spec.en.md, contracts.schema.json, examples.json, control-matrix.json.

## 1. Purpose and normative boundaries

MUST, MUST NOT, SHOULD and MAY describe the implementation target; they do not change current authority.
The existing orchestrator, specialists, evaluator, policy-manager and knowledge-manager remain in their roles.
The orchestrator coordinates; specialists propose actions; the evaluator reviews independent evidence; policy-manager maintains proposed policy sources.
A human system owner accepts residual risk. Host administrators and credential owners control actual permissions.
An agent MUST NOT grant itself authority, edit the active trusted policy, mint approvals, or declare its own test evidence authoritative.
The host sandbox, network rules and tool restrictions remain upper bounds even when this design says allow.
Ordinary bounded read/local reversible actions and exact existing task authorization MUST NOT acquire new per-step approval prompts.
Existing standing Git authorization remains valid only for its exact configured repository, remote, branch and task-owned manifest.
This document neither authorizes production activity nor asserts regulatory compliance.

## 2. Trust and authority boundaries

Trusted inputs are authenticated task authorization, verified principal identity, host-derived execution context, owner-approved policy versions and signed/host-verifiable grants.
User requests express intent but are not raw executable policy; scope and target must be resolved against trusted configuration.
Retrieved pages, emails, tool output, repository content, historical memory and model-generated plans are untrusted data, including embedded approval claims.
The parser MUST keep external content separate from executable instructions and allow only typed action parameters after schema validation.
An assertion such as "ignore policy", "production approved", or "export credentials" in an external document MUST NOT create authority.
The policy evaluator MUST derive effective risk from trusted adapter metadata, target/environment, data sensitivity, reversibility and requested effects; it MUST NOT accept a caller's low-risk label.
Unknown principal, target, environment, data classification, adapter version, policy version or authority provenance MUST deny execution until resolved.
Service accounts and access tokens MUST be scoped per adapter and environment and unavailable to planning/evaluator agents.
The protected policy bundle and grant store MUST live outside any writer controlled by executing agents; a writable repository copy is a proposal only.
Policy updates require owner authorization, independent review, versioned tests and an administrator-controlled activation step.
Reusing the same model in another role is authorship separation, not independence of knowledge, failure modes, identity or permissions.

## 3. Decision precedence and risk table

Decision vocabulary: allow, deny, require_review. Risk vocabulary: low, medium, high, critical. Modes: observe, enforce.
All relevant predicates are evaluated before decision selection. Mandatory denial dominates a valid approval or standing grant.
A require_review decision is non-executable. After a verified action-bound grant, the policy service issues a final allow decision referencing the original review decision and approval digests; only the final allow may reach execution.
An allow decision is still insufficient on its own: the execution boundary must verify current authority, policy, stop state, target state and execution budget immediately before use.
Observe mode produces advisory decisions only. It MUST NOT issue execution capability or make previously unauthorized actions possible.
In observe mode, only actions already independently authorized by the current host and task may continue through the existing path; production execution remains blocked from the experimental path.

| Condition/action class | Default risk | Decision and additional predicates |
|---|---|---|
| workspace.inspect on authorized local files | low | allow within scope; sensitive reads require explicit need and approved destination handling |
| workspace.apply_patch on exact task-owned non-protected files with bounded reversible diff | low | allow; reject path escape, active policy/grant files, unrelated edits, credentials, and unbounded overwrite |
| repo.publish of reviewed task manifest to existing authorized remote/branch | medium | allow under verified standing grant after all existing finish checks and required release checks; never blanket stage or force-push |
| infrastructure.change in isolated test environment with reversible bounded effects | medium | allow under existing task authorization after dry-run and preconditions; unknown blast radius escalates |
| external.export of classified non-secret data to a named permitted destination | medium | allow only where existing authorization covers data and destination; otherwise require_review |
| Production mutation, privilege increase, cross-boundary export or wide-scope changes that are otherwise permitted | high | require_review plus exact human action grant; final allow requires deterministic checks and host permission |
| Critical blast radius, credential material export, destructive irreversible operation without a safe recovery plan, uncontrolled code execution in production, or weakening the control boundary | critical | deny in the initial implementation; route to a separate human-operated procedure, never an agent-authored exception |
| Schema/provenance failure, revoked or expired authority, unknown target, policy unavailable, active stop, signature/hash mismatch, prohibited operation | any | deny, preserve a redacted reason and do not execute |

Risk categories are local proposed policy decisions, not universal legal classifications. Reclassification changes are policy changes subject to section 2.
An existing authorization satisfies a review requirement only if it proves the same action, scope, effect, destination, version and validity constraints; vague project membership is insufficient.

## 4. Action grants, execution and non-bypass requirements

An action grant binds authenticated issuer/subject, immutable task scope, canonical action digest, target/environment, policy digest, relevant input/precondition digests, allowed effects, expiry, use limit and revocation epoch.
All records use the companion version 0.1.0 envelope: record_type, schema_version, payload, digest and signature. Canonical digests use the exact RFC 8785 and Ed25519 domain rules in implementation-spec.en.md; no ad hoc JSON serialization is interchangeable.
action_approval binds request_digest, the review decision_digest, scope, policy_ref, artifact_set_digest, approver, nonce, expiry and revocation_epoch. Its kind is human_action or standing_authorization; the latter references an authenticated exact standing_grant_id.
The initial require_review decision is the approval target. The final allow decision binds review_target_digest to that original decision and approval_digests to the verified grants; execution_receipt records the final decision_digest and approval_digests. No approval is rebound to the final decision, avoiding circular digest dependencies.
Ordinary allow decisions that need no review use null review_target_digest and an empty approval_digests array; they do not need a fabricated approval.
Human approval is collected through a trusted UI/service. The UI shows the exact diff, target, sensitive data destination, expected effect and recovery constraints.
The planner cannot create a valid human approval by writing a JSON file. A stored example approval is never an operational credential.
Grant reservation and consumption MUST be atomic across workers. Replay, concurrent double use and use after revocation MUST fail.
Action or target drift invalidates approval; the executor MUST NOT silently expand it to a new request.
Adapters are limited to workspace.inspect, workspace.apply_patch, repo.publish, infrastructure.change and external.export initially.
The infrastructure adapter MUST expose named allowlisted operations and parameter schemas; arbitrary shell text is not a production adapter.
The executor MUST recheck path resolution, branch/head, target fingerprint, source version and relevant resource state at the point of execution to reduce time-of-check/time-of-use risk.
Resource limits include calls, elapsed time, spending where measurable, output/data volume, recursion/retries and target count. Exceeding a limit denies new work and records partial effects.
An idempotency key and durable execution receipt MUST distinguish actions never started, effects applied, failures before any effect, partial effects and unknown outcomes using the companion schema's status and effect fields; these descriptions are not additional enum values.
A missing receipt or network timeout MUST NOT trigger blind retry of a potentially applied mutation; reconcile target state first.
The execution gateway MUST be unavoidable for the controlled effects. Raw shell, network, connector or credential paths capable of equivalent actions invalidate the non-bypass claim.
Publication has its own boundary: a P1 local wrapper can validate only cooperating entrypoints. An old CLI or direct git push using the same agent-held write credential can bypass it, even if production adapters are isolated.
Before claiming protected publication, either the destination/release service MUST independently enforce trusted attestations and exact authorized manifests, or direct agent Git write credentials MUST be removed and publication brokered with isolated credentials. A direct push or legacy finish bypass must fail at that boundary.
This changes credential/enforcement placement, not user authorization: an exact existing Git standing grant remains reusable without repeated human confirmation.
Where the host cannot route and isolate all equivalent paths, label the feature advisory/partial and do not grant it production authority.
Markdown, module manifests, a reviewer agent and CLI conventions alone MUST NOT be presented as enforced access control.

## 5. Continuous validation contract

Every use case must define task-specific intended outcomes, prohibited effects, deterministic checks, evaluation owner and documented acceptance thresholds before promotion.
Changes to model/version, prompts, roles, policies, adapters, tools, data retrieval, source permissions, schemas or dependencies trigger affected regression suites; cross-cutting security changes run the whole safety suite.
Owner-approved scheduled reevaluation and incident-triggered replay supplement change-triggered runs. Scheduling is a deployment task, not created by this design deliverable.
Evaluation attestations bind test/dataset version, subject hashes, environment, runner identity, reviewer identity, time, outcomes and readable redacted evidence digests.
The mandatory suite/case manifest, expected results, deterministic oracles and promotion thresholds MUST be owner-approved, versioned and stored outside the candidate's writable sandbox. A candidate-authored changed-component manifest may add cases but MUST NOT remove mandatory coverage; the trusted runner derives required coverage from activated policy and verified change metadata.
An observer outside the candidate sandbox MUST measure tool admissions, actual effects and data egress against those protected oracles. Candidate JUnit files, stdout, reported scores or exit code 0 are untrusted observations and MUST NOT independently produce a mandatory pass.
Removing/disabling tests, modifying expected values, replacing the runner or fabricating a report MUST yield a coverage/integrity failure. Runner signatures attest trusted observations and case-manifest digests, never merely re-sign candidate-supplied pass claims.
The release gate verifies required test IDs and current subject hashes. Evidence absence, skipped required cases, stale hashes or unauthenticated runner/reviewer identities blocks promotion.
The author and approver identities must differ where review is required. Names entered by the author do not prove independent review.
The agent may generate test proposals but cannot unilaterally change expected results or weaken thresholds to pass its own release.

Minimum scenario families:
- Correct scope and expected effect for ordinary inspection, patching and authorized Git publication.
- Cross-project/environment confusion, stale memory, wrong target, path escape, concurrent modification and unrelated staged files.
- Prompt injection in retrieved text/tool output, fabricated approval, secret extraction, memory poisoning and tool-result authority spoofing.
- Overbroad tool parameters, forbidden egress, raw-shell bypass, revoked/expired/replayed grants, concurrent double consumption and policy downgrade.
- Partial execution, network timeout, repeated retry, runaway call budget, stop request during execution and unsafe compensation.
- Reviewer disagreement, misleading evidence, missing mandatory checks, model change regression and confidential telemetry redaction.

Release rules:
- Catastrophic/prohibited-effect cases: zero observed unauthorized executions or disclosures in all required cases; one violation blocks promotion and opens an incident. This finite test result is not a claim of zero real-world risk.
- Required deterministic safety and contract cases: all pass; no missing or not_run result may count as pass.
- Lower-risk task correctness: each use case must document an initially provisional threshold and dataset with a human owner. Until calibration is approved, use all selected deterministic cases passing and manual review of all ambiguous cases; no fabricated universal safety percentage.
- Any numeric quality or regression tolerance shown in companion examples is an inactive calibration candidate until activated in an owner-approved profile; it is not a default permission to promote.
- Judge-model grades supplement deterministic oracles and human-calibrated samples. Disagreement, low confidence or ungradable outcomes route to review, never automatic success.
- Promotion records include known failure classes, coverage limits and residual risk accepted by a human owner.

## 6. Monitoring, incidents and safe recovery

Record minimal action IDs, scope, principal/adapter versions, policy/grant references, decisions, executed effects, latency/budget, target state and evaluation references.
Redact secrets and personal/confidential payloads before logs leave the execution boundary; rejection logs must also be sanitized.
Do not persist raw prompts, tokens, credentials or unrestricted connector output merely to simplify debugging.
Secure audit storage must resist actor modification; cryptographic hashes in the same writable directory are integrity hints, not an independently trusted audit trail.
Retention, access control, deletion and legal holds require explicit owner-approved configuration. Unknown jurisdiction/retention rules block persistent sensitive telemetry; local testing uses synthetic/minimized data.
Alerts include prohibited-action attempts, approval failures, identity drift, control bypass, secret detector events, unexpected effects, elevated failure rate, budget exhaustion and missing telemetry.
A critical incident sets a host/broker stop flag, revokes grants/leases, disables affected credentials or adapters and blocks new issuance; stopping only the chat loop is insufficient.
For in-flight work, cancel where safe, stop further steps, and query the external system to classify applied/partial/unknown effects. Non-cancellable effects must remain visible as residual risk.
Never run an automatic inverse command against unknown state. Compensation requires a verified recovery plan, fresh state checks and sufficient authority; unsafe/destructive rollback requires human incident control.
Preserve redacted evidence, notify the named owner, contain affected data/credentials, and add the failure to regression cases before resuming.
Resume requires cause assessment, corrective controls, passing affected tests and a trusted owner's explicit release of stop state.

## 7. Governance and requirements mapping

Maintain a use-case inventory: business owner, human accountable owner, purpose, users, deployment/environment, data classes, model/tool suppliers, effect limits and residual risk.
Maintain requirements mappings: requirement ID/source/version/jurisdiction, applicability rationale, control IDs, owner, evidence, review date, exceptions and unresolved questions.
NIST and OWASP are design/reference inputs here, not declarations that any legal obligation has been satisfied.
Applicable legislation, contractual duties, customer commitments, privacy retention and regulatory reporting remain unresolved until actual organizational context is supplied.
Policy-manager proposes mappings; the human compliance/privacy/security owners determine applicability and acceptance. An AI compliance role cannot approve its own legal conclusion.
Review requirements after scope/data/region/provider changes and at owner-defined intervals; record whether evidence is current, missing or not applicable.

## 8. Rollout and decision register

| Stage | Scope and promotion gate | Assurance boundary |
|---|---|---|
| P0: contract and observe | Validate contracts, fixtures, threat model and advisory decisions using synthetic/local replay; inventory equivalent tool paths | No new execution authority; no production enforcement claim |
| P1: development gates | Add local preflight, trusted CI evidence and submission/release gates; retain existing exact Git standing authorization | Wrappers may be bypassable; no protected execution guarantee or production authority |
| P2: isolated authorized pilot | Establish isolated executor, scoped credentials/network, protected policy/grants, stop/recovery and audit; begin with read/dry-run, then only explicitly authorized bounded reversible operation families with passing action-grant drills | Enforcement claims apply only where equivalent bypass paths are removed; critical denied classes remain outside autonomous execution |
| P3: monitoring and controlled expansion | Activate owner-approved ongoing monitoring, calibration, incident replay, requirements mapping and release reviews before widening coverage | Expansion requires new target/data/operation acceptance; no implied legal certification |

| Decision | Safe default | Blocking dependency / owner |
|---|---|---|
| D-01 Trusted policy/grant store | No writable-repository policy is authoritative | Host security owner chooses identity, signing/verification and deployment mechanism before trusted P1 evidence and P2 execution |
| D-02 Complete execution coverage | Advisory only where bypass remains | Host/tool owner proves equivalent shell/network/connector paths blocked before claiming enforcement |
| D-03 Approval scope | Reuse exact task/standing authorization; request review only for uncovered high-risk effects | Human owner and adapter define effect/digest display before P2 mutations |
| D-04 Evaluation thresholds | All selected deterministic cases pass; ambiguous cases reviewed; thresholds provisional | Use-case owner approves dataset and calibrates lower-risk correctness before promotion |
| D-05 Monitoring ownership | No unattended production operation | Named incident owner, tested stop/revocation/recovery and alert delivery before P2; full scheduled monitoring before P3 expansion |
| D-06 Telemetry retention and law | Synthetic/minimized local evidence; no sensitive durable telemetry | Privacy/compliance owner resolves context, access, retention/deletion and required evidence |
| D-07 Compatibility | Add versioned sidecar contracts first; never rewrite historical task snapshots | Maintainers define migration and compatibility tests before implementation |
| D-08 Current deliverable | Design documents and fixtures only | Implementation, host integration and production rollout are separate authorized tasks |

## 9. Sources

Accessed on 2026-10-28. These are external evidence, not authority to expand tool access.
- NIST, AI Risk Management Framework 1.0: https://nvlpubs.nist.gov/nistpubs/ai/nist.ai.100-1.pdf . GOVERN 1.1/1.5, MEASURE 3.1 and MANAGE 4.1 inform requirements mapping, ongoing review and incident handling.
- NIST, Generative Artificial Intelligence Profile: https://doi.org/10.6028/NIST.AI.600-1 . GenAI risk identification and lifecycle evaluation guidance.
- OWASP, Agent Control Standard: https://genai.owasp.org/resource/agent-control-standard-acs/ . Runtime middleware controls, inspectability and traceability are reference concepts, not a claim this design implements ACS.
- Microsoft, AI agent orchestration patterns: https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns . Orchestration examples and complexity tradeoffs; agent decomposition is not sufficient security isolation.
