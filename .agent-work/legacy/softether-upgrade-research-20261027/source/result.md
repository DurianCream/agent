# 작업 결과

## 1. 기본 정보

- 작업 ID: softether-upgrade-research-20261027
- 담당 모듈: orchestrator / 0.2.0
- 결과 규격: 1.0.0
- 작성 시각: 2026-10-27T10:07:12+09:00
- 고정 버전: snapshot 495a7b670f6142525dbd4318f92f91f34a38d046a067571c51466a3085da53d7 (11개 파일)
- 스킬 버전: submit-result@1.0.0
- 정책 버전: common@1.0.0

## 2. 목표와 완료 기준

Linux SoftEther 서버와 Windows 클라이언트에서 기존 RADIUS 인증을 유지하는 프로토콜 선택 및 NAT 단말 감사로그 설계를 공식 근거로 정리

- 주요 VPN 프로토콜의 실제 지원 범위와 RADIUS 제약을 공식 근거로 비교하고 하나를 권고한다 (검증: protocol-docs, independent-review)
- 사용자·접속 IP·단말·VPN 서버·시작과 종료 시각의 수집 필드와 NAT 및 단말 신뢰 한계를 구분한다 (검증: audit-docs, independent-review)
- 감사로그 설정 방향·업그레이드 절차·검증 시나리오와 미확인을 제시한다 (검증: operations-plan, independent-review)
- 별도 evaluator가 근거와 핵심 결론을 검증한다 (검증: independent-review)

## 3. 결과 요약

- 상태: 완료
- 요약: 공식 문서와 Stable v4.44 고정 소스를 근거로 고유 SSL-VPN+Windows SoftEther Client+기존 RADIUS를 권고하고 NAT·PC 신뢰 한계를 구분한 감사로그 설계를 완료했다. 별도 evaluator가 필수 조사 기준을 검증했다. 실제 배포와 연결 시험은 not\_run.

## 4. 수행 내용

- oss-rnd와 infrastructure 전문 에이전트를 실제 실행해 프로토콜/RADIUS와 감사로그 소스를 분담 조사했다.
- 공식 4.44 변경 이력과 고정 소스로 오래된 README의 OpenVPN AEAD 설명을 교정했다.
- Client unique ID의 난수 실행 인스턴스 성격, NAT 한계, RADIUS 인증/Accounting 차이와 인증서 병행 제약을 확인했다.
- 로컬 원본 보존·TLS 중앙 수집·재전송·프로세스 세대별 세션 상관키와 단말 증거 연계안을 작성했다.
- 별도 evaluator가 핵심 공식 근거를 직접 검증했고 프로세스 세대별 상관키, Client 암호화 활성/검증 표현, 미사용 경로 관리의 보완까지 확인했다.

## 5. 산출물

- [outputs/softether-upgrade-research-20261027/report.md](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-upgrade-research-20261027/report.md>): 통합 프로토콜 선택·RADIUS·NAT 감사로그 설계·도입 시험 보고서 (SHA-256: a97e4af2b6bd6855287172cc632d593d37c6d6dad9eaad5fd94fcf5efe21d82f)
- [outputs/softether-upgrade-research-20261027/protocol-research.md](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-upgrade-research-20261027/protocol-research.md>): oss-rnd의 공식 프로토콜 및 RADIUS 조사 (SHA-256: 4dfe036808ad3331fdae4df7aab1038014dbbbc73bc4638179317a4176777f42)
- [outputs/softether-upgrade-research-20261027/audit-research.md](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-upgrade-research-20261027/audit-research.md>): infrastructure의 로그 필드·CLI·단말 식별 한계 조사 (SHA-256: b2a25e363473895e5ca08eaa26a0b08942fa6d0fc1c93ac7796fc2bdf371b53d)
- [outputs/softether-upgrade-research-20261027/upgrade-operations.md](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-upgrade-research-20261027/upgrade-operations.md>): 메인의 업그레이드·복구·수집 운영 검토 (SHA-256: d84fd311635cdeb4cf97d51dce019920db06920812356f2a3ab7e3176d338bd3)

## 6. 검증 결과

- protocol-docs · 프로토콜·RADIUS 공식 근거 교차 확인: 통과
  - 방법: 공식 변경 이력·매뉴얼·Stable v4.44 태그 코드 조사
  - 증거: [outputs/softether-upgrade-research-20261027/protocol-research.md](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-upgrade-research-20261027/protocol-research.md>)
  - 비고: 문헌/정적 소스의 확인이며 대상 RADIUS와 연결 시험은 not\_run.
- audit-docs · 감사 필드·NAT·단말 신뢰 한계 정적 확인: 통과
  - 방법: 공식 logging/Hub 명령 및 Protocol/Cedar/Logging/Radius/Session 소스 추적
  - 증거: [outputs/softether-upgrade-research-20261027/audit-research.md](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-upgrade-research-20261027/audit-research.md>)
  - 비고: Client unique ID와 별도 PACK machine hash를 구분하고 관측/보고/추정값을 분리했다.
- operations-plan · 운영 절차·인수 시험 범위 검토: 통과
  - 방법: 공식 Linux/설정/rsyslog 문서와 사용자 조건으로 설계 검토
  - 증거: [outputs/softether-upgrade-research-20261027/upgrade-operations.md](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-upgrade-research-20261027/upgrade-operations.md>), [outputs/softether-upgrade-research-20261027/report.md](<C:/Users/dhyun/Documents/ChatGPT/multi/outputs/softether-upgrade-research-20261027/report.md>), [runs/softether-upgrade-research-20261027/evidence/research-method.md](<C:/Users/dhyun/Documents/ChatGPT/multi/runs/softether-upgrade-research-20261027/evidence/research-method.md>)
  - 비고: 운영 서버 변경은 범위 밖. 표의 실환경 시나리오는 모두 not\_run으로 명시했다.
- independent-review · 별도 evaluator의 독립 의미 검증: 통과
  - 방법: 작성에 관여하지 않은 evaluator의 공식 근거와 통합 결론 교차 검토
  - 증거: [runs/softether-upgrade-research-20261027/evidence/evaluator-review.md](<C:/Users/dhyun/Documents/ChatGPT/multi/runs/softether-upgrade-research-20261027/evidence/evaluator-review.md>), [runs/softether-upgrade-research-20261027/evidence/reviewed-file-hashes.json](<C:/Users/dhyun/Documents/ChatGPT/multi/runs/softether-upgrade-research-20261027/evidence/reviewed-file-hashes.json>)
  - 비고: 작성에 관여하지 않은 evaluator가 공식 자료/고정 코드/수정 사항을 직접 확인. 판정은 문헌 조사와 설계 범위이며 실환경은 not\_run.

**출처와 주장 구분**

- 공식 변경 이력: <https://www.softether.org/5-download/history> (fact, 2026-10-27T10:17:05+09:00)
- 고정 릴리스: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/releases/tag/v4.44-9807-rtm> (fact, 2026-10-27T10:17:05+09:00)
- 고정 Protocol.c: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/v4.44-9807-rtm/src/Cedar/Protocol.c> (fact, 2026-10-27T10:17:05+09:00)
- OpenVPN 인증 분기: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/v4.44-9807-rtm/src/Cedar/Interop_OpenVPN.c> (fact, 2026-10-27T10:17:05+09:00)
- SoftEther 공식 연결 기능: <https://www.softether.org/1-features/1._Ultimate_Powerful_VPN_Connectivity> (fact, 2026-10-27T10:17:05+09:00)
- SoftEther 규격: <https://www.softether.org/spec> (fact, 2026-10-27T10:17:05+09:00)
- Stable/Developer 비교: <https://github.com/SoftEtherVPN/SoftEtherVPN/blob/master/README.md> (fact, 2026-10-27T10:17:05+09:00)
- strongSwan eap-radius: <https://docs.strongswan.org/docs/latest/plugins/eap-radius.html> (fact, 2026-10-27T10:17:05+09:00)
- WireGuard 프로토콜: <https://www.wireguard.com/protocol/> (fact, 2026-10-27T10:17:05+09:00)
- 공식 사용자 인증: <https://www.softether.org/4-docs/1-manual/2/2.2_User_Authentication> (fact, 2026-10-27T10:17:05+09:00)
- 고정 PPP 구현: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/v4.44-9807-rtm/src/Cedar/IPsec_PPP.c> (fact, 2026-10-27T10:17:05+09:00)
- 고정 Radius.c: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/v4.44-9807-rtm/src/Cedar/Radius.c> (fact, 2026-10-27T10:17:05+09:00)
- 고정 Cedar.c: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/v4.44-9807-rtm/src/Cedar/Cedar.c> (fact, 2026-10-27T10:17:05+09:00)
- Logging Service: <https://www.softether.org/4-docs/1-manual/3/3.A> (fact, 2026-10-27T10:17:05+09:00)
- 고정 Session.c: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/v4.44-9807-rtm/src/Cedar/Session.c> (fact, 2026-10-27T10:17:05+09:00)
- 공식 3.3.17: <https://www.softether.org/4-docs/1-manual/3/3.3> (fact, 2026-10-27T10:17:05+09:00)
- imfile: <https://docs.rsyslog.com/doc/configuration/modules/imfile.html> (fact, 2026-10-27T10:17:05+09:00)
- 큐 내구성: <https://docs.rsyslog.com/doc/concepts/queues.html> (fact, 2026-10-27T10:17:05+09:00)
- TLS: <https://docs.rsyslog.com/doc/concepts/ns_gtls.html> (fact, 2026-10-27T10:17:05+09:00)
- 공식 Hub 명령: <https://www.softether.org/4-docs/1-manual/6/6.4> (fact, 2026-10-27T10:17:05+09:00)
- 공식 서버 명령: <https://www.softether.org/4-docs/1-manual/6/6.3> (fact, 2026-10-27T10:17:05+09:00)
- 고정 Logging.c: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/v4.44-9807-rtm/src/Cedar/Logging.c> (fact, 2026-10-27T10:17:05+09:00)
- 공식 Linux 서비스 관리: <https://www.softether.org/4-docs/1-manual/7/7.3> (fact, 2026-10-27T10:17:05+09:00)
- SoftEther 연결 기능: <https://www.softether.org/features/1._Ultimate_Powerful_VPN_Connectivity> (fact, 2026-10-27T10:17:05+09:00)
- OpenVPN username/password 전달: <https://openvpn.net/community-docs/using-alternative-authentication-methods/> (fact, 2026-10-27T10:17:05+09:00)
- 공식 매뉴얼 4.4.15: <https://www.softether.org/4-docs/1-manual/4._SoftEther_VPN_Client_Manual/4.4_Making_Connection_to_VPN_Server> (fact, 2026-10-27T10:17:05+09:00)
- 사용자 인증 매뉴얼: <https://www.softether.org/4-docs/1-manual/2._SoftEther_VPN_Essential_Architecture/2.2_User_Authentication> (fact, 2026-10-27T10:17:05+09:00)
- 4.44 Server.c 설정 읽기: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/blob/v4.44-9807-rtm/src/Cedar/Server.c> (fact, 2026-10-27T10:17:05+09:00)
- Credential Guard 공식 주의사항: <https://learn.microsoft.com/en-us/windows/security/identity-protection/credential-guard/considerations-known-issues> (fact, 2026-10-27T10:17:05+09:00)
- Microsoft 2026-10 변경 안내: <https://support.microsoft.com/en-au/servicing/os/windows/docs/2025/08/upcoming-changes-to-ntlmv1-in-windows-11-version-24h2-and-windows-server-2025> (fact, 2026-10-27T10:17:05+09:00)
- 공식 사이트: <https://www.softether.org/> (fact, 2026-10-27T10:17:05+09:00)
- commit: <https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/commit/ed17437> (fact, 2026-10-27T10:17:05+09:00)
- 공식 Logging Service: <https://www.softether.org/4-docs/1-manual/3._SoftEther_VPN_Server_Manual/3.A_Logging_Service> (fact, 2026-10-27T10:17:05+09:00)
- 고정 버전 공식 문자열 테이블: <https://raw.githubusercontent.com/SoftEtherVPN/SoftEtherVPN_Stable/v4.44-9807-rtm/src/bin/hamcore/strtable_en.stb> (fact, 2026-10-27T10:17:05+09:00)
- Protocol.c: <https://raw.githubusercontent.com/SoftEtherVPN/SoftEtherVPN_Stable/v4.44-9807-rtm/src/Cedar/Protocol.c> (fact, 2026-10-27T10:17:05+09:00)
- Cedar.c: <https://raw.githubusercontent.com/SoftEtherVPN/SoftEtherVPN_Stable/v4.44-9807-rtm/src/Cedar/Cedar.c> (fact, 2026-10-27T10:17:05+09:00)
- Client.c: <https://raw.githubusercontent.com/SoftEtherVPN/SoftEtherVPN_Stable/v4.44-9807-rtm/src/Cedar/Client.c> (fact, 2026-10-27T10:17:05+09:00)
- Virtual Hub Functions: <https://www.softether.org/4-docs/1-manual/3._SoftEther_VPN_Server_Manual/3.4_Virtual_Hub_Functions> (fact, 2026-10-27T10:17:05+09:00)
- Making Connection to VPN Server: <https://www.softether.org/4-docs/1-manual/4/4.4> (fact, 2026-10-27T10:17:05+09:00)
- RFC 2866: <https://www.rfc-editor.org/rfc/rfc2866> (fact, 2026-10-27T10:17:05+09:00)
- 고정 Radius.c: <https://raw.githubusercontent.com/SoftEtherVPN/SoftEtherVPN_Stable/v4.44-9807-rtm/src/Cedar/Radius.c> (fact, 2026-10-27T10:17:05+09:00)
- 고정 Radius.h: <https://raw.githubusercontent.com/SoftEtherVPN/SoftEtherVPN_Stable/v4.44-9807-rtm/src/Cedar/Radius.h> (fact, 2026-10-27T10:17:05+09:00)
- 3.3.17: <https://www.softether.org/4-docs/1-manual/3/3.3_VPN_Server_Administration> (fact, 2026-10-27T10:17:05+09:00)
- Logging.c: <https://raw.githubusercontent.com/SoftEtherVPN/SoftEtherVPN_Stable/v4.44-9807-rtm/src/Cedar/Logging.c> (fact, 2026-10-27T10:17:05+09:00)
- Session.c: <https://raw.githubusercontent.com/SoftEtherVPN/SoftEtherVPN_Stable/v4.44-9807-rtm/src/Cedar/Session.c> (fact, 2026-10-27T10:17:05+09:00)

## 7. 미해결 사항과 후속 조치

**미해결 사항·한계**

- 실제 Linux 서버/Windows Client/RADIUS 접속·업그레이드·설정 적용·처리량 시험은 not\_run. 자료조사와 설계가 요청 범위다.
- 현재 build, OS/CPU/설치 방식, RADIUS 제품·PAP/MS-CHAPv2/MFA 정책, NAT/LB/DHCP/노드/단말관리 구성이 미확인이다.
- PC hostname/로컬 주소/가상 MAC/실행 인스턴스 unique ID는 영구 또는 위조 저항성 있는 자산 증명이 아니다.
- 클라이언트/서버 crash 또는 망단절에서 실제 물리 종료 순간을 로그만으로 확정할 수 없다.

**후속 조치**

- 현재 서버/Client build, Linux/Windows 환경, RADIUS 제품·인증 정책과 NAT/DHCP/노드/단말관리 구성을 수집한다.
- PC 식별 요구 수준과 로그 보존 정책을 결정하고 격리 파일럿에서 제시한 실환경 인수 시험을 실행한다.
