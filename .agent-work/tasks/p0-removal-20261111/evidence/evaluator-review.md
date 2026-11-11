# P0 제거 독립 최종 검수

판정: **accepted**. 독립 세션 `/root/p0_evaluator`가 작성자 `/root/p0_owner`의 실제 diff, 실행 로그, 보고서를 검수했다. 검수자는 제품 후보를 작성하지 않았고 재위임하지 않았다. 역할 판정은 실행 권한 또는 신원 인증이 아니다.

범위: repository/project multi, service agent-framework, environment development, issue p0-observation-removal, task p0-removal-20261111. 기준 커밋 1af99b354cb54f7e48e2b7f7159ee4b28843029f. 검수 작업공간 work/agents/p0-removal-20261111/evaluator/instance-lb2pxy92.

최종 소스 candidate digest: `d5cea859b5d9e54efb9d2cbef8e839dad763a2ee03dd7594fd7e8d1aba26e06b`.
최종 보고서 `outputs/p0-removal-20261111/report.md` SHA-256: `08e02b026cfd4d2a1c50e2b2a76e209cd97334ce58dbcda8e12137210598789d`.

## 기준별 판단

| 기준 | 결과 | 검수 근거 |
|---|---|---|
| 지정된 P0 제거 | passed | 제품 후보 48경로는 실제 diff와 정확히 일치한다. 23삭제/25수정, 신규 제품0, P0 코드5개·스키마4개·설정·정책·requirements·fixture·시험5개·전용 안내 제거를 확인했다. |
| P1 및 역사 호환 | passed | repoctl/automation의 관찰 hook·renderer 제거만 수행했고 제출·게시 판단과 실제 commit/원격/비밀값 검사를 유지했다. control_gate의 새 generated record는 observation 없이 엄격히 검증하며 spec 해시·checkpoint seal·canonical 비교가 남아 있다. 과거 읽기는 renderer를 재실행하지 않는 resume이며 합성·실제 역사 기록의 읽기와 바이트 불변 근거가 있다. |
| 환경·스냅샷·계약 보존 | passed | 독립 baseline에서 환경1,128+과거2,118+현재 result schema1=3,247파일을 해시 대조했고 최종 시험 후에도 변경0. 작성자 baseline은 schema 대신 현재 enrollment ledger1을 포함한 3,247파일이며 이 또한 불변이다. 환경 파일 증감0, result schema1.0.0·기존 기록·스냅샷 유지. |
| 시험 수·범위 제한 | passed | AST 기준 전용 정의148 삭제, 기존 P1 시험 파일에2 추가, 신규 시험 파일0. 기존 380→234 정의와 순감소146을 확인했다. P1 호출 부재 아닌 관찰 필드 부재, 역사 읽기, 기존 실패 게시 차단·변조 경계를 확인했다. |
| 문자열·지침·adapter | passed | hidden/no-ignore 활성 소스의 삭제 모듈·경로·스키마 URI·고유 설정/상수 검색 잔존0. runtime observation 3행은 새 부재/역사 회귀 시험의 의도된 키다. P1 controls와 일반 관찰·기존 OS 문맥은 유지한다. sync --check/doctor 성공 및 버전·생성 adapter 정합성 확인. |
| 필수 실행·독립 검수 | passed | 기존 선택기가 mapping 변경/protected/deletion으로 full p1-regression을 선택했다. enrollment나 필수 기준 변경 없이 최종110 case 통과 및 후보 불변. 공통117 case도 통과했다. 실제 실행 로그의 case 식별자를 대조해 두 묶음 교집합0/고유227을 확인했다. |

## 지적 및 영향 범위 재검수

- **P0-D1 / major / 해결**: runtime/tests/test_control_gate_impact.py:28,114에 삭제된 control_policy fixture가 남아 protected/shared 이유를 요구했다. PROTECTED에서 제거된 뒤에는 해당 기대가 맞지 않으므로 기존 P1 시험을 깨뜨린다. 소스 확인으로 지적했고, 유지되는 repoctl로 fixture만 바꾸어 원래 보호 경계 검증을 보존했다. 최종 full 로그의 test_shared_runtime_cluster_overrides_specific_suite_mapping 통과와 잔여 검색0을 확인했다. 신규 실행 동작·신규 시험 추가는 없다.
- **P0-D2 / minor / 해결**: 보고서의 과거 파일2,119개 표기에 현재 enrollment ledger1개가 섞였다. 최종 과거2,118+현재 ledger1로 분리했다. 합계·실제 해시는 정확했으며 보고서/근거 분류만 영향 범위 재검수했다. 소스 변경·시험 재실행은 필요하지 않았다.

해결되지 않은 필수 결함은 없다. 삭제된 P0 이외의 새 실행 의존성이나 범위 확대 필요도 발견하지 않았다.

## 실제 실행과 근거

작성자 증거: test-ledger.json 및 실제 gate-test-3ca281853fdf4379aad46bbcf6860a04.log에서 110 passed, 명령849.513초/unittest834.546초를 확인했고 로그 SHA-256을 gate 증거와 직접 대조했다. broader.log는117 passed, 명령463.061초/unittest462.841초다. 초기 경계2개8.541초는 최종110에 포함되므로 고유 case로 중복 계산하지 않는다. 최초 명령 탐색 실패와 구후보 mandatory 중단83.932초는 기록되어 있고 통과로 세지 않았다. sync0.113초/doctor0.167초 성공 근거를 읽었다.

독립 실행: 기존 generated record 정상/변조 경계3개를 `.venv-controls/Scripts/python.exe -I -B -m unittest discover -s runtime/tests -p test_control_gate.py -k generated -v`로 실행했다. 3 passed, unittest38.417초. 이는 full suite와 중복되는3개이며 신규 coverage로 세지 않는다. evaluator-generated-execution.json/evaluator-generated-tests.log가 실제 근거다. 전체 필수 suite는 중복 실행하지 않았다.

독립 파일·참조 확인은 evaluator-preservation.json/evaluator-residuals.json에 있다. 작성자의 historical-readback.json은 원래 네 범위로 실제 p0-workflow-apply를 읽어 observation/spec 보존과 record/spec/report 해시 불변을 확인한 근거이며 과거 작업 재실행이 아니다. preflight는 기존 full fallback 경로를 읽기 전용으로 확인했으며 임의 gate나 enrollment 변경을 권하지 않았다.

## 제한과 후속 절차

검증은 Windows의 기존 프로젝트 Python과 로컬 Git/bare remote 시험 환경에서 이루어졌다. P1은 로컬 협력 CLI이고 선언 신원·로컬 증거는 인증된 reviewer/격리 runner 보증이 아니다. Git 객체·work 임시 복제본·vendor·bytecode 및 역사 원문은 활성 참조 검색과 분리했다. 환경 축소·이름 변경이나 대체 관찰 서비스를 만들지 않았다.

이 파일 작성 시 실제 구성 저장소 commit/push는 아직 not_run이며 main의 validate/submit/finish 및 원격 확인이 남아 있다. 검수자의 P1 assessment는 이 최종 소스와 확정 result/동일 바이트 보관본을 확인한 뒤 직접 등록한다. 평가 후 제품·결과 내용·증거·시험 선택이 바뀌면 영향 범위 재검수가 필요하다. 게시 실패를 품질 승인으로 무시할 수 없다.
