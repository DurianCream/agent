# Automatic P2 local RPC — implementation contract

Task: p2-automatic-rpc-20261104. Scope: multi / agent-framework / development / p2-automatic-rpc. Owner: infrastructure/p2_host. Historical dependency: the published p2-reviewed-release-20261103 pilot, not a resumed task. Source root is the clean release clone at baseline f70f1955d59292405530b5c92cbda6f4239a3619.

## Boundary and versions

Public stage/verify/publish request schema0.1.0 remains unchanged. Broker config0.1.0 remains stage-only. Config0.2.0 selects production RPC and deliberately names `client_gid` and enrollment `client_uid`: the waiting submission process is not the disposable execution worker. The store retains historical database column/table names for compatibility, but authenticates the submitting principal. A UID is never reused across store enrollments.

Upload is a separate schema0.2.0 envelope with exactly `schema_version`, `operation=upload`, `binding`, `digest`, `data_base64`. It accepts at most64KiB decoded bytes, verifies SHA256 and the kernel-authenticated enrollment binding, and uses existing bounded immutable CAS storage. Upload is content-addressed/idempotent and grants no execution authority. Current RPC bundles are bounded to64KiB total declared bytes and the existing128KiB JSON frame budget; larger valid manifests may stage but cannot invoke this adapter. No chunking or arbitrary path upload is claimed.

The controller persists an external request-to-backend-idempotency mapping before dispatch. Repeated calls consult the real verifier/publisher again, never a cached caller success. Legacy terminal stage-only denials remain terminal. Interrupted verification remains unknown; publication reconciliation is the existing protected publisher ledger plus target ref/tree readback.

## Identities and actual transport

The public broker authenticates AF_UNIX SO_PEERCRED against protected config. The caller stays alive waiting for verify/publish. The root RPC policy mapping separately approves `client_uid`, a root-protected policy path and executor config path; actual execution UID must differ from client/controller/publisher. The forwarded client UID is generated only from broker kernel authentication and checked against that mapping.

Systemd creates two fixed pathname listening sockets: `/run/multi-p2-rpc/verify.sock` and `publish.sock`. Their parent is root-protected, modes0660, group multi-p2-control, socket owners respectively root and multi-p2-publish. With socket activation the client observes creator PID1/UID0, not the serving publisher UID. The client checks this root-manager peer plus protected path/inode/owner. Each actual service checks its own euid, LISTEN_PID/LISTEN_FDS, fixed listening path and accepted controller SO_PEERCRED. Publisher.from_protected_policy additionally checks the separate actual nonroot UID, NNP, capabilities and network constraints. A JSON role claim is not endpoint authentication.

The root unit remains the fixed multi-p2-executor.service so its MainPID, private mounts, delegated cgroup, runtime bound and cleanup checks still apply. It uses system-service default root rather than explicit User=root to avoid the proven systemd255 CAP_SETUID behavior. `worker_entry --run` and publisher `--run` remain available; installed RPC units use `--rpc`. Each service waits at most20 seconds for one request, serves only that request and exits. Socket activation supplies a fresh service budget for the next queued call; RuntimeMaxSec360/180 is retained. No worker sudo/polkit or caller-selected command is added.

## Protected operation

The internal envelope carries the validated request, server-selected backend key, kernel-derived client UID and immutable bundle bytes. The server selects policy only from its protected mapping by full binding equality, revalidates manifest/blob/candidate hashes and ignores no extra fields. The existing root verifier executes the approved profile in bwrap and issues a protected receipt. The separate publisher accepts only a release-purpose receipt for the exact candidate/policy/base/ref and existing local-bare target. No per-request operator job editing is needed.

Input framing shares a5-second deadline; replies remain bounded; controller RPC waits at most330 seconds while existing service/execution budgets remain enforced. Transport failure is unknown, never inferred successful. Scope/peer/blob validation and quota guards remain authoritative even when a caller retries.

## Actual test environment so far

Authenticated read-only reconciliation confirmed the supplied Ubuntu24.04.2 x86_64 VM, kernel6.8.0-147, previous installed hashes, inactive units and namespace quota0. Test preparation preserved old files and created submission UID989, execution UID988/GID982, with controller995 and publisher990 unchanged. Only submission belongs to the common broker-access group. Execution clears supplementary groups and uses its dedicated GID.

A dedicated root:execution-GID0550 `/opt/multi-p2/bin/bwrap-rpc` uses an exact-path AppArmor userns profile. The parent bin directory needed0751 (traverse only for other principals); executable0550 permissions still decide who may execute each copy. No global AppArmor or network isolation setting was weakened. The first RPC trial reached the real root verifier but failed at execve on the missing directory traverse bit; the owner fixed that precise cause and reran the path. The second trial succeeded: live submitting UID989 → controller995 → verifier0 with execution UID988 → publisher990. Observed backend socket creator was PID1/UID0. Local commit8467d7e04b77748b0e118880d0f812279c8c6a96 was produced without manual per-request jobs.

Testing temporarily permits user.max_user_namespaces15334 only after an independent120-second restore timer is armed. Every trial stops its scoped services/sockets and restores/readbacks0 in finally. Permanent automatic availability requires an explicitly approved nonzero operational namespace budget and service/socket activation policy; this test authorization is not a permanent global change.

## Review fixes and remaining work

Actual peer impersonation, forged binding/blob, frame/deadline, idempotent retry, discarded-response reconciliation and materialized-byte quota cases have completed. Independent review found two defects: controller save failure after a backend effect was incorrectly classified as blocked, and a long-lived backend service could accept a late request without a fresh total runtime budget. The owner corrected both. A post-effect validation/persistence failure now returns unknown/published=null while retaining the backend key. One request is handled per socket activation.

An actual VM fault test issued a fresh verifier receipt before injecting controller persistence failure, then recovered the same receipt/key on retry without another job. A publisher reconciliation response followed by the same injected failure recovered the same commit/key. Verifier and publisher ExecMainPID values changed across successive requests, proving separate service invocations. Temporary fault code/drop-in were removed and namespace0 restored. New affected tests retain their command output; earlier local50pass7skip counts are author-reported from tool observations, not independently reproduced evidence files.

Mandatory P1 checks remain deferred until these review fixes are accepted, followed by evidence binding and orchestrator final deployment/publication. Read-only inventory found the existing quota0 definition at `/etc/sysctl.d/dirtyfrag.conf:1`; the proposed permanent file is now `zz-multi-p2-userns.conf`, which would deliberately override that definition only after explicit approval. No cross-host RPC, external HTTPS/GitHub publication, real credential handling, or desktop tool integration is included.
