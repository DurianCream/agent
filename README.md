# Codex 인프라 멀티 에이전트 프로토타입

GitHub 관리 대상은 비공개 저장소 `DurianCream/private`다. 하나의 Git 저장소 안에 다섯 역할 폴더를 둔다. 역할별 폴더는 지침·스킬의 관리 원본이며 실제 업무의 코드 작업 공간이나 상주 에이전트 서버가 아니다.

## 폴더와 역할

```text
ai-agent-repos/
├── conductor/        # 주 대화의 조율 지침
├── planner/          # 조사·계획 역할
├── worker/           # 승인 범위의 작업 역할
├── critic/           # 완료 버전 비평 역할
└── acceptance-gate/  # 최종 증거 검사 역할
```

기본 흐름은 **조율 → 계획 → 작업 → 비평 → 최종 증거 검사**다. 주 대화가 결과 전달·실행 기록 저장·수정 루프·최종 보고를 맡는다. 같은 결과의 검수는 작업 이후 진행하며 독립적인 작업만 병렬로 배정한다. 운영 변경은 대상과 행위의 사용자 승인 및 실제 플랫폼 권한이 있어야 한다.

## 수정 위치

| 수정할 내용 | 관리 원본 |
|---|---|
| 주 대화의 기본 지침·분담 규칙 | `conductor/AGENTS.md`의 프로토타입 절 |
| 조율 절차 | `conductor/skills/infra-orchestrate/SKILL.md` |
| 하위 역할 등록 정의 | 각 역할 폴더의 `codex/infra_*.toml` |
| 역할별 상세 행동 | 각 역할 폴더의 `skills/*/SKILL.md` |
| 기존 서버·네트워크 진단 | `planner/skills/infra-server-triage`, `planner/skills/infra-network-diagnosis` |
| 실행 기록 형식·검사기 | `acceptance-gate/skills/infra-evidence-gate/references/protocol.md`, `scripts/check_evidence.py` |

현재 설치 원본 경로는 `/home/dhyun/ai-agent-repos`다. 전역 `AGENTS.md`·스킬은 원본에 심볼릭 링크로 연결되어 있고 역할 TOML은 Codex 설정의 `config_file`로 연결된다. 파일 안의 절대경로는 이 설치 기준이므로 다른 환경에 옮길 때 경로·링크·역할 등록·새 대화의 스킬 로딩을 다시 확인해야 한다. 저장소 복제만으로 다른 환경의 연결이 자동 완성되지는 않는다.

## 기록과 검증 범위

주 대화는 이 저장소 밖의 허용된 로컬 실행 폴더에 `request.json`, `plan.json`, `work.json`, `critique.json` 및 민감정보를 제거한 증거를 저장한다. 백업·실행 증거·자격증명은 저장소에 넣지 않는다.

비평 역할의 `PASS`, 로컬 증거 검사기의 `PASS`, Codex의 native 역할 선택·전체 단계 실행 검증은 서로 다른 결과다. 검사기의 통과는 파일·해시·참조 등 기록 정합성만 확인하며 증거 내용의 진위나 실제 서비스 성공을 보장하지 않는다. 전체 자동 역할 호출이 검증됐는지는 실제 실행 증거를 별도로 확인해야 한다.

이 구성은 계속 수정할 프로토타입이다. [자세한 사용법과 적용 한계](conductor/README.md), [단계 전달 기록 형식](acceptance-gate/skills/infra-evidence-gate/references/protocol.md)을 참고한다. Claude 설정과 운영 인프라는 이 저장소 통합의 변경 대상이 아니다.
