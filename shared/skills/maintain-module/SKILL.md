---
name: maintain-module
description: Add or revise modules, shared skills, policies, or result contracts in this modular agent workspace, and check compatibility before registration.
---

# Maintain Modules, Skills, and Policies

Inspect registry.json for overlapping roles and source assets. Place new roles in core/<id>/ or modules/<id>/ with module.json and instructions.md. The common contract is shared/schemas/module.schema.json.

- Use lowercase hyphenated IDs and three-component numeric versions. Start with experimental lifecycle.
- Declare input fields, result contract, activation conditions, requested tools, and work scope precisely. Pin dependencies by exact module ID and version.
- Put reusable skills in shared/skills/ and module-specific assets inside their module. Manage skill versions in skills.json. Keep one source of truth.
- Run meaningful evaluations and regression checks for the change. Structural validity alone does not justify stable status. Apply evals/module-evaluation.md.
- Register new modules with `python runtime/agentctl.py register modules/<id>/module.json`, then run doctor. Registration does not grant access to external services.
- After source changes, run `python runtime/sync_codex.py --write` and `--check` to refresh Codex adapters. If manual edits are detected, review and merge differences against the source.
- Never modify an existing task snapshot. Explain compatibility and handling of earlier versions when changing public contracts.
- Write agent-facing source instructions in English and user-facing reports in Korean.

Submit the final result through submit-result.
