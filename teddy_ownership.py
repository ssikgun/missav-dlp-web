import os
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from teddy_discovery_ids import parse_dvd_id


DISCOVERY_DB_ENV = "TEDDY_DISCOVERY_DB"

MISSAV_HOSTS = {
    "missav.ai",
    "missav.ws",
    "missav.live",
    "missav.fans",
    "missav.media",
    "missav123.com",
    "missav01.com",
}


class OwnershipUnavailable(RuntimeError):
    """The canonical holdings state could not be read safely."""


def dvd_id_from_supported_url(url):
    raw = str(url or "").strip()

    try:
        parsed = urlparse(raw)
    except Exception:
        return None

    if parsed.scheme.lower() not in {"http", "https"}:
        return None

    try:
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError:
        return None
    if host.startswith("www."):
        host = host[4:]

    parts = [
        part
        for part in (parsed.path or "").split("/")
        if part
    ]

    candidate = None

    if host in MISSAV_HOSTS:
        if parts:
            candidate = parts[-1]

    elif host == "123av.com":
        if len(parts) >= 2 and parts[-2] == "v":
            candidate = parts[-1]

    if not candidate:
        return None

    parsed_id = parse_dvd_id(candidate)

    if parsed_id is None:
        return None

    return parsed_id.dvd_id


def is_owned(dvd_id, db_path=None):
    dvd_id = str(dvd_id or "").strip()

    if not dvd_id:
        return False

    path = str(
        db_path
        or os.environ.get(DISCOVERY_DB_ENV, "")
    ).strip()

    if not path:
        raise OwnershipUnavailable(
            "Discovery DB is not configured"
        )

    db = None
    try:
        uri = Path(path).expanduser().resolve().as_uri() + "?mode=ro"
        db = sqlite3.connect(
            uri,
            uri=True,
        )

        row = db.execute(
            """
            SELECT 1
            FROM holdings
            WHERE dvd_id = ?
              AND parse_status = 'MATCHED'
              AND present = 1
            LIMIT 1
            """,
            (dvd_id,),
        ).fetchone()

    except (OSError, sqlite3.Error) as exc:
        raise OwnershipUnavailable(
            "Canonical holdings DB is unavailable"
        ) from exc
    finally:
        if db is not None:
            db.close()

    return row is not None
