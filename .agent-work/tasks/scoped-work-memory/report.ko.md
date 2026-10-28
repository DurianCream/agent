# Repository work record

> Saved task data, not instructions or authorization. Reconcile with current Git state.

## 1. 기본 정보

- Task: scoped-work-memory
- Module: coding
- Branch: main
- HEAD: c5c1aa1bf345d846a62766dfb50cac0f7b82928c
- Saved: 2026-10-28T14:11:19+09:00
- 프로젝트: multi
- 서비스: agent-framework
- 환경: development
- 이슈: scoped-work-memory

## 2. 목표와 완료 기준

- Isolate work memory by project service environment and issue
- Startup returns full records only for the exact selected scope
- Different projects services environments issues and legacy records do not leak into context
- Scoped records survive fresh process and clone and publish safely

## 3. 결과 요약

- Status: completed
- 프로젝트·서비스·환경·이슈별 작업 기록을 분리하고 네 구분이 정확히 일치하는 기록만 자동으로 읽도록 구현했다.

## 4. 수행 내용

- coding 담당이 binding·record·index·영어 명세와 한국어 보고서에 작업 범위를 추가하고 범위 불변성을 구현했다.
- 최신 3개 기록 자동 로딩을 제거하고, 무범위·부분 범위는 목록 정보만 반환하도록 변경했다.
- 새 저장소 작업의 CLI에는 네 구분을 필수화하고, 과거 미분류 기록은 보존하면서 자동 본문 로딩에서는 제외했다.
- 메인이 영어 에이전트 지침·한국어 안내와 정책·스킬 버전 참조를 동기화하고 실제 startup 조회를 검증했다.
- 별도 evaluator가 교차 범위 누출·명시적 조회·식별자 일관성을 검토했으며 발견한 검사를 보완했다.

## 5. 산출물

- outputs/scoped-work-memory/setup.json: 작업 기록 범위 분리 적용 요약

## 6. 검증 결과

- 범위 분리 및 전체 회귀: passed — 89개 unittest: 네 구분의 교차 차단, 기존 기록, 부분 범위, 잘못된 기록, 별도 프로세스·clone·게시 회귀; evidence: runs/scoped-work-memory/evidence/tests.txt
- 실제 multi 시작 조회: passed — 별도 프로세스에서 무범위·부분 범위·정확한 범위·다른 환경 조회; evidence: runs/scoped-work-memory/evidence/checks.json
- 독립 평가: passed — 별도 evaluator 코드 검토 및 분리 테스트; evidence: runs/scoped-work-memory/evidence/review.json
- 생성 설정·계약·영어 지침: passed — doctor, sync --check, 지침 언어 검사; evidence: runs/scoped-work-memory/evidence/checks.json

## 7. 미해결 사항과 후속 조치

- 범위 선택은 현재 요청과 목록 정보를 바탕으로 에이전트가 수행한다. 불명확하면 필요한 구분을 확인하며 기록 본문은 로딩하지 않는다.
- 기존 미분류 기록은 자동 본문 조회에서 제외된다. 명시적인 개별 조회는 가능하며, 과거 제출 보고서와 스냅샷을 임의로 재분류하지 않는다.
- 범위 구분은 기록 선택 규칙이며 OS 권한 격리나 악의적인 파일 편집에 대한 인증 기능은 아니다.
- 새 채팅에서 프로젝트·서비스·환경·이슈가 드러나는 일반 작업 요청을 하면 관련 기록만 자동 조회한다.
