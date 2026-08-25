from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
import tempfile

from teddy_discovery_db import (
    connect,
    initialize,
)

from teddy_discovery_javdatabase import (
    parse_javdatabase_weekly_envelope,
)

from teddy_discovery_rankings import (
    JAVDATABASE_WEEKLY_SOURCE,
    MISSAV_RELEASE_SOURCE,
    WEEKLY_CHART_TYPE,
    list_weekly_snapshot,
    replace_weekly_snapshot,
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def sqlite_backup(
    source_path: Path,
    destination_path: Path,
):
    source = sqlite3.connect(
        "file:"
        + str(source_path)
        + "?mode=ro",
        uri=True,
    )

    target = sqlite3.connect(
        str(
            destination_path
        )
    )

    try:
        source.backup(
            target
        )

    finally:
        target.close()
        source.close()


def load_snapshot(
    fixture: Path,
):
    with fixture.open(
        "r",
        encoding="utf-8",
    ) as fh:
        forensic = json.load(
            fh
        )

    article = forensic[
        "article"
    ]

    parsed = (
        parse_javdatabase_weekly_envelope(
            article
        )
    )

    observed_at = article.get(
        "requested_at"
    )

    require(
        observed_at,
        "weekly fixture requested_at missing",
    )

    return (
        parsed,
        observed_at,
    )


def seed_rich_jur786(
    connection,
):
    dvd_id = "JUR-786"

    connection.execute(
        """
        INSERT INTO titles(
            dvd_id,
            title,
            release_date,
            maker,
            cover_url,
            raw_metadata,
            metadata_source,
            first_seen_at,
            last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(dvd_id)
        DO UPDATE SET
            title = excluded.title,
            release_date =
                excluded.release_date,
            maker = excluded.maker,
            cover_url =
                excluded.cover_url,
            raw_metadata =
                excluded.raw_metadata,
            metadata_source =
                excluded.metadata_source,
            first_seen_at =
                excluded.first_seen_at,
            last_seen_at =
                excluded.last_seen_at
        """,
        (
            dvd_id,
            "RICH-FANZA-TITLE",
            "2001-01-01",
            "RICH-FANZA-MAKER",
            "https://rich.invalid/cover.jpg",
            '{"rich":true}',
            "fanza",
            "2001-01-01T00:00:00+00:00",
            "2001-01-01T00:00:00+00:00",
        ),
    )

    connection.execute(
        """
        DELETE FROM title_people
        WHERE dvd_id = ?
        """,
        (
            dvd_id,
        ),
    )

    connection.execute(
        """
        INSERT INTO people(name)
        VALUES ('RICH-FANZA-PERSON')
        ON CONFLICT(name)
        DO NOTHING
        """
    )

    person = connection.execute(
        """
        SELECT person_id
        FROM people
        WHERE name = 'RICH-FANZA-PERSON'
        """
    ).fetchone()

    connection.execute(
        """
        INSERT INTO title_people(
            dvd_id,
            person_id,
            role
        )
        VALUES (?, ?, ?)
        """,
        (
            dvd_id,
            int(
                person[
                    "person_id"
                ]
            ),
            "actress",
        ),
    )

    connection.execute(
        """
        DELETE FROM title_genres
        WHERE dvd_id = ?
        """,
        (
            dvd_id,
        ),
    )

    connection.execute(
        """
        INSERT INTO genres(name)
        VALUES ('RICH-FANZA-GENRE')
        ON CONFLICT(name)
        DO NOTHING
        """
    )

    genre = connection.execute(
        """
        SELECT genre_id
        FROM genres
        WHERE name = 'RICH-FANZA-GENRE'
        """
    ).fetchone()

    connection.execute(
        """
        INSERT INTO title_genres(
            dvd_id,
            genre_id
        )
        VALUES (?, ?)
        """,
        (
            dvd_id,
            int(
                genre[
                    "genre_id"
                ]
            ),
        ),
    )

    connection.commit()


def rich_metadata_preserved(
    connection,
    observed_at,
):
    row = connection.execute(
        """
        SELECT
            title,
            release_date,
            maker,
            cover_url,
            raw_metadata,
            metadata_source,
            last_seen_at
        FROM titles
        WHERE dvd_id = 'JUR-786'
        """
    ).fetchone()

    require(
        row is not None,
        "rich JUR-786 disappeared",
    )

    require(
        row[
            "title"
        ]
        == "RICH-FANZA-TITLE",
        "weekly overwrote rich title",
    )

    require(
        row[
            "release_date"
        ]
        == "2001-01-01",
        "weekly overwrote rich release date",
    )

    require(
        row[
            "maker"
        ]
        == "RICH-FANZA-MAKER",
        "weekly overwrote rich maker",
    )

    require(
        row[
            "cover_url"
        ]
        == "https://rich.invalid/cover.jpg",
        "weekly overwrote rich cover",
    )

    require(
        row[
            "raw_metadata"
        ]
        == '{"rich":true}',
        "weekly overwrote rich raw metadata",
    )

    require(
        row[
            "metadata_source"
        ]
        == "fanza",
        "weekly overwrote rich source",
    )

    require(
        row[
            "last_seen_at"
        ]
        == observed_at,
        "weekly observation time "
        "was not recorded",
    )

    people = connection.execute(
        """
        SELECT
            p.name,
            tp.role
        FROM title_people AS tp
        JOIN people AS p
          ON p.person_id =
             tp.person_id
        WHERE tp.dvd_id = 'JUR-786'
        ORDER BY p.name
        """
    ).fetchall()

    require(
        [
            (
                row[
                    "name"
                ],
                row[
                    "role"
                ],
            )
            for row
            in people
        ]
        == [
            (
                "RICH-FANZA-PERSON",
                "actress",
            ),
        ],
        "weekly overwrote rich people",
    )

    genres = connection.execute(
        """
        SELECT g.name
        FROM title_genres AS tg
        JOIN genres AS g
          ON g.genre_id =
             tg.genre_id
        WHERE tg.dvd_id = 'JUR-786'
        ORDER BY g.name
        """
    ).fetchall()

    require(
        [
            row[
                "name"
            ]
            for row
            in genres
        ]
        == [
            "RICH-FANZA-GENRE",
        ],
        "weekly overwrote rich genres",
    )


def missav_upgrade_verified(
    connection,
):
    row = connection.execute(
        """
        SELECT
            title,
            release_date,
            maker,
            cover_url,
            metadata_source
        FROM titles
        WHERE dvd_id = 'START-624'
        """
    ).fetchone()

    require(
        row is not None,
        "START-624 missing",
    )

    require(
        row[
            "metadata_source"
        ]
        == JAVDATABASE_WEEKLY_SOURCE,
        "MissAV metadata was not "
        "upgraded to JAV Database",
    )

    require(
        row[
            "release_date"
        ]
        == "2026-08-25",
        "START-624 release date missing",
    )

    require(
        row[
            "maker"
        ]
        == "SOD Create",
        "START-624 studio/maker missing",
    )

    require(
        row[
            "cover_url"
        ].startswith(
            "https://www.javdatabase.com/"
        ),
        "START-624 cover source changed",
    )


def new_weekly_metadata_verified(
    connection,
):
    row = connection.execute(
        """
        SELECT
            metadata_source,
            release_date,
            maker
        FROM titles
        WHERE dvd_id = 'SNOS-299'
        """
    ).fetchone()

    require(
        row is not None,
        "SNOS-299 weekly title missing",
    )

    require(
        row[
            "metadata_source"
        ]
        == JAVDATABASE_WEEKLY_SOURCE,
        "new weekly metadata "
        "source mismatch",
    )

    require(
        row[
            "release_date"
        ]
        == "2026-09-04",
        "SNOS-299 release date mismatch",
    )

    require(
        row[
            "maker"
        ]
        == "S1 Number One Style",
        "SNOS-299 maker mismatch",
    )

    people = connection.execute(
        """
        SELECT
            p.name,
            tp.role
        FROM title_people AS tp
        JOIN people AS p
          ON p.person_id =
             tp.person_id
        WHERE tp.dvd_id = 'SNOS-299'
        ORDER BY p.name
        """
    ).fetchall()

    require(
        [
            (
                row[
                    "name"
                ],
                row[
                    "role"
                ],
            )
            for row
            in people
        ]
        == [
            (
                "Miu Mirai",
                "unknown",
            ),
        ],
        "JAV Database Idol(s) "
        "role mapping changed",
    )

    genres = {
        row[
            "name"
        ]
        for row
        in connection.execute(
            """
            SELECT g.name
            FROM title_genres AS tg
            JOIN genres AS g
              ON g.genre_id =
                 tg.genre_id
            WHERE tg.dvd_id =
                'SNOS-299'
            """
        ).fetchall()
    }

    require(
        "4K"
        in genres,
        "SNOS-299 genres missing",
    )

    require(
        "Debut"
        in genres,
        "SNOS-299 genres incomplete",
    )


def metadata_policy_smoke(
    base_db: Path,
    fixture: Path,
):
    parsed, observed_at = (
        load_snapshot(
            fixture
        )
    )

    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-weekly-metadata-"
    ) as temp:
        copied = (
            Path(temp)
            / "metadata-v4.sqlite3"
        )

        sqlite_backup(
            base_db,
            copied,
        )

        connection = connect(
            copied
        )

        try:
            initialize(
                connection
            )

            start_before = (
                connection.execute(
                    """
                    SELECT metadata_source
                    FROM titles
                    WHERE dvd_id =
                        'START-624'
                    """
                ).fetchone()
            )

            require(
                start_before is not None,
                "Stage 2 base must "
                "contain START-624",
            )

            require(
                start_before[
                    "metadata_source"
                ]
                == MISSAV_RELEASE_SOURCE,
                "START-624 base source "
                "is not MissAV release",
            )

            seed_rich_jur786(
                connection
            )

            result = (
                replace_weekly_snapshot(
                    connection,
                    parsed,
                    observed_at=
                        observed_at,
                )
            )

            require(
                result[
                    "written"
                ]
                == 25,
                "weekly ranking "
                "write count changed",
            )

            require(
                result[
                    "metadata_preserved"
                ]
                >= 1,
                "rich metadata "
                "preservation not observed",
            )

            rich_metadata_preserved(
                connection,
                observed_at,
            )

            missav_upgrade_verified(
                connection
            )

            new_weekly_metadata_verified(
                connection
            )

            rows = (
                list_weekly_snapshot(
                    connection,
                    parsed[
                        "period"
                    ],
                )
            )

            require(
                len(rows) == 25,
                "weekly ranking count "
                "changed after metadata write",
            )

            first_people_count = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM title_people
                    WHERE dvd_id =
                        'SNOS-299'
                    """
                ).fetchone()[0]
            )

            first_genre_count = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM title_genres
                    WHERE dvd_id =
                        'SNOS-299'
                    """
                ).fetchone()[0]
            )

            replace_weekly_snapshot(
                connection,
                parsed,
                observed_at=
                    observed_at,
            )

            require(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM title_people
                    WHERE dvd_id =
                        'SNOS-299'
                    """
                ).fetchone()[0]
                == first_people_count,
                "weekly people "
                "idempotency failed",
            )

            require(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM title_genres
                    WHERE dvd_id =
                        'SNOS-299'
                    """
                ).fetchone()[0]
                == first_genre_count,
                "weekly genre "
                "idempotency failed",
            )

            rich_metadata_preserved(
                connection,
                observed_at,
            )

            require(
                connection.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]
                == "ok",
                "weekly metadata DB "
                "integrity failed",
            )

        finally:
            connection.close()

    print(
        "WEEKLY_RICH_METADATA_PRESERVATION_SMOKE=PASS"
    )

    print(
        "WEEKLY_MISSAV_METADATA_UPGRADE_SMOKE=PASS"
    )

    print(
        "WEEKLY_NEW_METADATA_INSERT_SMOKE=PASS"
    )

    print(
        "WEEKLY_IDOLS_UNKNOWN_ROLE_SMOKE=PASS"
    )

    print(
        "WEEKLY_METADATA_IDEMPOTENCY_SMOKE=PASS"
    )


def atomic_rollback_smoke(
    base_db: Path,
    fixture: Path,
):
    parsed, observed_at = (
        load_snapshot(
            fixture
        )
    )

    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-weekly-rollback-"
    ) as temp:
        copied = (
            Path(temp)
            / "rollback-v4.sqlite3"
        )

        sqlite_backup(
            base_db,
            copied,
        )

        connection = connect(
            copied
        )

        try:
            initialize(
                connection
            )

            titles_before = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM titles
                    """
                ).fetchone()[0]
            )

            people_links_before = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM title_people
                    """
                ).fetchone()[0]
            )

            genre_links_before = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM title_genres
                    """
                ).fetchone()[0]
            )

            rankings_before = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM ranking_snapshots
                    """
                ).fetchone()[0]
            )

            start_before = (
                connection.execute(
                    """
                    SELECT
                        title,
                        metadata_source
                    FROM titles
                    WHERE dvd_id =
                        'START-624'
                    """
                ).fetchone()
            )

            connection.execute(
                """
                CREATE TRIGGER
                    fail_weekly_rank_13
                BEFORE INSERT
                ON ranking_snapshots
                WHEN NEW.chart_type =
                    'javdatabase-weekly'
                 AND NEW.rank = 13
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'synthetic weekly failure'
                    );
                END
                """
            )

            connection.commit()

            try:
                replace_weekly_snapshot(
                    connection,
                    parsed,
                    observed_at=
                        observed_at,
                )

            except sqlite3.IntegrityError as exc:
                require(
                    "synthetic weekly failure"
                    in str(exc),
                    "unexpected synthetic "
                    "rollback failure",
                )

            else:
                raise RuntimeError(
                    "synthetic rank failure "
                    "must abort weekly write"
                )

            require(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM titles
                    """
                ).fetchone()[0]
                == titles_before,
                "failed ranking write "
                "changed titles",
            )

            require(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM title_people
                    """
                ).fetchone()[0]
                == people_links_before,
                "failed ranking write "
                "changed people links",
            )

            require(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM title_genres
                    """
                ).fetchone()[0]
                == genre_links_before,
                "failed ranking write "
                "changed genre links",
            )

            require(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM ranking_snapshots
                    """
                ).fetchone()[0]
                == rankings_before,
                "failed ranking write "
                "changed ranking rows",
            )

            start_after = (
                connection.execute(
                    """
                    SELECT
                        title,
                        metadata_source
                    FROM titles
                    WHERE dvd_id =
                        'START-624'
                    """
                ).fetchone()
            )

            require(
                tuple(
                    start_after
                )
                == tuple(
                    start_before
                ),
                "failed weekly write "
                "changed START-624 metadata",
            )

            require(
                connection.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]
                == "ok",
                "rollback DB integrity failed",
            )

        finally:
            connection.close()

    print(
        "WEEKLY_RANKING_METADATA_ATOMIC_ROLLBACK_SMOKE=PASS"
    )


def main():
    if len(
        sys.argv
    ) != 3:
        raise RuntimeError(
            "usage: "
            "teddy_discovery_"
            "rankings_metadata_smoke.py "
            "<stage2-v3-db> "
            "<javdatabase-fixture>"
        )

    base_db = Path(
        sys.argv[1]
    )

    fixture = Path(
        sys.argv[2]
    )

    metadata_policy_smoke(
        base_db,
        fixture,
    )

    atomic_rollback_smoke(
        base_db,
        fixture,
    )

    print(
        "WEEKLY_METADATA_ATOMICITY_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
