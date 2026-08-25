from __future__ import annotations

from pathlib import Path
import sqlite3


SCHEMA_VERSION = 1


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    storage_root TEXT NOT NULL,
    root_path TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL
        CHECK (status IN ('RUNNING', 'COMPLETE', 'FAILED')),
    video_files INTEGER,
    matched INTEGER,
    ambiguous INTEGER,
    unmatched INTEGER,
    error TEXT
);

CREATE TABLE IF NOT EXISTS titles (
    dvd_id TEXT PRIMARY KEY,
    title TEXT,
    release_date TEXT,
    maker TEXT,
    cover_url TEXT,
    raw_metadata TEXT,
    metadata_source TEXT,
    first_seen_at TEXT,
    last_seen_at TEXT
);

CREATE TABLE IF NOT EXISTS people (
    person_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS title_people (
    dvd_id TEXT NOT NULL,
    person_id INTEGER NOT NULL,
    PRIMARY KEY (dvd_id, person_id),
    FOREIGN KEY (person_id)
        REFERENCES people(person_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS genres (
    genre_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS title_genres (
    dvd_id TEXT NOT NULL,
    genre_id INTEGER NOT NULL,
    PRIMARY KEY (dvd_id, genre_id),
    FOREIGN KEY (genre_id)
        REFERENCES genres(genre_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS holdings (
    holding_id INTEGER PRIMARY KEY AUTOINCREMENT,

    storage_root TEXT NOT NULL,
    relative_path TEXT NOT NULL,

    dvd_id TEXT,

    parse_status TEXT NOT NULL
        CHECK (
            parse_status IN (
                'MATCHED',
                'AMBIGUOUS',
                'UNMATCHED'
            )
        ),

    parse_method TEXT,
    parse_candidates_json TEXT NOT NULL DEFAULT '[]',

    size_bytes INTEGER NOT NULL
        CHECK (size_bytes >= 0),

    mtime_ns INTEGER NOT NULL,

    discovered_by TEXT NOT NULL,

    present INTEGER NOT NULL DEFAULT 1
        CHECK (present IN (0, 1)),

    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,

    last_seen_run_id INTEGER,

    UNIQUE (storage_root, relative_path),

    FOREIGN KEY (last_seen_run_id)
        REFERENCES inventory_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_holdings_dvd_id
    ON holdings(dvd_id);

CREATE INDEX IF NOT EXISTS idx_holdings_parse_status
    ON holdings(parse_status);

CREATE INDEX IF NOT EXISTS idx_holdings_present
    ON holdings(present);

CREATE TABLE IF NOT EXISTS availability (
    dvd_id TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    page_url TEXT,
    last_checked_at TEXT,
    next_check_at TEXT,
    fail_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dvd_id, source)
);

CREATE TABLE IF NOT EXISTS ranking_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chart_type TEXT NOT NULL,
    period TEXT NOT NULL,
    dvd_id TEXT NOT NULL,
    rank INTEGER,
    score REAL,
    observed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ranking_lookup
    ON ranking_snapshots(
        chart_type,
        period,
        dvd_id
    );

CREATE TABLE IF NOT EXISTS downloads (
    task_id TEXT PRIMARY KEY,
    dvd_id TEXT,
    source TEXT,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS organizer_jobs (
    job_id INTEGER PRIMARY KEY AUTOINCREMENT,
    dvd_id TEXT,
    source_path TEXT NOT NULL,
    destination_path TEXT,
    status TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_usage (
    usage_id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    success INTEGER NOT NULL
        CHECK (success IN (0, 1))
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        db_path,
        timeout=30,
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )
    connection.execute(
        "PRAGMA journal_mode = WAL"
    )
    connection.execute(
        "PRAGMA synchronous = NORMAL"
    )

    return connection


def initialize(connection: sqlite3.Connection) -> None:
    from datetime import datetime, timezone

    connection.executescript(SCHEMA)

    row = connection.execute(
        """
        SELECT version
        FROM schema_migrations
        ORDER BY version DESC
        LIMIT 1
        """
    ).fetchone()

    current = int(row["version"]) if row else 0

    if current > SCHEMA_VERSION:
        raise RuntimeError(
            f"database schema {current} is newer "
            f"than supported {SCHEMA_VERSION}"
        )

    if current < SCHEMA_VERSION:
        now = datetime.now(
            timezone.utc
        ).isoformat(timespec="seconds")

        connection.execute(
            """
            INSERT INTO schema_migrations(
                version,
                applied_at
            )
            VALUES (?, ?)
            """,
            (
                SCHEMA_VERSION,
                now,
            ),
        )
        connection.commit()
