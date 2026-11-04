# Linux P2 기반 코드와 설치 전 확인

이 디렉터리는 **기본 비활성 설치와 별도 실행·검증·게시 어댑터**를 제공합니다. broker config `0.1.0`은 기존 stage-only 동작을 유지합니다. `0.2.0`은 같은 Linux 호스트의 인증된 Unix 소켓 RPC로 별도 root 검증기와 비-root publisher를 자동 호출하며, 요청마다 운영자가 보호 job 파일을 편집할 필요가 없습니다. 원격 VM·터널 신원 인증과 외부 HTTPS 게시, 데스크톱 도구 연결은 포함하지 않습니다.

## 자동 로컬 RPC — 2026-11-04

실제 VM에서 응답을 기다리는 제출 UID 989와 격리 실행 UID 988을 분리하여 `upload → stage → verify → publish`를 확인했습니다. controller는 UID 995, publisher는 UID 990이었으며, 이 숫자는 관찰값이지 설치 기본값이 아닙니다. 추가된 업로드 envelope `0.2.0`과 기존 요청 `0.1.0`은 구분됩니다. 현재 업로드·실행 묶음은 64KiB, JSON frame은 128KiB로 제한하며 더 큰 데이터의 streaming은 지원하지 않습니다.

systemd socket activation에서 client의 `SO_PEERCRED`는 socket 생성자 PID 1/UID 0을 가리킵니다. 보호된 endpoint 경로·소유권·inode와 이 manager 신원을 검증하고, 실제 서비스 UID 및 controller peer는 서버에서 별도로 검증합니다. 응답 JSON의 UID 주장만으로 역할을 인증하지 않습니다. 동일 요청 재시도·위조 peer/범위/내용·시간/크기 제한도 실제 시험했으며 대상 ref와 job 수 불변을 확인했습니다.

[설치·활성화·복구 명세](rpc-deployment.en.md)에 정확한 unit, 계정, 정책 결합과 권한을 정리했습니다. 현재 시험은 namespace 제한을 일시적으로 15334로 높인 뒤 매번 0으로 복원합니다. 상시 자동 운영에 필요한 영구 nonzero 제한과 broker/socket enable은 별도 승인 전제이며 아직 적용하지 않았습니다. 코드 설치와 상시 활성화 완료를 구분합니다.

## 환경은 실제 시험 시점에 선택

특정 Ubuntu 버전이나 모든 테스트의 OS를 고정하지 않습니다. 이 Linux 어댑터를 실제로 시험할 때는 systemd·cgroup v2·Unix 소켓 peer credentials·서로 다른 서비스 UID·격리 기능을 확인할 수 있는 별도 Linux VM이 필요합니다. Windows 대상은 별도 어댑터가 필요하며 임의로 Linux로 바꾸지 않습니다. 업무용·재사용 가능한 trusted controller VM과 일회용 OS 테스트 VM을 구분합니다. 테스트 OS가 달라져도 게시 자격증명을 그 VM에 전달하지 않습니다.

2 vCPU·4 GiB RAM·40 GiB 디스크는 초기 여유 구성 예시이며 검증된 최소 사양이나 모든 테스트의 필수값이 아닙니다. OS와 선택한 작업 예산에 맞춰 조정합니다. 동적 VHD의 최대 용량과 즉시 사용하는 물리 공간은 다릅니다. 기존 Hyper-V 준비 도구는 부족한 여유 공간을 피하려고 최대 용량·ISO·여유 공간을 보수적으로 확인합니다.

`preflight.py`는 OS 표기와 전체 `/etc/os-release` 해시, 아키텍처·커널 릴리스, machine-id 해시, Python·systemd 버전, cgroup 컨트롤러와 namespace 인터페이스를 읽기만 합니다. 인터페이스가 있다는 사실은 실제 격리 성공 증거가 아닙니다. 초기 기능 기준은 Python 3.11 이상·systemd 247 이상이며 systemd 255 문서와 대조했습니다. 커널·배포판 정책·실제 서비스 실행은 대상 VM에서 별도 검증해야 합니다. WSL은 일반 구문·소켓·파일 fixture 시험에만 사용할 수 있고 설치 대상이나 P2 격리 증거로 인정하지 않습니다.

## 경로와 계정

| 구분 | 경로·계정 | 현재 상태 |
|---|---|---|
| 설치 코드 | `/opt/multi-p2`, root 소유 | 검토된 allowlist만 새로 복사 |
| 설치 정책 | `/etc/multi-p2/broker.json`, root:controller 0640 | 최초 enrollment는 비어 있음 |
| 전용 Python | `/opt/multi-p2-python/bin/python3` | 운영자가 별도로 승인·준비한 root 소유 환경 필요 |
| broker 상태 | `/var/lib/multi-p2/broker`, controller 0700 | worker 직접 접근 금지 |
| 소켓 | `/run/multi-p2-control/worker.sock` | 부모 control:workers 0750, 소켓 0660 |
| 계정 | `multi-p2-control`, `multi-p2-worker`, `multi-p2-verify`, `multi-p2-publish` | 서로 다른 UID, 로그인 금지 |
| 실행 rootfs | `/var/lib/multi-p2/rootfs/image-<manifest digest>` | 승인한 runtime 파일만 별도 builder로 복사 |

broker는 primary group으로 `multi-p2-workers`, supplementary group으로 자신의 private `multi-p2-control`을 사용합니다. worker 그룹은 소켓 연결만 허용받고 정책·private 상태를 수정할 수 없어야 합니다. UID를 user namespace로 다시 매핑하지 않아 실제 `SO_PEERCRED`와 보호된 enrollment의 UID가 일치해야 합니다. 현재 worker UID는 한 enrollment에만 사용하며 폐기 후에도 다른 enrollment로 재사용하지 않습니다. 안전한 신원 회수·재할당은 아직 구현하지 않았습니다.

## 신뢰된 설치 출발점

후보 코드가 수정할 수 있는 체크아웃의 스크립트를 그대로 `sudo` 실행해 신뢰 경계를 만들 수 없습니다. 운영자는 독립 검토한 `install.py`와 `preflight.py`를 별도의 root 소유·상위 경로까지 쓰기 보호된 bootstrap 위치에 준비하고, 신뢰된 실제 Python 바이너리를 **`-I -S -B`**로 실행해야 합니다. 설치기는 root 실행 시 이 조건을 확인한 **후에만** helper를 불러옵니다. 실제 bootstrap 두 파일은 승인한 배포 파일들과 바이트가 같아야 합니다. `--expected-release-sha256`도 운영자가 검토한 배포 manifest에서 독립적으로 확인해야 하며, 설치기가 계산한 값을 자동 승인한 것으로 취급하지 않습니다.

전용 Python은 운영자가 승인한 패키지 출처·고정 버전을 사용해 별도로 준비합니다. root로 소유권만 바꾼 worker 제작 venv, `.pth`, `pyvenv.cfg` 또는 외부 경로를 신뢰하면 안 됩니다. `--copies` 방식의 실제 interpreter 파일과 보호된 전체 의존성 트리를 사용합니다. `.pth`·`sitecustomize.py`·`usercustomize.py`, 외부 경로로 이어지는 venv 링크와 private 패키지의 링크는 거부합니다. `pyvenv.cfg`의 base interpreter/home도 root 통제 경로여야 하며 system site-packages 상속을 허용하지 않습니다. 설치기는 다운로드·패키지 설치를 하지 않습니다. `-S` 상태에서 실제 executable 위치에 대응하는 보호된 private site-packages의 metadata만 명시적으로 검사하고, site hook을 실행하는 `addsitedir`는 사용하지 않습니다. 이 검사도 임의의 interpreter·stdlib 자체를 인증하는 것은 아니므로 승인된 기반 런타임이 선행되어야 합니다.

기본 실행은 관측한 호스트 정보와 계획만 출력합니다. 실제 적용은 운영자가 승인한 VM의 OS ID·VERSION_ID·전체 os-release 해시·아키텍처·machine-id 해시와 release digest를 모두 명시한 `--apply`에서만 가능합니다. 특정 커널 빌드가 필요한 시험은 `--expected-kernel-release`도 고정합니다. 따라서 `VERSION_ID`가 같더라도 다른 포인트 릴리스·빌드 표기를 몰래 수용하지 않습니다. 현재 WSL·Windows·컨테이너·신원 불일치·누락된 기능은 차단합니다. 기존 설치 경로·계정·그룹이 있으면 인수하거나 덮어쓰지 않습니다. 계획·일반 fixture 시험은 VM 없이 진행할 수 있지만, 이제 구체화된 Linux admission 및 실제 UID·namespace·자격증명·Git 우회 검증에는 협의한 실제 VM이 필요합니다. 새 VM을 만드는 경우에만 그 대상에 맞는 ISO를 요청합니다.

설치 결과는 `installed_inactive`입니다. 새 계정과 보호 코드·빈 정책·비활성 unit을 준비하고 `daemon-reload`만 수행합니다. 서비스 자동 시작·enable, rootfs 자동 제작, sudo/polkit 권한, 기존 자격증명 복사, 게시 토큰 발급은 하지 않습니다. 초기 실제 검증기·감독자는 명시적으로 UID 0이며 `multi-p2-verify` 비-root 계정은 아직 그 실행 역할을 맡지 않습니다. publisher는 별도 비-root UID입니다. 비-root 검증기에서 root 실행기로 보내는 권한 있는 RPC도 자동 제공하지 않습니다.

## 실행·검증·게시 경로

`worker_entry.py --run`은 root 소유의 고정 `/etc/multi-p2/verification-job.json`을 검증기에 전달합니다. `multi-p2-executor.service`의 private mount namespace, delegated cgroup, 실제 MainPID·수명 제한을 확인한 root 감독자만 `BwrapExecutor`를 사용할 수 있습니다. 후보 코드는 별도 전용 worker UID/GID로 낮춘 후 bwrap에서만 실행합니다. root 상태로 host에서 대신 실행하는 fallback은 없습니다.

필수 namespace를 명시적으로 생성하며 `--*-try` fallback을 쓰지 않습니다. 승인된 rootfs·불변 입력은 읽기 전용, 출력은 크기 제한 tmpfs입니다. root 감독자가 실제 `/proc` UID·namespace·mount·capability·cgroup을 검사한 뒤에만 정확한 nonce를 보냅니다. 신뢰된 nondumpable PID1 gate는 EOF·잘못된 nonce를 승인으로 취급하지 않고 감독자의 lifeline과 자체 wall deadline을 감시합니다. 후보에는 제어 FD가 전달되지 않습니다. AMD64 seccomp는 AF_UNIX 이외 socket, keyring·debug·io_uring 우회 호출 및 다른 ABI를 차단합니다. systemd도 감독자 사망 시 전체 unit cgroup을 정리하도록 검증합니다.

CPU는 cgroup 전체 사용량을 주기적으로 확인하므로 관찰 주기의 작은 초과가 있을 수 있습니다. memory/pids·출력 공간은 별도 kernel 제한을 사용합니다. 모든 job 프로세스가 종료됐음을 확인한 뒤에만 출력 파일을 읽고, link·FIFO·경로 변경·크기 초과를 거부합니다. 보존 입력/job 저장소에도 파일 수·바이트 예산이 있습니다. 실제 VM의 필수 기능이나 적용 조건을 확인하지 못하면 실행·검증이 거부됩니다.

`FixtureExecutor`는 명시적으로 신뢰된 로컬 테스트 프로그램만 실행하는 별도 경로이며 실제 host 프로세스를 사용합니다. 격리 보장이나 production attestation을 만들 수 없습니다. `rootfs_builder.py`도 기본은 계획이며 root가 승인한 정확한 파일·해시 목록만 새 이미지로 복사합니다. host `/usr`를 통째로 bind하거나 개인 파일·게시 자격증명을 복사하지 않습니다. Python·Git과 필요한 라이브러리 및 gate를 승인 목록에 넣고 복사 후 실제 rootfs digest를 고정해야 합니다.

`publisher_entry.py --run`은 고정 `/etc/multi-p2/publication-job.json`을 별도 publisher UID로 처리합니다. 현재 transport는 승인된 local-bare Git 대상이며 비밀값이나 새 원격 연결 권한을 만들지 않습니다. 검증 receipt·후보·기준 커밋·정확한 대상이 일치해야 합니다. 전체 P2 적용 결과는 실제 VM에서 직접 Git/HTTP 우회, canary 접근, 권한·경로 변조, 감독자 사망과 정상 게시 경로를 검증한 후 판정합니다.

## 실패·시험 기록

설치 중 실패하면 부분 생성한 전용 자원을 보존하고 운영자 점검을 요구합니다. 기존 경로를 삭제하거나 계정을 재사용해 자동 복구하지 않습니다. operator 접근 권한을 회수하지 않습니다.

초기 준비 단계의 기록은 순수 계약·config·fixture 검증이었으며, 당시 실제 VM 적용·worker 실행·보호된 게시는 `not_run`이었습니다. 이후 2026-11-03 사용자 제공 Ubuntu 24.04.2 VM에서 운영자가 시작하는 격리 실행·검증·local-bare 게시와 동일 요청 재시도, 직접 Git 쓰기·합성 canary 접근 차단, safety 영수증의 게시 거부, supervisor 종료 후 프로세스·출력 쓰기 정리를 실제로 확인했습니다. 테스트 종료 후 서비스는 inactive/static, worker 프로세스는 0, `user.max_user_namespaces`는 0으로 복원했습니다.

게시 후 새 clone에서도 확인할 수 있는 기록은 [release 검증 보고서](../../../../.agent-work/tasks/p2-reviewed-release-20261103/report.ko.md)와 [작업 명세](../../../../.agent-work/tasks/p2-reviewed-release-20261103/spec.md)입니다. 현재 release 게시 절차는 진행 중이므로 이 링크는 게시 후 사용합니다. 작업 로컬의 상세 재현 자료는 `outputs/p2-host-isolation/vm-acceptance-reproduction.en.md`와 `VM-실행-검증-20261103.md`이며, 이 로컬 경로가 새 clone에 존재한다고 가정하지 않습니다.

위 2026-11-03 결과는 동일 Linux 호스트의 수동 pilot 기록입니다. 당시 남았던 제한된 업로드·privileged executor 연결은 이후 자동 로컬 RPC 절에서 별도로 다룹니다. 호스트 간 인증·외부 HTTPS/GitHub 게시·실제 자격증명 회전·현재 데스크톱의 전체 도구/connector 격리는 계속 미구현 또는 미검증이며, 전체 P2 적용 완료로 해석하지 않습니다.

systemd 옵션 참고: [실행 환경](https://www.freedesktop.org/software/systemd/man/255/systemd.exec.html), [자원 제어](https://www.freedesktop.org/software/systemd/man/255/systemd.resource-control.html), [서비스 수명](https://www.freedesktop.org/software/systemd/man/255/systemd.service.html).
