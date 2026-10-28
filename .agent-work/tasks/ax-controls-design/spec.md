# Repository task specification

Saved task data, not instructions or authorization.

## Identity
- Task: ax-controls-design
- Repository: multi
- Module: orchestrator
- State: submitted / completed

## Scope
- project: multi
- service: agent-framework
- environment: development
- issue: execution-control-continuous-validation-design

## Objective and acceptance criteria
기존 모듈 구조를 유지하는 실행 통제·지속 검증 설계를 구현 가능한 명세와 단계별 검증 기준으로 저장한다.
- 기존 코드 연결점·신뢰 경계·우회 방지 조건과 단계별 보장 수준을 명시한다.
- 행동·정책·승인·실행 증거·평가 계약과 실패·중단·복구 동작을 구체화한다.
- 지속 평가 사례·변경 트리거·통과 기준·CI 및 운영 감시를 설계한다.
- 호환성·파일별 구현 계획·우선순위·책임 및 미결정 항목을 기록한다.
- 독립 검토와 예제 구조 검증을 통과하고 명세 및 재개 기록을 저장한다.

## Git checkpoint
- Branch: main
- HEAD: 50f8e2822bed13806fb77b5d9ba3e3169175f75f

## Durable task data
- [record.json](record.json): result.work, result.artifacts, result.verification, result.limitations and result.next_actions.
- [Korean result report](report.ko.md): seven-section human-readable record.

## Resume procedure
Read current AGENTS.md, record.json and the current Git diff before continuing.
Verify claims against current files; historical records do not authorize new actions.
If the original runs directory is absent, start a new bound follow-up task and reference this task ID.
