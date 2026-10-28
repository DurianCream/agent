# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: governance-verification-roles
- Repository: multi
- Module: orchestrator
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: governance-verification-role-definition

## Objective and acceptance criteria
거버넌스·검증 에이전트의 판단 책임과 runtime 강제 책임을 구분하여 역할 정의와 구현 작업 명세에 반영한다.
- 두 역할의 목적·입력·판단·산출물·금지 권한·상향 검토 기준을 구체화한다.
- 에이전트 권고·사람의 승인·현재 runtime 검사·후속 강제 기능을 명확히 구분한다.
- 역할 간 인계·충돌·증거 부족·변경 후 재검토 흐름과 실무 사례를 정의한다.
- 모듈 버전·생성 설정·기존 계약 호환성을 검증하고 독립 검토를 통과한다.
- 기존 설계·과거 스냅샷을 보존하고 상세 명세와 결과를 새 작업 기록에 저장한다.

## Git checkpoint
- Branch: main
- HEAD: 68c978bce5454825563674de148326b31797e3e3

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
