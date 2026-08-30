from teddy_discovery_missav_movie import (
    parse_missav_movie_envelope,
)
from teddy_discovery_refresh import (
    _fetch_html_envelope,
    _fetch_missav_html_envelope,
    collect_metadata_candidate,
)


DVD_ID = "AT-099"

CANONICAL_URL = (
    "https://missav.ws/en/at-099"
)

SHARD_URL = (
    "https://missav.ws/dm26/en/at-099"
)


HTML = """
<html>
  <head>
    <meta
      property="og:title"
      content="AT-099 English fixture title">

    <meta
      property="og:video:release_date"
      content="2022-06-07">

    <meta
      property="og:video:actor"
      content="Test Actress">
  </head>

  <body>
    <div class="space-y-2">

      <div class="text-secondary">
        <span>Release date:</span>
        <time datetime="2011-11-20T01:00:00+08:00">
          2011-11-20
        </time>
      </div>

      <div class="text-secondary">
        <span>Actress:</span>
        <a
          class="text-nord13 font-medium"
          href="/en/actresses/test-actress">
          Test Actress
        </a>
      </div>

      <div class="text-secondary">
        <span>Genre:</span>
        <a
          class="text-nord13 font-medium"
          href="/en/genres/test-genre">
          Test Genre
        </a>
      </div>

      <div class="text-secondary">
        <span>Maker:</span>
        <a
          class="text-nord13 font-medium"
          href="/en/makers/test-maker">
          Test Maker
        </a>
      </div>

    </div>
  </body>
</html>
"""


class FakeResponse:
    def __init__(
        self,
        *,
        status,
        url,
        headers=None,
        text="",
    ):
        self.status_code = status
        self.url = url
        self.headers = (
            headers
            or {}
        )
        self.text = text
        self.history = []


class FakeSession:
    def __init__(
        self,
        responses,
    ):
        self.responses = list(
            responses
        )
        self.calls = []

    def get(
        self,
        url,
        **kwargs,
    ):
        self.calls.append(
            (
                url,
                kwargs,
            )
        )

        if not self.responses:
            raise RuntimeError(
                "unexpected GET"
            )

        return self.responses.pop(
            0
        )


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


#
# 1. Release-date semantic contract:
# visible catalog Release date wins while
# OG date remains structurally required.
#
item = parse_missav_movie_envelope(
    {
        "status":
            200,

        "requested_url":
            CANONICAL_URL,

        "final_url":
            CANONICAL_URL,

        "body":
            HTML,
    },
    expected_dvd_id=
        DVD_ID,
)

require(
    item["release_date"]
    == "2011-11-20",
    "visible release date "
    "was not selected",
)

print(
    "MISSAV_VISIBLE_RELEASE_DATE_SMOKE=PASS"
)


#
# 2. Generic fetch must still reject a 301
# by default.
#
generic_session = FakeSession([
    FakeResponse(
        status=301,
        url=CANONICAL_URL,
        headers={
            "Location":
                SHARD_URL,
        },
    ),
])

try:

    _fetch_html_envelope(
        generic_session,
        CANONICAL_URL,
        proxy_url=
            "http://gluetun:8888",
        timeout=20,
        impersonate="chrome",
    )

except RuntimeError:

    print(
        "GENERIC_REDIRECT_STILL_FAIL_CLOSED=PASS"
    )

else:

    raise AssertionError(
        "generic fetch accepted redirect"
    )


#
# 3. Strict MissAV one-hop shard transport.
#
transport_session = FakeSession([
    FakeResponse(
        status=301,
        url=CANONICAL_URL,
        headers={
            "Location":
                SHARD_URL,
        },
    ),
    FakeResponse(
        status=200,
        url=SHARD_URL,
        headers={
            "Content-Type":
                "text/html",
        },
        text=HTML,
    ),
])

envelope, request_count = (
    _fetch_missav_html_envelope(
        transport_session,
        CANONICAL_URL,
        dvd_id=DVD_ID,
        proxy_url=
            "http://gluetun:8888",
        timeout=20,
        impersonate="chrome",
    )
)

require(
    request_count == 2,
    "shard transport request count changed",
)

require(
    [
        call[0]
        for call
        in transport_session.calls
    ]
    == [
        CANONICAL_URL,
        SHARD_URL,
    ],
    "shard transport URL order changed",
)

require(
    envelope["requested_url"]
    == CANONICAL_URL,
    "logical requested URL changed",
)

require(
    envelope["final_url"]
    == CANONICAL_URL,
    "logical final URL changed",
)

require(
    envelope["transport_url"]
    == SHARD_URL,
    "physical shard URL missing",
)

require(
    envelope["redirect_count"]
    == 1,
    "logical redirect count changed",
)

parsed = (
    parse_missav_movie_envelope(
        envelope,
        expected_dvd_id=
            DVD_ID,
    )
)

require(
    parsed["dvd_id"]
    == DVD_ID,
    "parsed DVD-ID changed",
)

require(
    parsed["release_date"]
    == "2011-11-20",
    "shard parsed release date changed",
)

require(
    parsed["source_url"]
    == CANONICAL_URL,
    "logical source URL changed",
)

print(
    "MISSAV_ONE_HOP_SHARD_TRANSPORT_SMOKE=PASS"
)


#
# 4. Host escape must fail after exactly
# one physical MissAV request.
#
bad_session = FakeSession([
    FakeResponse(
        status=301,
        url=CANONICAL_URL,
        headers={
            "Location":
                "https://example.com/"
                "dm26/en/at-099",
        },
    ),
])

try:

    _fetch_missav_html_envelope(
        bad_session,
        CANONICAL_URL,
        dvd_id=DVD_ID,
        proxy_url=
            "http://gluetun:8888",
        timeout=20,
        impersonate="chrome",
    )

except Exception as exc:

    require(
        getattr(
            exc,
            "_teddy_request_count_delta",
            None,
        )
        == 1,
        "unsafe redirect request telemetry changed",
    )

    print(
        "MISSAV_SHARD_HOST_ESCAPE_REJECTED=PASS"
    )

else:

    raise AssertionError(
        "unsafe shard host accepted"
    )


#
# 5. End-to-end collector request telemetry:
#
# direct JAVDatabase 404
# + canonical MissAV 301
# + validated shard 200
# = exactly 3 physical requests.
#
collector_session = FakeSession([
    FakeResponse(
        status=404,
        url=(
            "https://www.javdatabase.com/"
            "movies/at-099/"
        ),
    ),
    FakeResponse(
        status=301,
        url=CANONICAL_URL,
        headers={
            "Location":
                SHARD_URL,
        },
    ),
    FakeResponse(
        status=200,
        url=SHARD_URL,
        headers={
            "Content-Type":
                "text/html",
        },
        text=HTML,
    ),
])

result = collect_metadata_candidate(
    DVD_ID,
    session=collector_session,
    proxy_url=
        "http://gluetun:8888",
    timeout=20,
    impersonate="chrome",
)

require(
    result["status"]
    == "FOUND",
    "collector status changed",
)

require(
    result["route"]
    == "missav-en-movie",
    "collector route changed",
)

require(
    result["request_count"]
    == 3,
    "collector shard request telemetry changed",
)

require(
    len(
        collector_session.calls
    )
    == 3,
    "collector physical GET count changed",
)

require(
    result["item"][
        "release_date"
    ]
    == "2011-11-20",
    "collector release date changed",
)

print(
    "MISSAV_SHARD_REQUEST_TELEMETRY_SMOKE=PASS"
)

print(
    "DISCOVERY_MISSAV_STAGE8_MINIMAL_FIX_SMOKE=PASS"
)
