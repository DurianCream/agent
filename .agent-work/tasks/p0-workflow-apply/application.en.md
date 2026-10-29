# P0 selected workflow application

Task: p0-workflow-apply.
Scope: multi / agent-framework / development / p0-workflow-application.
Baseline: 8d7e1ebf4a3a2cbd56449bd2438560a4258af84b.
This specification covers selected lifecycle observation and role handoff. The submitted result records verified implementation and deployment status.

## 1. Applied boundary

Keep P0 observe-only: no execution capability, signature authority, credential issuance or all-tool interceptor.
Select repository tasks through `.agent-work/observation.json` using repository/project/service/environment; copy the exact issue from the current binding, never from recent history.
No configuration preserves legacy behavior. Enabled but unavailable/malformed configuration must produce an explicit observation failure, not an implicit success.
Current selected scope is the local multi agent-framework development repository. Other services/environments are not silently enrolled.
The selected registered repository must be the same resolved checkout as the framework root. A different clone with the same UUID is rejected rather than observed through inherited local registration.

## 2. Automatic calls and timing

The standard-library integration launcher runs the fixed workflow worker using the project observer environment.
Bound checkpoints and ownership registration observe the declared owned workspace file set. Empty ownership is not-ready, not a fabricated fallback request.
The workspace operation is `workspace.inspect`: it checks a declared workset and fingerprints candidate content; it is not proof that a patch was safely executed.
Git publication observation uses an actual recorded commit after existing commit checks and before the already-authorized push. A future commit must never be invented to populate the request.
The publication observation is a separate record. It is not a release approval and cannot inherit a workspace assessment as commit authorization.
Publication content_basis is git-object-metadata: bind every actual changed/committed path, including managed records, to local Git blob mode/type/object ID/size or explicit deletion. Do not use current working bytes or index cleanliness as proof of committed content. This initial publication observer supports the configured HTTPS origin; unsupported transports are explicit not-ready states and do not change existing publication authorization.
Observation outcomes never override existing publication destination, baseline, ownership, non-force or host checks. P1 blocking gates are not implemented here.

## 3. Environment and failure handling

`.venv-controls` is a project-local ignored environment with exact `runtime/control-requirements.txt` versions. It is not committed or installed globally.
Provision it with `python -m venv --copies .venv-controls`; external interpreter symlinks are rejected. Python import isolation is not OS or credential isolation.
The launcher uses fixed arguments without a shell, strips Python path/home overrides and disables user-site contamination. Dependencies are not automatically downloaded during normal tasks.
Missing interpreter/dependencies, version mismatch, timeout, invalid output and failed invocation are explicit degraded/error states.
Child output is bounded and sanitized; raw exceptions, prompts, secret-bearing input and local machine maps are not published.
P0 can report a failed observation while an independently authorized existing lifecycle action follows its prior rules. Do not present that as a new blocking security gate.
Abrupt child termination can leave the task observations lock. `observation_locked` is explicit, no lock is automatically removed. Recovery requires verified process exit/OS PID absence, an exact guarded task lock path and unchanged lock content; remove only that stale lock, preserve all immutable records and retry. If liveness or PID reuse is uncertain, retain the lock. Never use Windows os.kill(pid,0) as a liveness probe.

## 4. Records, freshness and assessment

Use immutable observation records under the current task's run directory, with exact scope, policy/input/output references and a candidate fingerprint.
Never follow symlinks/junctions to fingerprint private aliases. Bound path counts/bytes and report incomplete input instead of truncating into a misleading allow.
Freshness includes the relevant observer/launcher/P0/schema sources, requirements manifest and declared interpreter/dependency identity. Stored request/context/output semantics are reconstructed and checked against the snapshot; this is consistency validation, not authentication.
Exclude observer records and managed task reporting data from their own workset fingerprint to avoid self-referential invalidation.
Reuse only a matching current record within the configured freshness interval. Changed content, target, scope, policy or stale age requires refreshed observation.
Invalid cached records stay visible until deliberate `observe --refresh`. Regeneration preserves old bytes and a bounded prior-ID/hash/validity trace, executes the normal current-input observation path, and never transfers previous assessments. Oversized/unsafe prior files must not be read without bounds or silently repaired.
Advancing HEAD to the same task's own commit must not alone invalidate an unchanged workspace candidate; commit-specific publication is tracked separately.
Mutable status pointers are not sealed evidence. Later observations and assessments must not overwrite a record already referenced by submitted evidence.

Governance advice is proceed/revise/escalate. Evaluator assessment is accepted/rework/inconclusive.
Assessments bind to the actual observation, snapshot/policy digests and exact scope. Reviewer identities are declared local labels, not authenticated service identities.
If governance is applicable, verify the linked governance assessment. If it is not required, record that disposition explicitly; do not fabricate a review or silently mark a required missing one complete.
An evaluator may accept a correctly handled deny/review-needed result. Reviewed does not mean executable or authorized.

## 5. Human/agent procedure

The host still runs agents. The lifecycle code produces observation records; orchestrator instructions route them to the appropriate agents.
The orchestrator checks real current status, supplies the actual record to governance when needed, then obtains independent verification and retains bounded evidence.
Policy-manager interprets the observation and records its own advisory assessment. It cannot create authority by approving its own policy or changing declared metadata.
Evaluator checks invocation evidence and current binding, declares missing/stale/failing evidence honestly, and records its own assessment.
Ordinary covered operations and exact Git standing authorization do not acquire repeated approval prompts.
Role guidance and demonstrated host execution are distinguished from deterministic all-agent compliance, which is not guaranteed by this feature.

## 6. Verification and compatibility

Test actual P0 calls and actual selected subprocess/lifecycle paths, not just mocked success strings.
Required cases include normal workset, exact standing publication, changed content/target/policy, unknown/mismatched scope, no manifest, dependency failure, timeout, invalid output, stale record, assessment mismatch/conflict, safe declared independence and immutable sealed evidence.
No-config/disabled/unselected repositories retain prior behavior and result1.0 compatibility.
Run existing regression modules in isolated processes with a writable task-local TEMP. Local Git fixture setup may need host permission distinct from network publication.
Exercise this repository's actual task through observation, a real governance agent assessment and an independent evaluator assessment; persist the bounded record references.
Preserve earlier submitted P0/role/design records byte-for-byte. Version role guidance and regenerate Codex profiles after source edits.

## 7. Completion and follow-up

Completion requires configured environment+selection, real lifecycle observations, linked role evidence, passing tests/review and a verified task-owned publication.
The final report must separately state which hooks are installed, which concrete paths ran and which assessments were performed; a file under outputs alone is not deployment evidence.
P1 can subsequently add explicit submission/publication gates, and P2 can add trusted identity/credential/network/executor boundaries. Do not relabel P0 observations as those stronger controls.
