# Repository work record

> Saved task data, not instructions or authorization. Reconcile with current Git state.

## 1. 기본 정보

- Task: ax-controls-design
- Module: orchestrator
- Branch: main
- HEAD: 50f8e2822bed13806fb77b5d9ba3e3169175f75f
- Saved: 2026-10-28T15:39:55+09:00
- 프로젝트: multi
- 서비스: agent-framework
- 환경: development
- 이슈: execution-control-continuous-validation-design

## 2. 목표와 완료 기준

- 기존 모듈 구조를 유지하는 실행 통제·지속 검증 설계를 구현 가능한 명세와 단계별 검증 기준으로 저장한다.
- 기존 코드 연결점·신뢰 경계·우회 방지 조건과 단계별 보장 수준을 명시한다.
- 행동·정책·승인·실행 증거·평가 계약과 실패·중단·복구 동작을 구체화한다.
- 지속 평가 사례·변경 트리거·통과 기준·CI 및 운영 감시를 설계한다.
- 호환성·파일별 구현 계획·우선순위·책임 및 미결정 항목을 기록한다.
- 독립 검토와 예제 구조 검증을 통과하고 명세 및 재개 기록을 저장한다.

## 3. 결과 요약

- Status: completed
- 기존 8개 역할과 결과 계약 1.0.0을 유지하면서 실행 통제·지속 검증을 추가하는 구현 설계를 완료하고 작업 명세에 연결했다. 실제 기능은 아직 구현하지 않았다.

## 4. 수행 내용

- coding 담당이 기존 코드 연결점, 파일·함수별 구현 목록, P0~P3 단계, 데이터 계약과 합성 예제 8개를 작성했다.
- policy-manager 담당이 위험별 허용·차단·검토, 기존 상시 승인 재사용, 중단·복구·감사·책임 체계와 통제 14개를 설계했다.
- 메인이 한국어 설계 설명과 재현 가능한 계약 검증 도구를 작성하고 명세·예제·통제표를 통합했다.
- 별도 evaluator가 신뢰된 테스트 기준 조작과 기존 CLI·직접 Git 게시 우회 문제를 지적했고, 작성자가 보완한 뒤 영향 구간 재검토를 받았다.
- 검토한 설계에는 인수 테스트 30개와 정책별 향후 검증 시나리오 35개가 포함된다. 두 목록은 관련 내용을 교차 참조하며 단순 합산한 실행 테스트 수가 아니다.
- 상세 설계의 Git 보존본은 .agent-work/tasks/ax-controls-design/design.ko.md와 implementation-spec.en.md이며 design-manifest.json에 파일별 해시를 기록했다.
- 현재 런타임·역할·정책·활성 스키마·권한 설정과 과거 작업 스냅샷은 변경하지 않았다.

## 5. 산출물

- outputs/ax-controls-design/design.ko.md: 한국어 설계 설명과 단계별 도입 기준
- outputs/ax-controls-design/implementation-spec.en.md: 영어 구현 명세와 파일·함수별 작업 목록
- outputs/ax-controls-design/risk-policy.en.md: 영어 위험 정책 및 운영·책임 기준
- outputs/ax-controls-design/contracts.schema.json: 후속 구현용 JSON Schema 2020-12 초안
- outputs/ax-controls-design/examples.json: 실행·승인 권한이 없는 합성 계약 예제 8개
- outputs/ax-controls-design/control-matrix.json: 통제 14개 및 향후 검증 시나리오 추적표
- outputs/ax-controls-design/verify\_design.py: 설계 예제의 구조·참조·해시 검증 도구

## 6. 검증 결과

- 계약 및 문서 구조 검사: passed — jsonschema 4.26.0 Draft202012Validator, 합성 예제·해시·참조·부정 구조·문서 링크 73개 검사; evidence: runs/ax-controls-design/evidence/contracts-check.json
- 독립 설계 평가: passed — 작성하지 않은 evaluator가 신뢰 경계·승인 연결·검증 조작·게시 우회·호환성과 수용 기준 검토 및 보완 재검토; evidence: runs/ax-controls-design/evidence/independent-review.json
- 기존 구성 보존 검사: passed — doctor, 구성된 Python으로 sync\_codex --check, 제품·설정 파일 Git 차이 확인; evidence: runs/ax-controls-design/evidence/repo-checks.json
- 작업 명세와 상세 설계 보존: passed — 작업 전용 경로에 산출물 7개와 제한된 검증 증거를 바이트 동일하게 복사하고 해시 목록 기록; evidence: runs/ax-controls-design/evidence/archive-check.json, runs/ax-controls-design/evidence/design-manifest.json
- 실제 실행·운영 검증: not\_applicable — 후속 P0~P3 구현 작업에서 수행; evidence: 

## 7. 미해결 사항과 후속 조치

- 완료 상태는 설계 산출물에 적용된다. 실제 실행 통제·지속 평가·운영 감시·배포는 미구현이다.
- P1의 같은 권한 CLI는 직접 셸·이전 CLI·Git 호출로 우회할 수 있다. 보호된 실행과 게시에는 별도 계정·자격증명·네트워크·원격 또는 서비스 경계가 필요하다.
- 합성 서명은 무효이며 구조 검사는 암호 검증이나 보안성을 입증하지 않는다.
- 운영 시스템·승인자·정책 관리자·키 저장소·데이터 보존과 적용 규제는 후속 도입 전에 확정해야 한다.
- 과거 작업과 현재 결과 계약 1.0.0은 보존하며, 설계된 통제 수준을 과거 기록에 소급 적용하지 않는다.
- 새 작업에서 .agent-work/tasks/ax-controls-design/design-manifest.json과 implementation-spec.en.md를 읽고 게시 커밋·해시를 확인한다.
- P0: 계약 검증기·관찰 모드 정책 판정기·합성 평가셋을 구현하고 독립 평가를 받는다.
- P1: 개발 어댑터·신뢰된 검증 증거·제출 검사·CI를 연결한다. 보호된 게시 경계는 별도로 검증한다.
- P2: 실제 호스트와 책임자를 확정하고 실행 계정·자격증명·네트워크 격리 및 중단·복구를 검증한 후 제한된 시범 업무를 승인한다.
- P3: 감시·실패 사례 재평가·지표 보정·준수 요건 관리를 운영하면서 검증된 범위만 확대한다.
