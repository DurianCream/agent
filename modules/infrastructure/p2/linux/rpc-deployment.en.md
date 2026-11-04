# Protected P2 local RPC deployment and rollback

This extends the reviewed manual Linux pilot with automatic same-host requests. It does not enable cross-host RPC, external HTTPS/GitHub publication, or desktop-tool integration. `install.py` still installs inactive files only. Config0.1.0 remains stage-only; config0.2.0 explicitly selects the RPC workflow. No per-request protected job file is needed for RPC.

## Roles and bootstrap

An independently reviewed, root-protected Python/runtime package must already be installed. Use the pinned dependencies and `-I -S -B` bootstrap checks from README.ko.md. Do not run an unreviewed candidate checkout with sudo. On an existing pilot, stop only its services/sockets, record expected hashes and ownership, preserve the previous bytes in a root-only task backup, create exclusive temporary siblings, set intended ownership/mode, atomically replace and read back SHA256. Unknown prior bytes or existing unrelated resources are a blocker, not permission to overwrite.

Keep four distinct principals: submission client, controller, execution worker, publisher. A client waiting for verification must never share the execution UID: executor's no-preexisting-worker-process guard remains enforced. In the actual test these were respectively989,995,988,990; IDs are observed values, not portable defaults. Dedicated submission/execution accounts have nologin shells and `/nonexistent` homes. Submission alone joins `multi-p2-workers`, the historical broker-access group. Execution uses its own private primary group and receives no supplementary groups after privilege drop. Allocate fresh identities per enrollment; UID recycling is not implemented.

For the first new RPC enrollment on the tested existing pilot, the bounded provisioning commands were the following. Refuse preexisting user/group names rather than adopting them; for another enrollment choose new approved names with execution prefix `multi-p2-worker` and resolve actual IDs afterwards:

```sh
groupadd --system multi-p2-client-rpc01
useradd --system --gid multi-p2-client-rpc01 --groups multi-p2-workers --home-dir /nonexistent --shell /usr/sbin/nologin multi-p2-client-rpc01
groupadd --system multi-p2-worker-rpc01
useradd --system --gid multi-p2-worker-rpc01 --home-dir /nonexistent --shell /usr/sbin/nologin multi-p2-worker-rpc01
```

The root verifier retains the existing `multi-p2-executor.service`, private mounts, delegated cgroup, exact MainPID checks, resource budgets and cleanup. Do not add `User=root` on the tested systemd255: the explicit identity with syscall filtering drops CAP_SETUID before the supervisor. System-service default root plus independent euid0 guards is intentional. The publisher stays under `multi-p2-publish` with NNP, empty capabilities and a private network namespace.

## Executable and AppArmor

Copy the approved pinned bubblewrap bytes to `/opt/multi-p2/bin/bwrap-rpc`, root:execution-group0550. Verify regular single-link file, hash, no SUID/SGID or file capabilities. The shared root-owned bin parent must permit traversal by that private execution group; the tested mode is0751. This adds traversal only, not directory listing or write access to other principals. Each executable's0550 owner/group still determines execution access.

The exact-path profile is `profiles/multi-p2-bwrap-rpc.apparmor`. Preserve unknown existing profiles; do not overwrite them. For a new approved deployment, install this file as root0644 at `/etc/apparmor.d/multi-p2-bwrap-rpc`, compile with `apparmor_parser -Q -T <file>`, then add only that profile with `-a -T`. For a known task-owned update, validate prior bytes, compile, then replace only that profile with `-r -T`. Read back the named loaded profile. It is a narrow executable-specific userns exception, not complete AppArmor confinement. Never disable global AppArmor, NNP, mandatory namespaces, gate or seccomp.

## Protected configuration

Broker config0.2.0 has exactly `schema_version`, `state_root`, `socket_path`, `controller_uid`, `client_gid`, `enrollments`, `rpc`. Each enrollment is `{binding, client_uid}`. `rpc` is `{publisher_uid, listener_identity: "systemd-root"}`. Preserve the existing controller0700 state directory and controller:client-group0750 socket directory. The public socket is0660.

`/etc/multi-p2/rpc.json`, root:publisher0640, has exactly:

```json
{
  "schema_version": "0.1.0",
  "controller_uid": 995,
  "publisher_uid": 990,
  "policies": [{
    "policy_path": "/etc/multi-p2/APPROVED-policy.json",
    "executor_config_path": "/etc/multi-p2/APPROVED-executor.json",
    "client_uid": 989
  }]
}
```

Replace example values with verified local role IDs and root-protected approved files. Execution UID in each policy must differ from client/controller/publisher. An executor config binds the execution UID/GID, enrollment, machine hash, approved rootfs digest, dedicated bwrap path/hash, fixed jobs/cgroup roots and execution profiles. Compute `executor_configuration_digest(config)` into `policy.oracle.executor_config_digest`, then `policy_binding(policy)` into the broker enrollment. Policy, base commit and scope are immutable for that enrollment; a new baseline requires a deliberately provisioned new enrollment/identity until recycling is implemented. Do not silently update the binding in an existing store or reuse pending request keys.

The operator supplies the nonsecret binding descriptor to the authorized submission application once during enrollment provisioning. The live client sends upload/stage/verify/publish requests with its own durable request/idempotency IDs. The server never accepts an argv, host path, remote/ref, credential or claimed test result from request JSON. Root-owned policy selects those values. Existing --run entry modes remain for compatibility; RPC units use --rpc.

## Wire and identity contract

Public stage/verify/publish schema0.1.0 is unchanged. Upload schema0.2.0 contains exactly `{schema_version, operation:"upload", binding, digest, data_base64}`. It is content-addressed/idempotent, grants no authority, and is capped at64KiB decoded bytes. RPC bounds are64KiB total materialized candidate bytes and128KiB framed JSON; duplicate-digest paths still consume the materialized-byte budget. Larger manifests cannot invoke this adapter. Framing uses a4-byte big-endian length and a shared5-second input deadline. The controller waits at most330 seconds for a bounded response, subject to the existing service/executor limits.

The internal frame carries the validated request, controller-derived client UID, durable backend key and immutable bundle. Root and publisher endpoints select only a protected policy whose full binding matches, independently rehash bytes, and enforce the delegated-client mapping. Transport loss is unknown. Retrying uses the stored backend key and authoritative backend ledger/readback, not cached success JSON. Interrupted verification is not automatically reexecuted.

Systemd creates `/run/multi-p2-rpc/{verify,publish}.sock` under root-owned0755. Both sockets are0660/group `multi-p2-control`; owners are root and `multi-p2-publish` respectively. **Client SO_PEERCRED observes the socket creator PID1/UID0**, not the actual accepting publisher UID. The client verifies this manager identity plus protected path/owner/inode. Each server checks LISTEN_PID/LISTEN_FDS, exact listening path, its own euid and accepted controller SO_PEERCRED. The publisher's existing runtime guard also checks actual UID, NNP/caps/network. Reply role fields are server runtime assertions over that authenticated endpoint, not independent kernel proof supplied by a caller.

## Reviewed activation decision — not yet applied

The test host currently has `user.max_user_namespaces=0`. Sustained automatic execution needs an approved nonzero operational ceiling. The tested ceiling is15334. This is a host namespace setting, **not** a UID-specific allowlist; AppArmor and the dedicated executable permissions remain separate controls. The existing approval covers temporary test windows only, each restored to0. Do not infer permanent approval from a successful test.

Two concrete operating choices are available:

1. Keep installed code/config inactive, sockets and broker disabled, quota0. Controlled tests may continue under the already authorized temporary window and restore timer. This does not provide continuous automatic availability.
2. After explicit approval of sustained operation, create the new task-owned file `/etc/sysctl.d/zz-multi-p2-userns.conf` with exactly `user.max_user_namespaces = 15334` and root0644. Refuse an existing file; recheck only definitions of this key for later-precedence conflicts before claiming reboot persistence. Do not edit unrelated sysctls or run a global reload. Apply only this file with `sysctl -p /etc/sysctl.d/zz-multi-p2-userns.conf` and verify the live value.

The actual read-only inventory found only `/etc/sysctl.d/dirtyfrag.conf:1` defining this key as0; live value was0 and `/etc/sysctl.conf` had no additional definition. The original numeric90 proposal would sort before dirtyfrag.conf and would not remain effective at boot. The revised zz file was absent and no later definition was found. It would intentionally override the existing explicit0 restriction; that fact requires the human activation decision. Keep dirtyfrag.conf untouched. Installed running-kernel metadata reports `linux-image-6.8.0-147-generic` version `6.8.0-147.147`, with cached Ubuntu noble-updates/security origins; no index refresh, signature re-verification, package installation or reboot was performed. This inventory is not an authorization or a claim that every kernel risk is resolved.

For option2, after frozen source/config/profile/identity checks and daemon-reload, enable/start exactly:

```sh
systemctl enable --now multi-p2-executor.socket multi-p2-publisher.socket multi-p2-control.service
```

Do not directly enable the executor/publisher services; sockets activate them on demand. Each service waits at most20 seconds for one connection, handles exactly one request and exits so the next queued request gets a fresh RuntimeMaxSec budget. RuntimeMaxSec and systemd's existing start/trigger rate limits remain intact. Check socket owner/group/mode and broker ownership, then perform an approved bounded health request. A changed base/policy requires fresh enrollment rather than recycling the pilot's already-published base. The functional pilot receipt and local commit are evidence, not authorization for another candidate.

## Rollback and recovery

Stop incoming requests first: disable/stop only those three enabled units, then stop `multi-p2-executor.service` and `multi-p2-publisher.service`. Verify no execution-worker processes and no populated job cgroup. Restore namespace0 with the single explicit key and read it back. Remove `/etc/sysctl.d/zz-multi-p2-userns.conf` only if its path/content/hash match the task-owned file; otherwise stop and report the mismatch. The original dirtyfrag.conf definition stays untouched and again supplies the existing boot-time0 setting. Restore previous known runtime/unit/config bytes from root-only backups and daemon-reload. Unload only the task-owned `multi-p2-bwrap-rpc` profile if retiring this RPC setup. Do not delete historical receipts, CAS, ledgers, unknown/pending requests, original bwrap/profile, user SSH access, or unrelated services. Dedicated role accounts stay locked; deleting/reusing them is a separate lifecycle operation.

In temporary tests arm an independent120-second systemd restore timer before raising the quota, and restore0 in finally on every outcome. If the owner crashes, the timer remains the fallback. The test owner stops scoped sockets/services before returning. No persistent activation has been performed in this task's functional tests.

## Verification and limits

The actual nonroot submission client stayed alive through upload→stage→root verification→separate publisher. The successful local commit was8467d7e04b77748b0e118880d0f812279c8c6a96. Actual replay after service restart and a discarded reply returned the same authoritative commit. A prior uncertain verification key remained unknown without another job. Wrong kernel peer, scope, changed replay body, private endpoint access, delegated client UID, blob bytes, extra command, oversized frame, partial-frame deadline and duplicate-path byte quota were checked. Local target ref and job count stayed unchanged during denials. See the current task's durable report/evidence for hashes and counts.

Review-regression reproduction: `runtime/tests/test_p2_rpc.py ReviewRegressionTests` uses a real fixture ledger and a modeled idempotent backend, failing the first post-handler transaction to assert unknown/null and the same backend key on retry. A separate test asserts one accept per service invocation. The actual VM test used a temporary root-owned controller wrapper via a task-only `/run/systemd/system/multi-p2-control.service.d/` drop-in. It called the real ProductionWorkflow handler first, then replaced only the next store transaction with a one-shot SQLite error after verified/published success. Fresh verification produced a real receipt before the controller failure; retry returned that same receipt without another worker job. Publication reconciled the existing actual commit before the injected failure, and retry retained that commit/key. Systemd ExecMainPID changed across both verifier and publisher requests. The wrapper/drop-in were removed, daemon-reload completed, and quota0 was read back. This is test-only fault injection, not a production toggle or a new-commit claim for the publication fault case.

This remains same-host Linux/local-bare only. Cross-host APIs, external HTTPS publication, desktop tool routing, generalized large-blob streaming, identity recycling and per-enrollment scheduling fairness are not provided. Old sandbox isolation/lifetime proofs are reused only for unchanged executor/gate boundaries; changed RPC boundaries have their own actual evidence.
