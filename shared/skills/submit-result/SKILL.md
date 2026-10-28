---
name: submit-result
description: Produce and submit the common seven-section result for artifact-producing tasks in this workspace, including coding, infrastructure, research, and management work.
---

# Submit the Common Result

Use runtime/agentctl.py at the repository root. Ordinary conversation does not require an execution record.

1. Start with `python runtime/agentctl.py init --module <registered-id> --task <task-id> --objective <objective> --criterion <acceptance-criterion>`. Repeat --criterion as needed. Add --repo <repo-id> for a registered target repository. To continue existing work, inspect task.json instead of creating a replacement task.
2. Run `transition <task-id> running`. Store actual artifacts in outputs/<task-id>/ and verification logs in runs/<task-id>/evidence/.
3. Populate the fixed fields in runs/<task-id>/result.json. artifacts.path and verification.evidence are repository-root-relative. artifacts.sha256 may be null initially; submit computes it. Write user-facing narrative in Korean; schema keys remain unchanged.
4. Link real verification IDs in acceptance_criteria.verification_ids. Passed/failed checks require readable evidence files. Record unexecuted checks as not_run, and non-applicable checks as not_applicable with a reason. Never mark completed without proving every required criterion.
5. Run `validate <task-id>` and then `submit <task-id>`. Generate result.md from result.json; do not manually edit the report. Record post-submission changes under a new task ID. Repository-bound submission also refreshes the durable work record; checkpoint meaningful progress before handoff or interruption.
6. For a repository with enabled .agent-work/automation.json, automatically run `python runtime/repoctl.py finish --task <task-id>` after a completed submission. The main agent must already have captured the baseline and registered its exact task-owned paths with begin/track. Saving a report alone is not completion of the publication workflow. Preserve and report any commit/push failure; never force-push or include unrelated changes. A user request to skip publication overrides this default.
7. Final chat replies must retain seven ordered sections: basic information; objective and acceptance criteria; result summary; work performed; artifacts; verification results; unresolved issues and next actions. Use the result generator's Korean labels and Korean narrative. Be concise without omitting sections. State when an item is not applicable, unverified, or unexecuted.

Schema and policy sources are shared/schemas/result.schema.json and shared/policies/common.json. Existing tasks use their frozen versions under runs/<task-id>/snapshot/files/. Structural checks do not establish the truth of evidence.
