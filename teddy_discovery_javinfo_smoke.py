from pathlib import Path
import json
import sqlite3
import sys
import tempfile

from teddy_discovery_db import (
    connect,
    initialize,
)
from teddy_discovery_javinfo import (
    movie_payload_from_envelope,
    upsert_movie_metadata,
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(message)


def main():
    envelope_path = Path(
        sys.argv[1]
    )

    envelope = json.loads(
        envelope_path.read_text(
            encoding="utf-8"
        )
    )

    payload = (
        movie_payload_from_envelope(
            envelope
        )
    )

    with tempfile.TemporaryDirectory(
        prefix="teddy-javinfo-smoke-"
    ) as temp:
        db_path = (
            Path(temp)
            / "discovery.sqlite3"
        )

        connection = connect(
            db_path
        )

        initialize(connection)

        schema = connection.execute(
            """
            SELECT MAX(version)
            FROM schema_migrations
            """
        ).fetchone()[0]

        require(
            schema == 3,
            f"schema expected 3, "
            f"got {schema}",
        )

        first = upsert_movie_metadata(
            connection,
            payload,
        )

        second = upsert_movie_metadata(
            connection,
            payload,
        )

        require(
            first == "SSIS-001",
            f"unexpected first id: "
            f"{first}",
        )

        require(
            second == "SSIS-001",
            f"unexpected second id: "
            f"{second}",
        )

        row = connection.execute(
            """
            SELECT
                dvd_id,
                title,
                release_date,
                maker,
                cover_url,
                metadata_source
            FROM titles
            WHERE dvd_id = 'SSIS-001'
            """
        ).fetchone()

        require(
            row is not None,
            "SSIS-001 title missing",
        )

        require(
            row["release_date"]
            == "2021-02-19",
            "release date mismatch",
        )

        require(
            row["maker"]
            == "S1 NO.1 STYLE",
            "maker mismatch",
        )

        require(
            row["metadata_source"]
            == "fanza",
            "metadata source mismatch",
        )

        require(
            row["cover_url"]
            and row["cover_url"].startswith(
                "https://"
            ),
            "cover URL missing",
        )

        roles = dict(
            connection.execute(
                """
                SELECT
                    role,
                    COUNT(*)
                FROM title_people
                WHERE dvd_id = 'SSIS-001'
                GROUP BY role
                ORDER BY role
                """
            ).fetchall()
        )

        require(
            roles.get("actress") == 2,
            f"actress count mismatch: "
            f"{roles}",
        )

        require(
            roles.get("director") == 1,
            f"director count mismatch: "
            f"{roles}",
        )

        require(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM title_people
                WHERE dvd_id = 'SSIS-001'
                """
            ).fetchone()[0] == 3,
            "title_people must remain "
            "idempotent",
        )

        require(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM title_genres
                WHERE dvd_id = 'SSIS-001'
                """
            ).fetchone()[0] == 8,
            "expected 8 categories",
        )

        require(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM titles
                """
            ).fetchone()[0] == 1,
            "title upsert duplicated row",
        )

        connection.close()

    print("SCHEMA_V3_SMOKE=PASS")
    print("MOVIE_MAPPER_SMOKE=PASS")
    print("ROLE_MAPPING_SMOKE=PASS")
    print("IDEMPOTENCY_SMOKE=PASS")
    print("JAVINFO_OFFLINE_SMOKE=PASS")


if __name__ == "__main__":
    main()
