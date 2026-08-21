# Teddy Custom Downloader — Final Handoff

- 작성 시각: 2026-08-21 KST
- 상태: **PRODUCTION MIGRATION PASS**
- 운영 호스트: Proxmox CT108 (`downloader`, `192.168.1.155`)
- 운영 브랜치: `teddy-custom`
- 배포 이미지 소스 커밋: `6cb5415322ae420cefa96d8d48540af850b99b67`
- 운영 immutable image:
  `ghcr.io/ssikgun/missav-dlp-web:teddy-6cb5415322ae420cefa96d8d48540af850b99b67`
- 운영 image/index digest:
  `sha256:6de80934e40c5f6faf469e06464807663a90ab92b1fde5f82220a9428d8d1161`
- linux/amd64 manifest digest:
  `sha256:b802b7a2d5e967bd994e444558fb1e17d27337ad4285d59c663386b7f353ca09`

> 이 문서는 migration 완료 후 남기는 최종 handoff이다. 실제 production 이미지는 위 `6cb5415...` 코드 커밋에서 빌드된 immutable GHCR 이미지이며, 이 문서 자체는 이후 docs-only commit으로 추가될 수 있다. 따라서 문서 커밋으로 `teddy-custom` HEAD가 위 배포 소스 커밋보다 앞서더라도 정상이다. docs-only commit은 Docker 재빌드를 피하기 위해 `[skip ci]`를 사용한다.

---

## 1. 최종 판정

NAS Docker에서 운용하던 Teddy Custom Downloader를 새 Proxmox LXC CT108로 이전하고, 다운로드 작업 디스크와 최종 저장소를 분리했으며, Gluetun/VPN Browser/외부 HTTPS 경로/GHCR production image까지 포함한 운영 전환을 완료했다.

최종 확인 결과:

- Downloader production container 정상
- Gluetun 정상 및 health=`healthy`
- VPN Browser 정상
- 외부 `https://downloader.ssikgun.com` 정상
- embedded `https://browser.ssikgun.com` 정상
- Downloader local HTTP `200`
- `/api/browser/config` → `{"url":"https://browser.ssikgun.com"}`
- split storage startup 확인
  - Work directory: `/downloads`
  - Final directory: `/final`
- NAS final NFS mount RW 정상
- migration / production-candidate 로컬 테스트 이미지 제거 완료
- NAS의 구 Docker deployment 제거 완료

대규모 기능 E2E를 production cutover 후 다시 반복하지 않았다. 동일 migration image/candidate에서 이미 generic yt-dlp와 MissAV HLS split-storage E2E를 수행했고, production image는 해당 production source를 Dockerfile에 정식 wiring한 immutable GHCR build로 검증했다.

---

## 2. Git / Branch / Image 상태

Repository:

`ssikgun/missav-dlp-web`

Production source commit:

`6cb5415322ae420cefa96d8d48540af850b99b67`

Commit message:

`Remove obsolete LXC migration canary image`

Migration 완료 시점에는 다음 두 remote branch가 모두 위 커밋을 가리켰다.

- `teddy-custom`
- `teddy-lxc-migration`

`6cb5415...` 승격 전 production base는:

`db25e08af9e31d23dd1eaf353db4e30dc7b48c7c`

Migration 주요 커밋:

- `754e8542de8cf8f38e20cd0dc5e78af5c7574cc8` — Add split work and final storage primitives
- `abc8ba9e30e6476dc84d78cce1672c0210c7c76a` — Add deterministic split-storage runtime patch
- `11dc6642f9e50386c81da0afcb8482d0d91aff27` — Add isolated LXC migration canary image
- `62e6c5d` — Add configurable external VPN browser URL
- `b38e901` — Add browser runtime config patch
- `3fb8647` — Support external HTTPS VPN browser URL
- `f476c3e` — Stabilize network panel and task counter layout
- `8c37a8a` — Extend LXC canary with browser and layout fixes
- `bc65467` — Wire browser runtime config into full image build
- `5eb39ae` — Wire split storage into production image build
- `071146d` — Add CT108 production deployment compose
- `00139f0` — Ignore CT108 runtime and secret files
- `6cb5415` — Remove obsolete LXC migration canary image

Production Actions run:

- Workflow: `Build Teddy Custom Docker Image`
- Run ID: `32474799141`
- Initial attempt: failure due external SpoofDPI installer failing to resolve the latest version tag
- Failed job rerun: success
- Final workflow conclusion: **success**

The transient failure happened at:

```text
RUN curl -fsSL https://raw.githubusercontent.com/xvzc/SpoofDPI/main/install.sh | bash -s linux-amd64
Resolving latest version...
Failed to fetch latest version tag.
```

It occurred before migration runtime patching. A rerun succeeded without code change. Treat as a known external-installer transient unless it becomes recurrent.

GHCR verification:

Immutable tag and mutable `teddy-custom` tag both resolved to the same top-level digest:

`sha256:6de80934e40c5f6faf469e06464807663a90ab92b1fde5f82220a9428d8d1161`

linux/amd64 manifest for both:

`sha256:b802b7a2d5e967bd994e444558fb1e17d27337ad4285d59c663386b7f353ca09`

Live deployment intentionally pins the immutable tag, not the mutable `teddy-custom` tag.

---

## 3. CT108 / Proxmox

CT:

- CT ID: `108`
- hostname: `downloader`
- IP: `192.168.1.155/24`
- OS: Debian 13 trixie
- unprivileged LXC
- features: nesting/keyctl
- CPU: 4 cores
- RAM: 8 GB
- rootfs: 64 GB
- Docker: 29.7.2
- Docker Compose: v5.5.0

Host storage:

- local NVMe: WD SN740 2TB (`Data_2TB`)

TUN:

- `/dev/net/tun` works inside CT108

Intel iGPU:

Host GPU is Raptor Lake-S GT1 / UHD 770.

Only render node is passed through:

```text
/dev/dri/renderD128
```

Proxmox CT config command used:

```bash
pct set 108 --dev0 path=/dev/dri/renderD128,gid=992,mode=0660
```

Inside CT, render group GID is `992`.

Do not add `/dev/dri/card0` without new evidence that it is required.

VPN Browser Chromium hardware acceleration was validated. `chrome://gpu` showed hardware acceleration for Canvas/Compositing/Rasterization/Video Decode/WebGL/WebGL2/WebGPU interop. Software Video Encode is acceptable for this use.

---

## 4. Current production architecture

```text
Internet / LAN
   |
   +--> https://downloader.ssikgun.com
   |      -> NPM
   |      -> 192.168.1.155:58000
   |      -> missav-dlp-web
   |
   +--> https://browser.ssikgun.com
          -> NPM (WebSocket ON, HTTPS / Force SSL)
          -> 192.168.1.155:58001
          -> Gluetun published port
          -> vpn-browser sharing Gluetun network namespace
```

Docker layout:

```text
gluetun
  - ProtonVPN WireGuard
  - HTTP proxy :8888
  - control API :8000
  - published browser port host 58001 -> shared namespace :5800

vpn-browser
  - image: jlesage/chromium:latest
  - network_mode: service:gluetun
  - persistent profile: ./vpn-browser-config:/config
  - renderD128 passed through

missav-dlp-web
  - independent normal Docker network
  - host port 58000 -> container :5000
  - Direct route -> direct internet
  - Proxy route -> free proxy pool
  - VPN route -> http://gluetun:8888
```

Important: Downloader itself is **not** placed inside the Gluetun network namespace.

---

## 5. Current live compose

Live deployment directory:

`/opt/missav-dlp-web`

Live compose:

`/opt/missav-dlp-web/compose.yaml`

Relevant production services:

```yaml
services:
  gluetun:
    image: qmcgaw/gluetun:latest
    container_name: gluetun-missav
    restart: unless-stopped
    cap_add:
      - NET_ADMIN
    devices:
      - /dev/net/tun:/dev/net/tun
    env_file:
      - ./gluetun.env
    environment:
      - VPN_SERVICE_PROVIDER=protonvpn
      - VPN_TYPE=wireguard
      - HTTPPROXY=on
      - FREE_ONLY=on
      - TZ=Asia/Seoul
    ports:
      - "58001:5800/tcp"
    volumes:
      - ./gluetun-control-auth.toml:/gluetun/auth/config.toml:ro

  missav-dlp-web:
    image: ghcr.io/ssikgun/missav-dlp-web:teddy-6cb5415322ae420cefa96d8d48540af850b99b67
    container_name: missav-dlp-web
    restart: unless-stopped
    depends_on:
      - gluetun
    environment:
      - TEDDY_FINAL_DIR=/final
      - TEDDY_BROWSER_URL=https://browser.ssikgun.com
      - GLUETUN_PROXY_URL=http://gluetun:8888
      - GLUETUN_CONTROL_URL=http://gluetun:8000
    ports:
      - "58000:5000/tcp"
    volumes:
      - ./work:/downloads
      - /mnt/nas-downloads:/final

  vpn-browser:
    image: jlesage/chromium:latest
    container_name: missav-vpn-browser
    restart: unless-stopped
    network_mode: "service:gluetun"
    depends_on:
      - gluetun
    environment:
      - TZ=Asia/Seoul
      - ENABLE_CJK_FONT=1
      - VNC_LISTENING_PORT=-1
      - KEEP_APP_RUNNING=1
      - SUP_GROUP_IDS=992
      - CHROMIUM_CUSTOM_ARGS=--load-extension=/config/teddy-downloader-extension
    devices:
      - /dev/dri/renderD128:/dev/dri/renderD128
    volumes:
      - ./vpn-browser-config:/config:rw
```

Secrets/runtime files are deliberately not committed:

- `/opt/missav-dlp-web/gluetun.env`
- `/opt/missav-dlp-web/gluetun-control-auth.toml`
- `/opt/missav-dlp-web/work/`
- `/opt/missav-dlp-web/vpn-browser-config/`

The two secret files are root-owned `0600`. Never paste their contents into Git, chat, logs, or handoff documents.

`.gitignore` protects:

```gitignore
# CT108 production runtime / secrets
gluetun.env
gluetun-control-auth.toml
work/
vpn-browser-config/
```

A pre-GHCR-cutover compose backup exists as:

`/opt/missav-dlp-web/compose.yaml.before-ghcr-6cb5415`

An older browser-URL backup also exists as:

`/opt/missav-dlp-web/compose.yaml.before-browser-url`

---

## 6. Split storage design

Goal:

- downloads / fragments / remux / application state: CT108 local NVMe
- completed public media only: NAS NFS

Container layout:

```text
/downloads -> /opt/missav-dlp-web/work
/final     -> /mnt/nas-downloads
```

Runtime env:

```text
TEDDY_FINAL_DIR=/final
```

`teddy_storage.py` behavior:

- `work_root(core)` remains `core.DOWNLOAD_DIR` (`/downloads`)
- `public_root(core)` uses `TEDDY_FINAL_DIR`, fallback `core.DOWNLOAD_DIR`
- state/routing/proxy files remain local in `/downloads`
- public file listing/download/stream/delete use `/final` when configured

Cross-filesystem publish sequence:

1. copy completed local file to a hidden NFS-side `.<basename>.<uuid>.partial`
2. flush/fsync
3. verify source and partial sizes
4. `os.replace(partial, destination)` within final filesystem
5. best-effort fsync final directory
6. remove local source only after final rename succeeds

Failure behavior:

- publish failure cleans partial file where possible
- local source is retained
- task is not marked `완료` until all outputs are published
- storage publish errors do not trigger a network fallback
- subtitles/sidecars publish first, main media last
- crash recovery can recognize final destination when local source has already disappeared

`teddy_patch_split_storage.py` patches the runtime so both generic yt-dlp and custom HLS complete locally first and only then publish to NAS.

---

## 7. NAS NFS

NAS:

`192.168.1.201`

PVE mount:

```text
192.168.1.201:/volume1/video -> /mnt/nas-video
```

PVE `/etc/fstab`:

```fstab
# Synology video share for Downloader CT108
192.168.1.201:/volume1/video /mnt/nas-video nfs rw,vers=3,hard,_netdev,nofail,x-systemd.automount,x-systemd.idle-timeout=0 0 0
```

`findmnt --verify --verbose` passed before final deployment.

CT108 bind mount:

```text
/mnt/nas-video/video2/downloads -> /mnt/nas-downloads
```

Final production snapshot inside CT108:

```text
TARGET: /mnt/nas-downloads
SOURCE: 192.168.1.201:/volume1/video/video2/downloads
FSTYPE: nfs
OPTIONS include: rw,vers=3,hard
```

Synology squash ownership appears as nobody/nogroup/65534 in CT108. This is expected and functional; do not try to “fix” ownership without a real functional problem.

---

## 8. Browser / external access

External Downloader:

`https://downloader.ssikgun.com`

External VPN Browser:

`https://browser.ssikgun.com`

Downloader runtime API:

```text
GET /api/browser/config
```

Expected response:

```json
{"url":"https://browser.ssikgun.com"}
```

The embedded Browser panel reads this API and therefore works both internally and through the HTTPS external Downloader origin without hardcoding an HTTP/LAN URL.

Final external smoke test result:

- external Downloader: PASS
- embedded VPN Browser: PASS

Browser profile migrated from the previous NAS deployment to CT108 and retained bookmarks, developer mode, extension and profile state.

Downloader extension v1.1.0 current-page download path worked in migration E2E.

---

## 9. Network routing behavior

Expected paths:

```text
Direct -> downloader container direct internet
Proxy  -> free HTTP proxy pool
VPN    -> Gluetun HTTP proxy at http://gluetun:8888
```

Known learned routing examples from migration validation:

- YouTube -> Direct
- MissAV -> VPN

Gluetun validated:

- WireGuard kernelspace
- HTTP proxy on `:8888`
- control API on `:8000`
- VPN public IP different from direct WAN IP
- tunnel traffic proven
- automatic tunnel recovery observed

Do not move the Downloader container into `network_mode: service:gluetun`; that would destroy the intended Direct / Proxy / VPN separation.

---

## 10. Migration E2E evidence

### Generic yt-dlp split-storage

PASS.

Verified with YouTube Direct audio MP3:

- yt-dlp temp/home local in CT108 work storage
- post-processing local
- final MP3 published to NAS
- final size observed: `38,326,508` bytes
- local temporary/final working copy removed after successful publish

### MissAV HLS split-storage

PASS.

Representative task:

`ba7dda0e-5b34-49d6-b78a-39a45d2f6ac3`

Observed:

- extension POST path
- learned VPN route
- custom HLS with 16 workers
- per-worker HTTP/1.1 transport
- `network_recoveries: 1`
- local `.parts`
- local remux
- final NAS MP4 size `4,404,422,746` bytes
- local temp/final working copy absent after successful publish
- log ordering showed local completion -> Storage publish -> Routing learn

Additional completed migration task IDs:

- `f8a34019-a9b1-42c1-83e3-07e152cd9cd9`
- `43848250-c3b4-4a5d-bcb0-992d82571382`
- `d516a0b8-dffc-41b4-a8d1-dade04f611ee`

Before production cutover, active task check was repeated immediately before recreation:

```text
ACTIVE_TASKS = 0
yt-dlp/ffmpeg processes = none
```

---

## 11. Existing functionality that must not be reimplemented

These were already completed before/through migration and should not be redesigned unless new evidence shows a real bug:

- HLS per-worker session
- VPN async pool fallback/per-worker
- pause/resume `.parts`
- atomic remux
- Proxy/VPN recovery observers
- continuous scheduler, no batch barrier
- settings captured at execution/resume start; no active worker/pool resize
- deterministic runtime patch ownership/order
- generic yt-dlp support
- MP4 remux 99% UI behavior
- generic yt-dlp 99% UI behavior
- completed task bulk-clear behavior
- clearing tasks does not delete files
- VPN Browser profile persistence
- Chromium extension current-page download
- structured/allowlisted yt-dlp options
- MP3/MKV generic outputs
- cookies/login feature intentionally removed
- network panel and task counter layout stabilization
- external HTTPS Browser URL configuration

Performance result retained from prior benchmark:

- balanced recommendation: HLS workers/pool `16/16`
- HTTP/1.1 materially outperformed HTTP/2 on the tested Surrit/CDN + free HTTP proxy + curl_cffi async path

Current settings were migrated with 16 workers/pool and HLS HTTP v1.

---

## 12. Production cutover evidence

Before cutover:

- active tasks: `0`
- no yt-dlp/ffmpeg processes
- no temporary work artifacts
- NAS NFS RW mounted
- Gluetun running and healthy

Pulled immutable image:

`ghcr.io/ssikgun/missav-dlp-web:teddy-6cb5415322ae420cefa96d8d48540af850b99b67`

Local inspect after pull:

```text
ID=sha256:6de80934e40c5f6faf469e06464807663a90ab92b1fde5f82220a9428d8d1161
```

Only `missav-dlp-web` was recreated:

```bash
docker compose up -d --no-deps --force-recreate missav-dlp-web
```

Gluetun and VPN Browser were not recreated.

Live container after cutover:

```text
configured=ghcr.io/ssikgun/missav-dlp-web:teddy-6cb5415322ae420cefa96d8d48540af850b99b67
image_id=sha256:6de80934e40c5f6faf469e06464807663a90ab92b1fde5f82220a9428d8d1161
```

Startup smoke:

```text
[Teddy] site-aware storage enabled: work=/downloads final=/final
Work directory: /downloads
Final directory: /final
```

Local web:

```text
HTTP 200
```

Browser config:

```json
{"url":"https://browser.ssikgun.com"}
```

No fatal traceback was observed.

---

## 13. Cleanup completed

### Old NAS Docker deployment

Removed from Synology NAS:

- `gluetun-missav`
- `missav-dlp-web`
- `missav-vpn-browser`
- old compose network
- old project directory `/volume1/docker/missav-dlp-web`

NAS Docker image prune reclaimed approximately `20.19GB`. Final `docker system df` showed no remaining old Docker usage.

Final media directory `/volume1/video/video2/downloads` was not removed.

### CT108 migration artifacts

Removed:

- old canary container
- `/opt/chromium-ab-gpu-on`
- old migration state backup
- local image `missav-dlp-web:lxc-migration`
- local image `missav-dlp-web:production-candidate`

Final Teddy image inventory contained only the immutable production GHCR image.

Retained intentionally:

`/opt/missav-src`

This is an active Git checkout and was not auto-deleted.

GitHub CLI credentials also remain configured on CT108 and were not automatically logged out.

---

## 14. Final production snapshot

At final deployment verification:

Containers:

```text
gluetun-missav       qmcgaw/gluetun:latest                                                         Up (healthy)
missav-dlp-web       ghcr.io/ssikgun/missav-dlp-web:teddy-6cb5415322ae420cefa96d8d48540af850b99b67 Up
missav-vpn-browser   jlesage/chromium:latest                                                       Up
```

Downloader image:

```text
configured=ghcr.io/ssikgun/missav-dlp-web:teddy-6cb5415322ae420cefa96d8d48540af850b99b67
image_id=sha256:6de80934e40c5f6faf469e06464807663a90ab92b1fde5f82220a9428d8d1161
```

NFS:

```text
/mnt/nas-downloads
  <- 192.168.1.201:/volume1/video/video2/downloads
  nfs v3, rw, hard
```

Live compose image line:

```yaml
image: ghcr.io/ssikgun/missav-dlp-web:teddy-6cb5415322ae420cefa96d8d48540af850b99b67
```

---

## 15. Remaining item — 확인필요

Only one migration closure test remains deliberately deferred:

### PVE actual reboot / automatic recovery test — **확인필요**

A controlled Proxmox host reboot has not yet been performed because another workload was running on the host.

Pre-reboot configuration checks already passed:

- PVE `/etc/fstab` NFS line present
- `findmnt --verify --verbose` success
- CT108 `onboot: 1`
- CT108 `mp0` NAS bind configured
- CT108 static IP configured
- CT108 renderD128 device configured
- Docker enabled/active
- all three containers `restart: unless-stopped`
- NFS available inside CT108
- Gluetun healthy

No explicit CT `startup:` delay was added. Do not add one preemptively; only add boot-order delay if an actual reboot demonstrates a race.

### Reboot test procedure

Run only when the PVE host can safely be rebooted.

On `root@pve`:

```bash
sync
reboot
```

After PVE returns, **do not manually start CT108 or containers before checking automatic recovery**.

Check in this order:

1. PVE NFS automount is available
2. CT108 started automatically via `onboot: 1`
3. CT108 NAS bind mount is present
4. Docker started automatically inside CT108
5. all three containers started automatically
6. Gluetun becomes `healthy`
7. `/mnt/nas-downloads` inside CT108 resolves to the NAS NFS path and is RW
8. `http://192.168.1.155:58000` / API responds
9. `https://downloader.ssikgun.com` works
10. embedded `https://browser.ssikgun.com` works

If all ten pass, migration can be marked fully **CLOSED**.

---

## 16. Safe operational verification commands

### CT108 (`root@downloader`)

```bash
cd /opt/missav-dlp-web

docker compose ps

docker inspect missav-dlp-web \
  --format 'configured={{.Config.Image}} image_id={{.Image}}'

findmnt -T /mnt/nas-downloads -o TARGET,SOURCE,FSTYPE,OPTIONS

curl -sS -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:58000/
curl -sS http://127.0.0.1:58000/api/browser/config; echo

docker logs --tail 100 missav-dlp-web
```

Expected image:

```text
ghcr.io/ssikgun/missav-dlp-web:teddy-6cb5415322ae420cefa96d8d48540af850b99b67
```

Expected image ID/index digest:

```text
sha256:6de80934e40c5f6faf469e06464807663a90ab92b1fde5f82220a9428d8d1161
```

### Git source checkout

The retained checkout is:

`/opt/missav-src`

During migration it remained on `teddy-lxc-migration` with an intentionally narrow fetch refspec. Do not assume `origin/teddy-custom` is locally current unless it is explicitly fetched.

---

## 17. Rollback notes

If a new production image later proves faulty, prefer an explicit immutable-image rollback rather than using a mutable tag.

Current known-good immutable image:

```text
ghcr.io/ssikgun/missav-dlp-web:teddy-6cb5415322ae420cefa96d8d48540af850b99b67
```

Current compose backup before production image cutover:

```text
/opt/missav-dlp-web/compose.yaml.before-ghcr-6cb5415
```

Before any future recreate/rollback:

- verify active downloads are zero
- verify no `yt-dlp`/`ffmpeg` is running
- verify NAS NFS is mounted RW
- validate compose with `docker compose config -q`
- recreate only the Downloader with `--no-deps` unless Gluetun/Browser changes are explicitly intended

Do not destroy `/opt/missav-dlp-web/work` during a routine image rollback because it contains application state and may contain resumable local work.

---

## 18. Operating principles for future work

- Use logs and live server state as source of truth.
- Mark uncertain claims as **확인필요** rather than guessing.
- Do not reimplement already completed downloader features without evidence of a regression.
- Separate destructive/config-changing operations into small steps.
- Before dangerous CT108 commands, verify hostname/path when practical.
- Clearly distinguish commands for `root@pve`, `root@downloader`, and Synology NAS.
- Never request or expose VPN credentials, GitHub tokens, one-time codes, or Gluetun auth contents.
- Keep runtime/secrets out of Git.
- Production deploys should pin immutable GHCR tags.
- The PVE reboot test is the only currently known migration closure item still marked **확인필요**.
