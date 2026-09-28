from pathlib import Path


ROOT = Path(__file__).parent
HTML = (ROOT / "templates/index.html").read_text(encoding="utf-8")
STATUS_JS = (ROOT / "templates/teddy-subtitle-status.js").read_text(encoding="utf-8")
LIBRARY_JS = (ROOT / "templates/teddy-library.js").read_text(encoding="utf-8")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    # Sidebar has a single File Management route, and no standalone transient Files route.
    require(HTML.count('data-page="library"') == 1, "one File Management sidebar entry")
    require('title="파일 관리" aria-label="파일 관리"' in HTML, "sidebar naming")
    require('data-page="files"' not in HTML, "standalone Files sidebar must be absent")
    require('data-page="library" title="영상 라이브러리"' not in HTML, "old Library sidebar label")
    require('data-page="discovery"' in HTML, "Discovery route retained")

    # File Management defaults to the Library panel and exposes subtitle status as a sibling view.
    require('id="page-library" class="page"' in HTML, "File Management SPA page retained")
    require("<div class=\"page-title\">파일 관리</div>" in HTML, "File Management title")
    require("JAV 보유 작품 · 자막 · Jellyfin 상태" in HTML, "File Management subtitle")
    require('data-file-management-view="library" aria-selected="true">보유 라이브러리' in HTML,
            "Library is default subtab")
    require('data-file-management-view="subtitle-status" aria-selected="false">자막 처리 현황' in HTML,
            "subtitle status subtab")
    require('id="librarySummary"' in HTML and 'id="librarySearch"' in HTML
            and 'id="libraryFilter"' in HTML and 'id="librarySort"' in HTML
            and 'id="libraryList"' in HTML, "Library list/search/filter/sort remain")
    require("/api/library/" in HTML and "'/stream'" in HTML and "openVideoStream" in HTML,
            "Library playback adapter retained")
    require("data-file-management-panel=\"subtitle-status\"" in HTML,
            "subtitle panel moved into File Management")
    settings = HTML.split('id="page-settings"', 1)[1]
    settings = settings.split("<!--", 1)[0]
    require('id="subtitle-status-panel"' not in settings, "status panel removed from Settings")
    require("동시 다운로드 수" in settings and 'id="set-max-concurrent"' in settings,
            "Settings controls retained")

    # Status API stays the same and only polls while its page and subtab are active.
    require("/api/subtitles/status" in STATUS_JS, "status API contract")
    require("file-management-view-subtitle-status" in STATUS_JS, "active subtab guard")
    require("page-library" in STATUS_JS and "page-settings" not in STATUS_JS,
            "status lifecycle follows File Management")
    require("setInterval" in STATUS_JS and "10000" in STATUS_JS, "10s polling retained")
    require("subtitle-status-activate" in STATUS_JS, "status activation event")
    for glyph in ("🟢", "🔴", "⚪"):
        require(glyph not in STATUS_JS, "traffic-light emoji removed")

    # Download owns both task queue and the preserved existing Files controls/actions.
    require('data-download-view="tasks" aria-selected="true">다운로드 작업' in HTML,
            "Download tasks default tab")
    require('data-download-view="preclean" aria-selected="false">정리 전 파일' in HTML,
            "pre-clean Files tab")
    preclean = HTML.split('data-download-panel="preclean"', 1)[1].split("</section>", 1)[0]
    for marker in ('id="fileSearch"', 'id="fileSort"', 'id="filesSummary"', 'id="fileList"'):
        require(marker in preclean, "existing Files control moved: " + marker)
    require("JAV 라이브러리로 이동되면 이 목록에서 사라집니다" in preclean,
            "pre-clean storage explanation")
    require("if (view === 'preclean') fetchFiles()" in HTML, "pre-clean fetch on open")
    for marker in ("function fetchFiles()", "function renderFiles()", "function previewFile(name)",
                   "function deleteFile(name)", "document.getElementById('fileSearch').addEventListener",
                   "document.getElementById('fileSort').addEventListener"):
        require(marker in HTML, "existing Files behavior missing: " + marker)
    require("/api/files/' + name + '/stream" in HTML, "existing Files stream route")
    require(HTML.count('<video ') == 1, "shared video player count")
    require("method: 'DELETE'" not in LIBRARY_JS and "method: \"DELETE\"" not in LIBRARY_JS,
            "no Library permanent-delete request")
    require("삭제" not in LIBRARY_JS, "no Library delete UI")

    print("FILE_MANAGEMENT_NAVIGATION_SMOKE=PASS")


if __name__ == "__main__":
    main()
