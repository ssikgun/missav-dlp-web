import tempfile
from pathlib import Path

from teddy_discovery_db import (
    connect,
    initialize,
)

from teddy_discovery_ids import (
    parse_dvd_id,
)

from teddy_discovery_missav_movie import (
    normalize_dvd_id,
)

from teddy_discovery_refresh import (
    javdatabase_movie_url,
    missav_en_movie_url,
)

from teddy_discovery_held_backfill import (
    apply_held_collected_metadata,
)


standard = [
    "EBWH-353",
    "AT-099",
    "SW-893",
]

fc2 = [
    "FC2-PPV-4451371",
    "FC2-PPV-4551303",
    "FC2-PPV-4555371",
    "FC2-PPV-4575470",
    "FC2-PPV-4592689",
    "FC2-PPV-4640215",
]


for dvd_id in standard + fc2:

    parsed = parse_dvd_id(
        dvd_id
    )

    assert parsed is not None
    assert parsed.dvd_id == dvd_id

    assert (
        normalize_dvd_id(
            dvd_id
        )
        == dvd_id
    )


#
# 기존 편의 입력 동작 유지.
#
assert (
    normalize_dvd_id(
        "ebwh_353"
    )
    == "EBWH-353"
)

assert (
    normalize_dvd_id(
        "ebwh 353"
    )
    == "EBWH-353"
)

assert (
    normalize_dvd_id(
        "fc2_ppv_4451371"
    )
    == "FC2-PPV-4451371"
)

assert (
    normalize_dvd_id(
        "fc2ppv4451371"
    )
    == "FC2-PPV-4451371"
)


#
# parse_dvd_id가 leading ID를 찾을 수 있더라도
# metadata normalizer는 추가 suffix/prose를 허용하지 않는다.
#
for bad in (
    "SW-893-EXTRA",
    "FC2-PPV-4451371-EXTRA",
    "[EBWH-353]",
    "NOT-A-DVD-ID",
):
    try:
        normalize_dvd_id(
            bad
        )

    except ValueError:
        pass

    else:
        raise RuntimeError(
            "invalid metadata ID accepted: "
            + bad
        )


for dvd_id in fc2:

    assert (
        javdatabase_movie_url(
            dvd_id
        )
        ==
        "https://www.javdatabase.com/movies/"
        + dvd_id.lower()
        + "/"
    )

    assert (
        missav_en_movie_url(
            dvd_id
        )
        ==
        "https://missav.ws/en/"
        + dvd_id.lower()
    )


#
# FC2 수집 결과가 실제 native writer까지
# 통과할 수 있는지도 임시 DB에서 증명.
#
sample = {
    "dvd_id":
        "FC2-PPV-4451371",

    "status":
        "FOUND",

    "route":
        "javdatabase-movie",

    "request_count":
        1,

    "item": {
        "dvd_id":
            "FC2-PPV-4451371",

        "title":
            "FC2 Offline Test",

        "release_date":
            "2026-08-01",

        "studio":
            "FC2 Test Studio",

        "cover_url":
            "https://example.invalid/fc2.jpg",

        "idols":
            ["FC2 Test Actress"],

        "genres":
            ["FC2 Test Genre"],

        "source_url":
            "https://www.javdatabase.com/"
            "movies/fc2-ppv-4451371/",
    },
}


with tempfile.TemporaryDirectory(
    prefix="teddy-stage8-fc2-"
) as temp:

    db = connect(
        Path(temp) / "test.sqlite3"
    )

    initialize(db)

    written = (
        apply_held_collected_metadata(
            db,
            sample,
        )
    )

    assert (
        written
        == "FC2-PPV-4451371"
    )

    row = db.execute(
        """
        SELECT
            dvd_id,
            title,
            cover_url,
            metadata_source
        FROM titles
        WHERE dvd_id=?
        """,
        (
            "FC2-PPV-4451371",
        ),
    ).fetchone()

    assert row is not None

    assert (
        row["dvd_id"]
        == "FC2-PPV-4451371"
    )

    assert row["title"]
    assert row["cover_url"]

    assert (
        row["metadata_source"]
        == "javdatabase-movie"
    )

    assert (
        db.execute(
            """
            SELECT COUNT(*)
            FROM title_people
            WHERE dvd_id=?
            """,
            (
                "FC2-PPV-4451371",
            ),
        ).fetchone()[0]
        == 1
    )

    assert (
        db.execute(
            """
            SELECT COUNT(*)
            FROM title_genres
            WHERE dvd_id=?
            """,
            (
                "FC2-PPV-4451371",
            ),
        ).fetchone()[0]
        == 1
    )

    assert (
        db.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
        == "ok"
    )

    db.close()


print("STANDARD_NORMALIZATION=PASS")
print("FC2_CANONICAL_PARSE=PASS")
print("FC2_METADATA_NORMALIZE=PASS")
print("ALL_6_FC2_URL_BUILD=PASS")
print("NONCANONICAL_SUFFIX_REJECTED=PASS")
print("FC2_NATIVE_WRITER_TEMP_DB=PASS")
print("STAGE8_FC2_NORMALIZATION_SMOKE=PASS")
