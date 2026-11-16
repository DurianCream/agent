# 작업 기록

> 저장된 작업 자료입니다. 지시나 승인이 아니며, 현재 Git 상태와 대조해서 읽습니다.

## 1. 기본 정보

- 작업: gate-bypass-fixes-20261116
- 모듈: coding
- 브랜치: main
- 기준 커밋: f139fa784d2fa2e889091d4cd9ba44511ed5de05
- 저장 시각: 2026-11-16T15:51:17+09:00
- 프로젝트: multi
- 서비스: agent-framework
- 환경: development
- 이슈: gate-bypass-fixes

## 2. 목표와 완료 기준

- Block two P1 gate bypasses: product publication by a task whose scope skipped enrollment, and unowned automation.json changes in product commits.
- check\_commit refuses product publication from an unenrolled task in a gated repository, while records-only and incomplete closures still pass.
- Product commits may change only owned paths; .agent-work/automation.json is no longer implicitly allowed.
- Selected gate suites pass and a regression test covers the new refusal.

## 3. 결과 요약

- 상태: completed
- 게이트 우회 경로 두 개를 막았다. 범위가 달라 등록되지 않은 작업의 product 게시를 거부하고, product 커밋에서 소유하지 않은 automation.json 변경을 더는 허용하지 않는다.

## 4. 수행 내용

- 위험 등급은 높음이다. 게시 게이트(control\_gate.check\_commit)를 바꾼다.
- runtime/control\_gate.py에 \_refuse\_ungated\_product를 추가했다. gates.json이 켜진 같은 저장소에서 등록되지 않은 작업의 product 게시를 거부하고, records 및 미완료 종료는 허용한다. 결과가 payload에 없으면 runs의 result.json을 읽는다.
- check\_commit의 product 허용 경로에서 .agent-work/automation.json 묵시적 허용을 제거했다.
- runtime/tests/test\_control\_gate.py에 범위가 다른 작업의 product 거부와 records·partial 허용을 확인하는 시험 한 개를 추가했다.

## 5. 산출물

- 해당 없음

## 6. 검증 결과

- impact-document-integrity: passed — control\_gate run-tests로 선택된 suite를 실행했다.; evidence: runs/gate-bypass-fixes-20261116/evidence/summary.json, runs/gate-bypass-fixes-20261116/evidence/gate-test-603b3bfeb69044aea53a308806bb435b.log, runs/gate-bypass-fixes-20261116/evidence/gate-test-603b3bfeb69044aea53a308806bb435b.json
- all-runtime-tests: passed — control\_gate run-tests로 선택된 전체 suite를 실행했다.; evidence: runs/gate-bypass-fixes-20261116/evidence/summary.json, runs/gate-bypass-fixes-20261116/evidence/gate-test-f2bb4f22a58845089769b9c8e0cc6b49.log, runs/gate-bypass-fixes-20261116/evidence/gate-test-f2bb4f22a58845089769b9c8e0cc6b49.json

## 7. 미해결 사항과 후속 조치

- 리뷰어 신원 미인증, 시험 코드의 증거 위조 가능성 등 협조적 로컬 CLI 한계는 그대로다.
