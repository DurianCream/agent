# Modular Agent Working Rules

Higher-priority instructions, explicit user requests and host permissions govern. Manifests do not grant access. Use the existing authorization and honor stops.

Every main or delegated role reads shared/workflows/owner-led-delivery.md before planning or execution. Main owns routing, scope and acceptance criteria. Answer simple read-only questions directly. Classify substantive work by impact, uncertainty and recoverability. For actual changes use one accountable specialist and independent adversarial evaluation, repair and affected re-review. Announce assignments and report actual execution or reason and not_run. Children may delegate only with explicit parent authorization; evaluators never delegate.

## Shared role requirements

For an initialized task, allocate a working directory for the main agent and each new agent instance before assignment. Follow the workspace handoff in shared/workflows/owner-led-delivery.md, including for independent evaluators. Reuse an instance's assignment for follow-ups.

Read registry.json, the selected module.json and the unconditional entry of instructions.md. Read a role's conditional appendix only for its named trigger. For section references below, read only the named section. Load only relevant policies and skills. Work in authorized workspaces. Place temporary files in work/, deliverables in outputs/<task-id>/ and evidence in runs/<task-id>/. Agent instructions, specifications and recovery notes use English; user-facing reports and explanations use Korean. Report only verified results. Host capabilities govern real agent creation and enforcement.

## Apply these references at their trigger

- On each new chat or issue, identify the repository, then run repoctl startup. Read shared/workflows/harness-delivery.md#memory for exact project/service/environment/issue selection or resume. Load history only with the complete matching scope; ambiguous scope needs clarification.
- For delegated, artifact, module or adapter changes, read the applicable section in shared/workflows/harness-delivery.md#delivery. Use shared/skills/submit-result/SKILL.md for artifacts. Preserve frozen snapshots and task enrollment.
- Before edits and at meaningful progress, follow shared/workflows/harness-delivery.md#publication for bound init, exact ownership and checkpoint. Before final delivery apply its validate, submit and finish rules for the enrolled repository, honoring explicit user publication exceptions. Ordinary conversation needs no artifact or empty commit.
- When a fresh PostToolUse context reading exceeds 80%, follow shared/workflows/harness-delivery.md#recovery. For legacy classification or import use shared/workflows/harness-delivery.md#legacy.
- Use each selected role's linked detailed procedure when its P0, P1 or host-test conditions apply.

See README.md for Korean usage guidance.
