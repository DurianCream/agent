# P1 publication representation repair

Task: p1-publication-repair.
Scope: multi / multi / agent-framework / development / p1-publication-representation-repair.
Baseline: 01fbaaf717add7ecffc7a8b8d331163d90e16f79.

## Observed failure

The initial implementation passed 297 regression cases and independent review. The first live selected task passed 52 mandatory cases and its independent assessment, then actual publication correctly stopped on a dependency mismatch. Its commit 7821707aec089ccc7ef54699c1553bacacfc1299 remains unpublished and preserved on codex/p1-activation-blocked in the original checkout. Its submitted result, enrollment, evidence and seals remain unchanged; the publication attempt is not relabelled successful.

Read-only inspection found all 82 dependency files still matched the reviewed raw SHA256. Historical CRLF blobs can be byte-identical to the tested working file while a fresh Git clean conversion produces a different object ID. Other files legitimately use LF Git blobs with CRLF checkout bytes. Neither global normalization setting handles both cases safely.

## Correction

For each regular committed dependency or task-owned product/archive with the expected mode/path, accept either the exact committed raw SHA256 matching the pinned tested raw SHA256, or the existing exact Git-canonical comparison. Preserve all scope, mode, type, ownership, candidate, result, reviewer, test, checkpoint and destination checks. A different content or mode must still fail. Do not change Git attributes/configuration to manufacture a passing decision.

## Recovery and application

Use an isolated checkout of the last published baseline, with the same repository identity and exact authorized origin/main. Initialize a new selected P1 task before edits. Implement the focused fix, test mixed representations and rejection cases, run the actual configured gate suite, obtain independent review and the evaluator's own assessment, then submit and publish through the repaired gate. This new task is itself the real selected application exercise.

Keep the original pending commit on its named branch. After the repair is published, verify the original checkout is clean and its HEAD is exactly the known task-owned pending commit. Preserve it, detach, update the local main reference to the verified remote commit and switch to main. Do not force-push, discard user edits, amend the failed task, relax enrollment, or manually push past a failed gate.

## Evidence boundary

Save bounded diagnosis, test summaries, independent review and actual gate test/review records. Postcommit gate and remote confirmation remain separate local receipts; do not recursively insert a publication receipt into its own commit. Local records and identities remain unauthenticated, with no direct-Git or OS isolation guarantee.
