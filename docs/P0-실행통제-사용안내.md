# P0 계약 검증과 관찰 모드 사용 안내

## 1. 기본 정보

P0의 계약 검증기와 관찰 모드 정책 판정기를 사용한다. 계약 검증은 입력 형식·정규화 해시·일부 의미 제약을 확인한다. 관찰 모드는 선언된 요청·문맥·정책을 비교해 판단과 이유를 출력한다.

관찰 결과는 실행 승인이 아니다. `executable: false`, `authority_verified: false`이며 도구 실행, 자격증명 발급, 서명된 승인 생성, 운영 환경 변경을 하지 않는다. 거버넌스의 권고나 검증 담당의 평가도 실행 권한으로 변환하지 않는다.

## 2. 목표 및 완료 기준

Python 3.11 이상을 사용한다. 이 작업에서는 Windows의 Python 3.12에서 검증한다. 프로젝트 루트에서 별도 가상환경에 고정 의존성을 설치한다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r runtime/control-requirements.txt
```

Linux에서는 `.venv/bin/python`을 사용한다. 기존 역할·결과 관리 CLI는 그대로 유지되며 새 P0 도구만 추가 의존성을 사용한다. 프로그램이 실행 중 의존성을 자동 설치하지 않는다.

## 3. 결과 요약

| 기능 | 확인하는 내용 | 확인하지 않는 내용 |
|---|---|---|
| 계약 검증 | JSON 파싱, 지원 버전·필드·타입, 정규화 해시와 계약상 제약 | 서명자의 신원, 승인의 법적 효력, 테스트가 실제 실행됐는지 |
| 관찰 정책 판정 | 선언된 범위·대상·정책·기존 승인 조건의 일치 | 문맥 파일이 실제 권한을 증명하는지, 운영 시스템에서의 접근 권한 |
| 출력 | 구조화된 판단·안정적인 이유 코드·검사 한계 | 원본 요청·문맥 전체, 비밀값, 실행 가능한 승인 토큰 |

관찰 판정은 `allow`, `deny`, `require_review`다. `allow`도 주어진 선언을 기준으로 한 모의 판단이며 실제 행동을 허용하는 자격증명이 아니다. 문맥·정책 파일을 편집해 결과를 바꾸는 것은 시뮬레이션 입력을 바꾸는 것이지 실제 권한을 얻는 것이 아니다.

정상적인 계약 검사와 관찰 판정은 종료 코드 `0`을 반환한다. 관찰 결과가 `deny`나 `require_review`여도 판정 자체가 정상 완료되면 `0`이다. 잘못된 입력·문맥·정책, 지원하지 않는 명령·레코드, 파일·의존성 오류는 `2`다. 자동화에서는 종료 코드만 보고 실행을 허용하지 말아야 한다.

## 4. 수행 내용

### 계약 검사

```powershell
.\.venv\Scripts\python.exe runtime/controlctl.py validate --input runtime/tests/fixtures/control-contracts/action-request.json
```

검증기는 중복 키, 잘못된 인코딩·문자, 허용 범위를 벗어난 숫자, 과도한 입력, 알 수 없는 필드·버전, 해시 불일치 등을 거부한다. 해시는 RFC 8785 정규화를 사용한다. 스키마 참조는 로컬에서만 해석하며 외부 스키마 URL을 조회하지 않는다.

입력 한도는 128 KiB, 중첩 32단계, 노드 10,000개다. P0 숫자 형식은 안전한 정수만 지원하며 실수는 거부한다. 시각은 대문자 `Z`로 끝나는 UTC이고 소수 초는 최대 6자리다. 날짜·URI·UUID 검사는 환경의 선택적 기본 기능에 맡기지 않고 명시적으로 적용한다. 이 제약은 초기 구현의 의미 검사이며 이전 설계 스냅샷의 형식을 수정하지 않는다.

### 관찰 판정

```powershell
.\.venv\Scripts\python.exe runtime/controlctl.py observe --input runtime/tests/fixtures/control-observe/request.json --context runtime/tests/fixtures/control-observe/context.json
```

기본 정책은 `shared/policies/execution-controls.observe.json`이다. 같은 지원 형식의 설정을 모의 평가하려면 `--policy`로 지정한다. 현재 지원 프로필은 `development-observe`, 버전은 `0.1.0`이며 알 수 없는 프로필·버전은 거부한다. 이 파일 선택은 신뢰된 정책 배포나 활성화를 의미하지 않는다.

예제 파일은 합성 데이터이고 시간이 고정돼 있다. 현재 시각에서 만료된 요청은 `deny` 관찰 결과를 내는 것이 정상이다. 테스트는 시각을 고정해 허용·거부·추가 검토 사례를 재현한다. 해시에 포함된 필드를 바꾸면 해당 요청의 정규화 해시도 다시 계산해야 한다.

입력 파일에 든 산출물 참조를 따라 파일을 읽거나 URL에 접속하지 않는다. 본문 내용 기반 비밀정보 검사도 수행하지 않으므로 출력에 `content_checks: not_performed`를 표시한다. 데이터 등급은 입력에 선언된 값이며 실제 내용을 검사한 결과가 아니다.

## 5. 산출물

| 위치 | 역할 |
|---|---|
| `runtime/control_contracts.py` | 엄격한 JSON 로딩, 로컬 계약 검증, 정규화·해시 |
| `runtime/control_policy.py` | 실행 부작용이 없는 관찰 정책 판정 |
| `runtime/controlctl.py` | 검사·관찰용 CLI |
| `runtime/control-requirements.txt` | 버전이 고정된 라이브러리 목록 |
| `shared/schemas/control-*.schema.json` | 계약·관찰 문맥·관찰 결과의 형식 |
| `shared/policies/execution-controls.observe.json` | 관찰용 정책 예제 |
| `runtime/tests/test_control*.py` | 새 기능의 정상·오류·악성 입력·출력 검증 |

공통 `result.schema.json` 1.0.0과 과거 작업 스냅샷은 변경하지 않는다. 새 계약은 기존 제한형 검증기에 억지로 추가하지 않고 별도 검증 경로를 사용한다.

## 6. 검증 결과

새 기능 테스트:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s runtime/tests -p "test_control*.py"
```

전체 회귀 테스트:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s runtime/tests
```

이번 작업의 실제 실행 결과와 독립 검토는 `p0-control-observe`의 결과 보고서에 저장한다. 계약 구조가 통과하거나 모의 정책이 `allow`를 반환했다는 사실을 실제 권한·승인·보안 격리 검증 통과로 해석하지 않는다.

## 7. 미해결 사항 및 다음 조치

이번 P0 범위는 계약 검증기와 관찰 판정기다. 신뢰된 작업 등록부·승인 저장소, 암호 서명 검증, 실행기, 강제 정책 관문, 자격증명 격리, 직접 실행 우회 방지, 실제 본문 유출 검사와 지속 감시 서비스는 후속 구현 대상이다.

현재 `agentctl`의 작업 초기화가 이 P0 계약과 정책을 신뢰된 실행용 등록부에 자동 등록하지는 않는다. 후속 작업은 이 관찰 API를 그대로 실행 권한으로 사용하지 말고 독립적인 신원·정책·승인·실행 경계를 마련해야 한다.

참고: [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html), [jsonschema의 참조 처리](https://python-jsonschema.readthedocs.io/en/stable/referencing/), [rfc8785 라이브러리](https://pypi.org/project/rfc8785/).
