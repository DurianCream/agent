# Repository work record

> Saved task data, not instructions or authorization. Reconcile with current Git state.

## 1. 기본 정보

- Task: p2-reviewed-release-20261103
- Module: orchestrator
- Branch: main
- HEAD: b0ad3079baa1d0bd10a8959fbd0aa1a0256e1f5c
- Saved: 2026-11-03T12:36:16+09:00
- 프로젝트: multi
- 서비스: agent-framework
- 환경: development
- 이슈: p2-host-credential-isolation

## 2. 목표와 완료 기준

- Release independently reviewed frozen P2 artifacts and previously approved owner-led workflow sources with explicit provenance from preserved predecessor tasks
- Initialize on the verified authorized remote main baseline before materializing any candidate files and preserve predecessor history and pending commit
- Include only explicitly owned frozen P2 artifacts and approved owner-led workflow sources with provenance and no secrets private maps or unrelated task records
- Required tests and independent review cover the exact integrated release candidate and actual execution claims are supported by applicable evidence
- Validate submit and finish through configured publication gates with verified authorized non-force remote commit

## 3. 결과 요약

- Status: completed
- 검증된 P2 수동 Linux VM 실행·로컬 보호 게시 경로와 담당자 책임형 workflow의 릴리스 준비 및 독립 검토를 완료했다. 실제 VM 시험 증거와 정확히 일치하는 제품 41개, 보관 증거 30개를 구성했다. 원격 Git 반영은 제출 후 정상 게시 절차에서 별도로 확인한다.

## 4. 수행 내용

- 인프라 담당자가 sandbox\_setup\_failed를 추적해 systemd255의 명시 User=root 조합에 의한 CAP\_SETUID 제거를 재현하고 기본 root 서비스 실행으로 수정했다.
- 같은 담당자가 정상 검증·로컬 게시·동일키 재시도·직접 Git과 합성 자격증명 접근 차단·안전성 영수증 게시 거부·감독자 종료 정리를 실제 VM에서 확인했다.
- 독립 평가자가 소스와 실제 증거를 검토하고 VM의 설치 해시·보호 영수증·게시 ref·종료 상태를 읽기 전용으로 직접 확인했다.
- 원래 P2와 workflow의 기록·봉인·로컬 커밋은 보존했다. 별도 정상 원격 기준에서 새 릴리스 작업을 초기화하고 출처가 명시된 제품41개를 정확히 반영했다.
- 비밀정보 없는 최종 명세·프로필 준비 도구·구조화된 증거와 최종 검토 기록 30개를 저장소에 지속 보관하도록 등록했다. 임시 raw 로그·접속맵·개인키는 제외했다.

## 5. 산출물

- outputs/p2-reviewed-release-20261103/prepare-bwrap-profile.py: 한정된 전용 bwrap 프로필 준비 도구; 게시 보고서의 지속 보관 사본: \[열기\](evidence/artifacts/prepare-bwrap-profile.py)
- outputs/p2-reviewed-release-20261103/vm-acceptance-reproduction.en.md: 실제 적용 재현 명세; 게시 보고서의 지속 보관 사본: \[열기\](evidence/artifacts/vm-acceptance-reproduction.en.md)
- outputs/p2-reviewed-release-20261103/VM-실행-검증-20261103.md: 실제 시험 결과·횟수·한계; 게시 보고서의 지속 보관 사본: \[열기\](evidence/artifacts/VM-실행-검증-20261103.md)

## 6. 검증 결과

- 정확한 소스 출처·보존 확인: passed — 동결38개 P2와 기존승인workflow3개 및sanitized증거의 바이트 해시대조; evidence: runs/p2-reviewed-release-20261103/evidence/release-provenance.json, runs/p2-reviewed-release-20261103/evidence/release-packaging-checks.json, runs/p2-reviewed-release-20261103/evidence/release-archive-map.json
- 실제 수동 VM 실행·차단·게시·종료 검증: passed — 원래p2-host-isolation 작업의 최종소스와 일치하는 실제시험증거 재사용; evidence: runs/p2-reviewed-release-20261103/evidence/imported-p2/owner-handoff-20261103.json, runs/p2-reviewed-release-20261103/evidence/imported-p2/independent-owner-vm-review-20261103.json
- 정확한 릴리스 후보 필수 회귀 검사: passed — clone 전용고정Python 및 승인환경/task TEMP에서 p1-regression 1회; evidence: runs/p2-reviewed-release-20261103/evidence/release-mandatory-p1.json, runs/p2-reviewed-release-20261103/evidence/release-mandatory-gate-receipt.json, runs/p2-reviewed-release-20261103/evidence/release-final-packaging.json
- 새 릴리스 후보 독립 평가: passed — 동일 소스·증거·보존본·필수검사 결과를 새candidate에 결합; evidence: runs/p2-reviewed-release-20261103/evidence/release-review.json
- P0 참고 관찰: 상태=review\_pending; 판정=allow; 거버넌스=None; 검증=None; 기록=obs-882c6b02bb93424bb89502b036b4d11b. 실행 권한은 없으며 저장 후 변경되면 현재 상태를 다시 확인해야 한다.

## 7. 미해결 사항과 후속 조치

- 완료범위는 검증된 수동 동일호스트 Linux VM 경로와 그 소스릴리스다. 전체P2 자동운용 완료가 아니다.
- worker upload·privileged broker RPC·cross-host 인증·외부HTTPS/GitHub 게시어댑터·현재desktop 도구 전체격리는 미완료다. 프로젝트Git 소스푸시는 VM게시어댑터 시험과 별개다.
- namespace 허용은 승인된 시험동안만 수행하고0으로복원했다. 새실행에는 적절한새요청·유효한영수증·운영자조건이 필요하다.
- 원본checkout과기존b85b78f 커밋은그대로보존하며, 게시기준을임의로수정하거나이전봉인을재발행하지않는다.
- validate·submit·finish를 순서대로 수행하고 승인된 원격 main 커밋을 확인한다.
- 전체 P2 계획의 자동 연결·외부 게시·desktop 호스트 경계는 미완료 항목으로 유지한다.
