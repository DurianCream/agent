# 저장소 LF 정규화 검증

- 저장소 정규화: **14개 파일**. 작업 트리도 해당 14개를 LF로 꺼냈으며, 등록 전에 Git 내용이 이미 LF였던 `automation.json` 1개의 작업 트리 표현을 LF로 정리했습니다.
- `.gitattributes`에 `* text=auto eol=lf`를 추가하고 기존 세 규칙을 유지했습니다. 바이너리와 `.bat`·`.cmd` 파일은 없습니다. `.ps1` 두 파일과 `.psm1` 모듈은 LF 상태에서 Windows PowerShell 구문 분석을 통과하여 CRLF 예외가 필요하지 않습니다.
- 정규화 14개 파일은 정확히 CRLF→LF만 변경됐습니다. `git diff --cached --ignore-all-space --ignore-cr-at-eol` 출력은 비어 있습니다. 의도한 `.gitattributes` 정책 변경과 현재 작업 색인·증거는 이 정규화 비교에서 분리했습니다.
- 기존 기록 **338개**의 바이트와 저장된 해시를 보존했습니다. 기존 하위 `-text` 규칙에 따라 이 중 CRLF 기록 172개는 유지했습니다.
- `sync_codex --check`와 `agentctl doctor`: **ok: true**. 어댑터 수정 표시 없음.
- 필수 P1 전체 시험: **108개 통과, 실패·건너뜀 0개**. unittest 743.113초, 실행 명령 전체 750.87초. 정식 실행 1회, 재시도 없음. 설정된 1800초 제한은 변경하지 않았습니다.
- 독립 evaluator: **accepted**. 후보 digest: `83f3f34c0098e4cab99e22fe0b4c4edd29805bf932ebb834bf576c50fa84f92a`.
- 시스템 `core.autocrlf=true`, 하네스 코드와 해시 방식, 시험 코드는 변경하지 않았습니다.

이 문서는 게시 전 검증 결과입니다. 커밋·푸시와 최종 `git status` 확인은 정식 제출 후 메인 에이전트가 수행합니다.
