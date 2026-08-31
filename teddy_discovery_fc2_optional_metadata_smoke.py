import tempfile
from pathlib import Path

from teddy_discovery_db import (
    connect,
    initialize,
)

from teddy_discovery_held_backfill import (
    apply_held_collected_metadata,
    collected_to_javinfo_payload,
)

from teddy_discovery_missav_movie import (
    parse_missav_movie_html,
)

from teddy_discovery_missav_movie_writer import (
    apply_missav_en_movie_metadata,
)


DVD_ID = "FC2-PPV-4451371"

URL = (
    "https://missav.ws/en/"
    "fc2-ppv-4451371"
)


def sparse_html(
    extra="",
):
    return f"""
    <html>
      <head>
        <meta
          property="og:title"
          content="{DVD_ID} H-Cup Gravure title">

        <meta
          property="og:video:release_date"
          content="2024-05-28">
      </head>

      <body>
        <div class="space-y-2">

          <div class="text-secondary">
            <span>Release date:</span>
            2024-05-22
          </div>

          <div class="text-secondary">
            <span>Code:</span>
            {DVD_ID}
          </div>

          <div class="text-secondary">
            <span>Title:</span>
            FC2 sparse fixture title
          </div>

          <div class="text-secondary">
            <span>Tag:</span>
            amateur, Beautiful woman, Uncensored
          </div>

          {extra}

        </div>
      </body>
    </html>
    """


item = parse_missav_movie_html(
    sparse_html(),
    requested_url=URL,
    expected_dvd_id=DVD_ID,
)

assert item["dvd_id"] == DVD_ID

#
# Teddy catalog date remains the visible
# Release date, not OG publication timestamp.
#
assert (
    item["release_date"]
    == "2024-05-22"
)

assert item["studio"] is None
assert item["idols"] == []
assert item["genres"] == []

#
# Tag detail text must never become Genre.
#
assert "amateur" not in item["genres"]

print("FC2_SPARSE_PARSER=PASS")
print("FC2_RELEASE_LABEL_POLICY=PASS")
print("FC2_MAKER_ABSENT_ALLOWED=PASS")
print("FC2_ACTRESS_ABSENT_ALLOWED=PASS")
print("FC2_GENRE_ABSENT_ALLOWED=PASS")
print("FC2_TAG_NOT_PROMOTED_TO_GENRE=PASS")


#
# Partial maker remains invalid.
#
try:
    parse_missav_movie_html(
        sparse_html(
            """
            <div class="text-secondary">
              <span>Maker:</span>
              ONLY LABEL
            </div>
            """
        ),
        requested_url=URL,
        expected_dvd_id=DVD_ID,
    )

except ValueError as exc:
    assert (
        "maker contract mismatch"
        in str(exc)
    )

else:
    raise RuntimeError(
        "partial maker accepted"
    )


#
# Partial genre remains invalid.
#
try:
    parse_missav_movie_html(
        sparse_html(
            """
            <div class="text-secondary">
              <span>Genre:</span>
              Amateur
            </div>
            """
        ),
        requested_url=URL,
        expected_dvd_id=DVD_ID,
    )

except ValueError as exc:
    assert (
        "genre contract mismatch"
        in str(exc)
    )

else:
    raise RuntimeError(
        "partial genre accepted"
    )


print("PARTIAL_MAKER_REJECTED=PASS")
print("PARTIAL_GENRE_REJECTED=PASS")


collected = {
    "dvd_id":
        DVD_ID,

    "status":
        "FOUND",

    "route":
        "missav-en-movie",

    "request_count":
        1,

    "item":
        item,
}


payload = (
    collected_to_javinfo_payload(
        collected
    )
)

assert (
    payload["result"]["makers"]
    == []
)

assert (
    payload["result"]["categories"]
    == []
)

print("SPARSE_BACKFILL_PAYLOAD=PASS")


#
# Direct JAVDatabase metadata remains strict:
# it must still provide a studio.
#
direct_bad = {
    "dvd_id":
        "EBWH-353",

    "status":
        "FOUND",

    "route":
        "javdatabase-movie",

    "request_count":
        1,

    "item": {
        "dvd_id":
            "EBWH-353",

        "title":
            "Direct test",

        "release_date":
            "2026-08-01",

        "studio":
            None,

        "cover_url":
            "https://example.invalid/cover.jpg",

        "idols":
            [],

        "genres":
            [],

        "source_url":
            "https://www.javdatabase.com/"
            "movies/ebwh-353/",
    },
}

try:
    collected_to_javinfo_payload(
        direct_bad
    )

except ValueError as exc:
    assert (
        "direct metadata studio missing"
        in str(exc)
    )

else:
    raise RuntimeError(
        "direct missing studio accepted"
    )

print("DIRECT_STUDIO_STILL_REQUIRED=PASS")


with tempfile.TemporaryDirectory(
    prefix="teddy-stage8-fc2-optional-"
) as temp:

    root = Path(temp)

    #
    # Held-media native upsert path.
    #
    held_db = connect(
        root / "held.sqlite3"
    )

    initialize(
        held_db
    )

    assert (
        apply_held_collected_metadata(
            held_db,
            collected,
        )
        == DVD_ID
    )

    held_row = held_db.execute(
        """
        SELECT
            maker,
            release_date,
            metadata_source
        FROM titles
        WHERE dvd_id=?
        """,
        (DVD_ID,),
    ).fetchone()

    assert held_row is not None
    assert held_row["maker"] is None

    assert (
        held_row["release_date"]
        == "2024-05-22"
    )

    assert (
        held_row["metadata_source"]
        == "missav-en-movie"
    )

    assert (
        held_db.execute(
            """
            SELECT COUNT(*)
            FROM title_people
            WHERE dvd_id=?
            """,
            (DVD_ID,),
        ).fetchone()[0]
        == 0
    )

    assert (
        held_db.execute(
            """
            SELECT COUNT(*)
            FROM title_genres
            WHERE dvd_id=?
            """,
            (DVD_ID,),
        ).fetchone()[0]
        == 0
    )

    assert (
        held_db.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
        == "ok"
    )

    held_db.close()

    print(
        "SPARSE_HELD_NATIVE_WRITER=PASS"
    )


    #
    # Existing normal metadata fallback writer.
    #
    worker_db = connect(
        root / "worker.sqlite3"
    )

    initialize(
        worker_db
    )

    worker_db.execute(
        """
        INSERT INTO titles(
            dvd_id,
            title,
            metadata_source,
            first_seen_at,
            last_seen_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            DVD_ID,
            "Seed title",
            "missav-release",
            "first",
            "last",
        ),
    )

    worker_db.commit()

    assert (
        apply_missav_en_movie_metadata(
            worker_db,
            item,
        )
        == "updated"
    )

    worker_row = worker_db.execute(
        """
        SELECT
            maker,
            release_date,
            metadata_source,
            raw_metadata
        FROM titles
        WHERE dvd_id=?
        """,
        (DVD_ID,),
    ).fetchone()

    assert worker_row is not None
    assert worker_row["maker"] is None

    assert (
        worker_row["release_date"]
        == "2024-05-22"
    )

    assert (
        worker_row["metadata_source"]
        == "missav-en-movie"
    )

    assert worker_row["raw_metadata"]

    assert (
        worker_db.execute(
            """
            SELECT COUNT(*)
            FROM title_people
            WHERE dvd_id=?
            """,
            (DVD_ID,),
        ).fetchone()[0]
        == 0
    )

    assert (
        worker_db.execute(
            """
            SELECT COUNT(*)
            FROM title_genres
            WHERE dvd_id=?
            """,
            (DVD_ID,),
        ).fetchone()[0]
        == 0
    )

    assert (
        worker_db.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
        == "ok"
    )

    worker_db.close()

    print(
        "SPARSE_NORMAL_FALLBACK_WRITER=PASS"
    )


print(
    "STAGE8_FC2_OPTIONAL_METADATA_SMOKE=PASS"
)
