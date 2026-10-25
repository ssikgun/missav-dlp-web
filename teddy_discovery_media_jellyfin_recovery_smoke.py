from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from threading import Event
from unittest.mock import patch

from teddy_discovery_completion_ssh import CompletionSSH
from teddy_discovery_media_jobs import MEDIA_SCHEMA, run_retryable_media_jobs
from teddy_discovery_media_pipeline import (
    record_jellyfin_notification_status,
    run_media_pipeline,
)
from teddy_discovery_media_pipeline_smoke import FakeJellyfin, make_db
from teddy_discovery_media_publish import MediaMetadataSSHMutator


class RecoveryJellyfin(FakeJellyfin):
    def __init__(self, visibility=None):
        super().__init__(visibility)
        self.post_calls = 0
        self.accepted_posts = 0

    def exact_media_visibility(self, path):
        result = super().exact_media_visibility(path)
        if isinstance(result, BaseException):
            raise result
        return result

    def counted_notify_created(self, path):
        self.post_calls += 1
        self.accepted_posts += 1
        return super().notify_created(path)


class SimulatedProcessCrash(BaseException):
    pass


def read_job(path, dvd_id):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    row = db.execute("SELECT * FROM media_jobs WHERE dvd_id=?", (dvd_id,)).fetchone()
    db.close()
    return dict(row)


def main():
    with tempfile.TemporaryDirectory(prefix="stage9-jellyfin-recovery-") as temp:
        root = Path(temp)
        library = root / "library"
        library.mkdir()

        def fake_runner(command, **kwargs):
            return subprocess.run(["/bin/sh", "-c", command[-1]], **kwargs)

        ssh = CompletionSSH(
            host="fake",
            user="fake",
            key="/fake/key",
            known_hosts="/fake/known_hosts",
            downloads_root=str(root / "downloads"),
            library_root=str(library),
            runner=fake_runner,
        )
        mutator = MediaMetadataSSHMutator(ssh)
        lock_root = root / "title-locks"
        lock_root.mkdir()

        def make_case(dvd_id, jellyfin):
            discovery_db = root / f"{dvd_id}-discovery.sqlite3"
            media_db = root / f"{dvd_id}-media.sqlite3"
            media_dir = library / dvd_id.split("-", 1)[0] / dvd_id
            media_dir.mkdir(parents=True)
            video = media_dir / f"{dvd_id}.mp4"
            video.write_bytes(b"VIDEO")
            make_db(discovery_db, dvd_id=dvd_id, cover_url=None)
            db = sqlite3.connect(media_db)
            db.executescript(MEDIA_SCHEMA)
            now = datetime.now(timezone.utc).isoformat()
            db.execute(
                """INSERT INTO media_jobs
                   (dvd_id,status,attempt_count,error,nfo_status,poster_status,
                    jellyfin_notification_status,created_at,updated_at)
                   VALUES(?, 'PENDING', 0, NULL, 'PENDING', 'PENDING',
                          'UNKNOWN', ?, ?)""",
                (dvd_id, now, now),
            )
            db.commit()
            db.close()
            return discovery_db, media_db, video

        def run_case(dvd_id, dbs, jellyfin, *, now=None):
            discovery_db, media_db, _video = dbs
            return run_retryable_media_jobs(
                db_path=media_db,
                discovery_db_path=discovery_db,
                writer_lock_path=root / f"{dvd_id}.writer.lock",
                title_lock_dir=lock_root,
                target_dvd_id=dvd_id,
                max_items=1,
                now=now,
                processor=lambda target: run_media_pipeline(
                    db_path=discovery_db,
                    dvd_id=target,
                    ssh=ssh,
                    metadata_mutator=mutator,
                    jellyfin=jellyfin,
                    fetcher=lambda _url: (_ for _ in ()).throw(
                        AssertionError("posterless case must not fetch an image")
                    ),
                ),
            )

        # Process termination immediately after the durable ATTEMPTED record,
        # before the fake Jellyfin receives a request.
        jf = RecoveryJellyfin([{"status": "PENDING", "reason": None}])
        dbs = make_case("REC-101", jf)
        start = datetime.now(timezone.utc)

        def crash_before_send(_path):
            jf.post_calls += 1
            raise SimulatedProcessCrash()

        jf.notify_created = crash_before_send
        try:
            run_case("REC-101", dbs, jf, now=start)
        except SimulatedProcessCrash:
            pass
        else:
            raise AssertionError("pre-send process crash was not simulated")
        row = read_job(dbs[1], "REC-101")
        assert row["status"] == "RUNNING" and row["attempt_count"] == 1
        assert row["jellyfin_notification_status"] == "ATTEMPTED"
        assert row["jellyfin_recovery_status"] == "CHECK_PENDING"
        jf.notify_created = lambda path: RecoveryJellyfin.counted_notify_created(jf, path)
        resumed = run_case(
            "REC-101", dbs, jf, now=start + timedelta(seconds=7201)
        )
        assert resumed["completed"] == 1 and jf.post_calls == 1
        assert read_job(dbs[1], "REC-101")["jellyfin_recovery_status"] == "CHECK_PENDING"

        # Connection failure before acceptance and response loss after
        # acceptance have the same safe restart rule: exact GET only, no POST.
        for dvd_id, accepted in (("REC-102", False), ("REC-103", True)):
            jf = RecoveryJellyfin([{"status": "PENDING", "reason": None}])
            dbs = make_case(dvd_id, jf)
            start = datetime.now(timezone.utc)

            def lose_request(_path, *, _accepted=accepted):
                jf.post_calls += 1
                if _accepted:
                    jf.accepted_posts += 1
                raise ConnectionError("simulated response uncertainty")

            jf.notify_created = lose_request
            failed = run_case(dvd_id, dbs, jf, now=start)
            assert failed["failed"] == 1
            before = read_job(dbs[1], dvd_id)
            assert before["jellyfin_notification_status"] == "ATTEMPTED"
            assert before["jellyfin_recovery_status"] == "CHECK_PENDING"
            jf.notify_created = lambda path: RecoveryJellyfin.counted_notify_created(jf, path)
            resumed = run_case(dvd_id, dbs, jf, now=start + timedelta(seconds=3601))
            assert resumed["completed"] == 1
            assert jf.post_calls == 1
            assert jf.accepted_posts == int(accepted)
            assert read_job(dbs[1], dvd_id)["jellyfin_recovery_status"] == "CHECK_PENDING"

        # Remote acceptance followed by a local status-write failure leaves
        # ATTEMPTED durable; restart confirms visibility without another POST.
        jf = RecoveryJellyfin([{"status": "PENDING", "reason": None}])
        dbs = make_case("REC-104", jf)
        start = datetime.now(timezone.utc)
        jf.notify_created = lambda path: RecoveryJellyfin.counted_notify_created(jf, path)

        def fail_local_notice(status, error=None):
            if status == "NOTIFIED":
                raise RuntimeError("simulated crash before local completion")
            return record_jellyfin_notification_status(status, error)

        with patch(
            "teddy_discovery_media_pipeline.record_jellyfin_notification_status",
            side_effect=fail_local_notice,
        ):
            failed = run_case("REC-104", dbs, jf, now=start)
        assert failed["failed"] == 1 and jf.accepted_posts == 1
        assert read_job(dbs[1], "REC-104")["jellyfin_notification_status"] == "ATTEMPTED"
        jf.visibility.append({"status": "VISIBLE", "reason": None, "item_id": "movie-104"})
        resumed = run_case("REC-104", dbs, jf, now=start + timedelta(seconds=3601))
        assert resumed["completed"] == 1 and jf.post_calls == 1
        row = read_job(dbs[1], "REC-104")
        assert row["jellyfin_notification_status"] == "VISIBLE"
        assert row["jellyfin_recovery_status"] == "VISIBLE"

        # A successful POST is followed only by bounded exact-path checks.
        # Five total job attempts retain the existing cap; still-PENDING ends
        # in a durable manual action state with no future automatic recheck.
        jf = RecoveryJellyfin([{"status": "PENDING", "reason": None}] * 5)
        dbs = make_case("REC-105", jf)
        start = datetime.now(timezone.utc)
        jf.notify_created = lambda path: RecoveryJellyfin.counted_notify_created(jf, path)
        first = run_case("REC-105", dbs, jf, now=start)
        assert first["completed"] == 1
        for check in range(1, 5):
            result = run_case(
                "REC-105",
                dbs,
                jf,
                now=start + timedelta(seconds=3601 * check),
            )
            assert result["completed"] == 1, result
        row = read_job(dbs[1], "REC-105")
        assert row["attempt_count"] == 5
        assert row["jellyfin_notification_status"] == "NOTIFIED"
        assert row["jellyfin_recovery_status"] == "MANUAL_ACTION_REQUIRED"
        assert row["jellyfin_next_check_at"] is None
        assert row["jellyfin_error"].startswith("MANUAL_ACTION_REQUIRED:")
        assert jf.post_calls == 1 and jf.accepted_posts == 1
        held = run_case("REC-105", dbs, jf, now=start + timedelta(seconds=18010))
        assert held["attempted"] == 0 and jf.post_calls == 1

        # ATTENTION stays terminal; a failed lookup before any POST remains
        # UNKNOWN and may safely perform its first POST after recovery.
        jf = RecoveryJellyfin([{"status": "ATTENTION", "reason": "AMBIGUOUS"}])
        dbs = make_case("REC-106", jf)
        attention = run_case("REC-106", dbs, jf)
        assert attention["completed"] == 1 and jf.post_calls == 0
        assert read_job(dbs[1], "REC-106")["jellyfin_recovery_status"] == "ATTENTION"

        jf = RecoveryJellyfin([TimeoutError("simulated GET failure")])
        dbs = make_case("REC-107", jf)
        start = datetime.now(timezone.utc)
        failed_get = run_case("REC-107", dbs, jf, now=start)
        assert failed_get["failed"] == 1 and jf.post_calls == 0
        row = read_job(dbs[1], "REC-107")
        assert row["jellyfin_notification_status"] == "UNKNOWN"
        assert row["jellyfin_recovery_status"] == "UNKNOWN"
        jf.visibility.append({"status": "PENDING", "reason": None})
        jf.notify_created = lambda path: RecoveryJellyfin.counted_notify_created(jf, path)
        recovered = run_case("REC-107", dbs, jf, now=start + timedelta(seconds=3601))
        assert recovered["completed"] == 1 and jf.post_calls == 1

        # Concurrent and repeated runs retain title-lock/job-state protection.
        jf = RecoveryJellyfin([{"status": "PENDING", "reason": None}])
        dbs = make_case("REC-108", jf)
        start = datetime.now(timezone.utc)
        entered_post = Event()
        release_post = Event()

        def blocking_notify(path):
            jf.post_calls += 1
            jf.accepted_posts += 1
            entered_post.set()
            if not release_post.wait(5):
                raise TimeoutError("concurrent smoke release timed out")
            jf.notifications.append(path)
            return {"status": "JELLYFIN_NOTIFIED", "path": path}

        jf.notify_created = blocking_notify
        with ThreadPoolExecutor(max_workers=2) as pool:
            first_future = pool.submit(run_case, "REC-108", dbs, jf, now=start)
            assert entered_post.wait(5), "first worker did not reach POST"
            second = run_case("REC-108", dbs, jf, now=start + timedelta(seconds=1))
            assert second["attempted"] == 0 and second["held_fresh_running"] == 1
            release_post.set()
            first = first_future.result(timeout=5)
        assert first["completed"] == 1
        repeated = run_case("REC-108", dbs, jf, now=start + timedelta(seconds=2))
        assert repeated["attempted"] == 0 and repeated["held_cover_url_missing"] == 1
        assert jf.post_calls == 1

        # Posterless NFO state and the independent Jellyfin follow-up state
        # remain separate; no poster is synthesized.
        row = read_job(dbs[1], "REC-108")
        assert row["nfo_status"] == "COMPLETE" and row["poster_status"] == "PENDING"
        assert row["jellyfin_recovery_status"] == "CHECK_PENDING"
        assert (library / "REC" / "REC-108" / "REC-108.nfo").is_file()
        assert not (library / "REC" / "REC-108" / "poster.jpg").exists()

    print("STAGE9_JELLYFIN_RECOVERY_SMOKE=PASS")


if __name__ == "__main__":
    main()
