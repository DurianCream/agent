# Lightweight submission profile design checkpoint

Scope: repo multi / project multi / service agent-framework / environment development / issue lightweight-submission-profile.
Task: lightweight-profile-20261105. Accountable design/implementation/test owner: light_profile_owner. High risk: execution and publication gate selection. Current task remains enrolled under unchanged full P1 policy. Parent owns final review, submission and publication.

## Minimal architecture

1. Keep `.agent-work/gates.json`, its 0.1.0 schema, existing snapshots/enrollments/seals and result schema untouched. Add `.agent-work/submission-profiles.json` version 0.1.0 as an optional future-enrollment capability. New enrollment captures the complete profile and its byte hash only when the file equals the committed baseline version. Old enrollment without this field remains full. Missing/mutated captured config fails closed.
2. Default every enrolled task to full required suites. Support only explicit exact allowlisted `docs/prose/*.txt` existing ordinary UTF-8 prose files, regular/nonexecutable, bounded size; no new/deleted files, instructions, executable content, configs, root README/AGENTS or control documents. Runtime checks are conservative necessary conditions, not proof of semantic safety.
3. `select-profile` accepts independent reviewer declaration, exact candidate digest, profile, low-impact rationale and evidence hashes. Reviewer attests actual diff is ordinary wording, no product/security/permission/process behavior. Neither author tier nor file suffix grants eligibility. Selection records are append-only and bound to task/scope/baseline/candidate. No automatic light selection.
4. Recheck baseline equality of control/runtime/instruction dependencies and profile config. Candidate policy changes cannot approve themselves. Any file-set/content/dependency mutation invalidates prior selection; submit fails closed until fresh review or explicit irreversible promotion to full. Promotion does not rewrite enrollment/history.
5. Light executes a fixed repository document-integrity unittest via existing runner, covering exact approved candidate, permitted paths, UTF-8/prose bounds, no executable mode/control changes and baseline profile. Reuse current test log hashing, actual positive test count and candidate-unchanged checks. Selection proof is bound into final proof set; normal/full suites unchanged.
6. Final independent adversarial review remains mandatory after executed checks; preserve full result fields, artifact/evidence hashes, replay/scope checks, generated records, exact commit content and destination/remote guards. Local reviewer identity remains declarative, not authenticated; no OS authority claims.
7. Publish activation file with empty allowlist initially or a bounded existing ordinary prose file; future allowlist changes require full review and only affect fresh tasks after publication. This high-risk task cannot activate light for itself.

## Verification plan

First exercise minimum normal-to-light path in a local Git fixture, then meaningful negative boundaries: no opt-in, author/self-review, missing semantic declaration, protected/mixed paths, content growth, stale selection, config/control changes, unknown version/deletion, promotion, legacy enrollment unchanged, review/test/evidence replay, executable/symlink, final exact commit mismatch. Actual subprocess CLI lifecycle: init -> record/track -> independent profile approval -> actual checker -> independent final review -> validate/submit -> local bare-remote finish and readback. Identify fixture identities as synthetic; independent agent review of this implementation is separate and real.

Run focused tests during implementation. Run current mandatory p1-regression suite once after final fixes, preserving unchanged evidence. Compare hashes of preexisting snapshot/enrollment/seal files before and after; never refresh them. Parent receives exact hashes, commands/counts/reasons, evidence and remaining limitations before final review. No claimed measured time/token savings.

## Early review request

Adversarially review selection/enrollment/activation boundaries before large implementation. Particular question: does optional immutable companion profile plus independent candidate-specific semantic attestation preserve fail-closed legacy semantics without modifying pinned gates configuration? Supported light scope is intentionally narrow; configuration and control-related documentation remain full.

## Concrete refinements before early review

- Activation includes one useful ordinary-prose `docs/prose/project-overview.txt` entry, created under this full-reviewed task. It is not eligible until the activation and file are committed; future allowlist edits likewise use full gates.
- Capability-bearing new controls use enrollment schema 0.2.0; old controls remain 0.1.0 byte-for-byte. Gate configuration, candidate/seal formats and result contract remain unchanged.
- Profile selection is stored as an append-only gate record with a task state pointer and mirrored state file; missing or mismatched state fails closed. Full promotion persists an irreversible state through supported CLI operations. No raw-JSON editing is part of the workflow.
- Reuse one substantive independent document review for semantic profile approval and final mechanical proof binding. The final review command binds the actual executed checks and final result; it is not a demand for a repeated full audit.
- The fixed light checker executes three cases: current selection and evidence integrity; document eligibility; unchanged control dependencies. Existing test runner captures real exit/log/count/candidate integrity. Focused implementation regressions are separate from that per-document checker.
- A successful local fixture CLI finish is evidence of local lifecycle mechanics only. It does not authenticate synthetic reviewer identities or certify external deployment. Actual independent evaluator review of this implementation is performed separately.
