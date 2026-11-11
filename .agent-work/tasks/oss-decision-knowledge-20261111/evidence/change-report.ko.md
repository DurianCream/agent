# 오픈소스 도입 결정 지식 기록 절차

도입 검토를 시작할 때 이전 결정을 조회하고, 독립 검수를 마친 결론을 기존 지식 색인에 한 건 추가하도록 절차를 수정했습니다. 이번 작업은 실제 도구의 도입 검토가 아니므로 `shared/knowledge/index.json`은 비어 있는 원본 그대로 유지합니다.

## 바뀐 파일

| 파일 | 변경 내용 |
| --- | --- |
| `shared/skills/oss-research/SKILL.md` | 같은 대상의 이전 결정 조회, 완료된 결정 추가, 중복 방지, 재검토 기본값과 비밀정보 제외 규칙 |
| `shared/skills/skills.json` | `oss-research` 버전 1.2.0 → 1.3.0 |
| `modules/oss-rnd/module.json` | 스킬 버전 참조 갱신, 모듈 0.3.0 → 0.4.0, 쓰기 대상에 정확한 `shared/knowledge/index.json` 경로 선언 |
| `modules/oss-rnd/adoption-report.ko.md` | ‘이전 결정’ 및 지식 기록 안내, 재검토 날짜와 근거 기재 |
| `.agents/skills/oss-research/SKILL.md` | 스킬 어댑터 재생성 |
| `.codex/agents/oss-rnd.toml` | 모듈 어댑터 재생성 |
| `runtime/native-map.json` | 위 두 어댑터의 생성 해시 갱신; 실행 코드 변경 없음 |

모듈의 쓰기 범위는 요청된 색인 파일 하나만 명시합니다. 이 선언은 OS 권한을 부여하지 않으며, 사용자 허용 범위와 기존 작업 소유권 절차를 그대로 따릅니다. 지식 스키마·기존 색인·과거 보고서·하네스 코드·시험 코드는 수정하지 않았습니다. 기존 작업의 스냅샷은 보존하며 새 작업부터 새 스킬 버전을 사용합니다.

## 기록과 재사용 규칙

정식 상위 프로젝트 URL과 확인된 별칭으로 같은 대상을 찾고, 범위·프로젝트·용도·버전·날짜를 비교합니다. 관련 결정의 ID와 결론을 보고서의 ‘이전 결정’에 적습니다. 기한이 지난 결정이나 대체된 결정은 과거 자료로 표시하며 현재 판단으로 간주하지 않습니다. 다른 프로젝트의 결론도 적용 가능성을 다시 검토합니다. 색인 또는 출처를 읽지 못한 경우 ‘이전 결정 없음’으로 처리하지 않습니다.

완료된 검토는 기존 필드 `id`, `scope`, `project_id`, `claim_kind`, `statement`, `sources`, `observed_at`, `review_after`, `supersedes`만 사용합니다. 같은 ID와 내용의 재실행은 중복 추가하지 않습니다. 대체 관계는 새 항목의 `supersedes`에 적고 과거 항목은 보존합니다. 비밀값, 자격증명, 사내 호스트명·IP, 비공개 엔드포인트 URL과 불필요한 개인정보는 문장과 출처에 넣지 않습니다.

## 재검토 기본값과 근거

- **도입 권고: 6개월.** 이미 수용 가능한 것으로 판단한 대상을 반복 조사하는 비용과 정기적인 재확인의 균형을 위한 운영 기본값입니다.
- **조건부 권고·보류·비권고: 3개월.** 해결되지 않은 조건이나 차단 요인이 달라졌는지 더 이르게 확인하기 위한 기본값입니다.
- 실제 결정 시각부터 달력 월로 계산하고 시간대를 보존합니다. 해당 일이 없는 달은 말일로 맞춥니다. 증거상 필요하면 더 이른 날짜와 그 이유를 적습니다.
- 보안 공지, 라이선스·지원 정책 변경, 주요 릴리스, 요구사항 변경은 기한 전 재검토 사유입니다. 날짜를 저장하는 절차이며 자동 알림을 새로 구현하지는 않습니다.

이 기간은 실측에 기반한 안정성 보증이나 외부 표준이 아니라 이번 작업에서 정한 운영 정책입니다.

## 가상 결정 한 건 — 실제 색인에 넣지 않은 예시

아래 대상·프로젝트·판단 근거는 모두 형식 설명을 위한 가정입니다. 실제 제품을 조사하거나 권고한 결과가 아닙니다. `example.invalid`는 가상의 대상 식별자이며, 출처는 이 보고서의 예시 설명만 가리킵니다.

가상 근거: 예시 프로젝트가 요구하는 로컬 캐시 기능과 복구 절차를 충족했다고 가정하고 도입을 권고합니다. 이전 결정은 없다고 가정합니다.

```json
{
  "id": "oss-decision-example-20261111-cedarcache",
  "scope": "project",
  "project_id": "example-project",
  "claim_kind": "decision",
  "statement": "Illustrative only: adoption of fictional CedarCache v1.0 (https://example.invalid/cedarcache) is recommended for the example project's local cache, assuming its required cache and recovery criteria are met. This is not an actual adoption assessment.",
  "sources": [
    "outputs/oss-decision-knowledge-20261111/change-report.ko.md"
  ],
  "observed_at": "2026-11-11T14:00:00+09:00",
  "review_after": "2027-05-11T14:00:00+09:00",
  "supersedes": null
}
```

문장의 한국어 뜻: “가상의 CedarCache v1.0이 예시 프로젝트의 캐시·복구 요건을 충족했다고 가정하여 로컬 캐시에 도입을 권고한다. 실제 도입 검토는 아니다.” 도입 권고 예시이므로 관찰 시각 6개월 뒤를 재검토일로 적었습니다. 예시 타임스탬프도 가상 값입니다.

## 검증

영향 범위 선택 결과는 **impact**, 선택된 suite는 **`impact-document-integrity` 하나**입니다. 변경한 일곱 경로 모두 등록·어댑터·결과 계약·문서 무결성 규칙에 매핑되었고, 보호된 런타임 변경이나 매핑되지 않은 경로가 없어 전체 `p1-regression`은 선택되지 않았습니다.

선택된 suite는 **4개 검사 통과**, 호출 전체 소요 시간 **6.887초**였습니다. 실제 시험 로그의 검사 시간과 호출 준비·결과 기록까지 포함한 전체 시간을 구분합니다. 단일 실행이며 재시도하지 않았습니다. `sync_codex --write`, `--check`, `doctor`도 통과했습니다.

별도 `skill-creator`의 `quick_validate.py`는 시스템·프로젝트 Python에서 모두 `PyYAML` 부재로 검사 시작 전에 중단됐습니다. 저장소 의존성을 추가하지 않았으며, 이를 통과로 세지 않습니다. 필수 기존 suite와 어댑터·등록 검사, 독립 의미 검수로 변경을 확인합니다.
