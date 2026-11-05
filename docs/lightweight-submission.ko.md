# 일반 문구 변경용 경량 제출 프로필

이 기능은 기존 제출 기록을 줄이지 않고, 제한된 일반 문구 변경에서 전체 회귀 검사 대신 문서 무결성 검사 세 개를 실행합니다. 초기 지원 범위는 대화에서 사용하는 light 등급보다 좁습니다.

현재 등록 예시는 `docs/prose/project-overview.txt`입니다. 활성화 설정과 문서가 커밋된 뒤 생성한 새 작업에서만 사용할 수 있습니다. 기존 작업의 등록 정보·전체 검사·스냅샷은 바뀌지 않습니다. 실제 절약 시간이나 비용은 측정하지 않았습니다.

## 적용 조건

- 기준 커밋의 `.agent-work/submission-profiles.json`에 정확한 경로가 등록된 기존 `docs/prose/*.txt` 일반 문서여야 합니다.
- UTF-8 일반 텍스트이며 실행 권한이 없어야 합니다. 새 파일·삭제·설정·코드·정책·명령·권한 안내·루트 README/AGENTS 변경은 지원하지 않습니다.
- 독립 평가자가 실제 변경과 영향, 불확실성을 확인하고 정확한 후보에 승인해야 합니다. 확장자나 작성자의 light 선언만으로 선택되지 않습니다.
- 보호 대상 소스·설정·지침이 기준 커밋과 달라지면 경량 선택이 거부됩니다. 혼합 변경은 전체 검사로 처리합니다.

## 사용 순서

기존 `init → transition → track` 절차로 범위와 파일 소유권을 기록합니다. `candidate`로 정확한 후보를 확인하고 독립 평가자의 검토 입력을 준비합니다. 입력 필드는 `shared/skills/submit-result/SKILL.md`의 Optional runtime profile commands 절에 정의되어 있습니다.

```text
python runtime/control_gate.py select-profile --task <task-id> --input runs/<task-id>/evidence/profile-input.json
python runtime/control_gate.py run-tests --task <task-id> --suite light-document-integrity
```

검사 후 기존 `assess` 명령으로 최종 결과와 실제 검사 증거를 묶습니다. 후보와 근거가 그대로이면 같은 실질 검토를 재사용하며, 별도의 전체 재감사를 요구하지 않습니다. 이후 `checkpoint → validate → submit → finish`를 그대로 수행합니다. `result.json`의 필수 필드와 생성되는 일곱 절 보고서는 유지됩니다.

후보·파일 집합·의존성·검토 근거가 바뀌면 이전 경량 승인을 재사용할 수 없습니다. 재검토하거나 아래 명령으로 전체 검사에 복귀합니다.

```text
python runtime/control_gate.py promote-full --task <task-id> --reason "변경 영향이 커져 전체 검사가 필요함"
```

전체 복귀 후에는 해당 작업에서 경량으로 되돌릴 수 없습니다. 최초 등록된 전체 검사와 현재 후보의 독립 검토가 필요합니다. 등록 목록을 수정하는 작업도 전체 경로를 사용하며, 과거 등록이나 봉인 기록을 직접 고치지 않습니다. 새로운 등록 목록은 게시 후 시작한 작업에만 적용됩니다.

문서 검사 세 개는 승인·근거의 최신성, 문서 형식·범위, 보호 대상의 불변성을 확인합니다. 의미 검토나 전체 회귀 검사를 대신했다는 뜻은 아닙니다. 평가자 신원은 로컬 선언이며 인증된 신원이 아닙니다. 같은 사용자 권한의 기록 조작이나 직접 Git 실행을 막는 운영체제 격리 기능도 아닙니다. 기존 원격 주소·브랜치·실제 커밋 내용 검사와 호스트 권한은 계속 적용됩니다.
