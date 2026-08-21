# Teddy Custom Downloader — Feature Roadmap

- 작성 시각: 2026-08-21 KST
- 기준: 현재 CT108 production migration 완료 직전 상태
- 운영 코드 기준 이미지 소스: `6cb5415322ae420cefa96d8d48540af850b99b67`

## 현재 우선순위

### 0. Migration closure — PVE reboot automatic recovery test

상태: **확인필요 / 최우선 마무리 항목**

실제 Proxmox host reboot 후 다음 자동복구를 확인한다.

- PVE NFS automount
- CT108 `onboot: 1` 자동기동
- CT108 NAS bind mount
- Docker 자동기동
- `gluetun-missav`, `missav-dlp-web`, `missav-vpn-browser` 자동기동
- Gluetun `healthy`
- `/mnt/nas-downloads` NFS RW
- Downloader local/API 응답
- 외부 `downloader.ssikgun.com`
- embedded `browser.ssikgun.com`

전부 PASS하면 migration을 CLOSED 처리하고 최종 handoff를 갱신한다.

---

## Planned Feature 1 — Responsive PC / Mobile UI

상태: **PLANNED**

목표: PC와 모바일을 별도 제품으로 분리하지 않고, 동일한 Teddy Downloader URL/백엔드에서 화면 너비에 따라 적절한 UI를 제공한다.

기본 방향:

- 하나의 `https://downloader.ssikgun.com`
- Desktop 기본 UI 유지
- CSS media query / responsive layout 중심으로 모바일 UI 제공
- User-Agent 기반 분기보다 viewport width 기반 반응형을 우선
- 기존 Downloader backend, HLS engine, routing, VPN, split-storage 동작은 변경하지 않는 것을 원칙으로 함

### Desktop

- 현재 넓은 화면 레이아웃 최대한 유지
- 기존 네트워크 패널 / 작업 목록 / Browser embedded 사용성 보존
- 모바일 대응 때문에 PC UI가 퇴행하지 않도록 회귀검증

### Mobile

- 좁은 화면에서 겹침/overflow 제거
- 주요 영역을 세로 1열 또는 필요한 경우 2열 카드로 재배치
- URL 입력창과 실행 버튼 모바일 친화적 배치
- 작업 목록을 모바일용 카드 형태로 검토
- 긴 파일명 / URL / 상태 문자열 줄바꿈 또는 말줄임 처리
- 진행률 bar는 가용 폭 100% 사용
- 터치 버튼 최소 hit area를 충분히 확보
- Direct / Proxy / VPN 상태를 작은 badge/card 형태로 표시 검토
- network panel 모바일 1열화
- `overflow-wrap: anywhere` 등 긴 문자열 안전 처리
- iPhone safe area (`safe-area-inset-*`) 대응 검토
- 불필요한 전체 페이지 가로 스크롤 제거

### VPN Browser on Mobile

Desktop에서는 현재 embedded Browser를 유지한다.

모바일에서는 작은 iframe 내부에서 원격 Chromium을 조작하기 불편할 수 있으므로 다음 UX를 우선 검토한다.

- `VPN Browser 전체 화면으로 열기` 버튼
- `https://browser.ssikgun.com`을 모바일 전체 화면/새 화면 형태로 사용
- Downloader로 쉽게 돌아올 수 있는 흐름 유지

구현 전에 현재 Browser iframe/JS/CSS 구조를 실제 코드 기준으로 확인하고, 기존 Browser 기능을 다시 만들거나 backend를 변경하지 않는다.

### Optional follow-up — PWA

Responsive Mobile UI가 안정화된 뒤 선택적으로 검토한다.

- 홈 화면 추가
- standalone/app-like 실행
- 아이콘 / manifest / theme metadata
- App Store native app 개발과는 별도이며 필수 항목 아님

### Acceptance criteria

최소 다음을 실제 화면에서 확인한다.

- PC 브라우저: 기존 주요 레이아웃 및 기능 회귀 없음
- iPhone/mobile viewport: 텍스트/버튼/상태 영역이 서로 겹치지 않음
- 모바일에서 가로 overflow가 의도하지 않은 영역에 발생하지 않음
- task cards / progress / controls 조작 가능
- external Downloader 정상
- embedded 또는 full-screen VPN Browser 정상
- Downloader의 다운로드/VPN/split-storage backend 동작에는 불필요한 변경 없음

---

## 작업 원칙

- 이미 완료된 Downloader 기능을 재구현하지 않는다.
- UI 작업은 가능한 한 HTML/CSS/JS presentation layer에 국한한다.
- 실제 repository 코드와 live 동작을 먼저 확인한 뒤 수정한다.
- Desktop regression과 Mobile usability를 함께 검증한다.
- Production 변경은 immutable GHCR image로 배포한다.
- 위험한 서버/Compose 변경은 작은 단계로 수행한다.
