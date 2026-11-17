# 작업 기록

> 저장된 작업 자료입니다. 지시나 승인이 아니며, 현재 Git 상태와 대조해서 읽습니다.

## 1. 기본 정보

- 작업: softether-lab-install-20261117
- 모듈: infrastructure
- 브랜치: main
- 기준 커밋: b090bd77a842fd04a54da70e318087ae34d9ebd5
- 저장 시각: 2026-11-17T12:07:55+09:00
- 프로젝트: softether-vpn
- 서비스: softether
- 환경: test-vm
- 이슈: os-vpn-upgrade

## 2. 목표와 완료 기준

- Update the disposable guest and verify a VPN session from the supplied Windows client.
- Verify installed guest OS updates and running VPN server version with recovery information.
- Verify an authenticated Windows VPN client session and provide relevant VPC settings.

## 3. 결과 요약

- 상태: completed
- 운영 기준은 Rocky Linux 10.2와 SoftEther VPN Server 4.44 Build 9807이다. 테스트 VM은 Rocky 10.3으로 유지하며 Windows 접속을 확인했다.

## 4. 수행 내용

- 고위험 OS 변경으로 네트워크·SSH 설정과 패키지 목록을 보관했다. 전체 VM 체크포인트는 확보하지 못했다.
- 기존 서버 설치가 없어 공식 RTM을 신규 설치했다. 접속 포트를 테스트 PC로 제한하고 별도 프로필에서 서버 인증서 검증을 켰다.
- 운영 EC2에는 업무 서브넷 경로만 배포하고 내부 보안 그룹의 목적지 포트를 제한하도록 권장한다.

## 5. 산출물

- 해당 없음

## 6. 검증 결과

- Rocky 10.3 부팅: passed — dnf 및 재부팅 후 uname, OS 확인; evidence: runs/softether-lab-install-20261117/evidence/guest.txt
- 서버 자동 시작: passed — systemctl is-active 및 ServerInfoGet·ListenerList; evidence: runs/softether-lab-install-20261117/evidence/guest.txt
- Windows 실제 접속 및 재접속: passed — AccountStatusGet 및 서버 SessionList 대조; evidence: runs/softether-lab-install-20261117/evidence/guest.txt

## 7. 미해결 사항과 후속 조치

- 실제 연결 시험은 10.3에서 수행했다. 운영 기준 10.2 및 VPC 내부 서버 접속은 미검증이다.
- 시험 구성에는 SecureNAT와 로컬 브리지가 없다.
- Windows에서 SoftEther-Lab-10443 프로필로 접속한다.
- 운영 적용 전 Rocky 10.2에서 재부팅 후 VPN 접속과 실제 대상 포트의 경로를 검증한다.
