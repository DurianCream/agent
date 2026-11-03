# P2 Linux pilot: reproducible application and acceptance

Scope: repository/project `multi`, service `agent-framework`, environment `development`, issue `p2-host-credential-isolation`, task `p2-host-isolation`. Accountable experiment owner: infrastructure/p2_host. This is an operator-controlled pilot, not a desktop-wide enforcement deployment. Remote connection details and private keys are intentionally absent.

## Verified platform and installed boundary

The supplied VM used Ubuntu 24.04.2 LTS, x86_64, kernel 6.8.0-147-generic, systemd 255, bubblewrap 0.9.0, and Python 3.12.3. The trusted root verifier runs in `multi-p2-executor.service`; the disposable workload uses host UID 994 / group `multi-p2-workers` (987). The separate publisher uses UID 990 / group `multi-p2-publish` (984). Both accounts have `/nonexistent` homes, nologin shells, and no privileged supplementary groups. Numeric IDs are observed values, not portable defaults.

Use the existing `modules/infrastructure/p2/linux/README.ko.md`, `install.py`, and `rootfs_builder.py` for the reviewed inactive foundation. Do not rerun the fresh-install installer over existing resources. The base interpreter, dependency environment, installed source, configuration, and image must already be independently approved and root-protected. Use `-I -S -B`; do not load `.pth` or user startup hooks. Ordinary WSL fixtures are not deployment evidence.

This pilot uses a root-owned image containing approved copies of Python, Git, their libraries and `p2_sandbox_gate.py`. No host `/usr`, home, credentials, Docker socket, or publisher directory is mounted into the candidate. The image identity observed here is `image-f31753f12b49c0f81d88ea80ddbf03c596f1c115336eafad5f55e1672a84ae54`. A different image requires a newly approved manifest and recomputed image digest; never relabel another image with this identity.

## Exact application details that resolved real failures

1. `worker_entry.prepare_private_mounts()` first checks Linux/root and that the service mount namespace differs from PID 1, then performs `mount(NULL, "/", NULL, MS_REC|MS_PRIVATE, NULL)`. It cannot silently change host propagation. The executor retains its mountinfo checks.
2. `prepare_delegated_controllers()` verifies the fixed `/system.slice/multi-p2-executor.service/supervisor` membership, empty delegated parent, and available cpu/memory/pids controllers. It enables those controllers only in the unit subtree and checks readback.
3. The executor unit deliberately omits `User=` and uses the system manager's root default with `Group=root`. The entry and executor independently require euid 0. On this systemd 255 host, explicit `User=root` with syscall filtering removed CAP_SETUID before entry, preventing the trusted helper from dropping to the worker UID. Controlled comparisons reproduced the failure. The unit retains NNP, syscall filters, mount/network isolation, budgets and control-group cleanup; it does not add ambient capabilities. See [systemd v255 source](https://raw.githubusercontent.com/systemd/systemd/v255/src/core/exec-invoke.c), `keep_seccomp_privileges` and `drop_capability(CAP_SETUID)`.
4. Child setup failures now preserve only exit code and up to 4096 nonblocking stderr bytes in an exclusive root-owned mode0600 `setup-diagnostic.json` outside candidate input/output. Nonce strings are redacted. The original fail-closed error and cgroup cleanup remain in force.

For an existing stopped pilot, verify expected installed hashes before replacing any source. Preserve the old bytes in a root-only backup, create a new sibling file with exclusive creation, root ownership and the existing mode, fsync it, atomically rename it, and read back its SHA256. Reload systemd after changing the unit. Never replace unrelated resources or start the service while sources are partially updated.

## Exact-path AppArmor exception

`prepare-bwrap-profile.py` beside this document is the preserved one-off preparation artifact (SHA256 `f690188e084849605a9c2504158a31ea64b842c22a0331fd07dd9c8d4efea7ae`). Review it and stage it under a root-protected directory before running:

```sh
/usr/bin/python3.12 -I -S -B /root/approved-p2/prepare-bwrap-profile.py
```

It refuses existing destination resources/profiles, verifies the existing config's bubblewrap hash and absence of SUID/file capabilities, installs only `/opt/multi-p2/bin/bwrap` as root:worker-group0550, then compiles and adds only this new profile:

```text
abi <abi/4.0>,
include <tunables/global>
profile multi-p2-bwrap /opt/multi-p2/bin/bwrap flags=(unconfined) {
  userns,
}
```

This is an executable-specific user namespace exception, **not** complete AppArmor confinement. The helper does not change sysctls or executor configuration. The actual diagnostic checked the effective `multi-p2-bwrap (unconfined)` profile and trusted Python execution. Keep NNP, `--unshare-net`, all other required namespaces, capability drops, gate and payload seccomp. Never disable global AppArmor or substitute the unrestricted host binary silently. Ubuntu documents this exception mechanism in its [24.04 release notes](https://documentation.ubuntu.com/release-notes/24.04/).

If preparation fails, unload only the new profile and remove only its newly created resources after successful unload readback. Preserve resources if unload cannot be established. Do not reload or disable all AppArmor profiles.

## Configuration and authorization binding

The effective pilot job uses `/etc/multi-p2/executor-profile.json` and a root-owned policy file. The executable path/hash, worker/publisher IDs, machine-id hash, image digest, fixed jobs/cgroup roots and approved execution profiles are bound by `p2_executor.executor_configuration_digest(config)`. Set `policy.oracle.executor_config_digest` to that value. This pure digest is not an attestation.

Each fresh case uses the actual local target head as `policy.identity.base_commit`, computes `p2_verifier.policy_binding(policy)`, and computes the candidate digest with `control_contracts.canonical_digest({"binding": binding, "files": files})`. Create a fresh UUID candidate and request key. Store raw blobs under a root-owned export directory with SHA256 filename verification. Export directories are root:publisher0750, files0440; policy/job files are root:publisher0640. The fixed verification job has exactly:

```json
{"schema_version":"0.1.0","policy_path":"<protected policy>","executor_config_path":"/etc/multi-p2/executor-profile.json","export_dir":"<protected export>","candidate_id":"<uuid4>","candidate_digest":"sha256:<digest>","idempotency_key":"<fresh uuid4>"}
```

The publisher job uses the same policy/export/candidate binding, an actual unexpired verification ID and its own idempotency key, with no `executor_config_path`. Publication transport is strictly `local-bare`, remote `/var/lib/multi-p2/publication-target.git`, ref `refs/heads/main`. No URL, external credentials or arbitrary command is accepted. A source/image/config/policy change must not reuse an incompatible old receipt. Existing pending request keys remain preserved; do not reset their ledger state to force a retry.

## Bounded test window

The operator authorized temporary `user.max_user_namespaces=15334` during these tests, with restoration to 0 after **every** invocation. The AppArmor exception does not override a zero namespace quota. Before each invocation, assert the value is 0, services are stopped, and no worker UID processes are present. Before raising the value, arm a unique independent 120-second restore timer:

```sh
systemd-run --quiet --on-active=120s --unit=multi-p2-userns-restore-UNIQUE \
  /usr/sbin/sysctl -w user.max_user_namespaces=0
```

Use a `try/finally` owner process: raise the limit, start only `multi-p2-executor.service`, poll its bounded state, and on every success/error stop the scoped service if necessary, restore and read back 0, then stop the backup timer. Keep the timer armed if the owner cannot confirm restoration. No persistent sysctl change is part of this pilot. Final state was both units inactive/static, worker processes zero, quota zero.

## Actual acceptance cases and observations

1. **Final-source normal execution:** approved argv `/usr/bin/python3 -I -B /input/program.py /output/result.txt`, wall/CPU budget5 seconds, memory256MiB, tasks16, output1MiB. The program writes exact `result` bytes and `ok\n` stdout. The root verifier measured exit0, matching stdout/stderr/output digests, no timeout/overflow/budget breach, host worker UID994 and kernel isolation. It issued root-owned publisher-readable0440 receipt `7fa31805-4bb6-485b-afaa-28a3e1f807cf` for candidate `bd5aa0bd-eccd-4ed3-bc27-f3d2d839af16`.
2. **Protected publication and retry:** `systemctl start multi-p2-publisher.service` published that exact candidate to the local target. A second invocation with the identical fixed job/key preserved commit `fb8b48e52b419f7ecef296ad6e7cdb481d38ae2f`. Independently reading `refs/heads/main:program.py` as publisher yielded candidate SHA256 `831f4f531a574c7dbc87819ff09882eb2810816cdd9b01f9937041c5973ba7d4`.
3. **Actual sandbox denial:** the root-approved probe initialized a bare Git repository under its writable output, wrote an object/tree/commit and updated its private ref successfully. It then attempted `git push /var/lib/multi-p2/publication-target.git refs/heads/main:refs/heads/p2-bypass-probe`, which failed. The same candidate could not read a separately root-created synthetic random canary or append to `/input/program.py`. `socket(AF_INET/AF_INET6/AF_VSOCK/AF_NETLINK/AF_PACKET, SOCK_STREAM)` each failed with EPERM, not merely connection refused. It deleted its private Git control repository and wrote a canonical JSON result containing all nine true assertions; expected SHA256 `2a0664fa7f1ac6e276483a756a47d1fb53be729aac2d1c4de8e4d97072a8779a`. The safety oracle measured that exact output and issued receipt `4cbd65b7-00ce-41f6-a88d-70754fc6407d`.
4. **Host worker principal denial and positive controls:** with only worker UID994/GID987, cleared supplementary groups and sanitized environment, `/usr/bin/git --version` succeeded but `git --git-dir=/var/lib/multi-p2/publication-target.git update-ref refs/heads/p2-bypass-probe <existing commit>` returned128. The bypass ref remained absent and main stayed unchanged. Worker Python reading the synthetic canary raised PermissionError; root could read and hash the canary. No real key/token was used.
5. **Safety is not release authority:** submitting the safety receipt to the publisher failed with `production_release_profile_required`. The target main ref remained unchanged. The publisher's conservative `unknown/published=unverified` error wrapper is not the proof of no publication; the separate target readback supplies that evidence.
6. **Supervisor death after authorization:** a controlled candidate and one child append heartbeats for30 seconds to the same output inode. While they were running, the external root test owner opened that inode through the supervisor's mount namespace and retained its FD. After proving growth21→73 bytes and four worker processes, the owner SIGKILLed only the exact service MainPID. Within0.31 seconds workers were zero and the job cgroup was empty/removed. The retained FD still referenced the same device/inode and remained73 bytes across a further300ms check. No verification receipt was issued. This avoids a false pass caused solely by tmpfs path disappearance. It proves the combined actual service/gate cleanup path, not independent attribution to each mechanism.

For fault reproduction, verify the MainPID cmdline is the installed `worker_entry.py --run` before signaling. Do not kill by UID or signal unrelated units. Retain output FD identity before signaling, inspect process/cgroup absence afterwards, and preserve the pending verification request. A killed or timed-out job must never produce a successful release receipt.

## Evidence, counts and remaining limits

`runs/p2-host-isolation/evidence/owner-handoff-20261103.json` records frozen hashes and evidence mapping. During this resumed owner run:10 executor invocations (6 progressively diagnosed setup failures,2 successful normal executions,1 successful safety probe,1 expected SIGKILL fault);4 publisher invocations (2 successful publications,1 identical-key retry,1 expected safety rejection);4 trusted UID-diagnostic comparisons and1 direct worker-principal denial probe. Local focused tests:3 cases in2 invocations. Unchanged broad suites were not repeated. Earlier evidence retains its original scope.

The successful VM path is operator/manual, same-host and local-bare. Worker upload transport, broker-to-privileged-executor RPC, cross-host authentication, external HTTPS/GitHub publication, real credential rotation, and isolation of the active desktop agent's existing tools/connectors are not implemented or verified here. `production` in an adapter receipt describes protected local execution mode; it is not a claim of complete P2 coverage. Independent final review and orchestrator-controlled final deployment/publication remain separate steps.
