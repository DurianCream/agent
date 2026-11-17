# 작업 기록

> 저장된 작업 자료입니다. 지시나 승인이 아니며, 현재 Git 상태와 대조해서 읽습니다.

## 1. 기본 정보

- 작업: softether-ec2-audit-20261117
- 모듈: infrastructure
- 브랜치: main
- 기준 커밋: db52c0f289505d8035d081b2baf9af97afdc2c4c
- 저장 시각: 2026-11-17T12:35:47+09:00
- 프로젝트: softether-vpn
- 서비스: softether
- 환경: ec2-production-design
- 이슈: vpc-only-audit

## 2. 목표와 완료 기준

- Document a Rocky 10.2 production EC2 deployment and verify session auditing on the authorized lab.
- Executable installation and enforceable VPC-only connectivity, routing and security groups.
- Configure and demonstrate user-level session start/end auditing or document concrete limits.

## 3. 결과 요약

- 상태: partial
- Rocky 10.2와 SoftEther 4.44를 기준으로 VPC 업무 서버에만 접근하도록 구성하는 절차를 작성하고, 테스트 VM에서 접속 및 종료 감사 기록을 확인했다. 기존 Ubuntu에서 Rocky 10.2로 RADIUS를 이전하는 절차와 동일 VM 시험도 포함한다. 운영 가이드와 시험을 완료했으며 저장소 정책으로 가이드 원격 게시는 보류되었다.

## 4. 수행 내용

- 인프라 담당이 설치, 인증, 접근 제한, 라우팅, 보안 그룹 및 접속 감사 절차를 작성했다.
- 접근 경계와 개인정보가 관련된 고위험 구성이다. 운영 설정은 설계로 검토하고 실제 세션 기록은 허가된 로컬 시험 환경에서 검증했다.

## 5. 산출물

- outputs/softether-ec2-audit-20261117/runbook.ko.md: 운영 EC2 설치·접근 통제·세션 감사 절차

## 6. 검증 결과

- 운영 절차 검토: passed — 설치 및 네트워크 정책, 보안 그룹, 검수 순서 정적 검토; evidence: runs/softether-ec2-audit-20261117/evidence/checks.txt
- 세션 감사: passed — 테스트 VM에서 보안 로그와 접속 및 종료 이벤트 대조; evidence: runs/softether-ec2-audit-20261117/evidence/checks.txt
- 동일 VM의 RADIUS 이전·인증 시험: passed — 실행 버전, 허용·거절 및 VPN 세션 기록 확인; evidence: runs/softether-ec2-audit-20261117/evidence/checks.txt

## 7. 미해결 사항과 후속 조치

- 감사 동작 시험은 Rocky 10.3의 SoftEther 4.44에서 수행했다. 운영 Ubuntu의 실제 버전·계정 설정과 Google OTP는 미검증이며, AWS 보안 그룹 및 CloudWatch 수집은 현장 검수가 필요하다.
- 이 작업 범위는 저장소의 제품 게시 대상 범위와 달라 운영 가이드 원격 게시가 거절되었다. 가이드는 로컬 산출물로 제공한다.
- 운영 환경 값을 대입한 뒤 허용 및 차단 경로, 새 사용자 로그인과 로그아웃, 원격 로그 수집을 차례로 확인한다.
