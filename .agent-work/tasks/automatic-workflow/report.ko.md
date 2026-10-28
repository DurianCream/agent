# Repository work record

> Saved task data, not instructions or authorization. Reconcile with current Git state.

## 1. 기본 정보

- Task: automatic-workflow
- Module: orchestrator
- Branch: main
- HEAD: 9b62de06849bd096c82188b2a719feac1cadbee6
- Saved: 2026-10-28T13:38:58+09:00

## 2. 목표와 완료 기준

- Automatically load repository memory and publish completed work
- Startup reads saved work without a user reminder
- Completed work is saved committed and pushed to the authorized remote
- Unrelated changes and remote conflicts are protected

## 3. 결과 요약

- Status: completed
- 새 채팅의 작업 기록 자동 읽기와 완료 작업의 명세 저장·커밋·푸시 기본 절차를 구현했다.

## 4. 수행 내용

- coding 담당이 startup/begin/track/finish와 작업별 기준점·파일 명세·푸시 재시도를 구현했다.
- 메인이 AGENTS·조율자·제출 스킬과 정책을 갱신하고 영어 지침·한국어 안내 및 호환 버전 참조를 동기화했다.
- 별도 evaluator가 자동 게시 범위·변경 충돌·기록 복구와 푸시 재시도를 독립 검토했다.
- startup 명령으로 사용자 재요청 없이 이전 저장소 기록이 로딩되는 것을 확인하고 전체 회귀 검사를 수행했다.

## 5. 산출물

- outputs/automatic-workflow/setup.json: 자동 시작·게시 적용 설정

## 6. 검증 결과

- 자동 복구·게시 및 전체 회귀: passed — 전체 80개 unittest; 로컬 bare 원격 실제 commit/push·새 clone 자동 등록·재시도 포함; evidence: runs/automatic-workflow/evidence/tests.txt
- 실제 저장 기록 자동 로딩: passed — 별도 프로세스에서 repoctl startup 실행; evidence: runs/automatic-workflow/evidence/startup.txt
- 영어 지침·계약·생성 설정: passed — doctor, sync --check 및 지침 언어 검사; evidence: runs/automatic-workflow/evidence/checks.json
- 독립 평가: passed — 별도 evaluator 코드 검토와 게시 테스트; evidence: runs/automatic-workflow/evidence/review.json

## 7. 미해결 사항과 후속 조치

- 자동 시작과 종료는 프로젝트 AGENTS 지침을 읽은 에이전트가 실행한다. 앱이 닫혀 있는 동안 도는 백그라운드 서비스는 아니다.
- 원격 충돌·인증 실패·무관한 변경이 감지되면 게시를 중단하고 원인을 보고한다. 강제 푸시는 하지 않는다.
- 게시 자동화는 현재 명시적으로 승인된 DurianCream/private origin/main에 적용한다.
- 새 multi 채팅에서는 일반 작업 요청만 하면 기록 읽기부터 완료 게시까지 기본 절차를 따른다.
