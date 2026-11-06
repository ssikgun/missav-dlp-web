#!/usr/bin/env python3
"""One-time exact 11-row Stage9 poster-status reconciliation on CT108.

Run only on Teddy's downloader CT108 as root with the pinned Stage9 batch
helper present. This intentionally makes no NAS, Jellyfin, or systemd changes.
"""

import datetime
import fcntl
import hashlib
import importlib.util
import os
import sqlite3
import stat
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path("/opt/missav-dlp-web/stage9-runtime/existing-image-batch-54-v1")
SCRIPT = ROOT / "teddy_discovery_existing_image_batch.py"
MANIFEST = ROOT / (
    "docs/governance/stage9-media/evidence/"
    "2026-11-06-existing-image-targets-54.json"
)
BACKUPS = Path("/opt/missav-dlp-web/backups")
SHA = "503598bded6f5c358c2078e3c4623d98f7eab5255debc3e1cdce6f1b8d4c5131"

# Exact DVD_ID -> (media_job_id, historic attempt_count).
COMPLETE = {
    "MAAN-945": (176329, 2),
    "NTR-102": (1345296, 2),
    "FC2-PPV-4983582": (1386579, 2),
    "PRIAN-060": (1387338, 3),
    "PRIAN-059": (1387566, 2),
    "FC2-PPV-4982148": (1387644, 1),
    "FC2-PPV-3087371": (3378694, 1),
    "GANA-3223": (4442407, 1),
    "MIUM-1406": (4785616, 2),
    "LUXU-1725": (4786654, 2),
}
PROTECTED = {"MBRBI-015": (4786003, 1)}
FAILED = {
    "MFCS-085": (174261, 17161),
    "NHDTB-778": (2468371, 5),
    "DANDYA-033": (2468469, 5),
}
ERROR_PROTECTED = "MANUAL_JELLYFIN_PRIMARY_PROTECTED_NO_LOCAL_PRIMARY"


def safety(condition, code):
    if not condition:
        raise RuntimeError(code)


def flag(base, name):
    safety(base.count(name) == 1, "FLAG_MISSING_OR_DUPLICATE_" + name)
    i = base.index(name)
    safety(i + 1 < len(base), "FLAG_VALUE_MISSING_" + name)
    value = Path(base[i + 1])
    safety(value.is_absolute(), "FLAG_PATH_NOT_ABSOLUTE_" + name)
    return value


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def state(unit, name):
    return subprocess.check_output(
        ["systemctl", "show", unit, "--property=" + name, "--value"],
        text=True, timeout=10,
    ).strip()


def row_dict(db):
    return {r["dvd_id"]: dict(r) for r in db.execute("SELECT * FROM media_jobs")}


def eligibility(rows, jobs):
    return {
        dvd: jobs.retry_eligibility(row)
        for dvd, row in rows.items()
        if jobs.retry_eligibility(row) in {"ELIGIBLE", "EXHAUSTED"}
    }


def check_pre(rows, jobs):
    expected = set(COMPLETE) | set(PROTECTED)
    status_map = eligibility(rows, jobs)
    safety({d for d, v in status_map.items() if v == "ELIGIBLE"} == expected,
           "ELIGIBLE_QUEUE_CHANGED")
    safety({d for d, v in status_map.items() if v == "EXHAUSTED"} == set(FAILED),
           "EXHAUSTED_QUEUE_CHANGED")
    for dvd, (job_id, attempts) in {**COMPLETE, **PROTECTED}.items():
        r = rows.get(dvd)
        safety(r is not None, "TARGET_NOT_FOUND_" + dvd)
        safety(
            r["media_job_id"] == job_id
            and r["attempt_count"] == attempts
            and r["status"] == "COMPLETED"
            and r["nfo_status"] == "COMPLETE"
            and r["poster_status"] == "PENDING"
            and r["jellyfin_notification_status"] == "VISIBLE"
            and r["jellyfin_recovery_status"] == "VISIBLE"
            and r["error"] is None
            and r["poster_error"] is not None,
            "TARGET_PRESTATE_CHANGED_" + dvd,
        )
    for dvd, (job_id, attempts) in FAILED.items():
        r = rows.get(dvd)
        safety(r is not None, "FAILED_ROW_NOT_FOUND_" + dvd)
        safety(
            r["media_job_id"] == job_id
            and r["attempt_count"] == attempts
            and r["status"] == "FAILED"
            and r["poster_status"] == "UNKNOWN",
            "FAILED_HISTORY_CHANGED_" + dvd,
        )
    return status_map


def open_lock(path):
    safety(path.parent.is_dir() and not path.parent.is_symlink(), "LOCK_DIR_UNSAFE")
    fd = os.open(
        path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    info = os.fstat(fd)
    safety(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "LOCK_FILE_UNSAFE")
    safety(info.st_uid == 0 and not (info.st_mode & 0o022), "LOCK_OWNER_UNSAFE")
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fd


def main():
    committed = False
    print("===== PRECHECK =====", flush=True)
    safety(os.geteuid() == 0, "ROOT_REQUIRED")
    safety(SCRIPT.is_file() and not SCRIPT.is_symlink(), "SCRIPT_INVALID")
    safety(digest(SCRIPT) == SHA, "SCRIPT_SHA_MISMATCH")
    safety(BACKUPS.is_dir() and not BACKUPS.is_symlink(), "BACKUP_DIR_INVALID")
    safety(BACKUPS.resolve() == BACKUPS.absolute(), "BACKUP_DIR_SYMLINK")

    spec = importlib.util.spec_from_file_location("stg9_clean_11", SCRIPT)
    safety(spec is not None and spec.loader is not None, "SCRIPT_MODULE_INVALID")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    targets, base, plan = helper.prepare_plan(MANIFEST)
    safety(len(targets) == 54 and "MBRBI-015" not in targets, "MANIFEST_CHANGED")
    media_db = flag(base, "--media-db")
    writer_lock = flag(base, "--media-writer-lock")
    run_lock = flag(base, "--run-lock")
    safety(writer_lock != run_lock, "LOCK_COLLISION")
    safety(media_db.is_file() and not media_db.is_symlink(), "DB_UNSAFE")
    safety(media_db.stat().st_uid == 0, "DB_OWNER_CHANGED")

    releases = [Path(x) for x in base if x.endswith("/teddy_discovery_media_only_runner.py")]
    safety(len(releases) == 1, "RUNNER_MISMATCH")
    sys.path.insert(0, str(releases[0].parent))
    import teddy_discovery_media_jobs as jobs
    safety(Path(jobs.__file__).resolve().parent == releases[0].parent,
           "JOBS_MODULE_MISMATCH")

    for unit in ("teddy-stage9-media.service", "teddy-stage9-media.timer"):
        safety(state(unit, "ActiveState") == "inactive", "STAGE9_UNIT_ACTIVE")
    safety(state("teddy-stage9-media.service", "MainPID") == "0",
           "STAGE9_MAIN_PID_ACTIVE")
    print("PINNED_RUNNER=PASS", flush=True)
    print("TIMER_REMAINS_STOPPED=PASS", flush=True)

    fd_run = None
    fd_writer = None
    try:
        fd_run = open_lock(run_lock)
        fd_writer = open_lock(writer_lock)
        print("EXCLUSIVE_LOCKS=PASS", flush=True)
        source = sqlite3.connect("file:" + media_db.as_posix() + "?mode=ro", uri=True)
        source.row_factory = sqlite3.Row
        before = row_dict(source)
        pre = check_pre(before, jobs)
        safety(source.execute("PRAGMA quick_check").fetchone()[0] == "ok",
               "SOURCE_DB_INTEGRITY_FAILED")
        print("DRY_RUN_ELIGIBLE=11", flush=True)
        print("DRY_RUN_EXHAUSTED=3", flush=True)
        print("DRY_RUN_PLAN=10_COMPLETE_1_ATTENTION_3_UNCHANGED", flush=True)

        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = BACKUPS / (
            "stage9-media-before-poster-reconcile-11-" + stamp
            + "-" + uuid.uuid4().hex[:12] + ".sqlite3"
        )
        fd = os.open(
            backup,
            os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        os.close(fd)
        try:
            with sqlite3.connect(backup) as destination:
                source.backup(destination)
            source.close()
            with sqlite3.connect("file:" + backup.as_posix() + "?mode=ro", uri=True) as saved:
                saved.row_factory = sqlite3.Row
                safety(saved.execute("PRAGMA quick_check").fetchone()[0] == "ok",
                       "BACKUP_INTEGRITY_FAILED")
                safety(row_dict(saved) == before, "BACKUP_STATE_MISMATCH")
            backup_sha = digest(backup)
            with open(backup, "rb") as f:
                os.fsync(f.fileno())
            print("BACKUP_CREATED=PASS", flush=True)
            print("BACKUP=" + str(backup), flush=True)
            print("BACKUP_SHA256=" + backup_sha, flush=True)
        except Exception:
            print("BACKUP_FAILED_NO_DB_WRITE", flush=True)
            raise

        changed = []
        with sqlite3.connect("file:" + media_db.as_posix() + "?mode=rw",
                             uri=True, isolation_level=None, timeout=5) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("BEGIN IMMEDIATE")
            try:
                current = row_dict(db)
                safety(current == before, "DB_CHANGED_SINCE_BACKUP")
                check_pre(current, jobs)
                now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
                for dvd, (job_id, attempts) in {**COMPLETE, **PROTECTED}.items():
                    new_status = "ATTENTION" if dvd in PROTECTED else "COMPLETE"
                    new_error = ERROR_PROTECTED if dvd in PROTECTED else None
                    result = db.execute(
                        """UPDATE media_jobs
                           SET poster_status=?, poster_error=?, updated_at=?
                           WHERE dvd_id=? AND media_job_id=? AND attempt_count=?
                             AND status='COMPLETED' AND nfo_status='COMPLETE'
                             AND poster_status='PENDING'
                             AND jellyfin_notification_status='VISIBLE'
                             AND jellyfin_recovery_status='VISIBLE'
                             AND error IS NULL AND poster_error IS NOT NULL""",
                        (new_status, new_error, now, dvd, job_id, attempts),
                    )
                    safety(result.rowcount == 1, "CAS_FAILED_" + dvd)
                    changed.append((dvd, new_status))
                after = row_dict(db)
                for dvd in FAILED:
                    safety(after[dvd] == before[dvd], "FAILED_HISTORY_MUTATED_" + dvd)
                for dvd in before:
                    if dvd not in COMPLETE and dvd not in PROTECTED:
                        safety(after[dvd] == before[dvd], "UNRELATED_ROW_MUTATED_" + dvd)
                safety(not any(x == "ELIGIBLE" for x in eligibility(after, jobs).values()),
                       "ELIGIBLE_QUEUE_REMAINS")
                db.execute("COMMIT")
                committed = True
                print("DB_COMMIT=PASS", flush=True)
            except Exception:
                db.execute("ROLLBACK")
                raise
        with sqlite3.connect("file:" + media_db.as_posix() + "?mode=ro", uri=True) as check:
            check.row_factory = sqlite3.Row
            verified = row_dict(check)
            safety(verified == after, "POST_COMMIT_READBACK_FAILED")
            safety(check.execute("PRAGMA quick_check").fetchone()[0] == "ok",
                   "POST_COMMIT_INTEGRITY_FAILED")
        print("===== APPLY RESULT =====", flush=True)
        for dvd, status in changed:
            print(f"UPDATED={dvd}:{status}")
        print("POSTER_COMPLETE=10")
        print("POSTER_ATTENTION=1")
        print("HISTORICAL_FAILED_PRESERVED=3")
        print("ELIGIBLE_REMAINING=0")
        print("MEDIA_DB_RECONCILIATION=PASS")
        print("TIMER_ACTIVATION=NOT_RUN")
        print("NAS_JELLYFIN_WRITES=0")
    finally:
        if committed:
            print("COMMIT_OCCURRED=YES", flush=True)
        if fd_writer is not None:
            os.close(fd_writer)
        if fd_run is not None:
            os.close(fd_run)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("MEDIA_DB_RECONCILIATION=STOPPED", flush=True)
        print("STOP_REASON=" + type(exc).__name__ + ":" + str(exc), flush=True)
        sys.exit(2)
