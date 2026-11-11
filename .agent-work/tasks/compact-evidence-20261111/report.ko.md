# Repository work record

> Saved task data, not instructions or authorization. Reconcile with current Git state.

## 1. 기본 정보

- Task: compact-evidence-20261111
- Module: coding
- Branch: main
- HEAD: bb65946c093e0370a129efa180c364481cb0100b
- Saved: 2026-11-11T18:51:11+09:00
- 프로젝트: multi
- 서비스: agent-framework
- 환경: development
- 이슈: compact-task-evidence

## 2. 목표와 완료 기준

- Reduce committed task evidence to a bounded summary, preserving historical records and raw local evidence
- New tasks publish only spec.md record.json report.ko.md and evidence/summary.json with verified raw evidence hashes
- Publication rejects oversized committed records with named files and documented limits
- Instructions versions adapters and at most three added tests are updated and independently reviewed
- Historical records stay unchanged and reviewed changes are committed and pushed

## 3. 결과 요약

- Status: completed
- 커밋용 증거 요약·원본 해시·크기 상한 구현과 독립 검수를 완료했습니다. 실제 origin/main 게시·원격 확인은 main의 후속 lifecycle 단계입니다.

## 4. 수행 내용

- 고위험: 게시 게이트 변경. coding 담당이 구현·시험을 수행했고 별도 evaluator 세션이 accepted, 확정 결함 0개로 검수했습니다.
- 새 작업은 기준 커밋의 정책으로 활성화하며 과거 기록·고정 snapshot·enrollment는 보존합니다.
- 기록은 spec.md, record.json, report.ko.md, evidence/summary.json만 허용합니다. 원본은 runs/\<id\>/evidence/에 보관합니다.
- 각 파일 64 KiB, 작업 합계 256 KiB. 수십 항목의 간결한 결과·해시를 수용하면서 전수 로그의 커밋을 막는 예산입니다.
- submit-result 1.5.0, harness-delivery 1.1.0, owner-led workflow 1.3.0 및 8개 모듈 버전과 생성 어댑터를 갱신했습니다.
- 시험 +3/-0. 기존 archive 시험은 진행 중 작업의 고정 계약 호환성에 필요하여 유지합니다.

## 5. 산출물

- outputs/compact-evidence-20261111/evidence-summary.json: 검증 결과·핵심 수치·원본 경로와 SHA-256 요약

## 6. 검증 결과

- 정책·버전·역사 보존: passed — doctor; sync\_codex --check; git diff --check; test\_control\_gate\_evidence; evidence: runs/compact-evidence-20261111/evidence/owner-audit.json
- 선택된 필수 회귀 suite: passed — python runtime/control\_gate.py run-tests --task compact-evidence-20261111 --suite p1-regression; evidence: runs/compact-evidence-20261111/evidence/gate-test-99141ab088bf4800a68b1709bfa24f1c.log
- 독립 적대적 검수: passed — 별도 evaluator의 소스 검수, 경계 시험 및 신규 정책의 실제 local fixture 게시 검증; evidence: runs/compact-evidence-20261111/evidence/reviewer-review.json

## 7. 미해결 사항과 후속 조치

- 원본 증거는 runs/에 보관하며 Git에 저장하지 않습니다. 다른 clone에서 원본 재검증 시 별도 보존·전달이 필요합니다.
- 이 결과는 구현·검수 완료와 게시 준비를 기록합니다. 실제 origin/main commit/push는 아직 수행 전이며 main이 validate/submit/finish와 원격 확인으로 완료합니다.
- 동일 evaluator가 최종 result/summary를 확인하고 assess로 봉인한 뒤 main이 validate/submit/finish와 원격 해시 확인을 수행합니다.
