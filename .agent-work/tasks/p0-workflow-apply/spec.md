# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: p0-workflow-apply
- Repository: multi
- Module: coding
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: p0-workflow-application

## Objective and acceptance criteria
P0 관찰 기능을 선정한 개발·Git 작업 흐름에 연결하고 실제 거버넌스·검증 인계와 기록을 검증하여 적용 완료한다.
- 작업 범위와 파일·정책 상태에서 P0 입력을 구성하고 고정된 실행 환경으로 실제 관찰을 호출한다.
- 선정한 기존 작업 경로에서 자동 호출·상태 보고·기록이 동작하며 실행 권한이나 승인으로 오인하지 않는다.
- 거버넌스 해석과 독립 검증을 관찰 기록·현재 대상에 연결하고 변경·실패·누락·오래된 결과를 구분한다.
- 정상·거부·추가 검토·실패·기존 승인 재사용 통합 사례와 회귀 테스트·독립 검토를 통과한다.
- 현재 저장소에 설정과 실행 환경을 적용하고 실제 작업의 관찰·해석·검증 증거 및 상세 명세를 저장한다.

## Git checkpoint
- Branch: main
- HEAD: 8d7e1ebf4a3a2cbd56449bd2438560a4258af84b

## P0 observation
- Mode: observe; executable: false; authority_verified: false
- Status: review_pending
- Record: obs-a4c5eb18a9574eb58029448e5fff7ded
- Snapshot: sha256:de66d53e4b291e3406dbdd96ab2aeac9abcce1abfe1c1a2584a08da55d6ee818
- Decision: allow
- Assessment status: none
- Governance recommendation: None
- Evaluator assessment: None
- Reason codes: review_pending
This saved advisory summary may become stale; inspect current observer status before relying on it.

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
