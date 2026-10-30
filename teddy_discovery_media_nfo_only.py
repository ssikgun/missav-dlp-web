"""Single-holding NFO candidate. Only injected offline File Station transports are allowed."""
from contextlib import closing
from pathlib import Path
from urllib.parse import quote
import sqlite3
import json
import re

from teddy_discovery_media_filestation import (
    MAX_NFO_BYTES, REAL_LIBRARY_ROOT, FileStationMediaError,
    SynologyFileStationMediaAdapter, _video_paths,
)
from teddy_discovery_media_metadata import (
    MediaBundle, _normalize_dvd_id, build_nfo_bytes, load_media_metadata,
)
from teddy_discovery_media_publish import _safe_video_relative, canonical_nfo_filename


def create_nfo_only(db_path, dvd_id, *, expected_owner, expected_group, adapter):
    """Create one NFO using a read-only holding and an already opened fake adapter.

    The caller supplies expected video ownership; independent read-only verification
    is required before any future live use. Sidecar ownership may differ.
    """
    if not isinstance(adapter, SynologyFileStationMediaAdapter) or adapter.transport is None:
        raise FileStationMediaError("OFFLINE_TRANSPORT_REQUIRED")
    dvd_id = _normalize_dvd_id(dvd_id)
    if any(not isinstance(x, str) or not x.strip() or x != x.strip() for x in (expected_owner, expected_group)):
        raise ValueError("video owner and group required")
    uri = 'file:' + quote(str(Path(db_path).resolve()), safe='/') + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        rows = db.execute(
            'SELECT storage_root, relative_path, dvd_id, parse_status, size_bytes, discovered_by '
            'FROM holdings WHERE dvd_id=? AND present=1 LIMIT 2', (dvd_id,)
        ).fetchall()
        completed = db.execute(
            "SELECT 1 FROM organizer_jobs WHERE dvd_id=? AND status='COMPLETED' LIMIT 1",
            (dvd_id,),
        ).fetchone()
        evidence = db.execute(
            'SELECT title, metadata_source, raw_metadata FROM titles WHERE dvd_id=?',
            (dvd_id,),
        ).fetchall()
    if not completed:
        raise ValueError("completed organizer job required")
    if len(evidence) != 1:
        raise ValueError("metadata evidence missing or ambiguous")
    title, source, raw = evidence[0]
    # These producers serialize an item with source, DVD-ID and title. Enrichment
    # can retain a different presentation title; without further evidence such
    # cases are deliberately blocked rather than assuming the titles agree.
    if source not in {'javdatabase-weekly', 'javdatabase-movie', 'missav-en-movie'}:
        raise ValueError("metadata evidence source unverified")
    try:
        payload = json.loads(raw)
        item = payload['item']
        if (payload['source'] != source or not isinstance(item, dict)
                or not isinstance(item.get('dvd_id'), str)
                or _normalize_dvd_id(item['dvd_id']) != dvd_id
                or not isinstance(item.get('title'), str)
                or not isinstance(title, str)):
            raise ValueError("metadata evidence mismatch")
        prefix = re.compile(r'^\s*(?:\[\s*' + re.escape(dvd_id)
                            + r'\s*\]\s*|' + re.escape(dvd_id)
                            + r'(?=\s|$)\s*)', re.IGNORECASE)
        def unprefix(value):
            value = ' '.join(value.split())
            while prefix.match(value):
                value = prefix.sub('', value, count=1).strip()
            return value
        if not unprefix(title) or unprefix(title) != unprefix(item['title']):
            raise ValueError("metadata title evidence mismatch")
    except (TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("metadata evidence invalid") from exc
    if len(rows) != 1:
        raise ValueError("exactly one present holding required")
    root, relative, held_id, status, size, provenance = rows[0]
    if root != 'jav' or held_id != dvd_id or status != 'MATCHED' or type(size) is not int or size <= 0 or provenance not in {'library-inventory', 'organizer-apply'}:
        raise ValueError("holding identity or size invalid")
    canonical = _safe_video_relative(relative, dvd_id)
    if _video_paths(relative)[0] != canonical:
        raise ValueError("video path mismatch")
    metadata = load_media_metadata(db_path, dvd_id)
    if (metadata.dvd_id != dvd_id or metadata.title != title.strip()
            or metadata.metadata_source != source):
        raise ValueError("metadata identity mismatch")
    nfo = build_nfo_bytes(metadata)
    if not nfo or len(nfo) > MAX_NFO_BYTES:
        raise ValueError("NFO size invalid")
    video = adapter.stat_library(canonical)
    if (not video or video.get('size') != size or video.get('owner') != expected_owner
            or video.get('group') != expected_group
            or video.get('real_path') != REAL_LIBRARY_ROOT + '/' + canonical):
        raise ValueError("video path, size or ownership mismatch")
    bundle = MediaBundle(dvd_id, canonical_nfo_filename(dvd_id), nfo, None)
    result = adapter.publish_bundle(video_relative=canonical, bundle=bundle)
    if result['nfo']['status'] != 'CREATED':
        raise FileStationMediaError('NFO_ALREADY_PRESENT')
    return result
