# P1 cooperating submission and publication gates

Task: p1-submit-publish.
Repository/scope: multi / multi / agent-framework / development / p1-submission-publication-gates.

## Objective and assurance boundary

Connect enforceable checks to the current agentctl submission and repoctl publication paths. New selected tasks must supply candidate-bound test execution evidence and an independent declared evaluator assessment before completed submission. Publication must compare the real commit against the sealed submission and exact standing destination authorization before push.

This is a cooperating local CLI control. The same user can modify local files, use older tools, or invoke Git directly. Local enrollment, process execution records and declared reviewer identities are not protected trust roots, signatures, authenticated agents, a sandbox, or regulatory certification. The distributed executor and protected remote/service boundary in the earlier design remain later work.

## Compatibility and selection

Keep result.schema.json 1.0.0 and historical snapshots/results unchanged. Select new bound tasks in multi / agent-framework / development with a separate versioned gate configuration. Pin exact issue from each binding; never reuse another task's issue. Existing tasks remain explicitly legacy, including this implementation task initialized before gate deployment. Do not retrofit enrollment or relax a started task to finish it.

## Candidate and evidence

Bind reviewed content to the exact owned paths, Git-normalized content and mode, scope, baseline, policy and gate implementation. Test execution must capture the actual bounded child result and evidence bytes with candidate checks before and after execution. Review must bind the same candidate and test evidence; author/reviewer declared identities must differ. Missing, changed, contradictory or failing evidence cannot become a completed gate.

Generated task reporting data must have a narrowly enumerated derivation and a submission seal, avoiding a self-referential report digest. Arbitrary source files or user artifacts cannot be excluded as reporting data. P0's short observation TTL is separate from candidate-based P1 validity; P0 advisory allow or accepted-denial must not be reused as P1 permission.

## Lifecycle and recovery

Enroll at new task binding after the publication baseline exists. Compliant task loading detects deletion or inconsistency of enrolled controls. Validate and submit check evidence before successful completed submission. Failed or partial task reporting remains possible without permitting completed publication.

Immediately before push, compare the real commit's tree, exact changed paths, parent, selected destination, submitted result and bound evidence. Preserve existing non-force publication and remote readback checks. Failure after commit preserves that pending commit for a matching retry; do not create a duplicate completion commit or silently replace reviewed content.

## Verification and application

Exercise positive and negative cases: missing tests/review, failed execution, candidate and evidence tampering, declared identity conflict, scope/policy/destination drift, missing/downgraded enrollment, generated-record boundaries, legacy compatibility and retry. Run regression tests and an independent evaluator review against final source hashes.

Publish the implementation task first to avoid concurrent shared-index ownership. Then initialize a separate real selected activation task, demonstrate rejection before required evidence, execute configured tests, have an independent evaluator record its own assessment, submit through the gate and publish through the actual commit check. Save bounded specifications and evidence for both tasks. Completion of installation alone is not claimed as successful end-to-end gate use.

## Ownership

- p1_engine: gate engine and engine tests.
- p1_integration: lifecycle entry points and integration tests.
- p1_governance: advisory requirements and governance evidence.
- independent evaluator: review and affected rechecks; no principal implementation authorship.
- main orchestrator: scope, configuration, documentation, evidence integration, results and bounded publication.
