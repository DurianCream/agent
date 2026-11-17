# 작업 기록

> 저장된 작업 자료입니다. 지시나 승인이 아니며, 현재 Git 상태와 대조해서 읽습니다.

## 1. 기본 정보

- 작업: softether-lab-upgrade-20261117
- 모듈: infrastructure
- 브랜치: main
- 기준 커밋: 96e96d61736a37607952689da1119178d107020d
- 저장 시각: 2026-11-17T11:32:33+09:00
- 프로젝트: softether-vpn
- 서비스: softether
- 환경: test-vm
- 이슈: os-vpn-upgrade

## 2. 목표와 완료 기준

- Upgrade the supplied lab VPN guest and evaluate private server access.
- Verify the guest OS and VPN upgrade with recovery conditions.
- Verify the Windows client path or document precise limitations and VPC recommendations.

## 3. 결과 요약

- 상태: partial
- 테스트 VM에 대한 SSH 인증이 거절되어 서버 업그레이드와 VPN 세션 시험은 진행하지 못했다. PC의 클라이언트와 기존 프로필 상태를 확인했다.

## 4. 수행 내용

- 인프라 담당이 지정된 VM의 SSH 응답, Windows 클라이언트 및 프로필의 수신 포트 접근을 확인했다.
- OS 이전은 복구 가능 여부가 중요한 고위험 변경이다. 게스트 로그인 및 복구 경로를 확보하지 못했으며 서버와 PC 설정은 변경하지 않았다.

## 5. 산출물

- 해당 없음

## 6. 검증 결과

- PC 클라이언트: passed — 로컬 서비스와 프로필 읽기; evidence: runs/softether-lab-upgrade-20261117/evidence/guest.txt
- 게스트 관리 로그인: failed — 지정된 SSH 서버 인증; evidence: runs/softether-lab-upgrade-20261117/evidence/guest.txt
- VPN 수신 포트 접근: failed — 지정된 VM에 TCP 연결; evidence: runs/softether-lab-upgrade-20261117/evidence/guest.txt
- OS 및 VPN 업그레이드: not\_run — 게스트 버전 및 재시작 후 서비스 확인; evidence: runs/softether-lab-upgrade-20261117/evidence/guest.txt
- VPN 세션: not\_run — PC와 서버에서 연결 상태 대조; evidence: runs/softether-lab-upgrade-20261117/evidence/guest.txt

## 7. 미해결 사항과 후속 조치

- 게스트 OS 및 VPN 서버 버전, 방화벽 상태, 인증 거절 이유는 미확인. 현재 Windows 세션에는 Hyper-V 관리 권한이 없다.
- 요청에 따라 별도 VPC 서버 접속은 시험 범위에서 제외했다.
- 사용 가능한 SSH 계정 또는 키를 확보하고 VM 복구 경로를 확인한다.
- VPN 연결 시험은 서버 인증서를 확인하는 별도 테스트 프로필에서 진행한다. EC2 적용 시에는 업무 서브넷만 터널로 보내고 대상 보안 그룹에서 필요한 포트만 허용한다.
