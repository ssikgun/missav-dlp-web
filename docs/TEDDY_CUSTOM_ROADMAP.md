# Teddy Custom Downloader — Feature Roadmap

- 작성 시각: 2026-08-21 KST
- 업데이트 시각: 2026-08-21 KST
- 기준: CT108 production migration **CLOSED** 후 모바일 UI 개발 시작
- 운영 코드 기준 이미지 소스: `6cb5415322ae420cefa96d8d48540af850b99b67`
- 현재 개발 브랜치: `teddy-mobile-ui`

## 완료 — Migration closure

상태: **CLOSED / PASS**

실제 Proxmox host reboot 후 다음 자동복구를 모두 확인했다.

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

별도 CT startup delay 없이 boot race가 발생하지 않았다. 최종 handoff에서 migration 상태를 CLOSED 처리했다.

---

## Feature 1 — Responsive PC / Mobile UI

상태: **IN PROGRESS**

목표: PC와 모바일을 별도 제품으로 분리하지 않고, 동일한 Teddy Downloader URL/백엔드에서 화면 너비와 모바일 입력 특성에 따라 적절한 UI를 제공한다.

기본 방향:

- 하나의 `https://downloader.ssikgun.com`
- Desktop 기본 UI 유지
- CSS media query / responsive layout 중심으로 모바일 UI 제공
- User-Agent 기반 분기보다 viewport width를 우선하고, 모바일 landscape 보완에는 coarse pointer 조건을 함께 사용 가능
- 기존 Downloader backend, HLS engine, routing, VPN, split-storage 동작은 변경하지 않는 것을 원칙으로 함
- 1차 실기 기준: iPhone 17 Pro Max

### Desktop

- 현재 넓은 화면 레이아웃 최대한 유지
- 기존 네트워크 패널 / 작업 목록 / Browser embedded 사용성 보존
- 파일 관리: `재생 / 다운로드 / 삭제`
- 모바일 대응 때문에 PC UI가 퇴행하지 않도록 회귀검증

### Mobile

- 좁은 화면에서 겹침/overflow 제거
- 주요 영역을 세로 1열 또는 필요한 경우 2열 카드로 재배치
- 사이드 내비게이션은 모바일에서 하단 내비게이션 형태 우선
- URL 입력창과 실행 버튼 모바일 친화적 배치
- 작업 목록 모바일 카드 대응
- 긴 파일명 / URL / 상태 문자열 안전 줄바꿈
- 진행률 bar는 가용 폭 100% 사용
- 터치 버튼 최소 hit area를 충분히 확보
- Direct / Proxy / VPN 상태/제어 모바일 재배치
- network panel 모바일 1열화
- `overflow-wrap: anywhere` 등 긴 문자열 안전 처리
- iPhone safe area (`safe-area-inset-*`) 대응
- iOS 입력창 자동 확대 방지를 위해 필요한 텍스트 입력은 16px 기준 검토
- 불필요한 전체 페이지 가로 스크롤 제거

### File Manager / Playback

확정 요구사항:

- 사용자 표시 용어 `미리보기` → **`재생`**
- Desktop 파일 카드: `재생 / 다운로드 / 삭제`
- Mobile 파일 카드: **`재생 / 삭제`**, 다운로드 버튼 숨김
- PC와 Mobile 모두 파일 삭제 전 확인 팝업 표시
- 삭제 확인 문구는 NAS 실제 파일이 삭제되고 되돌릴 수 없음을 명확히 표시
- 삭제 API/backend 자체는 기존 동작 유지
- 기본 재생은 현재 Teddy HTML5 `<video>` + `/api/files/<file>/stream` Direct Play 유지
- 모바일 video에 `playsinline`을 사용하여 iPhone inline playback 지원
- 세로 화면에서 모바일 친화 플레이어
- 가로 회전 시 영상이 화면을 최대한 사용하도록 landscape layout
- iOS native video controls / fullscreen 사용성 보존

### Optional playback fallback — Jellyfin

상태: **후순위 / 실제 필요 시 검증**

Media LXC의 Jellyfin은 이미 Synology video mount와 `/dev/dri/renderD128` 장치를 가지고 있다. 다만 Teddy 기본 재생 엔진으로 교체하지 않는다.

원칙:

- iPhone/Safari가 직접 재생 가능한 파일 → Teddy HTML5 Direct Play
- 직접 재생이 안 되는 코덱/컨테이너가 실제로 발견될 때 → Jellyfin/FFmpeg hardware transcode fallback 검토
- Jellyfin 연동을 위해 정상 MP4 direct-play 경로를 불필요하게 복잡하게 만들지 않는다
- 실제 hardware transcoding 활성 여부는 연동 전에 별도 확인

### VPN Browser on Mobile

Desktop에서는 현재 embedded Browser를 유지한다.

모바일에서는 작은 iframe 내부에서 원격 Chromium을 조작하기 불편할 수 있으므로 다음 UX를 우선 검토한다.

- 현재 iframe이 모바일 viewport에서 정상 동작하는지 먼저 확인
- 필요하면 `VPN Browser 전체 화면으로 열기` 버튼 제공
- `https://browser.ssikgun.com`을 모바일 전체 화면/새 화면 형태로 사용
- Downloader로 쉽게 돌아올 수 있는 흐름 유지

기존 Browser 기능을 다시 만들거나 backend를 변경하지 않는다.

### Implementation stages

1. Responsive base layer / iPhone safe area / bottom navigation
2. Download task cards / network / routing / settings mobile layout
3. File manager mobile cards
4. `미리보기` → `재생`, mobile download action 숨김, 공통 NAS delete confirmation
5. Mobile video portrait / landscape playback
6. VPN Browser mobile UX
7. iPhone 17 Pro Max 실기 검증
8. Desktop regression 검증
9. 필요 시 Jellyfin fallback feasibility 검증
10. immutable GHCR image로 production 승격

### Optional follow-up — PWA

Responsive Mobile UI가 안정화된 뒤 선택적으로 검토한다.

- 홈 화면 추가
- standalone/app-like 실행
- 아이콘 / manifest / theme metadata
- App Store native app 개발과는 별도이며 필수 항목 아님

### Acceptance criteria

최소 다음을 실제 화면에서 확인한다.

- PC 브라우저: 기존 주요 레이아웃 및 기능 회귀 없음
- iPhone 17 Pro Max portrait: 텍스트/버튼/상태 영역이 서로 겹치지 않음
- iPhone 17 Pro Max landscape: video playback이 가용 화면을 정상 사용
- 모바일에서 가로 overflow가 의도하지 않은 영역에 발생하지 않음
- task cards / progress / controls 조작 가능
- Mobile 파일 관리에는 `재생 / 삭제`만 표시
- PC 파일 관리에는 `재생 / 다운로드 / 삭제` 표시
- PC/Mobile 삭제 모두 confirmation 후에만 실제 DELETE 수행
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
