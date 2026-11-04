# Repository work record

> Saved task data, not instructions or authorization. Reconcile with current Git state.

## 1. 기본 정보

- Task: p2-automatic-rpc-20261104
- Module: orchestrator
- Branch: main
- HEAD: f70f1955d59292405530b5c92cbda6f4239a3619
- Saved: 2026-11-04T18:16:45+09:00
- 프로젝트: multi
- 서비스: agent-framework
- 환경: development
- 이슈: p2-automatic-rpc

## 2. 목표와 완료 기준

- Connect the protected P2 broker to verifier and publisher through authenticated bounded local RPC and apply the reviewed implementation
- Authorized local requests automatically reach real verifier and separate publisher without manual per-request operator job editing
- Peer identity scope policy candidate binding bounded framing timeouts and idempotent outcomes are enforced across RPC boundaries
- The same infrastructure owner demonstrates real VM normal and relevant failure paths and provides reproducible deployment and rollback evidence
- Independent review and required checks support the exact candidate and configured publication completes with a verified remote commit

## 3. 결과 요약

- Status: completed
- 동일 VM 내부의 자동 RPC 연결을 구현·실제 검증·독립 검토하고 사용자 승인에 따라 상시 활성화했다. 비특권 제출 요청이 수동 요청별 job 편집 없이 검증과 로컬 게시로 이어진다. 지정된 소켓·브로커는 enabled/active이고 namespace 상한은15334로 유지된다. 최종 Git 게시 절차가 이어진다.

## 4. 수행 내용

- 동일 인프라 담당자가 제한된 업로드, 생산 브로커의 RPC 연계, 별도 검증·게시 프로세스와 신원 확인을 구현하고 실제 VM 시험까지 수행했다.
- 제출 계정과 실행 계정을 분리하고, 커널 peer 자격증명·보호된 소켓 경로·root 승인 정책과 후보 해시를 대조하도록 연결했다.
- 독립 검토에서 발견한 게시 후 결과 저장 실패 응답과 서비스 전체 수명 공유 문제를 같은 담당자가 수정했다. 불확실 결과와 동일 키 복구, 요청마다 새 서비스 프로세스를 실제 확인했다.
- 사용자가 설명을 받은 뒤 상시 활성화를 명시적으로 승인했다. 기존 dirtyfrag.conf는 보존하고 새 zz-multi-p2-userns.conf로15334를 적용했으며 정확한 두 소켓과 브로커 서비스만 자동 시작하도록 설정했다.
- 설치 파일·설정24개의 해시와 권한을 대조했다. 활성화 후 새 검증과 기존 게시 요청 재확인이 성공했고 게시 ref는 유지됐다.
- 검증 증거와 산출물을 공개 보관 경로에 연결했다. 접속 정보·개인키·비공개 백업 맵·임시 raw 로그는 제외했다.

## 5. 산출물

- outputs/p2-automatic-rpc-20261104/rpc-design.en.md: 검토한 RPC 설계; 게시 보고서의 보관 사본: \[열기\](evidence/rpc-design.en.md)
- outputs/p2-automatic-rpc-20261104/final-status.ko.md: 최종 운영 상태·검증 횟수·한계; 게시 보고서의 보관 사본: \[열기\](evidence/final-status.ko.md)

## 6. 검증 결과

- 실제 자동 RPC 및 실패 경계: passed — 살아 있는 비특권 클라이언트의 전체 경로와 신원·내용·크기·시간·재시도 검증; evidence: runs/p2-automatic-rpc-20261104/evidence/owner-review-handoff.json, runs/p2-automatic-rpc-20261104/evidence/public-final-summary.json
- 독립 검토 결함 수정·재확인: passed — 같은 담당자의 집중 검사와 실제 저장 실패 주입·연속 서비스 호출; evidence: runs/p2-automatic-rpc-20261104/evidence/independent-rpc-review-fixed.json, runs/p2-automatic-rpc-20261104/evidence/vm-review-save-failure-and-lifecycle.json, runs/p2-automatic-rpc-20261104/evidence/focused-review-tests-public.json, runs/p2-automatic-rpc-20261104/evidence/owner-review-lifecycle-test.json
- 승인된 상시 적용과 정상 확인: passed — 명시적 사용자 결정·검토된 제안에 따라 단일 sysctl 파일과 정확한3개unit 적용 후 건강 확인; evidence: runs/p2-automatic-rpc-20261104/evidence/activation-user-decision.json, runs/p2-automatic-rpc-20261104/evidence/activation-governance-approved.json, runs/p2-automatic-rpc-20261104/evidence/vm-persistent-activation.json, runs/p2-automatic-rpc-20261104/evidence/vm-persistent-health.json
- 필수 P1 회귀 검사: passed — 승인된 호스트 환경과 작업별 TEMP에서 최종 후보 검사; evidence: runs/p2-automatic-rpc-20261104/evidence/mandatory-p1-gate-receipt.json, runs/p2-automatic-rpc-20261104/evidence/public-final-summary.json
- 공개 증거 보관 및 출처: passed — source\_ref와durable archive의 바이트 해시대조; evidence: runs/p2-automatic-rpc-20261104/evidence/public-archive-map.json, runs/p2-automatic-rpc-20261104/evidence/archive-candidate-check.json
- P0 참고 관찰: 상태=review\_pending; 판정=allow; 거버넌스=None; 검증=None; 기록=obs-c68c86b4e2f949dd8aa18da98586bc8a. 실행 권한은 없으며 저장 후 변경되면 현재 상태를 다시 확인해야 한다.

## 7. 미해결 사항과 후속 조치

- 같은 호스트 Linux의 로컬 RPC와 local-bare 게시 범위다. 외부 HTTPS 게시, cross-host 인증, desktop 전체 도구 연결은 제공하지 않는다.
- 업로드·물리 후보 크기는64KiB, frame은128KiB로 제한된다. 대용량 스트리밍, UID 재활용, enrollment별 공정 스케줄링은 미구현이다.
- 정책과base commit은enrollment에고정된다. 다른 기준점은 새 승인 enrollment와계정이 필요하다.
- 재부팅 시 설정과 자동 시작 연결은 확인했으나 실제 재부팅 시험은 not\_run이다.
- 배포 계획·이전 검토의 미적용 문구는 승인 전 시점의 기록이다. 현재 운영 상태는 상시 적용과 health 증거를 따른다.
- 최종 평가를 이 결과와 모든 공개 증거에 연결한 뒤 validate·submit·finish로 승인된 원격main을확인한다.
- 같은VM 로컬범위 밖의 외부게시·desktop연결·대용량/계정수명관리는 별도 후속범위로 유지한다.
