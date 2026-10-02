from pathlib import Path
import re


def require(condition, message):
    if not condition:
        raise AssertionError(message)


root = Path(__file__).parent
html = (root / "templates/index.html").read_text()
js = (root / "templates/teddy-library.js").read_text()
css = (root / "templates/teddy-library.css").read_text()
discovery_js = (root / "templates/teddy-discovery.js").read_text()

# File Management owns the Library view; transient files moved under Download.
for marker in ('data-page="library"', 'id="page-library"', 'id="librarySummary"',
               'id="librarySearch"', 'id="libraryFilter"', 'id="librarySort"',
               'id="libraryStatus"', 'id="libraryList"'):
    require(marker in html, f"missing File Manager marker: {marker}")
require('data-page="files"' not in html and 'id="page-files"' not in html,
        "old standalone Files page/sidebar must be removed")
require('id="fileSearch"' in html and 'id="fileSort"' in html and 'id="fileList"' in html,
        "transient Files controls must remain")
require('data-download-view="preclean"' in html and 'data-download-panel="preclean"' in html,
        "transient Files view must live under Download")
require("if (view === 'preclean') fetchFiles()" in html, "pre-clean tab must fetch files on open")
require('/static/teddy-library.css' in html and '/static/teddy-library.js' in html,
        "Library assets are not wired")
require("/api/library/" in html and "'/stream'" in html and "openVideoStream" in html,
        "Library playback adapter is not connected to the shared player")
require(html.count('<video ') == 1 and 'id="videoPlayer"' in html,
        "Library must reuse the single existing player")
require("player.src = url" in html and "player.pause()" in html,
        "shared player source and close behavior must remain present")

# Server-side search, filters and all Stage13-B sort modes.
for marker in ("fetch(queryUrl()", "params.set('q', q)", "params.set('ko', 'present')",
               "params.set('ko', 'absent')", "params.set('unresolved', 'true')",
               "params.set('mismatch', 'true')", "params.set('sort', sortBy)",
               "params.set('order', order)", "setTimeout(loadLibrary, 300)"):
    require(marker in js, f"missing query wiring: {marker}")
for sort_key in ('nas_added:desc', 'nas_added:asc', 'release_date:desc', 'dvd_id:asc',
                 'title:asc', 'size:desc', 'subtitle_status:asc'):
    require(sort_key in html, f"missing sort choice: {sort_key}")

# Display mappings; values are read from the API response without client-side reclassification.
for marker in ("case 'VALID'", "case 'ABSENT'", "case 'UNRESOLVED'",
               "한국어 자막", "자막 없음", "자막 미해결", "자막 상태 확인 필요",
               "jellyfinLabel", "RECOGNIZED", "Jellyfin 미인식",
               "추가 날짜 확인 불가", "nas_added_date", "managed_size_bytes",
               "size_unknown_count", "size_complete", "managed_relative_path",
               "stage12_status", "unresolved_label"):
    require(marker in js, f"missing display contract: {marker}")
require("/api/discovery/media/cover/" in js, "existing Discovery cover route not reused")
require("discovery-row" in js and "discovery-row-summary" in js and "discovery-detail" in js,
        "Discovery expandable row structure not reused")
require("data-play-dvd" in js and "playLibraryItem" in js,
        "Library row does not use the shared playback adapter")

# No actual delete request or private/raw payload rendering. E1 adds only a
# prepare + validate-only confirmation flow.
require("method: 'DELETE'" not in js and 'method: "DELETE"' not in js and "fetch('/api/library" not in js,
        "Library UI must not call a delete endpoint")
for marker in ("session_id", "subtitle_body", "artifact_json", "report_json"):
    require(marker not in js, f"raw or private payload marker present: {marker}")
for marker in ("/delete/prepare", "/delete/validate", "data-delete-prepare",
               "data-delete-ack", "data-delete-typed", "ack.checked && typed.value === dvd",
               "actual_delete_performed !== false", "영구 삭제임을 이해했습니다",
               "삭제 준비 검증 완료 · 실제 삭제는 아직 비활성"):
    require(marker in js, f"missing dry-run delete confirmation boundary: {marker}")
for marker in ("/delete/commit", "data-delete-final-ack", "data-delete-final-typed",
               "data-delete-final-phrase", "영구 삭제 실행", "payload.commit_enabled === true",
               "deleteCommitInFlight", "activeDeleteToken = null",
               "delete_target_active", "delete_activity_unavailable"):
    require(marker in js, f"missing gated final confirmation boundary: {marker}")
require("? '' : 'disabled'" in js and "서버 feature gate가 비활성이라" in js,
        "commit controls must remain disabled while the server feature gate is off")
require("prepare_token</code>" not in js, "prepare token must not be rendered")
nas_error_fixture = {"error": {"code": "nas_inspection_unavailable",
                               "message": "internal NAS detail must stay hidden"}}
require(nas_error_fixture["error"]["code"] == "nas_inspection_unavailable",
        "NAS inspection failure fixture is invalid")
for marker in ("'nas_inspection_unavailable'", "function safeDeleteErrorCode(payload)",
               "SAFE_DELETE_ERROR_CODES.has(code)",
               "error.safeCode = safeDeleteErrorCode(payload)"):
    require(marker in js, f"safe NAS inspection error handling missing: {marker}")
require("internal NAS detail must stay hidden" not in js,
        "backend error detail must not be rendered")
for marker in ("라이브러리를 불러오는 중", "조건에 맞는 작품이 없습니다.",
               "라이브러리 정보를 불러오지 못했습니다."):
    require(marker in js, f"missing load/empty/error state: {marker}")

# Responsive layout uses the Discovery family and adapts at desktop/tablet/mobile widths.
require(".discovery-row-summary.library-row-summary" in css, "Discovery summary styling not reused")
for breakpoint in ("max-width: 1020px", "max-width: 720px", "max-width: 420px"):
    require(breakpoint in css, f"missing responsive breakpoint: {breakpoint}")
require("overflow-wrap: anywhere" in css, "long IDs/paths must wrap on narrow screens")

# Stage13 UI-P1: landscape covers and an independent, accessible preview dialog.
def css_rule(source, selector):
    match = re.search(re.escape(selector) + r"\s*\{([^}]+)\}", source)
    require(match is not None, f"missing CSS rule: {selector}")
    return match.group(1)


desktop_css, tablet_css = css.split("@media (max-width: 1020px)", 1)
tablet_css, mobile_css = tablet_css.split("@media (max-width: 720px)", 1)
for source, width in ((desktop_css, 132), (tablet_css, 108), (mobile_css, 96)):
    cover_rule = css_rule(source, ".library-cover")
    summary_rule = css_rule(source, ".discovery-row-summary.library-row-summary")
    require(f"width: {width}px;" in cover_rule, f"cover width must be {width}px")
    require("height:" not in cover_rule, "responsive covers must retain their aspect ratio")
    require(f"grid-template-columns: {width}px minmax(0," in summary_rule,
            f"summary grid must reserve {width}px and allow text to shrink")
require("aspect-ratio: 3 / 2;" in css_rule(desktop_css, ".library-cover"),
        "landscape 3:2 cover sizing missing")
require("width: 54px;" not in css and "height: 72px;" not in css and
        "width: 44px;" not in css and "height: 60px;" not in css,
        "old tiny portrait sizing must be removed")
require("object-fit: contain;" in css_rule(css, ".library-cover img"),
        "thumbnails must show the entire cover")
require('<button type="button" class="library-cover library-cover-button"' in js and
        'data-cover-preview="${dvd}" aria-label=' in js,
        "cover must be an accessible preview button")
cover_click = js.split("const cover = event.target.closest('[data-cover-preview]');", 1)[1]
cover_click = cover_click.split("const prepare =", 1)[0]
for marker in ("event.preventDefault()", "event.stopPropagation()", "!cover.disabled",
               "openCoverPreview(cover.dataset.coverPreview)", "return;"):
    require(marker in cover_click, f"cover click must isolate summary activation: {marker}")
preview = js.split("function openCoverPreview(dvd)", 1)[1].split("function clearDeleteDialog()", 1)[0]
for marker in ("document.createElement('dialog')", "library-cover-dialog", "dialog.showModal()",
               "aria-label", "library-cover-close", "autofocus", "dialog.close()",
               "addEventListener('cancel'", "event.preventDefault()", "close();",
               "addEventListener('click'", "event.target !== dialog", "getBoundingClientRect()",
               "event.clientX < bounds.left", "event.clientX > bounds.right",
               "event.clientY < bounds.top", "event.clientY > bounds.bottom",
               "addEventListener('close'", "dialog.remove()",
               "/api/discovery/media/cover/${encodeURIComponent(dvd)}",
               "image.addEventListener('error'", "image.hidden = true", "image.removeAttribute('src')",
               "포스터를 불러오지 못했습니다", "library-cover-caption"):
    require(marker in preview, f"missing cover lightbox contract: {marker}")
require("fetch(" not in preview and "response" not in preview,
        "preview must load only the existing cover image without rendering backend payloads")
thumbnail_failure = js.split("list.addEventListener('error'", 1)[1].split("list.addEventListener('click'", 1)[0]
for marker in ("cover.disabled = true", "cover.innerHTML =", "포스터 없음", "}, true)"):
    require(marker in thumbnail_failure, f"missing safe thumbnail failure contract: {marker}")
dialog_rule = css_rule(css, ".library-cover-dialog")
require("max-width: min(92vw, 1200px);" in dialog_rule and "max-height: 88vh;" in dialog_rule,
        "cover dialog must fit the viewport")
image_rule = css_rule(css, ".library-cover-preview-image")
for marker in ("max-width: min(92vw, 1200px);", "max-height: calc(88vh - 90px);",
               "height: auto;", "object-fit: contain;"):
    require(marker in image_rule, f"large cover sizing missing: {marker}")
require(".library-cover-dialog::backdrop" in css and
        'html[data-theme="dark"] .library-cover-dialog' in css and
        ".library-cover-preview-image[hidden]" in css,
        "cover dialog theme/backdrop/failure visibility styles missing")
require("library-delete-dialog" in js and ".library-delete-dialog" in css,
        "existing delete dialog must remain independent")

require("discovery-row" in discovery_js, "Discovery regression source unavailable")
require('title="파일 관리" aria-label="파일 관리"' in html,
        "sidebar File Management label changed")
require('data-file-management-view="library"' in html and 'data-file-management-view="subtitle-status"' in html,
        "File Management subtabs missing")
require('GET' not in js, "unexpected Library method marker")

print("Stage13 UI-P1 Library UI shell smoke: OK")
