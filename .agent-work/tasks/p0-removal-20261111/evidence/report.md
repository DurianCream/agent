# P0 관찰 기능 제거 결과

기준 커밋 `1af99b354cb54f7e48e2b7f7159ee4b28843029f`, 작업 `p0-removal-20261111`, 범위 `multi / agent-framework / development / p0-observation-removal`.

조사 보고서의 1~5단계를 하나의 후보로 구현했다. P0 자동 관찰·수동 계약/관찰 CLI·정책·스키마·전용 시험을 제거하고 P1 제출·게시 검사를 유지했다. P1 판단·검토·실제 커밋·원격·비밀값 검사는 그대로이며, 새 생성 기록에서는 observation 필드와 P0 렌더링을 없앴다. 과거 record/spec는 기존 resume 경로로 읽고 원본을 다시 쓰지 않는다.

## 삭제량과 유지 범위

제품 파일 **23개 삭제, 25개 수정**, Git diff 기준 **7,514행 삭제·79행 추가**다. 신규 제품 파일은 0개다. 정적 test_ 정의는 **380→234**, 전용 정의 148개를 삭제하고 기존 시험 파일에 2개를 추가해 **순감소 146개**다. 이 수치는 실제 실행 case 수와 구분한다.

- `.agent-work/observation.json` (22행)
- `docs/P0-실행통제-사용안내.md` (114행)
- `runtime/control-requirements.txt` (12행)
- `runtime/control_contracts.py` (436행)
- `runtime/control_integration.py` (349행)
- `runtime/control_policy.py` (177행)
- `runtime/control_workflow.py` (726행)
- `runtime/controlctl.py` (81행)
- `runtime/tests/fixtures/control-contracts/action-request.json` (54행)
- `runtime/tests/fixtures/control-contracts/all-envelopes.json` (445행)
- `runtime/tests/fixtures/control-contracts/unicode-vector.json` (15행)
- `runtime/tests/fixtures/control-observe/context.json` (49행)
- `runtime/tests/fixtures/control-observe/request.json` (46행)
- `runtime/tests/test_control_contracts.py` (327행)
- `runtime/tests/test_control_integration.py` (488행)
- `runtime/tests/test_control_policy.py` (299행)
- `runtime/tests/test_control_workflow.py` (584행)
- `runtime/tests/test_controlctl.py` (175행)
- `shared/policies/execution-controls.observe.json` (23행)
- `shared/schemas/control-envelope.schema.json` (1472행)
- `shared/schemas/control-observation.schema.json` (143행)
- `shared/schemas/control-observe-policy.schema.json` (423행)
- `shared/schemas/control-workflow.schema.json` (804행)

`.venv-controls` 이름과 1,128개 파일 내용은 변경하지 않았다. 과거 `.agent-work/tasks`, `outputs`, `runs`, `evals/results` 2,118개 파일과 현재 작업의 enrollment ledger 1개도 변경하지 않았다. 합계 **3,247개 SHA-256 일치**, 환경 파일 추가·삭제 0개, `result.schema.json` 변경 0건이다. 현재 작업의 나머지 작업 기록은 이 역사 비교에서 제외한다. 시작 당시 작업 snapshot/enrollment는 수정하지 않았다.

P1의 `control_gate.py`는 신규 generated record의 필드·renderer 인자를 observation 없는 현재 형식에 맞췄다. 원래의 canonical 내용·spec 해시·checkpoint seal·실제 commit 비교는 유지했다. 역사 읽기는 별도 `repoctl.resume` 경로라 과거 기록을 현재 renderer로 재생성하지 않는다.

실제 과거 `p0-workflow-apply`도 원래의 정확한 네 범위로 현재 `repoctl.resume`를 호출해 확인했다. 원본 observation과 저장 spec를 그대로 읽었고 record/spec/report 세 파일의 해시는 호출 전후 동일했다(`historical-readback.json`, 0.387초). 과거 작업을 다시 실행하거나 수정한 것은 아니다.

## 남긴 경계 시험과 문자열 정리

`runtime/tests/test_control_gate_integration.py`에 다음 2개만 추가했다.

- `test_new_lifecycle_records_only_include_gate_metadata`: 실제 로컬 bare remote에서 checkpoint/track/submit/finish를 거쳐 관찰 필드·관찰 저장 디렉터리 없이 기록과 게시가 성공하고 P1 호출이 남는지 확인한다. 이 시험의 gate는 호출 경계를 확인하는 mock이며, 실제 canonical gate 검증은 기존 P1 suite가 담당한다.
- `test_resume_preserves_historical_extra_metadata_and_specification`: 합성 과거 observation 필드·저장 spec를 resume가 그대로 반환하고 기록 바이트를 바꾸지 않는지 확인한다.

기존 `test_publication_gate_blocks_push_and_retry_reuses_commit` 및 generated record 정상·변조 시험을 유지했다. P0-D1은 기존 `test_control_gate_impact.py`의 삭제된 모듈명을 보호 대상 `repoctl` fixture로 교체해 해결했다. 신규 시험이나 실행 동작 변경을 추가하지 않았다. `test_submission_profile.py`의 삭제된 설정명 예시는 일반 unknown-workflow 설정명으로 바꿔 기존 거부 검증 의미를 유지했다.

단순 문서 언급은 AGENTS, README, 세 역할 지침, P1 안내와 디렉터리 안내에서 정리했다. 추가 발견된 infrastructure 지침의 `P0/P1` 표현은 `P1`로 정리했다. 해당 역할 manifest 패치 버전은 orchestrator 0.3.4, evaluator 0.3.3, policy-manager 0.2.6, infrastructure 0.1.10로 올리고 4개 생성 adapter 및 native-map을 동기화했다. 역할 ID·권한·공통 결과 계약은 바꾸지 않았다. `.venv-controls` 준비 설명은 삭제된 P0 안내 링크 대신 기존 P1 안내에 포함했다.

숨김·ignore 포함 활성 텍스트 104개를 검색했다. 삭제 모듈명·파일 경로·정책·스키마 URI·P0 고유 설정/상수의 **잔여 참조 0건**이다. 조사에서 추출한 **395개 키·심볼**도 다시 검색해 잔여 범용 키의 위치를 기록했다. 넓은 `observation/controls/P2/P3/stage` 검색은 243행이며 P1 제어·일반 실험/지식 관찰·기존 OS 문맥 및 위 두 역사/부재 회귀 시험의 의도적 observation 키다. 이 범용 단어까지 없다고 주장하지 않는다. 역사 기록, Git 객체, work 임시 복제본, 가상환경 vendor, bytecode는 활성 검색에서 분리·제외했다. 상세 위치·파일 해시는 `reference-audit.json`에 있다.

## 실제 검증

| 검사 | 결과 | 실제 소요 시간 |
|---|---|---:|
| 기존 규칙으로 선택된 `p1-regression` (`test_control_gate*.py`) | **110 passed**, 후보 불변 | 849.513초(명령 전체) |
| 관련 공통 회귀 9개 suite | **117 passed** | 463.061초(명령 전체), unittest 462.841초 |
| 초기 신규 경계 시험 | 2 passed; 최종 P1에 다시 포함 | 8.541초 |
| `sync_codex.py --check` | passed | 0.113초 |
| `agentctl.py doctor` | passed; module 8 / skill 5 / result 1.0.0 | 0.167초 |
| 독립 evaluator의 기존 canonical 경계 시험 | 3 passed; 최종 P1과 중복 | 38.417초 |

관련 공통 suite는 contract, agent-workspaces, repoctl, work-scope, repo-automation, submission-profile, codex-settings, context-checkpoint, legacy-memory다. 최종 두 묶음의 고유 실행 case는 227개다. 삭제·보호 파일·impact mapping 변경 때문에 기존 선택기가 **full P1**을 선택했으며, 고정 enrollment나 gate 설정을 변경하지 않았다. 삭제되는 P0 suite를 억지로 통과시키지 않았다.

초기 named-module 시험 명령은 Python -I의 탐색 경로 때문에 실제 시험을 로드하기 전에 실패했다(0.116초). 기존 시험 파일 직접 실행으로 고쳤다. 첫 mandatory 시도는 P0-D1 발견 후 83.932초에 중단하고 실패 기록을 보존했다. 수정된 최종 후보로만 full suite를 완료했다. 중단·중복 실행은 추가 고유 통과 수로 계산하지 않는다.

독립 세션 `/root/p0_evaluator`는 참조 누락, P1 보호 경계, 새 기록 형식, 과거 읽기, 환경·역사 불변 및 두 추가 시험 범위를 검수했다. P0-D1의 시험 fixture와 P0-D2의 보호 파일 분류 표기를 수정·재검수했다. P0-D2는 합계 3,247개 중 현재 enrollment ledger 1개를 과거 기록과 분리한 것이며 제품 변경이나 추가 시험을 요구하지 않았다. 최종 판정과 후보 바인딩은 `runs/p0-removal-20261111/evidence/evaluator-review.md` 및 evaluator의 직접 P1 assessment를 기준으로 한다. 역할 추천은 실행 권한이나 신원 인증을 뜻하지 않는다.

## 게시와 근거

이 보고서는 `outputs/p0-removal-20261111/report.md`에 저장한다. 보고서와 필요한 작업 근거의 바이트가 같은 게시용 사본은 `.agent-work/tasks/p0-removal-20261111/evidence/`에만 등록한다. 정상 P1 검수·validate·submit·finish를 거친 실제 커밋과 원격 확인은 main의 최종 전달에서 보고한다. 이 보고서 작성 시점에 아직 실행하지 않은 push를 완료했다고 주장하지 않는다.

주요 근거: `change-statistics.json`, `reference-audit.json`, `preservation-check.json`, `test-ledger.json`, 최종 gate 시험 로그, `broader.log`, `sync.log`, `doctor.log`, `selection.log`, 독립 검수 기록. 원본은 `runs/p0-removal-20261111/evidence/`에 있다. 환경 축소·이름 변경, 신규 관찰 대체 서비스, 과거 snapshot 수정은 수행하지 않았다.
