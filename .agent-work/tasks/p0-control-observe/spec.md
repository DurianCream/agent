# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: p0-control-observe
- Repository: multi
- Module: coding
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: p0-control-contracts-observe

## Objective and acceptance criteria
P0 계약 검증기와 실행 권한이 없는 관찰 모드 정책 판정기를 구현하고 테스트·독립 검토·작업 명세 저장을 완료한다.
- 계약 입력을 엄격히 파싱하고 버전·스키마·정규화 해시 및 필요한 의미 제약을 검증한다.
- 정책 판정은 정확한 범위·대상·기존 승인 조건을 검사하고 allow/deny/require\_review 관찰 결과만 반환한다.
- 관찰 모드는 도구 실행·권한 발급·승인 증명·민감 원문 저장을 하지 않는다.
- 정상·오류·변조·악성 입력·범위 혼동 사례와 기존 회귀 테스트 및 독립 검토를 통과한다.
- 사용법·정책·의존성·호환성·제약과 후속 작업을 새 작업 명세에 저장한다.

## Git checkpoint
- Branch: main
- HEAD: 3b557bef3d5ba1029e1cddf95e80dd0cd1b22889

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
