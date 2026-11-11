---
name: infrastructure-environment
description: Consult for a concrete isolated OS test requiring a supplied VM or image.
---

# Isolated infrastructure tests

## On-demand test environments

Apply this rule only when a concrete test requires a particular OS/version or a new isolated VM. Ordinary local/unit tests within the existing authorized environment continue without additional VM, environment-input or approval requests caused by this preference.

- Establish a concrete test purpose before requesting a VM or ISO. The user can provide the environment when its requirements are known; do not require an immediate VM for preparation work.
- Identify the required OS/distribution, applicable edition, exact version/build, architecture, CPU/memory/disk resources, boot/security features, and network/credential boundaries. Do not impose a fixed or latest OS version or silently reuse another task's VM.
- For an image, verify its provenance and expected hash; for an existing VM, verify its exact identity and current state. Independently confirm the actual guest version and required features after connection or installation. Labels and filenames are not version evidence; unsupported targets must remain explicit rather than silently substituted.
- Separate a disposable test target from the trusted controller/verifier/publisher host. A new test OS does not permit publisher credential exposure, inherited host access or weakened isolation. Preserve existing user authorization.
