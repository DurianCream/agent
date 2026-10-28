# 작업 결과

## 1. 기본 정보

- 작업 ID: softether-ssl-vpn-runbook-20261027
- 담당 모듈: orchestrator / 0.2.0
- 결과 규격: 1.0.0
- 작성 시각: 2026-10-27T14:38:12+09:00
- 고정 버전: snapshot 10a3ef778c7f99d79697736f08acc57334278081ad38923500e90090e1aee9de (11개 파일)
- 스킬 버전: submit-result@1.0.0
- 정책 버전: common@1.0.0

## 2. 목표와 완료 기준

既存RADIUSを維持するLinux SoftEther native SSL-VPNアップグレード・監査設定とNAT下Windows端末の接続履歴確認の手順書作成

- 기존 RADIUS와 구성·데이터를 보존하는 Linux/Windows 업그레이드·검증·복구 절차를 공식 근거로 제시한다 (검증: upgrade-source-review, independent-review)
- 감사로그 활성화와 NAT PC정보·접속 및 종료의 실제 조회 명령·연계 예시를 정확히 제시한다 (검증: audit-source-review, independent-review)
- 모의 예시와 실측을 구분하고 NAT·단말식별·종료누락·로그유실 한계 및 인수 시험을 명시한다 (검증: central-plan-review, synthetic-check, independent-review)
- 별도 evaluator가 핵심 명령과 안전성·근거를 검증한다 (검증: independent-review)

## 3. 결과 요약

- 상태: 완료
- 요약: 기존 RADIUS를 보존하는 SoftEther 고유 SSL-VPN 업그레이드·복구, Windows Client 점검, 감사로그 활성화와 NAT PC·접속/종료 조회 절차서를 완료했다. 별도 evaluator가 공식 근거와 최종 8개 파일을 검증했다. 실제 운영 시험은 not\_run이다.

## 4. 수행 내용

- oss-rnd가 공식 Stable 4.44 재확인과 Linux/Windows 업그레이드·설정 보존·실패기간 로그를 포함한 복구 절차를 작성했다.
- infrastructure가 로그 설정 GUI/vpncmd, DHCP 주소 이력, 현재 세션 및 사용자→CID→SID→PC→종료 조회를 검증해 작성했다.
- 메인이 통합 절차서, 선택적 rsyslog TLS 파일 수집 템플릿과 인수 시험표를 작성했다.
- ConfigGet/ServerCertGet의 위치 인수, RadiusServerGet/SessionGet의 민감 출력, Message-Authenticator의 Hub 직하 위치 및 DHCP 설정 덮어쓰기 위험을 공식 근거로 확인했다.
- 합성 11개 이벤트의 구조·연결·NAT·엔진ID·종료누락 일관성을 확인하고 실제 로그/원문 파서 시험과 구분했다.
- 별도 evaluator가 공식 문서·고정 소스·예제 조회와 복구 안전성을 독립 검토하고 정확한 ID 검색 보완을 확인했다.

## 5. 산출물

- [outputs/softether-ssl-vpn-runbook-20261027/runbook.md](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-ssl-vpn-runbook-20261027/runbook.md>): 통합 단계별 운영 절차서 (SHA-256: 4a2ddc9e418a08aa51e7a030f7e5a7bb78784c950ce775abb23ae4d37187a72b)
- [outputs/softether-ssl-vpn-runbook-20261027/upgrade-steps.md](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-ssl-vpn-runbook-20261027/upgrade-steps.md>): Linux/Windows/RADIUS 보존·업그레이드·롤백 세부 명령 (SHA-256: 60e4554afd22ecd29b2e4073c16655d3b715b443a2f349767ee96202223bfb75)
- [outputs/softether-ssl-vpn-runbook-20261027/audit-steps.md](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-ssl-vpn-runbook-20261027/audit-steps.md>): 감사로그 설정 및 현재/과거 접속·PC·종료 조회 (SHA-256: b7bff80a6a30594fde055790086d8a3592a98f02d636b2703cf97d2ca0b7891c)
- [outputs/softether-ssl-vpn-runbook-20261027/central-logging.md](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-ssl-vpn-runbook-20261027/central-logging.md>): 로컬 원본 보존과 선택적 중앙 TLS 수집 절차 (SHA-256: dee2acf5949386af848f7b1411514d34a13fde656abd1116975611eb3f5b3555)
- [outputs/softether-ssl-vpn-runbook-20261027/acceptance-tests.md](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-ssl-vpn-runbook-20261027/acceptance-tests.md>): 실환경 인수 시험표(현재 not\_run) (SHA-256: 206d702350a0d4a40be52b958c02460f6d1c4376e9ccbeb424e2eb49fd2e4035)
- [outputs/softether-ssl-vpn-runbook-20261027/examples/rsyslog-softether.conf.example](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-ssl-vpn-runbook-20261027/examples/rsyslog-softether.conf.example>): 현장 수정·검증 전제 rsyslog 파일 수집/TLS 예제 (SHA-256: a5d76884aab6261905698f45aa7935b56f32045b05f777416338b841a511f800)
- [outputs/softether-ssl-vpn-runbook-20261027/examples/synthetic-normalized-events.jsonl](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-ssl-vpn-runbook-20261027/examples/synthetic-normalized-events.jsonl>): 실제 로그가 아닌 합성 정규화 이벤트 설명 데이터 (SHA-256: 5d235e98fd5c71ba0aadf31d0f78e48037815894dce3b1d7a4a026582e754f37)
- [outputs/softether-ssl-vpn-runbook-20261027/examples/README.md](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-ssl-vpn-runbook-20261027/examples/README.md>): 합성 데이터 의미와 한계 (SHA-256: a2682d2126be7c7ef62b11841ba5f0fb8043f5cbda5390eea803d5c87ec63676)

## 6. 검증 결과

- upgrade-source-review · 업그레이드·RADIUS 보존·복구 절차 근거 확인: 통과
  - 방법: 공식 매뉴얼/배포 목록/Stable v4.44 고정 소스 대조
  - 증거: [outputs/softether-ssl-vpn-runbook-20261027/upgrade-steps.md](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-ssl-vpn-runbook-20261027/upgrade-steps.md>)
  - 비고: 문서 절차의 검토이며 운영 명령 실행은 not\_run.
- audit-source-review · 로그 설정·NAT·PC·접속종료 조회 근거 확인: 통과
  - 방법: 공식 명령/NodeInfo/로그 문자열 및 설정 변경 범위의 정적 대조
  - 증거: [outputs/softether-ssl-vpn-runbook-20261027/audit-steps.md](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-ssl-vpn-runbook-20261027/audit-steps.md>)
  - 비고: 조회는 운영 원문에서 재검증해야 한다. 단말 보고값·실행 인스턴스 ID를 자산 신원과 구별했다.
- central-plan-review · 통합·중앙 수집·인수 시험 범위 검토: 통과
  - 방법: 공식 imfile/omfwd/TLS/queue 기능과 사용자 조건에 따른 설계 검토
  - 증거: [outputs/softether-ssl-vpn-runbook-20261027/runbook.md](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-ssl-vpn-runbook-20261027/runbook.md>), [outputs/softether-ssl-vpn-runbook-20261027/central-logging.md](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-ssl-vpn-runbook-20261027/central-logging.md>), [outputs/softether-ssl-vpn-runbook-20261027/examples/rsyslog-softether.conf.example](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-ssl-vpn-runbook-20261027/examples/rsyslog-softether.conf.example>), [outputs/softether-ssl-vpn-runbook-20261027/acceptance-tests.md](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-ssl-vpn-runbook-20261027/acceptance-tests.md>), [runs/softether-ssl-vpn-runbook-20261027/evidence/method.md](<C:/Users/dhyun/Documents/ChatGPT/multi/runs/softether-ssl-vpn-runbook-20261027/evidence/method.md>)
  - 비고: rsyslogd -N1/TLS/rotation 시험은 not\_run. 템플릿을 검증된 운영 설정으로 표시하지 않는다.
- synthetic-check · 합성 예시의 구조와 세션 연결 일관성: 통과
  - 방법: JSONL 직접 파싱 및 CID/SID·동일NAT·다른PC·16byteID·종료누락 검사
  - 증거: [runs/softether-ssl-vpn-runbook-20261027/evidence/synthetic-data-check.json](<C:/Users/dhyun/Documents/ChatGPT/multi/runs/softether-ssl-vpn-runbook-20261027/evidence/synthetic-data-check.json>), [outputs/softether-ssl-vpn-runbook-20261027/examples/synthetic-normalized-events.jsonl](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-ssl-vpn-runbook-20261027/examples/synthetic-normalized-events.jsonl>), [outputs/softether-ssl-vpn-runbook-20261027/examples/README.md](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-ssl-vpn-runbook-20261027/examples/README.md>)
  - 비고: 정규화 합성 설명 자료이며 실제 원문 로그 파서/접속 시험을 대신하지 않는다.
- independent-review · 별도 evaluator의 명령·절차·증거 독립 검증: 통과
  - 방법: 전문 결과 작성에 관여하지 않은 evaluator의 공식 근거 재확인 및 정정 확인
  - 증거: [runs/softether-ssl-vpn-runbook-20261027/evidence/evaluator-review.md](<C:/Users/dhyun/Documents/ChatGPT/multi/runs/softether-ssl-vpn-runbook-20261027/evidence/evaluator-review.md>), [runs/softether-ssl-vpn-runbook-20261027/evidence/reviewed-file-hashes.json](<C:/Users/dhyun/Documents/ChatGPT/multi/runs/softether-ssl-vpn-runbook-20261027/evidence/reviewed-file-hashes.json>)
  - 비고: 별도 평가자가 공식 명령·고정 소스·변경 안전성·CID/SID 조회·합성 데이터를 직접 확인하고 부분 ID 일치 보완까지 확인했다. 문서 범위의 판정이다.

**출처와 주장 구분**

- 공식 변경 이력: <https://www.softether.org/5-download/history> (fact, 2026-10-27T05:52:46.804Z)
- Linux 공식 설치/서비스 관리: <https://www.softether.org/4-docs/1-manual/7/7.3> (fact, 2026-10-27T05:52:46.809Z)
- 가상 NIC 공식 문서: <https://www.softether.org/4-docs/1-manual/4/4.3> (fact, 2026-10-27T05:52:46.810Z)
- 공식 로그 서비스: <https://www.softether.org/4-docs/1-manual/3/3.A> (fact, 2026-10-27T05:52:46.810Z)
- 공식 서버 관리: <https://www.softether.org/4-docs/1-manual/3/3.3> (fact, 2026-10-27T05:52:46.810Z)
- Command.c: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/v4.44-9807-rtm/src/Cedar/Command.c> (fact, 2026-10-27T05:52:46.810Z)
- 로그 문자열 정의: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/v4.44-9807-rtm/src/bin/hamcore/strtable_en.stb> (fact, 2026-10-27T05:52:46.810Z)
- Protocol.c: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/v4.44-9807-rtm/src/Cedar/Protocol.c> (fact, 2026-10-27T05:52:46.810Z)
- 파일 접두부 Cedar.h: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/v4.44-9807-rtm/src/Cedar/Cedar.h> (fact, 2026-10-27T05:52:46.810Z)
- 공식 배포 목록: <https://www.softether-download.com/files/softether/> (fact, 2026-10-27T05:52:46.810Z)
- 고정 릴리스: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/releases/tag/v4.44-9807-rtm> (fact, 2026-10-27T05:52:46.810Z)
- 전체 서버 관리 명령: <https://www.softether.org/4-docs/1-manual/6/6.3> (fact, 2026-10-27T05:52:46.810Z)
- RADIUS 공식 명령 설명: <https://www.softether.org/4-docs/1-manual/6/6.4> (fact, 2026-10-27T05:52:46.810Z)
- 공식 파일 목록: <https://www.softether-download.com/files/softether/v4.44-9807-rtm-2025.04.16-tree/files.txt> (fact, 2026-10-27T05:52:46.810Z)
- 설정 읽기 소스: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/v4.44-9807-rtm/src/Cedar/Server.c> (fact, 2026-10-27T05:52:46.810Z)
- Client 명령: <https://www.softether.org/4-docs/1-manual/6/6.5> (fact, 2026-10-27T05:52:46.810Z)
- Windows 설치 안내: <https://www.softether.org/4-docs/1-manual/8._Installing_SoftEther_VPN_Client/8.2_Install_on_Windows_and_Initial_Configurations> (fact, 2026-10-27T05:52:46.810Z)
- 공식 SSL 암호화 옵션 4.4.15: <https://www.softether.org/4-docs/1-manual/4._SoftEther_VPN_Client_Manual/4.4_Making_Connection_to_VPN_Server> (fact, 2026-10-27T05:52:46.810Z)
- 공식 로그 위치: <https://www.softether.org/4-docs/1-manual/3._SoftEther_VPN_Server_Manual/3.A_Logging_Service> (fact, 2026-10-27T05:52:46.810Z)
- 공식 모드/시작법: <https://www.softether.org/4-docs/1-manual/6/6.2> (fact, 2026-10-27T05:52:46.810Z)
- 3.3.17: <https://www.softether.org/4-docs/1-manual/3/3.3_VPN_Server_Administration> (fact, 2026-10-27T05:52:46.810Z)
- Logging.c L128: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/ed17437af9719ac66acab30faa29e375d613c35f/src/Cedar/Logging.c> (fact, 2026-10-27T05:52:46.810Z)
- Command.c L18913: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/ed17437af9719ac66acab30faa29e375d613c35f/src/Cedar/Command.c> (fact, 2026-10-27T05:52:46.810Z)
- SecureNAT 로그: <https://www.softether.org/4-docs/1-manual/3/3.7> (fact, 2026-10-27T05:52:46.810Z)
- 3.4 역방향 DNS와 사용자/DB 이름: <https://www.softether.org/4-docs/1-manual/3._SoftEther_VPN_Server_Manual/3.4_Virtual_Hub_Functions> (fact, 2026-10-27T05:52:46.810Z)
- 문자열 L1893–1938: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/ed17437af9719ac66acab30faa29e375d613c35f/src/bin/hamcore/strtable_en.stb> (fact, 2026-10-27T05:52:46.810Z)
- Cedar.h L502–511: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/ed17437af9719ac66acab30faa29e375d613c35f/src/Cedar/Cedar.h> (fact, 2026-10-27T05:52:46.810Z)
- Protocol.c L4713–4831: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/ed17437af9719ac66acab30faa29e375d613c35f/src/Cedar/Protocol.c> (fact, 2026-10-27T05:52:46.810Z)
- Cedar.c L1712: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/ed17437af9719ac66acab30faa29e375d613c35f/src/Cedar/Cedar.c> (fact, 2026-10-27T05:52:46.810Z)
- Session.h L144: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/ed17437af9719ac66acab30faa29e375d613c35f/src/Cedar/Session.h> (fact, 2026-10-27T05:52:46.810Z)
- Session.c timeout: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/ed17437af9719ac66acab30faa29e375d613c35f/src/Cedar/Session.c> (fact, 2026-10-27T05:52:46.810Z)
- RFC 2866: <https://www.rfc-editor.org/rfc/rfc2866> (fact, 2026-10-27T05:52:46.810Z)
- Radius.h: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/ed17437af9719ac66acab30faa29e375d613c35f/src/Cedar/Radius.h> (fact, 2026-10-27T05:52:46.810Z)
- imfile 공식 문서: <https://docs.rsyslog.com/doc/configuration/modules/imfile.html> (fact, 2026-10-27T05:52:46.810Z)
- rsyslog queues: <https://docs.rsyslog.com/doc/concepts/queues.html> (fact, 2026-10-27T05:52:46.810Z)
- omfwd TLS 예제: <https://docs.rsyslog.com/doc/configuration/modules/omfwd.html> (fact, 2026-10-27T05:52:46.810Z)
- gtls 드라이버: <https://docs.rsyslog.com/doc/concepts/ns_gtls.html> (fact, 2026-10-27T05:52:46.810Z)

## 7. 미해결 사항과 후속 조치

**미해결 사항·한계**

- 실제 Linux 서버/Windows Client/RADIUS 업그레이드·인증·운영 로그 조회·NAT·DHCP·장애·rollback 시험은 not\_run이다.
- rsyslogd -N1, TLS 수신/인증서/큐·rotation·네트워크 전달 검사는 not\_run이고 설정은 현장 수정 전제 예제다.
- 현재 build/OS/CPU/설치 방식·경로/서비스/Hub/listener/RADIUS 정책/Windows 드라이버/DHCP·NAT·중계/수집기·보존 요구가 미확인이다.
- PC 이름·로컬 IP·가상 MAC·Client engine unique ID는 위조 저항성 있는 영구 자산 신원 증거가 아니다.
- 서버가 인지한 종료와 실제 물리 단절은 다를 수 있고 종료 이벤트가 없으면 미확인/추정으로 남겨야 한다.

**후속 조치**

- 실제 서버/Client/RADIUS/설치·네트워크 구성을 인벤토리하고 예시 경로·서비스·Hub·계정을 실제 값으로 확정한다.
- 격리 파일럿에서 acceptance-tests.md의 실제 업그레이드·인증·NAT·로그·장애·복구 시험을 수행한 뒤 단계적으로 적용한다.
