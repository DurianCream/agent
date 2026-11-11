# Infrastructure

Work on IaC, cloud, runtime, deployment and operations foundations. Current repository authorization and host controls govern each target and effect.

## Change procedure

1. Preflight. Identify the exact environment and owner, service, approved effects, current configuration/version, baseline health and an independent recovery route. Record facts with aliases only. Reconcile the requested operation with the actual authorization.
2. Impact. Read-only inspection is low risk only when it has no meaningful side effect and protected output is controlled. Treat configuration changes as at least normal risk and assess dependencies, blast radius and rollback. Deletion, migration, credentials, permissions, production application or changes that can lock out operators require high-risk handling.
3. Apply. Use the reviewed candidate and the authorized maintenance window. A successful plan establishes planning only. Without authorization for the specific production effect, stop before applying; provide the plan, read-only findings and outstanding decision. Preserve a known-good recovery artifact in authorized storage; exclude passwords and keys from files.
4. Verify. After an actual change, check service health, a representative client path, authorized authentication continuity, monitoring and expected logs against the baseline. Report plan, apply, post-apply health and rollback separately with observed evidence or not_run. Send missing execution evidence to the accountable owner. Independent review uses read-only evidence and does not repeat apply.
5. Rollback. Name the trigger, accountable person, known-good configuration/version, access method and recovery checks before apply. If the change fails, preserve sanitized failure evidence and restore via the authorized recovery path. Verify baseline service and access before reporting recovery.

Before changing routing, firewall, SSH, VPN or authentication on the operator's own access path, verify a separate authorized management session or console and a tested restoration route. Keep the current session open while a second session verifies reconnect. Defer a lockout-prone change when recovery access is unavailable. Never disable the only management route to test recovery.

Minimize tool output at the source. Never echo or persist passwords, private keys, tokens, raw configuration exports or connection maps in logs, files, prompts or reports. Use an existing host-provided secret handle only within authorized operations. If output contains a secret, omit the value, retain only relevant nonsensitive fields, identify possible exposure without repeating it, and route any required response to the owner through the approved channel.

Use modules/infrastructure/runbook.ko.md for a change plan. Commit only the inventory schema and pseudonymous example as inventory data. Keep real host, IP and account mappings in the ignored local inventory; passwords and keys belong in no inventory or artifact. This procedure does not enroll production in P0/P1. For a concrete isolated OS test, read modules/infrastructure/p2-test-environment.md; P2 is frozen and requires an explicit reviewed resumption.

Follow the shared role requirements in AGENTS.md.
