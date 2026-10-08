# Codex 멀티 에이전트 프로토타입

현재 구성은 **조율 → 계획 → 작업 → 비평 → 최종 증거 검사**다. 실제 사용 중 발견한 문제에 맞춰 역할 지침과 기록 형식을 수정하는 출발점이다.

## 역할과 관리 원본

| 단계 | 실행 담당 | 원본 역할 폴더 |
|---|---|---|
| 조율 | 주 대화 | `../conductor` |
| 계획 | `infra_planner` | `../planner` |
| 작업 | `infra_worker` | `../worker` |
| 비평 | `infra_critic` | `../critic` |
| 최종 증거 검사 | `infra_acceptance` | `../acceptance-gate` |

다섯 디렉터리는 GitHub `DurianCream/private` 단일 Git 저장소 안의 역할 관리 폴더다. 저장소 루트는 `/home/dhyun/ai-agent-repos`이며 각 역할 폴더를 같은 저장소의 변경 이력으로 관리한다. Git 연결·원격 반영의 실제 완료 여부는 해당 작업의 검증 결과로 확인한다.

## 수정할 곳

- 주 대화의 기본 분담 규칙: `AGENTS.md`. 기존 인프라 지침을 유지하고 마지막 프로토타입 절을 편집한다.
- 조율 절차: `skills/infra-orchestrate/SKILL.md`.
- 하위 역할의 이름·설명·기본 실행 환경: 각 역할 폴더의 `codex/infra_*.toml`.
- 각 역할의 상세 행동: 해당 역할 폴더의 `skills/*/SKILL.md`.
- 기록 형식과 검사 로직: `../acceptance-gate/skills/infra-evidence-gate/references/protocol.md`, `scripts/check_evidence.py`.
- 서버·네트워크 진단 스킬 원본: `../planner/skills/infra-server-triage`, `../planner/skills/infra-network-diagnosis`.

전역 `AGENTS.md`와 스킬은 원본 파일·폴더를 심볼릭 링크로 연결한다. 역할 TOML은 Codex의 `agents.<name>.config_file`로 직접 연결한다. 원본을 수정한 뒤 새 Codex 대화에서 로딩 상태를 확인한다. 별도로 텍스트 사본을 다시 붙여 넣는 과정은 필요하지 않다.

## 실행 방식

주 세션이 조율하고 나머지 단계를 필요한 순서로 호출한다. 독립 작업은 같은 작업 역할에 나누어 병렬 배정할 수 있다. 같은 산출물의 최종 검수는 결과가 준비된 뒤 진행한다. 실제 동시 실행 수는 플랫폼과 활성 설정의 제한을 따른다.

새 대화에서 구성을 명시적으로 사용하려면 다음과 같이 요청할 수 있다.

```text
$infra-orchestrate
이 작업을 조율 → 계획 → 작업 → 비평 → 최종 증거 검사 순서로 진행해 줘.
실제 작업 목표와 허용된 대상·행위 범위: 여기에 작성
```

마지막 줄은 실제 목표와 승인 범위로 교체하는 설명용 자리표시자다. 위 요청만으로 별도의 운영 시스템 변경이 승인되는 것은 아니다.

최종 증거 검사 프로그램은 실행 폴더만 읽고 정합성 결과를 표준 출력으로 반환한다. 직접 명령을 실행하거나 운영 배포를 하지 않는다. 실행 예와 반환 값은 [프로토콜](../acceptance-gate/skills/infra-evidence-gate/references/protocol.md)에 있다. 읽기 전용 역할의 결과 기록은 조율자가 저장한다.

## 적용 범위와 검증 한계

Codex 사용자 설정에 등록했다. 프로젝트별 지침·설정이나 시작 옵션이 기본 동작에 영향을 줄 수 있고, 이미 열려 있는 대화에 새 역할·스킬이 자동 재로딩된다고 보장하지 않는다. 새 대화에서 확인한다.

계획·비평·증거 검사 역할에는 읽기 전용 기본값을 두고 작업 역할에는 워크스페이스 쓰기 기본값을 둔다. 실제 권한은 플랫폼과 부모 세션의 권한이 결정하며 역할 지침으로 권한을 추가할 수 없다.

정합성 프로그램의 통과는 증거 내용의 정확성이나 실제 서비스 상태를 보증하지 않는다. 최종 담당은 원래 목표에 맞는 증거인지도 확인한다.

## 되돌리기

설치 시점의 설정·기존 진단 스킬은 `/home/dhyun/.codex-orchestration-backups`의 이번 설치 백업과 `manifest.json`에 보관했다. 되돌릴 때 변경 대상 전역 설정·링크만 원래 상태로 복구한다. 역할 원본 폴더와 이후 작업 산출물은 별도 보관하며 임의로 삭제하지 않는다. 설치 이후 다른 변경이 있으면 비교 후 필요한 부분만 복원한다.

## 공식 근거

- [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Configuration Reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Custom instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [Build skills](https://learn.chatgpt.com/docs/build-skills)
