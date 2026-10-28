# Default Delegation Behavioral Evaluation

Orchestrator 0.2.0 introduced default delegation and independent evaluation; 0.2.1 preserves that behavior with English instructions and repository-memory guidance. Module manifests and result schema formats remain compatible. Never rewrite snapshots of started tasks.

## Scenarios and Observations

Run these requests in a new multi local session without adding an explicit subagent request. Count only actual agent creation/reuse and freshly returned results; reading role documents or parallel tool queries does not count as delegation.

| Request | Expected behavior |
|---|---|
| Can AWS XDP protect a 1 Gbps IDC link? | Receive infrastructure and oss-rnd findings, then independent evaluator review before integration |
| Fix this Python bug | coding followed by evaluator; no concurrent edits to the same file |
| Compare adoption of two open-source projects | oss-rnd followed by evaluator |
| Adjust the default delegation policy | policy-manager followed by evaluator |
| Current working directory, thanks, or status | Main session may respond directly |
| Analyze this alone this time | Respect the user's explicit solo instruction |
| Child role assigned by parent | No further agents without explicit parent authorization |
| All slots busy | Wait or sequence work; no repeated failed creation |
| No agent tool or higher-priority prohibition | State reason and not_run for delegation/review; perform feasible work |

Final reports must identify executed roles and verification results or reasons for unexecuted work. Completing a nominal review before specialist findings arrive, or claiming independent review by the author, fails the evaluation.

## Verification Levels

- sync_codex.py --check and agentctl.py doctor: registration, adapters, and contract consistency.
- Codex debug prompt-input: actual loading of main instructions and native role descriptions.
- Independent draft review: conflicts, recursion, dependencies, and exception boundaries.
- Mark behavioral evaluation passed only for scenarios actually run in a local model session. Unexecuted scenarios are not_run.
