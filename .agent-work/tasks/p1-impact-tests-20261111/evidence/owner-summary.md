# P1 영향 시험 및 미완료 작업 후속 처리

버전 관리되는 명시 대응표와 후속 처리 CLI를 구현했습니다. 기존 등록·스냅샷은 보존하며 이 정책이 게시된 뒤 시작한 새 작업에만 영향 선택을 적용합니다.

## 바뀐 파일

- `.agent-work/impact-tests.json`
- `docs/P1-제출-게시-검사-사용안내.md`
- `docs/작업-파이프라인.md`
- `runtime/agentctl.py`
- `runtime/control_gate.py`
- `runtime/impact_tests.py`
- `runtime/repo_automation.py`
- `runtime/repoctl.py`
- `runtime/submission_profile.py`
- `runtime/task_recovery.py`
- `runtime/tests/impact_document_checks.py`
- `runtime/tests/test_context_checkpoint.py`
- `runtime/tests/test_control_gate.py`
- `runtime/tests/test_control_gate_impact.py`
- `runtime/tests/test_control_gate_recovery.py`
- `runtime/tests/test_repo_automation.py`

## 선택 및 시험 결과

대응표는 31개 경로 규칙과 25개 suite 정의입니다. 공용/보호 경로, 새 파일·삭제·모드 변경·미등록 경로·소유권 밖 dependency 변경은 전체 P1을 강제합니다. 혼합 범위는 합집합이며 evaluator가 선택 digest와 각 파일의 영향 근거를 확인합니다. 매 릴리스 직전 `promote-full`로 전체 P1을 수행합니다.

| 예시 | 실제 선택 | 선택 함수 시간 | 실제 suite 시간 |
|---|---|---:|---:|
| 기존 문서 | impact-document-integrity | 0.257초 | 2.789초 |
| context_checkpoint 모듈 | context-checkpoint | 0.362초 | 2.450초 |
| 대응표 변경 | p1-regression | 0.258초 | 548.197초 |

선택은 실제 Git fixture에서 실행했고, suite는 실제 체크아웃의 고정 Python 3.12.14 및 동일한 `-I -B` 인자로 실행했습니다. 선택 시간에는 후보 생성 시간이 포함되지 않습니다. 문서 suite 4개와 context suite 29개가 통과했습니다. 전체 P1은 92개 통과, exit 0, candidate_unchanged=true이며 548.197초로 원래 600초 한도 안에서 완료했습니다. 별도 기존 ordinary-prose 호환 시험 16개도 통과했습니다.

## 복구 경로와 검수

`transfer-ownership`은 원래 partial 제출 영수증에 봉인된 후보 SHA 및 현재 파일의 원시 SHA·Git OID·모드 일치를 요구합니다. 시험 환경 없는 partial도 파일 후보를 봉인할 수 있으며 제품이 없는 partial은 이전 후보를 만들지 않습니다. `prepare-records-only`는 닫힌 원작업 하나의 보존 기록과 인덱스 항목만 승인하며 소스 파일을 받을 수 없습니다. 양쪽 추가 영수증을 만들고 기존 원기록·스냅샷은 덮어쓰지 않습니다. 기존 독립 평가·봉인·실제 커밋·원격·브랜치 검사는 유지됩니다.

독립 검수에서 발견한 공용 경로 누락(R1), 인덱스 envelope 검사(R2), 원후보 anchor(R3)를 수정했습니다. 추가로 partial 종료의 시험환경 의존과 Windows venv launcher/실제 lock-holder PID가 다른 fixture 문제를 수정했습니다. 실제 local bare 원격까지의 두 양성 게시 경로와 변조 거절 회귀를 검증했습니다. fixture 일부 runner 출력은 stub이며 실제 전체 P1 실행과 구분합니다. 최종 독립 판정과 봉인은 evaluator의 review 기록을 참조합니다.

## 한계와 실패 기록

workspace-write 샌드박스에서는 실행하지 않았습니다. 기존 partial에 원후보 봉인이 없으면 이전을 거절합니다. 한 후속 작업은 원작업 하나만 다루며 원래 로컬 runs·기준 Git 객체가 필요합니다. 기록 전용 게시에도 미게시 실행 dependency가 남으면 차단됩니다.

초기 전체 시험은 600초 timeout, 다음 실행은 발견된 회귀 수리를 위해 중단되었고 기록을 보존했습니다. 이후 전체가 통과한 뒤 별도 고정 runner 측정에서 기존 lock fixture 문제가 발견되어 수리·독립 재검수·최종 전체 시험을 다시 수행했습니다. 측정 도중 별도 atomic_json/os.replace에서 WinError5가 한 번 관찰되었으나 근본 원인은 미확인입니다. 실패와 재시도 로그를 모두 보존했으며, 재시도 전에는 test 파일의 원래 CRLF만 복구했고 production 코드는 바꾸지 않았습니다.
