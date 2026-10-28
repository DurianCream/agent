# multi: 모듈형 에이전트

코딩·인프라·오픈소스 R&D와 공통 관리 역할을 제공하는 프로젝트입니다. 전문 역할이 작업하고 별도 evaluator가 검증합니다.

에이전트 지침은 영어, 사용자 보고서는 한국어로 작성합니다. 작업 대상 저장소별로 .agent-work/에 작업 명세를 남겨 새 채팅에서 다시 읽을 수 있습니다.

- [설치 및 작업 기록 사용 안내](docs/작업기록-사용안내.md)
- 에이전트 시작 규칙: AGENTS.md
- 역할 목록: registry.json
- 작업 기록: [.agent-work/INDEX.md](.agent-work/INDEX.md)

Python 3.11 이상과 Git이 필요합니다. 처음 clone한 뒤 python runtime/sync_codex.py --write와 python runtime/agentctl.py doctor를 실행하세요. 모델·호스트 기능과 훅 지원은 실행 환경에 따라 달라집니다.
