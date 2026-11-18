# Modular Agent Working Rules

Higher-priority instructions, explicit user requests and host permissions govern. Manifests do not grant access. Use the existing authorization and honor stops.

Every main or delegated role reads shared/workflows/owner-led-delivery.md before planning or execution. Main owns routing, scope and acceptance criteria. Answer simple read-only questions directly. Classify substantive work by impact, uncertainty and recoverability. For actual changes use one accountable specialist and independent adversarial evaluation, repair and affected re-review. Announce assignments and report actual execution or reason and not_run. Children may delegate only with explicit parent authorization; evaluators never delegate.

## Shared role requirements

When several agents work on one task at once, allocate a workspace per agent as described in shared/workflows/owner-led-delivery.md section 1. Reuse an instance's assignment for follow-ups.

Read registry.json, the selected module.json and the unconditional entry of instructions.md. Read a role's conditional appendix only for its named trigger. For section references below, read only the named section. Load only relevant policies and skills. Work in authorized workspaces. Place temporary files in the allocated workspace or work/ and evidence in runs/<task-id>/. Agent instructions, specifications and recovery notes use English; user-facing reports and explanations use Korean. Report only verified results. Host capabilities govern real agent creation and enforcement. This repository holds framework material only: instructions, skills, policies and runtime.

Deliverable location:
- Infrastructure and research deliverables (runbooks, verification and adoption reports): bind the task to the registered infra-docs repository, write each deliverable there as a tracked file under docs/<topic>/ and register it with repoctl track. Do not also copy it to outputs/<task-id>/; leave result.json artifacts empty and name the docs/ path in work and verification. This overrides "artifacts in outputs/<task-id>/" in shared/skills/submit-result/SKILL.md and "submit the report as an artifact" in modules/oss-rnd/instructions.md for such work.
- Runbooks, guides and feature or verification documents in infra-docs follow shared/templates/reference-doc.ko.md: a reusable reference, not a task report. Keep dates, actors, task narrative and test-result tables in the task records; the document carries only a short verification-scope section. Adoption decisions keep modules/oss-rnd/adoption-report.ko.md. The evaluator checks template conformance as part of the review.
- Framework work in this repository: deliverables go in outputs/<task-id>/ as before.

## Apply these references at their trigger

- On each new chat or issue, identify the repository, then run repoctl startup. Read shared/workflows/harness-delivery.md#memory for exact project/service/environment/issue selection or resume. Load history only with the complete matching scope; ambiguous scope needs clarification.
- For delegated, artifact, module or adapter changes, read the applicable section in shared/workflows/harness-delivery.md#delivery. Use shared/skills/submit-result/SKILL.md for artifacts. Preserve frozen snapshots and task enrollment.
- Before edits and at meaningful progress, follow shared/workflows/harness-delivery.md#publication for bound init, exact ownership and checkpoint. Before final delivery apply its validate, submit and finish rules for the enrolled repository, honoring explicit user publication exceptions. Close incomplete tasks through its closing procedure. Ordinary conversation needs no artifact or empty commit.
- When a fresh PostToolUse context reading exceeds 80%, follow shared/workflows/harness-delivery.md#context-checkpoints. For legacy classification or import use shared/workflows/harness-delivery.md#legacy.
- Use selected roles' linked procedures for publication checks or host-test conditions.

See README.md for Korean usage guidance.
