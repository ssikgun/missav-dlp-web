# Teddy Custom Downloader — Mobile UI Production Handoff

- 작성 시각: 2026-08-22 15:28 KST
- 상태: **CLOSED — RESPONSIVE MOBILE UI PRODUCTION COMPLETE**
- 운영 호스트: Proxmox CT108 (`downloader`, `192.168.1.155`)
- 운영 브랜치: `teddy-custom`
- production 이미지 소스 커밋:
  `54e83d344d0b8a90b81b1570fd30a1376298d91a`
- production immutable image:
  `ghcr.io/ssikgun/missav-dlp-web:teddy-54e83d344d0b8a90b81b1570fd30a1376298d91a`
- production image/index digest:
  `sha256:06e49f05791cc9f10e5c60646a6c5007a264798ef863e609c46acff1a932a2e0`
- deployment compose sync commit:
  `6542c13dcc6d1f97fe93847c23f7624d19a26d38`

> 이 문서는 2026-08-21 migration closure 이후 진행한 Responsive Mobile UI 작업의 별도 closure handoff이다. 기존 `TEDDY_CUSTOM_HANDOFF_20260821.md`는 migration 당시의 역사적 production snapshot이므로 수정하지 않고 보존한다.

---

## 1. 최종 판정

Responsive PC/Mobile UI 작업을 production에 승격했고 iPhone 실사용 및 PC desktop regression을 확인했다.

최종 판정:

- Responsive Mobile UI: **PASS**
- iPhone portrait layout: **PASS**
- Mobile HTML5 direct playback/fullscreen: **PASS**
- Mobile embedded VPN Browser: **PASS**
- Desktop regression: **PASS**
- Completion-card UX polish: **PASS**
- Mobile canary cleanup: **PASS**
- Repository deployment compose sync: **PASS**

**Mobile UI feature status: CLOSED.**

완료 task의 iPhone Safari client download finalization 문제는 Responsive UI closure와 분리된 별도 follow-up으로 남긴다. 원인은 아직 확정하지 않는다.

---

## 2. Production deployment

CT108 live deployment directory:

`/opt/missav-dlp-web`

Live app image:

`ghcr.io/ssikgun/missav-dlp-web:teddy-54e83d344d0b8a90b81b1570fd30a1376298d91a`

Local image inspect during deployment:

```text
ID=sha256:06e49f05791cc9f10e5c60646a6c5007a264798ef863e609c46acff1a932a2e0
```

Deployment procedure deliberately changed only the Downloader app container:

1. live `compose.yaml` image line changed from the prior immutable `2dc0280...` image to `54e83d...`
2. `docker compose config -q` PASS
3. new immutable image pull PASS
4. `docker compose up -d --no-deps missav-dlp-web`
5. running image and HTTP verified

Gluetun, desktop VPN Browser, and mobile VPN Browser were not intentionally recreated as part of the app image deployment.

---

## 3. Responsive UI behavior

Single product/origin remains:

`https://downloader.ssikgun.com`

The backend is shared between PC and mobile. Responsive behavior is driven primarily by viewport/layout CSS rather than a separate mobile application.

Mobile behavior includes:

- bottom navigation
- iPhone safe-area handling
- touch-friendly controls
- mobile task cards
- mobile network/routing layout
- safe wrapping for long file names, URLs and status text
- system-driven mobile dark/light appearance rather than a separate mobile theme toggle

Desktop keeps the existing wide-screen layout and controls.

---

## 4. File Manager / Playback

Final UI semantics:

Desktop file cards:

```text
재생 / 다운로드 / 삭제
```

Mobile file cards:

```text
재생 / 삭제
```

The mobile File Manager download action is intentionally hidden. This does not remove the completed-task `받기` action.

User-facing playback wording was changed from `미리보기` to `재생`.

Video element uses:

```html
<video controls playsinline preload="metadata">
```

Default playback remains Teddy native HTML5 Direct Play via the existing file stream endpoint. Jellyfin was not inserted into the normal MP4 playback path.

NAS file deletion confirmation is:

```text
이 파일을 NAS에서 삭제할까요? 삭제 후 되돌릴 수 없습니다.
```

This confirmation refers to actual NAS file deletion.

---

## 5. Completed-task action semantics

The completed task card intentionally retains:

```text
↓ 받기
```

because completed server-side downloads may later be downloaded to the client device for sharing or local use.

The previous large grey `×` task action was replaced with a red-toned textual action:

```text
목록에서 삭제
```

Important semantic boundary:

- `목록에서 삭제` → removes the task-list record
- NAS media file → remains untouched
- NAS file deletion → only through File Manager delete action and its irreversible confirmation

Existing completed bulk-clear semantics remain unchanged and must not be reimplemented.

---

## 6. Mobile VPN Browser

Final mobile browser design keeps the browser **inside the same Teddy Downloader page** using an iframe.

Desktop browser:

`https://browser.ssikgun.com`

Mobile browser:

`https://mobile-browser.ssikgun.com`

Downloader environment:

```text
TEDDY_BROWSER_URL=https://browser.ssikgun.com
TEDDY_MOBILE_BROWSER_URL=https://mobile-browser.ssikgun.com
```

Mobile browser service:

- container: `missav-vpn-browser-mobile`
- image: `jlesage/chromium:latest`
- host port: `58003`
- display: `720x1200`
- persistent config: `/opt/missav-mobile-browser-config:/config:rw`
- GPU render node: `/dev/dri/renderD128`
- Chromium proxy: `http://gluetun:8888`
- existing Teddy downloader extension loaded

The mobile iframe was changed to full-bleed layout. iPhone visual verification confirmed that the browser fills the available width without the previous right-side black margin.

Do not revert to direct navigation/new-window behavior unless a new explicit requirement is established.

---

## 7. Desktop regression result

After production promotion, desktop use was rechecked and reported normal.

Verified behavior included:

- existing PC layout
- completed-task `받기`
- `목록에서 삭제`
- File Manager / playback
- embedded desktop VPN Browser

No desktop rollback was required.

---

## 8. Canary cleanup

The mobile UI canary was intentionally retained until production and desktop regression passed, then removed.

Removed container:

`Teddy mobile canary: teddy-mobile-ui-test`

Removed local canary image tags:

- `missav-dlp-web:mobile-ui-test-2dc0280`
- `missav-dlp-web:mobile-ui-test-b92c6f5`
- `missav-dlp-web:mobile-ui-test-2906371`
- `missav-dlp-web:mobile-ui-test-6bdfdaf`
- `missav-dlp-web:mobile-ui-test-d344ac3`

Removed temporary work directories:

- `/opt/missav-mobile-ui-test-work-2906371`
- `/opt/missav-mobile-ui-test-work-2dc0280`
- `/opt/missav-mobile-ui-test-work-6bdfdaf`
- `/opt/missav-mobile-ui-test-work-b92c6f5`

Post-cleanup checks showed no remaining matching canary container, image tag, or work directory.

---

## 9. Deployment compose repository sync

The repository deployment compose was updated after production validation so it now describes the mobile browser runtime as well as the desktop browser.

File:

`docker-compose.gluetun.yml`

Sync commit:

`6542c13dcc6d1f97fe93847c23f7624d19a26d38`

Repository deployment compose now includes:

- `TEDDY_MOBILE_BROWSER_URL=https://mobile-browser.ssikgun.com`
- `vpn-browser-mobile`
- `DISPLAY_WIDTH=720`
- `DISPLAY_HEIGHT=1200`
- host port `58003`
- Gluetun HTTP proxy for mobile Chromium
- `/opt/missav-mobile-browser-config:/config:rw`

The repository compose intentionally keeps:

```yaml
image: ${TEDDY_IMAGE:?TEDDY_IMAGE must be an immutable GHCR Teddy image}
```

rather than hardcoding the current live SHA. Future deployment should continue to provide an explicit immutable GHCR image tag.

---

## 10. Open follow-up — iPhone Safari completed-file `받기`

This is **not** the server-side YouTube/MissAV download queue. It is the later client download of a completed NAS file from Teddy to iPhone Safari.

Reported symptom:

- Safari download progresses to 100%
- final state may become `!`

Basic response/header diagnostics already observed:

- HTTP `200`
- `Content-Disposition: attachment`
- `Content-Type: video/mp4`
- expected `Content-Length`
- `Accept-Ranges: bytes`
- matching ETag / Last-Modified behavior in basic checks

Therefore a simple server-side wrong `Content-Length` claim is not currently supported by evidence.

Still **확인필요**:

1. external first 1KB Range GET → expected `206` and correct `Content-Range`
2. external last 1KB Range GET → expected `206` and correct total size
3. if Range is correct, isolate iOS Safari final-save / filename sanitization / iCloud download destination behavior

A Unicode filename edge case is possible but unproven. Do not change server filename or split-storage behavior without a reproducer/evidence.

---

## 11. Existing functionality that must not be redone

Do not reopen or redesign these merely because mobile work is complete:

- HLS engine and worker/session behavior
- Proxy/VPN routing and recovery
- pause/resume
- remux
- scheduler
- generic yt-dlp behavior
- split local-work / NAS-final storage
- completed bulk clear semantics
- Browser profile / downloader extension
- network panel behavior
- current responsive mobile layout
- current mobile full-bleed iframe
- current HTML5 direct playback
- current task-record versus NAS-file delete boundary

Use live behavior and logs as source of truth before changing any of the above.

---

## 12. Optional future work

### PWA

Optional only after the responsive web UI is considered stable enough to benefit from app-like launch behavior.

Potential scope:

- Add to Home Screen
- manifest / icons
- standalone display mode
- theme metadata

PWA is not required for current mobile closure.

### Jellyfin fallback

Keep deferred until a real file fails native Safari playback because of codec/container compatibility.

Normal compatible files should remain on Teddy HTML5 Direct Play.

---

## 13. Operational principles

- Production deploys pin immutable GHCR tags.
- Keep dangerous Compose/server changes in small steps.
- Validate hostname/path before destructive CT108 operations when practical.
- Never expose runtime secrets in Git or documentation.
- Preserve PC behavior while changing mobile UI.
- Do not confuse task-list deletion with NAS file deletion.
- Do not reimplement completed Downloader functionality without regression evidence.
- Mark uncertain causes **확인필요** rather than guessing.

**Responsive Mobile UI closure status: CLOSED / PASS.**
