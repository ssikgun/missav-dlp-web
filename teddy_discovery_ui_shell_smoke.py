from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys


class MarkerParser(
    HTMLParser
):
    def __init__(
        self,
    ):
        super().__init__()

        self.ids = set()
        self.data_pages = []
        self.discovery_views = []
        self.stylesheets = []
        self.scripts = []

    def handle_starttag(
        self,
        tag,
        attrs,
    ):
        values = dict(
            attrs
        )

        element_id = values.get(
            "id"
        )

        if element_id:
            self.ids.add(
                element_id
            )

        data_page = values.get(
            "data-page"
        )

        if data_page:
            self.data_pages.append(
                data_page
            )

        discovery_view = values.get(
            "data-discovery-view"
        )

        if discovery_view:
            self.discovery_views.append(
                discovery_view
            )

        if (
            tag == "link"
            and values.get(
                "rel"
            ) == "stylesheet"
        ):
            href = values.get(
                "href"
            )

            if href:
                self.stylesheets.append(
                    href
                )

        if tag == "script":
            src = values.get(
                "src"
            )

            if src:
                self.scripts.append(
                    src
                )


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def sha256_file(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def main():
    if len(
        sys.argv
    ) != 4:
        raise RuntimeError(
            "usage: "
            "teddy_discovery_ui_shell_smoke.py "
            "<index> <css> <js>"
        )

    index_path = Path(
        sys.argv[1]
    )

    css_path = Path(
        sys.argv[2]
    )

    js_path = Path(
        sys.argv[3]
    )

    index = index_path.read_text(
        encoding="utf-8"
    )

    css = css_path.read_text(
        encoding="utf-8"
    )

    js = js_path.read_text(
        encoding="utf-8"
    )

    parser = MarkerParser()

    parser.feed(
        index
    )

    for required_id in (
        "page-download",
        "page-files",
        "page-settings",
        "page-discovery",
        "discoverySummary",
        "discoveryGenreControls",
        "discoveryGenreSelect",
        "discoveryStatus",
        "discoveryList",
    ):
        require(
            required_id
            in parser.ids,
            "missing UI id: "
            + required_id,
        )

    require(
        parser.data_pages.count(
            "download"
        ) == 1,
        "download sidebar changed",
    )

    require(
        parser.data_pages.count(
            "files"
        ) == 1,
        "files sidebar changed",
    )

    require(
        parser.data_pages.count(
            "settings"
        ) == 1,
        "settings sidebar changed",
    )

    require(
        parser.data_pages.count(
            "discovery"
        ) == 1,
        "Discovery sidebar count changed",
    )

    require(
        parser.discovery_views
        == [
            "latest",
            "weekly",
            "monthly",
            "genre",
        ],
        "Discovery view tabs changed",
    )

    require(
        parser.stylesheets.count(
            "/static/teddy-discovery.css"
        ) == 1,
        "Discovery stylesheet hook changed",
    )

    require(
        parser.scripts.count(
            "/static/teddy-discovery.js"
        ) == 1,
        "Discovery script hook changed",
    )

    expected_endpoints = (
        "/api/discovery/latest",
        "/api/discovery/weekly",
        "/api/discovery/monthly",
        "/api/discovery/categories",
        "/api/discovery/category?name=",
        "/api/discovery/media/cover/",
        "/api/discovery/media/preview/",
        "/api/discovery/download",
    )

    for endpoint in expected_endpoints:
        require(
            js.count(
                endpoint
            ) == 1,
            "Discovery JS endpoint "
            "count changed: "
            + endpoint,
        )

    require(
        js.count(
            "method: 'POST'"
        ) == 1,
        "Discovery JS POST count changed",
    )

    require(
        'method: "POST"'
        not in js,
        "unexpected double-quoted POST added",
    )

    require(
        js.count(
            "dvd_id: dvdId"
        ) == 1,
        "Discovery download must send DVD ID only",
    )

    for forbidden in (
        "http://",
        "https://",
        ".m3u8",
        "/stream",
        "method: 'PUT'",
        'method: "PUT"',
        "method: 'DELETE'",
        'method: "DELETE"',
        "cover_url",
        "source_url",
        "page_url",
    ):
        require(
            forbidden
            not in js,
            "Discovery JS crossed "
            "browser/write boundary: "
            + forbidden,
        )

    require(
        "function coverEndpoint("
        in js,
        "cover endpoint builder missing",
    )

    require(
        "function loadCover("
        in js,
        "lazy cover loader missing",
    )

    require(
        "function bindCoverLazyLoad("
        in js,
        "cover lazy binding missing",
    )

    require(
        "row.addEventListener("
        in js
        and "'toggle'"
        in js
        and "if (row.open)"
        in js,
        "cover is not gated by details open",
    )

    require(
        "row.dataset.coverRequested"
        in js,
        "cover repeat-request guard missing",
    )

    require(
        "image.src = coverEndpoint("
        in js,
        "internal cover endpoint assignment missing",
    )

    require(
        "bindCoverLazyLoad(\n            items"
        in js,
        "cover binding missing after list render",
    )

    require(
        "function previewEndpoint("
        in js,
        "preview endpoint builder missing",
    )

    require(
        "function startPreview("
        in js
        and "function stopActivePreview("
        in js
        and "function togglePreview("
        in js,
        "preview lifecycle functions missing",
    )

    require(
        "function bindPreviewLazyLoad("
        in js,
        "preview lazy binding missing",
    )

    require(
        "(hover: hover) and (pointer: fine)"
        in js
        and "'pointerenter'"
        in js
        and "'pointerleave'"
        in js,
        "desktop hover preview binding missing",
    )

    require(
        "'click'"
        in js
        and "!hoverPreviewMedia.matches"
        in js,
        "mobile tap preview binding missing",
    )

    require(
        "row.dataset.previewTouched = '1'"
        in js,
        "preview touched-only marker missing",
    )

    require(
        "state.activePreview"
        in js
        and "stopActivePreview();"
        in js,
        "one-preview-at-a-time guard missing",
    )

    require(
        "video.src = previewEndpoint("
        in js,
        "internal preview endpoint assignment missing",
    )

    require(
        js.count(
            "/api/discovery/media/preview/"
        ) == 1,
        "preview endpoint literal count changed",
    )

    require(
        "bindPreviewLazyLoad(\n            items"
        in js,
        "preview binding missing after list render",
    )

    require(
        "document.createElement(\n            'video'"
        in js,
        "lazy video DOM creation missing",
    )

    require(
        "video.removeAttribute(\n            'src'"
        in js,
        "preview media cleanup missing",
    )

    require(
        "discovery-cover-slot"
        in js,
        "cover placeholder slot missing",
    )

    require(
        ".discovery-cover-slot"
        in css,
        "cover slot CSS missing",
    )

    require(
        ".discovery-cover-image"
        in css,
        "cover image CSS missing",
    )

    require(
        ".discovery-cover-base"
        in css,
        "cover base CSS missing",
    )

    require(
        ".discovery-preview-video"
        in css,
        "preview video CSS missing",
    )

    require(
        ".discovery-preview-hint"
        in css,
        "preview hint CSS missing",
    )

    require(
        "#page-discovery"
        in css,
        "Discovery CSS page scope missing",
    )

    require(
        ".discovery-row"
        in css,
        "Discovery row CSS missing",
    )

    require(
        ".sidebar"
        not in css,
        "Discovery CSS modifies "
        "global sidebar",
    )

    require(
        ".page {"
        not in css,
        "Discovery CSS modifies "
        "global page class",
    )

    require(
        '<div class="discovery-title" title="'
        not in js,
        "dynamic title attribute "
        "construction returned",
    )

    require(
        '<option value="'
        not in js,
        "dynamic option HTML "
        "construction returned",
    )

    require(
        "genreSelect.innerHTML = categories.map"
        not in js,
        "Genre options returned to "
        "innerHTML construction",
    )

    require(
        "genreSelect.replaceChildren("
        in js,
        "Genre DOM construction missing",
    )

    require(
        "option.value = String("
        in js,
        "Genre option value DOM "
        "assignment missing",
    )

    require(
        "option.textContent = ("
        in js,
        "Genre option textContent "
        "assignment missing",
    )

    # Regression guard:
    # categories API exposes `name`, not `category`.
    require(
        js.count(
            "item.name"
        ) == 2,
        "Genre UI must use "
        "categories[].name contract",
    )

    require(
        "item.category"
        not in js,
        "legacy Genre category field "
        "returned",
    )

    # Regression guard:
    # Discovery owns light styles, so it must
    # also provide explicit dark-theme overrides.
    for selector in (
        'html[data-theme="dark"] .discovery-summary',
        'html[data-theme="dark"] .discovery-tabs',
        'html[data-theme="dark"] .discovery-select',
        'html[data-theme="dark"] .discovery-row',
        'html[data-theme="dark"] .discovery-title',
        'html[data-theme="dark"] .discovery-detail-value',
    ):
        require(
            selector
            in css,
            "Discovery dark-theme "
            "selector missing: "
            + selector,
        )

    oracle_payload = {
        "index_sha256":
            sha256_file(
                index_path
            ),

        "css_sha256":
            sha256_file(
                css_path
            ),

        "js_sha256":
            sha256_file(
                js_path
            ),

        "views":
            parser.discovery_views,

        "endpoints":
            expected_endpoints,
    }

    oracle = hashlib.sha256(
        json.dumps(
            oracle_payload,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        ).encode(
            "utf-8"
        )
    ).hexdigest()

    print(
        "DISCOVERY_UI_SHELL_ORACLE_SHA256="
        + oracle
    )

    print(
        "DISCOVERY_UI_NATIVE_SPA_HOOK_SMOKE=PASS"
    )

    print(
        "DISCOVERY_UI_FOUR_VIEW_SHELL_SMOKE=PASS"
    )

    print(
        "DISCOVERY_UI_EXISTING_PAGE_MARKERS_SMOKE=PASS"
    )

    print(
        "DISCOVERY_UI_DEDICATED_ASSETS_SMOKE=PASS"
    )

    print(
        "DISCOVERY_UI_SAME_ORIGIN_DOWNLOAD_BOUNDARY_SMOKE=PASS"
    )

    print(
        "DISCOVERY_UI_DYNAMIC_ATTRIBUTE_SAFETY_SMOKE=PASS"
    )

    print(
        "TEDDY_DISCOVERY_UI_SHELL_STATIC_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
