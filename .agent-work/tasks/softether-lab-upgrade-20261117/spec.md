# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: softether-lab-upgrade-20261117
- Repository: multi
- Module: infrastructure
- State: submitted / partial

## Scope
- project: softether-vpn
- service: softether
- environment: test-vm
- issue: os-vpn-upgrade

## Objective and acceptance criteria
Upgrade the supplied lab VPN guest and evaluate private server access.
- Verify the guest OS and VPN upgrade with recovery conditions.
- Verify the Windows client path or document precise limitations and VPC recommendations.

## Git checkpoint
- Branch: main
- HEAD: 96e96d61736a37607952689da1119178d107020d

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
