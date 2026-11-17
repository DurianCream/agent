# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: softether-lab-install-20261117
- Repository: multi
- Module: infrastructure
- State: submitted / completed

## Scope
- project: softether-vpn
- service: softether
- environment: test-vm
- issue: os-vpn-upgrade

## Objective and acceptance criteria
Update the disposable guest and verify a VPN session from the supplied Windows client.
- Verify installed guest OS updates and running VPN server version with recovery information.
- Verify an authenticated Windows VPN client session and provide relevant VPC settings.

## Git checkpoint
- Branch: main
- HEAD: b090bd77a842fd04a54da70e318087ae34d9ebd5

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
