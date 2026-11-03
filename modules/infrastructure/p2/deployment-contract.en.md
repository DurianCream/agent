# P2 deployment boundary contract

Status: preparation only. The infrastructure option is a local Hyper-V VM; no guest OS or version is preselected. When an actual test needs an environment, the agent requests the exact OS/version and requirements, and the user supplies an existing VM or an ISO for a new VM. No VM, guest service, credential migration, or remote protection has been applied by this work.

Scope: repository multi; project multi; service agent-framework; environment development; issue p2-host-credential-isolation.

## Observed host and operator prerequisite

Windows Professional build 26200 has Hyper-V tools, vmms and the hypervisor running. The actual tool token is neither an administrator nor a Hyper-V Administrator; management queries are denied. This is not evidence that Hyper-V needs installation or reboot. Discovery observed 31.5 GiB RAM, 2.3 GiB free RAM, 10 logical processors and 155 GiB free workspace-volume space. Resource observations must be refreshed before use.

An operator executes the reviewed per-test provisioning entry point elevated only after the test environment is selected, or supplies an already provisioned VM. No VM/ISO is requested merely to continue OS-independent design or tests. Do not grant the agent broad host group membership, alter existing VMs, disable UAC, or change machine-wide networking to make a test pass.

## Per-test request and preparation API 0.2.0

The request identifies the test purpose and exact scope, OS name, concrete OS version/build and edition where relevant, architecture, boot/security requirements, resource requirements and requested read-only identity probes. These are requested labels, never evidence of an installed guest. The agent asks when the actual test needs them rather than defaulting to a distribution or latest release.

For an existing VM, the user supplies its immutable VM identifier/name, endpoint and authenticated host-key/certificate fingerprint. A separate read-only validation compares VM identity and guest-reported OS/version to the request before selecting OS-specific tests. The creation script never reuses, reconfigures, reinstalls or deletes that VM by name. Later mutation needs the task's explicit authorized scope.

For a new VM, `New-P2VM.ps1` requires `VmName`, `OsName`, `OsVersion`, `Architecture`, `SecureBootTemplate`, `CpuCount`, `MemoryGiB`, `DiskGiB`, exact existing switch, local ISO and independently authenticated SHA256. There are no implicit OS, template or sizing defaults. The unique name uses `multi-p2-` plus 1..40 lowercase alphanumeric/hyphen characters, with alphanumeric endpoints. The new directory leaf must match the name; existing names and paths are rejected.

Current capability is Gen2 AMD64 with Secure Boot always On and an explicit `MicrosoftWindows` or `MicrosoftUEFICertificateAuthority` template. CPU count is 1..64 and cannot exceed host logical capacity; RAM is 1..128 GiB and RAM plus 2 GiB must fit physical capacity; dynamic disk capacity is 8..256 GiB and requires capacity plus copied ISO plus 2 GiB free disk. Explicit start rechecks free RAM against requested RAM plus 2 GiB. These bounds do not prove vendor requirements or guest compatibility. VM configuration and Secure Boot/template readback must match before start.

Legacy BIOS/Gen1, ARM and vTPM provisioning are not implemented. If a test needs them, request an already correctly provisioned VM or separately implement and verify the missing capability. Never silently disable Secure Boot or substitute a different architecture, version or template. ISO digests pin media bytes but do not authenticate OS labels or prove installed versions. Output keeps `requested_guest` separate from `installed_guest=unverified` and `guest_compatibility=unverified` until an actual guest probe.

Creation remains stopped by default. ISO copy and storage are created atomically with protected administrator-owned descriptors; parent replacement, reparse, mapped-drive and alias risks are rejected. API 0.2.0 requires explicit new parameters: earlier fixed-target commands are not silently translated into a guessed profile. Guest installation and P2 isolation remain separate work.

## Trust domains

| Domain | Required authority | Forbidden relationship |
|---|---|---|
| Human host operator | Hyper-V lifecycle, recovery, trusted installation | No automatic delegation of host administration to the worker |
| Controller | Enroll exact tasks, stage immutable source and route typed requests | Must not execute candidate code with controller credentials |
| Worker | Read staged inputs; write its bounded disposable work/output area | No publisher key, Docker/hypervisor socket, host share, sudo, signing service or unrestricted network |
| Trusted verifier | Owner-installed immutable suites and external observations | No candidate-owned interpreter/import/oracle can forge its measurements |
| Publisher | Exact authorized repository/ref through a reviewed immutable candidate | No arbitrary shell, remote, ref, hooks or credential-helper values supplied by worker |
| Independent evaluator | Separate review of concrete candidate and evidence | Advice is not an authority token or a replacement for required tests |

The current desktop Codex session and connected service tools are outside a future guest worker boundary. A child VM does not remove those existing privileges. Before claiming whole-agent enforcement, enumerate every untrusted agent tool path and migrate or disable host execution and direct write connectors. Treat the deployment operator separately from the isolated worker; do not relabel the current host session isolated.

## Guest installation requirements

Install controller code, policy, accepted evaluation suites, public trust roots and service configuration under root/administrator ownership outside the candidate checkout. Workers must be unable to write the files, replace parent directories, change the service definition or substitute its interpreter. A repository JSON configuration is a proposal until installed through the operator's trusted path.

Use distinct worker, verifier and publisher OS principals. Bound CPU, memory, process count, time, writable storage and output size. Run candidate code in an actual OS/container sandbox with no administrative capabilities, no host process namespace, no setuid escalation, and no control sockets. Worker network access starts denied. The transport for narrow controller requests is explicitly authenticated and cannot imply authority from a caller-provided name.

The guest must not mount the Windows user profile, host Git configuration, SSH-agent socket, credential manager, cloud keys or publisher checkout. The private repository is staged by the trusted controller as an immutable snapshot; worker access does not require receiving a fetch or write credential. Copy data through a bounded validated protocol rather than a worker-writable trusted directory.

## Publication and credential requirements

The publisher holds a separate narrowly scoped credential outside worker-readable storage, preferably short-lived and delivered only to the publisher process. Existing personal host credentials are not read, copied or revoked by preparation code. Any migration/revocation occurs through an explicit operator/provider control path and preserves human recovery.

Resolve destination repository, remote and branch from the trusted enrollment. Resolve artifacts by verified content digest, with exact object type, mode, scope and baseline checks. The publisher's clean checkout, Git configuration, hooks, executable and credential helper must be trusted and inaccessible to the worker. Do not use candidate `.git`, filter configuration, arbitrary commands or mutable path aliases.

The verifier's actual observations and independent review must bind the same candidate and policy. Candidate-generated passed fields or copied P1 receipts are not trusted attestations. If signing is used, only the isolated trusted service can use its key; an agent-writable signing script or secret is not a trust boundary.

Use provider-supported remote restrictions where available and verify the exact repository, issuer and bypass actors. A required status is insufficient when the worker can set it or has an alternate direct write credential. Inventory raw Git, SSH, HTTP APIs, connected tools and inherited sessions. If any untrusted path retains direct write authority, report the rollout incomplete.

## Required actual acceptance probes

| Probe | Required observed result |
|---|---|
| Worker reads host-only synthetic credential/file canary | Access denied; no real secret is used or printed |
| Worker opens publisher key or invokes a signing service | Denied; no valid grant or signature is produced |
| Raw Git over HTTPS/SSH/local path attempts publication | Denied and target ref unchanged; a missing Git executable alone is not sufficient |
| Direct HTTP/connector publication path | Denied or unavailable to the worker by independently enforced permissions |
| Worker alters installed policy, suite, broker or parent directory | Denied; trusted installed digests unchanged |
| Worker uses symlink, mount, process handle, ptrace or service socket | Denied within the declared OS threat boundary |
| Worker attempts arbitrary egress and host control access | Denied by actual network/host controls, not a model instruction |
| Approved reviewed candidate through publisher | Exact target commit/ref succeeds and independent readback matches |
| Wrong scope/ref/content, stale review, replay, broker unavailable | No publication; explicit failed or inconclusive state and bounded audit |
| Controller/publisher restart after uncertain effect | Durable reconciliation; no duplicate or force publication |

Run adverse probes against bounded fixtures first. Real remote mutation tests use only explicitly authorized disposable targets. Do not infer denial from a timeout, missing command, mock response or unexecuted check. Record exact identity, configuration digests, scope, evidence and readback for each actual probe.

## Rollback and operator access

Preserve an independent human administrative path and verified recovery information. Rollout must never revoke the only operator access. On failure, stop new admissions, retain bounded evidence and reconcile any in-flight publication before changes. Preparation does not automatically remove a partially created VM or directory. The operator inspects the exact new VM ID and owned path before any cleanup; no blanket VM shutdown or recursive deletion is part of this entry point.

## Pending work

Operator provisioning, guest installation, authenticated SSH bootstrap, isolated service implementation, credential provisioning, trusted test execution, remote policy setup, full agent-tool routing and all actual acceptance probes are pending. The request parser and VM preparation scripts do not by themselves satisfy these criteria.
