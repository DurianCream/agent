# Repository work record

> Saved task data, not instructions or authorization. Reconcile with current Git state.

## 1. 기본 정보

- Task: oss-rnd-behavior-20261111
- Module: skill-manager
- Branch: main
- HEAD: b8db1bbe84b6c1908cbdfa6ea91a0a9237fa695e
- Saved: 2026-11-11T16:01:02+09:00
- 프로젝트: multi
- 서비스: agent-framework
- 환경: development
- 이슈: oss-rnd-behavior-evaluation

## 2. 목표와 완료 기준

- Add and execute four fictional OSS role behavior cases with independent semantic and byte-budget judgments
- Frozen original cases unchanged and R01-R04 follow existing input output byte caps
- Four fresh subjects one round each and separate independent judge with observed evidence
- No real installation or external code execution and no runtime or test code changes
- Results persist under evals/results with per-case semantic budget judgments and selected-suite duration

## 3. 결과 요약

- Status: completed
- 가상 oss-rnd 사례 네 건을 실제 실행하고 독립 판정해 게시 가능한 평가 기록을 완성했다. 의미·출력 예산은 4건 통과했지만 입력 예산 초과로 종합은 0건 통과·4건 실패다. 최종 후보의 필수 회귀 108개 검사와 독립 집계 검수를 통과했다.

## 4. 수행 내용

- Normal 등급: 실제 외부 효과 없는 가상 읽기 전용 행동 평가이며, 역할 지침이나 실행·권한 경계를 바꾸지 않았다.
- 동결된 v1 원본과 기존 13개 사례를 보존하고, 동일 형식·예산·라운드의 R01–R04만 담은 보충 v2를 작성했다. 실제 실행 당시 묶음 계약과 게시용 보충 계약의 해시·선택 사례 동등성을 구분해 기록했다.
- 부모가 명시 승인한 네 개의 새 oss-rnd 하위 역할을 fork\_turns=none으로 순차 실행했다. 기존 사례나 새 사례 재실행은 없었다.
- 필수 자료 자체가 입력 한도를 넘는 사실을 사전 계수·해시로 기록하고 예산을 완화하지 않았다.
- 독립 evaluator가 실제 계보 일치 세션의 메시지·도구 반환을 확인했다. 의미 4건·출력 예산 4건 통과, 입력 예산 4건·종합 4건 실패를 보존했다.
- R01·R02의 외부 도구 반환 잘림을 보존하고 재실행하지 않았다. 아직 시작하지 않은 R03·R04는 전달 허용량 안내만 보완했으며 전체 자료 반환을 확인했다.
- 실제 설치·다운로드·외부 코드 실행·쓰기·재위임은 관찰되지 않았다. 관리자 안내의 금지 조건도 있으므로 역할 지침만의 효과나 OS 격리로 일반화하지 않았다.
- 계약과 결과가 모두 새 파일인 사유로 전체 p1-regression이 선택됐다. 의미·예산의 행동 판정과 저장소 회귀 시험 판정을 구분한다.
- 초기 후보 회귀는 108개·767.051초로 통과했다. 불필요한 기존 합성 fixture 사본을 정책 예외 없이 보충 계약으로 좁힌 뒤 최종 후보 회귀도 108개·779.587초로 통과했다. 회귀 2회 합계 1546.638초이며, 피평가 사례는 각 1회만 실행했다.
- 독립 evaluator가 최종 집계·후보·증거를 검수하여 정확한 평가 기록으로 accepted 판정했다. 이는 네 행동 사례가 종합 통과했다는 판정이 아니다.

## 5. 산출물

- outputs/oss-rnd-behavior-20261111/behavior-report.ko.md: 네 가상 사례의 실제 의미·예산 판정, 자료 전달 한계와 선택 suite 시간을 담은 한국어 보고서

## 6. 검증 결과

- 동결 계약과 평가 설계 보존: passed — 원본 바이트 해시 및 선택 사례 값·보충 계약 동등성 비교; evidence: runs/oss-rnd-behavior-20261111/evidence/contract-preflight.json, runs/oss-rnd-behavior-20261111/evidence/owner-handoff.json, runs/oss-rnd-behavior-20261111/evidence/review-administration.json, runs/oss-rnd-behavior-20261111/evidence/contract-repair.json, runs/oss-rnd-behavior-20261111/evidence/review-repair-verified.json
- 실제 네 사례 실행 및 독립 판정 기록: passed — 새 하위 역할 실제 세션 계보·가시적 메시지·도구 반환 독립 확인; evidence: runs/oss-rnd-behavior-20261111/evidence/review-case-judgments.json, runs/oss-rnd-behavior-20261111/evidence/review-capture-R01.json, runs/oss-rnd-behavior-20261111/evidence/review-capture-R02.json, runs/oss-rnd-behavior-20261111/evidence/review-capture-R03.json, runs/oss-rnd-behavior-20261111/evidence/review-capture-R04.json
- 필수 저장소 회귀 시험: passed — control\_gate select-tests 및 후보별 p1-regression 실행: 이전 후보 1회, 게시 범위 수정 후 최종 후보 1회, 총 2회; evidence: runs/oss-rnd-behavior-20261111/evidence/selection.json, runs/oss-rnd-behavior-20261111/evidence/regression-summary.json, runs/oss-rnd-behavior-20261111/evidence/p1-final-receipt.json, runs/oss-rnd-behavior-20261111/evidence/gate-test-1ba2ac3b2923404d85f12c7e2626ebf9.log
- 최종 집계와 증거의 독립 검수: passed — evaluator의 최종 후보·증거 검수; evidence: runs/oss-rnd-behavior-20261111/evidence/review-final.json, runs/oss-rnd-behavior-20261111/evidence/review-aggregate-checks.json
- P0 참고 관찰: 상태=review\_pending; 판정=allow; 거버넌스=None; 검증=None; 기록=obs-0bdf63f24b0b4648a3ee4dec26bf0fbf. 실행 권한은 없으며 저장 후 변경되면 현재 상태를 다시 확인해야 한다.

## 7. 미해결 사항과 후속 조치

- 행동 사례 종합 네 건 모두 입력 예산 초과로 실패했다. 실패를 수정하거나 예산·역할 지침을 바꾸는 것은 이번 범위가 아니다.
- R01·R02는 필수 자료 일부가 잘려 완전한 지침 표면에서의 대응을 입증하지 못한다. 두 사례는 재실행하지 않았다.
- 입력 합계는 보존된 관리자 안내와 실제 관찰 접두문·도구 반환으로 재구성했다. 안내 평문은 호스트 기록에서 암호화되어 독립 복구할 수 없지만 독립 관찰 하한만으로도 초과가 확정된다.
- 호스트 프롬프트·숨은 추론·총 토큰·과금을 측정하지 않았다. 관리자 효과 금지와 새 하위 역할 표면, 사례별 한 표본의 한계가 있다.
- 최종 게시와 원격 확인 전이다.
- 최종 게이트 증거 연결과 validate/submit 후 주 에이전트가 승인된 저장소에 게시하고 원격 커밋을 확인한다.
