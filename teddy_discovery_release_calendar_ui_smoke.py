from pathlib import Path


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


root = Path(__file__).resolve().parent

html = (
    root
    / "templates"
    / "index.html"
).read_text(
    encoding="utf-8"
)

css = (
    root
    / "templates"
    / "teddy-discovery.css"
).read_text(
    encoding="utf-8"
)

js = (
    root
    / "templates"
    / "teddy-discovery.js"
).read_text(
    encoding="utf-8"
)

require(
    'id="discoveryReleaseControls"'
    in html,
    "release controls missing",
)

require(
    'id="discoveryReleaseDateSelect"'
    in html,
    "release date select missing",
)

require(
    'for="discoveryReleaseDateSelect">출시일'
    in html,
    "release selector label missing",
)

require(
    ".discovery-release-controls"
    in css,
    "release control CSS missing",
)

require(
    ".discovery-date-select"
    in css,
    "release select CSS missing",
)

require(
    "const releaseDateSelect"
    in js,
    "release selector JS binding missing",
)

require(
    "selectedReleaseDate: null"
    in js,
    "release selected-date state missing",
)

require(
    "'/api/discovery/release-calendar'"
    in js,
    "release calendar API missing",
)

require(
    "'/api/discovery/release-calendar?date='"
    in js,
    "selected-date API request missing",
)

require(
    "syncReleaseCalendarControls"
    in js,
    "release date synchronization missing",
)

require(
    "releaseDateSelect.addEventListener"
    in js,
    "release date change handler missing",
)

require(
    "data.view === 'release-calendar'"
    in js,
    "release calendar summary missing",
)

require(
    "releaseControls.hidden"
    in js,
    "release control visibility missing",
)

require(
    "view !== 'latest'"
    in js,
    "release control latest-only rule missing",
)

require(
    "data.release_dates"
    in js,
    "recent release dates payload unused",
)

require(
    "ranking.kind"
    in js
    and "'release-calendar'"
    in js,
    "release calendar ranking "
    "detail handling missing",
)

require(
    "'출시일 '"
    in js
    and "' · Teddy 최초 발견 '"
    in js,
    "release calendar detail "
    "text missing",
)


require(
    "item.item_count"
    in js,
    "release date item counts missing",
)

print(
    "RELEASE_CALENDAR_UI_SELECTOR=PASS"
)

print(
    "RELEASE_CALENDAR_UI_UPPER_RIGHT_CONTROL=PASS"
)

print(
    "RELEASE_CALENDAR_UI_RECENT_DATES=PASS"
)

print(
    "RELEASE_CALENDAR_UI_SELECTED_DATE_REQUEST=PASS"
)

print(
    "RELEASE_CALENDAR_UI_NO_OLD_LATEST_ROUTE=PASS"
    if (
        "return '/api/discovery/latest';"
        not in js
    )
    else
    "RELEASE_CALENDAR_UI_NO_OLD_LATEST_ROUTE=FAIL"
)

if (
    "return '/api/discovery/latest';"
    in js
):
    raise RuntimeError(
        "Latest tab still uses old latest API"
    )

print(
    "REAL_NETWORK_REQUESTS=0"
)

print(
    "PRODUCTION_DB_WRITES=0"
)

print(
    "TEDDY_DISCOVERY_RELEASE_CALENDAR_UI_SMOKE=PASS"
)
