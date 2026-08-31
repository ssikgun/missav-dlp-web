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


def collected(
    dvd_id,
    route,
    *,
    cover=True,
):
    item = {
        "dvd_id": dvd_id,
        "title": dvd_id + " Test Title",
        "release_date": "2026-08-01",
        "studio": "Test Studio",
        "idols": [
            "Actress A",
            "Actress B",
        ],
        "genres": [
            "Genre A",
            "Genre B",
        ],
        "source_url":
            "https://example.invalid/"
            + dvd_id.lower(),
    }

    if cover:
        item["cover_url"] = (
            "https://example.invalid/"
            "cover.jpg"
        )

    return {
        "dvd_id": dvd_id,
        "status": "FOUND",
        "route": route,
        "request_count": 1,
        "item": item,
    }


direct = collected(
    "AKDL-312",
    "javdatabase-movie",
)

fallback = collected(
    "AT-099",
    "missav-en-movie",
    cover=False,
)

direct_payload = (
    collected_to_javinfo_payload(
        direct
    )
)

fallback_payload = (
    collected_to_javinfo_payload(
        fallback
    )
)

assert (
    "jacketFullUrl"
    in direct_payload["result"]
)

assert (
    "jacketFullUrl"
    not in fallback_payload["result"]
)

with tempfile.TemporaryDirectory(
    prefix="teddy-cp80-"
) as temp:
    db = connect(
        Path(temp) / "test.sqlite3"
    )

    initialize(db)

    for _ in range(2):
        assert (
            apply_held_collected_metadata(
                db,
                direct,
            )
            == "AKDL-312"
        )

        assert (
            apply_held_collected_metadata(
                db,
                fallback,
            )
            == "AT-099"
        )

    direct_row = db.execute(
        """
        SELECT
            metadata_source,
            cover_url
        FROM titles
        WHERE dvd_id='AKDL-312'
        """
    ).fetchone()

    fallback_row = db.execute(
        """
        SELECT
            metadata_source,
            cover_url
        FROM titles
        WHERE dvd_id='AT-099'
        """
    ).fetchone()

    assert (
        direct_row["metadata_source"]
        == "javdatabase-movie"
    )

    assert direct_row["cover_url"]

    assert (
        fallback_row["metadata_source"]
        == "missav-en-movie"
    )

    assert (
        fallback_row["cover_url"]
        is None
    )

    assert (
        db.execute(
            """
            SELECT COUNT(*)
            FROM title_people
            WHERE dvd_id='AKDL-312'
            """
        ).fetchone()[0]
        == 2
    )

    assert (
        db.execute(
            """
            SELECT COUNT(*)
            FROM title_genres
            WHERE dvd_id='AT-099'
            """
        ).fetchone()[0]
        == 2
    )

    assert (
        db.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
        == "ok"
    )

    db.close()


bad = dict(fallback)
bad["status"] = "NOT_FOUND"

try:
    collected_to_javinfo_payload(
        bad
    )
except ValueError:
    pass
else:
    raise RuntimeError(
        "NOT_FOUND accepted"
    )


bad = collected(
    "AKDL-312",
    "javdatabase-movie",
    cover=False,
)

try:
    collected_to_javinfo_payload(
        bad
    )
except ValueError:
    pass
else:
    raise RuntimeError(
        "direct missing cover accepted"
    )


bad = collected(
    "AT-099",
    "missav-en-movie",
    cover=False,
)

bad["item"]["dvd_id"] = "AT-098"

try:
    collected_to_javinfo_payload(
        bad
    )
except ValueError:
    pass
else:
    raise RuntimeError(
        "DVD-ID mismatch accepted"
    )


print(
    "DIRECT_ADAPTER=PASS"
)

print(
    "MISSAV_NO_COVER_ADAPTER=PASS"
)

print(
    "IDEMPOTENT_INSERT=PASS"
)

print(
    "FAIL_CLOSED_CHECKS=PASS"
)

print(
    "STAGE8_HELD_BACKFILL_ADAPTER_SMOKE=PASS"
)
