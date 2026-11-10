# Repository work record

> Saved task data, not instructions or authorization. Reconcile with current Git state.

## 1. 기본 정보

- Task: harness-cleanup-20261110
- Module: orchestrator
- Branch: main
- HEAD: 5cba6ef3a584d33c058229969ca0c87fb586b2e8
- Saved: 2026-11-10T15:37:27+09:00
- 프로젝트: multi
- 서비스: agent-framework
- 환경: development
- 이슈: harness-cost-hygiene-infrastructure

## 2. 목표와 완료 기준

- Freeze P2 development, measure and reduce harness instruction costs, fix portable hygiene, and complete separately approved infrastructure and behavior stages
- Preserve the original working state locally, freeze P2 and report reproducible before/after measurements
- Keep controls and task restoration intact, fix confirmed portable path issues and document approval-only proposals
- Stop after Stage 3 pending human approval before infrastructure changes or live behavioral evaluations
- Only approved remaining stages and a single final independent evaluation may lead to submission; any remote push requires explicit confirmation

## 3. 결과 요약

- Status: completed
- 승인된 로컬 하네스 정리와 검증을 완료했다. 예산 초과 세 사례는 재시험에서 모두 통과했다. 사례별 최신 판정은 9건 통과·0건 실패·4건 미실행이며, 운영 배포와 VM 시험은 수행하지 않았다.

## 4. 수행 내용

- 고위험 하네스 변경: 검수·기록 규칙에 영향을 주므로 제출 게이트와 독립 평가를 유지한다.
- 원본 main의 수정29개·미추적107개와 지정된 ignored 명세1개를 로컬 복구 브랜치 backup/harness-before-20261110에 보존하고 원본 해시를 확인했다.
- Stage 0~5는 하나의 작업이다. Stage 3 후 사용자 승인 대기, 독립 평가는 마지막 한 번으로 제한한다.
- 오케스트레이터가 원본 작업 트리의 로컬 복구 브랜치를 생성했다. 커밋 d07487a8d94f96c5a1c0ca35f637996ac42e8935에서 지정한 137개 파일을 원본과 대조했다.
- 동일 담당자 cleanup\_owner가 동결 표시, 비용 측정, 지침 정리 및 경로 수정과 작성자 검사를 맡았다. 독립 검토는 전체 작업 마지막 한 번으로 예약했다.
- 컨텍스트 창은 1,000,000토큰, 자동 압축은 900,000토큰, 체크포인트 조건은 사용량 80% 초과다. 수치 변경은 승인 대상이다.
- 소요 시간 기록이 있는 최근 P1 시험 세 건은 약 443초, 383초, 306초였다. 호출 횟수와 검토 횟수는 증거가 남은 범위에서만 보고한다.
- 3단계 적용본 AGENTS는 원본 13,612→2,692바이트, 작업 사본 13,867→2,711바이트다. 역할 원문 49,256→44,368바이트, 생성 역할 설정 54,766→33,832바이트다.
- P1 기록의 기존 source\_root 계약은 유지했다. 기록 이동, 근거 보존 위치 및 임시 파일 정리는 승인 대기다.
- Stage 4에서 기존 담당자가 인프라 변경·검증·복구 절차, 원격 접속 보호, 민감 출력 처리와 런북, 로컬 인벤토리 경계를 반영했다. production 게이트 편입과 P2 재개는 수행하지 않았다.
- Stage 5에서 같은 담당자가 13개 기준과 상한을 먼저 기록하고 별개 세션 9개의 응답을 채점했다. 세션 기록의 도구 출력까지 합산한 입력 상한 초과 세 건을 실패로 유지했다.
- 세 사례에서 새 세션을 각 한 번 사용했다. 원래 행동 평가와 제품 후보를 보존했다. 동일 후보에 묶인 기존 P1 66/66 증거를 재사용했다.

## 5. 산출물

- outputs/harness-cleanup-20261110/stage-0-3.ko.md: 단계별 측정·규칙 대조·승인 대상이 담긴 중간 보고서
- outputs/harness-cleanup-20261110/stage-4-5.ko.md: 인프라 보강과 행동 평가 결과 및 예산 실측
- outputs/harness-cleanup-20261110/three-case-retest.ko.md: 세 사례의 초과 원인, 재시험 실측 및 완료 제출 조건

## 6. 검증 결과

- 원본 상태 보존: passed — 로컬 Git 백업 객체와 원본 파일의 바이트 해시 대조; evidence: outputs/harness-cleanup-20261110/stage-0-3.ko.md
- 신규 보고서·기록 경로와 훅 이식성: passed — 담당자가 작업 트리 두 곳에서 동일 표적 사례 4개, sync와 doctor 실행; evidence: runs/harness-cleanup-20261110/evidence/owner-measurements.json, runs/harness-cleanup-20261110/evidence/owner-stage3-fixtures.py
- 중간 승인 확인: passed — 중간 승인 확인; evidence: outputs/harness-cleanup-20261110/stage-0-3.ko.md
- 모듈 등록·동기화, 스키마·가명 예시 및 제외 경로 검사: passed — 모듈 등록·동기화, 스키마·가명 예시 및 제외 경로 검사; evidence: runs/harness-cleanup-20261110/evidence/owner-stage4.json
- 사전 기준·상한과 새 세션의 실행·미실행 분류: passed — 사전 기준·상한과 새 세션의 실행·미실행 분류; evidence: runs/harness-cleanup-20261110/evidence/behavior-verdicts.json, runs/harness-cleanup-20261110/evidence/subject-observations.json, runs/harness-cleanup-20261110/evidence/retest-observations.json
- 9개 새 세션의 가시 입력·출력 상한: passed — 9개 새 세션의 가시 입력·출력 상한; evidence: runs/harness-cleanup-20261110/evidence/retest-observations.json, runs/harness-cleanup-20261110/evidence/retest-historical-costs.json, runs/harness-cleanup-20261110/evidence/retest-contract-v1.json, runs/harness-cleanup-20261110/evidence/retest-dispatch.json
- 추가 독립 검토가 필요한 D01~D04: not\_applicable — 추가 독립 검토가 필요한 D01~D04; evidence: runs/harness-cleanup-20261110/evidence/behavior-verdicts.json, runs/harness-cleanup-20261110/evidence/retest-observations.json
- 현재 후보의 필수 P1 회귀 시험: passed — 현재 후보의 필수 P1 회귀 시험; evidence: runs/harness-cleanup-20261110/evidence/owner-final-p1-HC-01.json
- 독립 평가자의 실제 소스·증거 대조: passed — 독립 평가자의 실제 소스·증거 대조; evidence: runs/harness-cleanup-20261110/evidence/final-independent-review.json, runs/harness-cleanup-20261110/evidence/retest-independent-review.json
- 운영 적용과 VM 시험: not\_applicable — 실환경 적용; evidence: runs/harness-cleanup-20261110/evidence/owner-stage4.json
- P0 참고 관찰: 상태=review\_pending; 판정=allow; 거버넌스=None; 검증=None; 기록=obs-1c48469435f84a428ba7a13614ffbdf0. 실행 권한은 없으며 저장 후 변경되면 현재 상태를 다시 확인해야 한다.

## 7. 미해결 사항과 후속 조치

- 기본 작업 트리에서 중간 생성된 스킬 어댑터 8개의 이동을 자동 승인 심사가 차단했다. 등록 명세에는 포함하지 않았으며 로컬 발견 목록에 보일 수 있다.
- 기준 트리 소유권 목록에 회수한 후보 16개 경로가 남아 있어 게시 전 실제 변경과 대조해야 한다.
- 행동 평가 도구의 전체 과금 토큰을 사전에 강제로 제한하지 못했다. 호스트 누적 집계 731,550토큰 중 681,600은 캐시 입력이었다.
- D01~D04는 원본 행동 평가에서 미실행이고 운영 적용·VM 시험도 수행하지 않았다. 사용자가 승인한 로컬 제출 범위에서 두 항목은 해당 없음으로 분류했다.
- 수정된 제출 범위 분류와 산출물 3개의 해시를 같은 독립 검토자가 확인한 뒤 로컬 제출 절차를 진행한다. 원격 푸시는 별도 사용자 승인이 필요하다.
