from __future__ import annotations

import sqlite3
import stat
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from teddy_discovery_stage12_reconcile import (
    Stage12ReconciliationError,
    reconcile_failed_publication,
)
from teddy_discovery_stage12_rollout import STATE_FAILED_RETRYABLE, STATE_PUBLISHED
from teddy_discovery_stage12_rollout_smoke import (
    failed_reconciliation_fixture,
)
from teddy_discovery_subtitle import validate_canonical_holding


class FakeNAS:
    def __init__(self, record, payload):
        self.video_path = record.media_path_identity
        video = validate_canonical_holding(
            {
                "dvd_id": record.dvd_id,
                "storage_root": "jav",
                "relative_path": record.media_path_identity,
                "parse_status": "MATCHED",
                "present": 1,
            },
            record.dvd_id,
        )
        from teddy_discovery_subtitle import derive_target_ko_relative

        self.destination = derive_target_ko_relative(video)
        self.payload = payload

    def lstat(self, relative_path):
        if relative_path == self.video_path:
            return SimpleNamespace(
                st_mode=stat.S_IFREG | 0o644,
                st_size=100,
                st_mtime_ns=200,
            )
        if relative_path == self.destination:
            return SimpleNamespace(
                st_mode=stat.S_IFREG | 0o644,
                st_size=len(self.payload),
                st_mtime_ns=300,
            )
        raise FileNotFoundError(relative_path)


class FakeSubtitleReader:
    def __init__(self, nas, payload=None):
        self.nas = nas
        self.payload = nas.payload if payload is None else payload

    def read_subtitle_bytes(self, video, candidate):
        assert video.relative_path == self.nas.video_path
        assert candidate.relative_path == self.nas.destination
        return self.payload


class FakeJellyfin:
    def __init__(
        self,
        video_path,
        subtitle_path,
        *,
        stream_path=None,
        language="kor",
        external=True,
        codec="subrip",
    ):
        self.video_path = "/media/adult/" + video_path
        self.subtitle_path = "/media/adult/" + subtitle_path
        self.stream_path = stream_path or self.subtitle_path
        self.language = language
        self.external = external
        self.codec = codec
        self.calls = []

    def _request(self, method, path):
        self.calls.append((method, path))
        assert method == "GET", "reconciliation must not refresh Jellyfin"
        if path.startswith("/Items?"):
            return {
                "Items": [{"Id": "exact-item", "Path": self.video_path}]
            }
        if path == "/Items/exact-item/PlaybackInfo":
            return {
                "MediaSources": [
                    {
                        "Path": self.video_path,
                        "MediaStreams": [
                            {
                                "Type": "Subtitle",
                                "IsTextSubtitleStream": True,
                                "Language": self.language,
                                "IsExternal": self.external,
                                "Path": self.stream_path,
                                "Codec": self.codec,
                            }
                        ],
                    }
                ]
            }
        raise AssertionError("unexpected Jellyfin route: " + path)


def run_case(root: Path, *, nas_payload=None, row_drift=False, stream=None):
    store, record, digest, destination, _ = failed_reconciliation_fixture(root)
    clean_path = Path(record_path(store, record.dvd_id))
    clean = clean_path.read_bytes()
    nas = FakeNAS(record, clean)
    reader = FakeSubtitleReader(nas, nas_payload)
    row = {
        "holding_id": record.holding_id,
        "storage_root": "jav",
        "relative_path": record.media_path_identity,
        "dvd_id": record.dvd_id,
        "parse_status": "MATCHED",
        "size_bytes": record.source_size_bytes,
        "mtime_ns": record.source_mtime_ns,
        "present": 1,
    }
    if row_drift:
        row["mtime_ns"] += 1
    video_path = record.media_path_identity
    jellyfin_values = stream or {}
    client = FakeJellyfin(
        video_path,
        destination,
        **jellyfin_values,
    )
    return store, record, destination, row, nas, reader, client


def record_path(store, dvd_id):
    return store.get(dvd_id).artifact_path


def reconcile(root: Path, parts):
    store, record, destination, row, nas, reader, client = parts
    return reconcile_failed_publication(
        dvd_id=record.dvd_id,
        store=store,
        discovery_row=row,
        artifact_root=root / "artifacts",
        nas_filesystem=nas,
        subtitle_reader=reader,
        jellyfin_client=client,
    )


def rejected_without_state_change(root: Path, *, kwargs):
    parts = run_case(root, **kwargs)
    store, record = parts[0], parts[1]
    try:
        reconcile(root, parts)
    except Stage12ReconciliationError:
        pass
    else:
        raise AssertionError("unsafe reconciliation evidence was accepted")
    assert store.get(record.dvd_id).status == STATE_FAILED_RETRYABLE


def main():
    with TemporaryDirectory(prefix="stage12-reconcile-smoke-") as raw:
        root = Path(raw) / "valid"
        root.mkdir()
        parts = run_case(root)
        store, record, _, _, _, _, client = parts
        result = reconcile(root, parts)
        assert result.status == STATE_PUBLISHED
        assert store.get(record.dvd_id).status == STATE_PUBLISHED
        assert all(method == "GET" for method, _ in client.calls)

    with TemporaryDirectory(prefix="stage12-reconcile-smoke-") as raw:
        root = Path(raw) / "absent-stream"
        root.mkdir()
        rejected_without_state_change(root, kwargs={"stream": {"stream_path": "/other/file.ko.srt"}})

    for label, stream in (
        ("wrong-path", {"stream_path": "/media/adult/other.ko.srt"}),
        ("wrong-language", {"language": "eng"}),
        ("non-external", {"external": False}),
        ("wrong-codec", {"codec": "ass"}),
    ):
        with TemporaryDirectory(prefix="stage12-reconcile-smoke-") as raw:
            root = Path(raw) / label
            root.mkdir()
            rejected_without_state_change(root, kwargs={"stream": stream})

    with TemporaryDirectory(prefix="stage12-reconcile-smoke-") as raw:
        root = Path(raw) / "nas-sha-mismatch"
        root.mkdir()
        rejected_without_state_change(
            root,
            kwargs={"nas_payload": b"different valid-looking payload"},
        )

    with TemporaryDirectory(prefix="stage12-reconcile-smoke-") as raw:
        root = Path(raw) / "source-mismatch"
        root.mkdir()
        rejected_without_state_change(root, kwargs={"row_drift": True})

    with TemporaryDirectory(prefix="stage12-reconcile-smoke-") as raw:
        root = Path(raw) / "provenance-mismatch"
        root.mkdir()
        parts = run_case(root)
        store, record = parts[0], parts[1]
        with sqlite3.connect(store.state_path) as connection:
            row = connection.execute(
                """
                SELECT event_id, provenance_json
                FROM stage12_rollout_events
                WHERE dvd_id = ? AND from_status = 'GENERATED'
                """,
                (record.dvd_id,),
            ).fetchone()
            import json

            provenance = json.loads(row[1])
            provenance["publication_provenance"]["destination_sha256"] = "0" * 64
            connection.execute(
                "UPDATE stage12_rollout_events SET provenance_json = ? WHERE event_id = ?",
                (json.dumps(provenance), row[0]),
            )
        try:
            reconcile(root, parts)
        except Stage12ReconciliationError:
            pass
        else:
            raise AssertionError("mismatched publication proof was accepted")
        assert store.get(record.dvd_id).status == STATE_FAILED_RETRYABLE

    print("STAGE12_RECONCILIATION_SMOKE=PASS")


if __name__ == "__main__":
    main()
