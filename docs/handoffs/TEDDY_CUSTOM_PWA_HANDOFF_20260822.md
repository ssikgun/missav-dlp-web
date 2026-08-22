# Teddy Custom Downloader — PWA Production Handoff

- 작성 시각: 2026-08-22 21:03 KST
- 상태: **CLOSED — PWA PHASE 1 PRODUCTION COMPLETE**
- 운영 호스트: Proxmox CT108 (`downloader`, `192.168.1.155`)
- 운영 브랜치: `teddy-custom`
- production 이미지 소스 커밋:
  `06a9b6ae79e8da47b7c386ec7f2b6c2d115ac14e`
- production immutable image:
  `ghcr.io/ssikgun/missav-dlp-web:teddy-06a9b6ae79e8da47b7c386ec7f2b6c2d115ac14e`
- production image/index digest:
  `sha256:bb0d26e7ffc5b3e993fe6efcafbf0ad7444c204fb20e9a7ca6bb503479a6ebf9`
- amd64 manifest digest:
  `sha256:f42e8d500c36d12b83be673d420a7c239bf0c5176aafe517e0d6a8ff29d761f2`

> 이 문서는 Responsive Mobile UI closure 이후 진행한 PWA Phase 1의 별도 production closure handoff이다.
> 기존 migration/mobile handoff는 당시 상태의 역사적 snapshot으로 유지한다.

---

## 1. 최종 판정

PWA Phase 1을 production에 승격하고 실제 iPhone 홈 화면 설치 및 standalone 실행까지 확인했다.

최종 판정:

- Add to Home Screen: **PASS**
- Teddy 전용 홈 화면 아이콘: **PASS**
- standalone / 주소창 없는 실행: **PASS**
- iPhone safe area / bottom navigation: **PASS**
- embedded mobile VPN Browser: **PASS**
- mobile browser full-height fit: **PASS**
- manifest / PWA assets runtime: **PASS**
- no-service-worker 정책: **PASS**
- production deployment: **PASS**
- canary/test resource cleanup: **PASS**

**PWA Phase 1 status: CLOSED.**

---

## 2. PWA architecture

PWA는 별도 backend나 별도 production server가 아니다.

기존 production origin:

`https://downloader.ssikgun.com`

을 그대로 사용하며 동일한 Teddy Downloader backend/UI가 다음 세 가지 형태를 모두 제공한다.

- Desktop browser
- Mobile Safari responsive UI
- iPhone Home Screen standalone PWA

PWA Phase 1은 기존 Teddy application에 얇은 install/app-like shell만 추가한다.

별도 native app, 별도 mobile backend, 별도 download engine은 추가하지 않았다.

---

## 3. Implemented PWA Phase 1

구현 항목:

- Web App Manifest
- Teddy PWA icon
- Apple touch icon
- `display=standalone`
- app name / short name
- theme/background metadata
- Apple web-app metadata
- `viewport-fit=cover`
- standalone safe-area handling

Manifest 주요 설정:

- `id=/`
- `start_url=/`
- `scope=/`
- `display=standalone`

관련 파일:

- `templates/teddy-manifest.webmanifest`
- `templates/teddy-icon.svg`
- `pwa/teddy-icon-180.png.b64`
- `teddy_patch_pwa.py`
- `templates/index.html`
- `templates/teddy-mobile.css`
- `Dockerfile`

---

## 4. Service worker policy

Phase 1에서는 **service worker를 사용하지 않는다.**

목적은 offline-first application이 아니라 Home Screen 설치 및 standalone UX 제공이다.

따라서 다음 위험을 만들지 않는다.

- stale task state
- stale download state
- stale API response
- stale UI shell
- cached video/file stream
- cached Browser iframe state

Production runtime 검증에서도 `PASS: no service worker marker`를 확인했다.

향후 명확한 이점이 확인되지 않는 한 service worker를 선제적으로 추가하지 않는다.

---

## 5. iPhone safe-area fix

초기 PWA canary에서 standalone 실행 시 다음 현상이 관찰되었다.

- bottom navigation이 iPhone home indicator와 겹침
- embedded Browser 상하 공간이 맞지 않음

최종 수정:

`templates/index.html` viewport에 `viewport-fit=cover`를 추가했다.

standalone browser 영역에는 `top: env(safe-area-inset-top);`을 적용했다.

실제 iPhone에서 bottom navigation이 home indicator 위에 정상 위치하는 것을 확인했다.

---

## 6. Mobile VPN Browser viewport

기존 production mobile Chromium display `720x1200`은 standalone PWA의 실제 가용 화면 비율과 맞지 않아 embedded Browser 위/아래에 빈 공간이 발생했다.

별도 test Chromium으로 실기 검증 후 최종 production 값을 다음과 같이 변경했다.

- `DISPLAY_WIDTH=720`
- `DISPLAY_HEIGHT=1300`

Production mobile Browser:

- container: `missav-vpn-browser-mobile`
- image: `jlesage/chromium:latest`
- host port: `58003`
- display: `720x1300`
- persistent config: `/opt/missav-mobile-browser-config:/config:rw`
- GPU: `/dev/dri/renderD128`
- proxy: `http://gluetun:8888`
- Teddy downloader extension 유지

실제 iPhone PWA embedded Browser에서 화면이 상하 공백 없이 채워지는 것을 확인했다.

---

## 7. Production deployment

Live directory:

`/opt/missav-dlp-web`

Running app image:

`ghcr.io/ssikgun/missav-dlp-web:teddy-06a9b6ae79e8da47b7c386ec7f2b6c2d115ac14e`

Running image/index digest:

`sha256:bb0d26e7ffc5b3e993fe6efcafbf0ad7444c204fb20e9a7ca6bb503479a6ebf9`

Runtime revision:

`06a9b6ae79e8da47b7c386ec7f2b6c2d115ac14e`

Deployment was intentionally split into small steps.

1. `teddy-pwa` canary verification
2. iPhone Home Screen standalone verification
3. safe-area correction
4. 720x1300 Browser canary verification
5. `teddy-pwa` -> `teddy-custom` fast-forward
6. immutable GHCR image verification
7. live Compose app image update
8. `missav-dlp-web` only recreate
9. live Compose mobile Browser height update
10. `missav-vpn-browser-mobile` only recreate
11. production runtime verification
12. canary/test cleanup

Rollback Compose snapshots created during deployment:

- `/opt/missav-dlp-web/compose.yaml.pre-pwa-20260822-204610`
- `/opt/missav-dlp-web/compose.yaml.pre-browser1300-20260822-205215`

---

## 8. Production verification result

Final production verification:

- HOME: `200 text/html; charset=utf-8`
- MANIFEST: `200 application/manifest+json`
- ICON PNG: `200 image/png`
- ICON SVG: `200 image/svg+xml; charset=utf-8`

PWA markers:

- `apple-mobile-web-app-capable`
- `teddy-manifest.webmanifest`
- `viewport-fit=cover`

Mobile Browser:

- `DISPLAY_WIDTH=720`
- `DISPLAY_HEIGHT=1300`
- HTTP `200`

Core containers:

- `missav-dlp-web` — running
- `missav-vpn-browser` — running
- `missav-vpn-browser-mobile` — running
- `gluetun-missav` — healthy

Compose validation: **PASS**

---

## 9. Canary / test cleanup

Removed:

- `teddy-pwa-test`
- `missav-vpn-browser-pwa-test`
- `/opt/missav-pwa-browser-test-config`

Released test ports:

- `58004`
- `58005`

Both ports were confirmed free after cleanup.

Production `58000`, `58001`, `58003` remain in use as designed.

---

## 10. Preserved behavior

PWA work did not intentionally redesign the Downloader backend.

Preserved:

- existing download engine
- routing / proxy / VPN behavior
- split storage
- NAS final storage
- completed task `↓ 받기`
- `목록에서 삭제` task-record semantics
- mobile File Manager `재생 / 삭제`
- desktop File Manager `재생 / 다운로드 / 삭제`
- NAS delete confirmation
- HTML5 direct playback / fullscreen
- embedded desktop VPN Browser
- embedded mobile VPN Browser
- system-driven mobile dark/light appearance

---

## 11. Deferred / out of scope

Still deferred:

- service worker / offline cache
- push notifications
- offline download queue
- native App Store application
- Jellyfin default playback integration
- iPhone Safari completed-file `받기` 100% -> `!` issue unless it reproduces again

Do not reopen these without a concrete requirement or reproducible issue.

---

## 12. Closure

PWA Phase 1 is production complete.

**Status: CLOSED — PWA PHASE 1 PRODUCTION COMPLETE**

Current production baseline:

- source: `06a9b6ae79e8da47b7c386ec7f2b6c2d115ac14e`
- image: `ghcr.io/ssikgun/missav-dlp-web:teddy-06a9b6ae79e8da47b7c386ec7f2b6c2d115ac14e`
- digest: `sha256:bb0d26e7ffc5b3e993fe6efcafbf0ad7444c204fb20e9a7ca6bb503479a6ebf9`
- mobile Browser: `720x1300`

Future work should treat this state as the PWA Phase 1 production baseline.
