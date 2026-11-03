"""Isolated thumbnail processor checks: fake SQLite, HTTP and File Station."""
from pathlib import Path
import sqlite3
import tempfile
from datetime import datetime, timezone
from teddy_discovery_media_pipeline import run_thumbnail_processor
from teddy_discovery_media_pipeline_smoke import make_db
from teddy_discovery_media_filestation_smoke import FakeFileStation, _adapter, API_LIBRARY_ROOT, VIDEO_BYTES
from teddy_discovery_media_jobs import _media_transaction, run_thumbnail_jobs


def main():
    checks = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for dvd, prefix in (('ABC-123', 'ABC'), ('XYZ-456', 'XYZ')):
            db_path = root / (dvd + '.sqlite'); make_db(db_path, dvd_id=dvd, cover_url=None)
            with sqlite3.connect(db_path) as db:
                db.execute('UPDATE holdings SET size_bytes=?', (len(VIDEO_BYTES),))
            fake = FakeFileStation(); folder = API_LIBRARY_ROOT + '/' + prefix + '/' + dvd
            fake.directories.update({API_LIBRARY_ROOT + '/' + prefix, folder})
            video = folder + '/' + dvd + '.mp4'; fake.files[video] = VIDEO_BYTES
            nfo = folder + '/' + dvd + '.nfo'; fake.files[nfo] = b'existing nfo'
            image = b'\xff\xd8\xffsynthetic-original\xff\xd9'; calls = []
            def fetch(url, maximum):
                calls.append(url); return 200, url, 'image/jpeg', image
            job_db = root / (dvd + '-jobs.sqlite'); lock = root / (dvd + '.lock'); lock_dir = root / (dvd + '-locks'); lock_dir.mkdir()
            now = datetime(2026, 11, 3, tzinfo=timezone.utc)
            with _media_transaction(job_db, lock) as db:
                db.execute("""INSERT INTO media_jobs(dvd_id,status,nfo_status,poster_status,
                    jellyfin_notification_status,created_at,updated_at) VALUES (?, 'COMPLETED', 'COMPLETE',
                    'PENDING', 'VISIBLE', ?, ?)""", (dvd,now.isoformat(),now.isoformat()))
            with _adapter(root, fake) as adapter:
                def process(): return run_thumbnail_processor(db_path=db_path, dvd_id=dvd, file_station=adapter, fetcher=fetch)
                # A poster is observed before any candidate request.
                poster = folder + '/poster.jpg'; fake.files[poster] = b'original poster'
                assert process()['status'] == 'SKIPPED' and not calls and not fake.uploads; checks += 1
                del fake.files[poster]  # Synthetic fixture only.
                # Incomplete listing prevents the fetch.
                old = adapter._parent_listing
                def bad_listing(path): raise RuntimeError('listing unavailable')
                adapter._parent_listing = bad_listing
                try:
                    assert process()['status'] == 'ATTENTION'
                finally: adapter._parent_listing = old
                assert not calls and not fake.uploads; checks += 1
                def denied(url, maximum): return 403, url, 'image/jpeg', image
                def bad(url, maximum): return 200, url, 'image/jpeg', b'broken'
                assert run_thumbnail_processor(db_path=db_path, dvd_id=dvd, file_station=adapter, fetcher=denied)['status'] == 'PENDING'
                assert run_thumbnail_processor(db_path=db_path, dvd_id=dvd, file_station=adapter, fetcher=bad)['status'] == 'PENDING'; checks += 2
                before = dict(fake.files)
                result = run_thumbnail_jobs(db_path=job_db, writer_lock_path=lock, title_lock_dir=lock_dir, now=now, processor=lambda _: process())
                assert result[0]['status'] == 'COMPLETE'; assert fake.files[folder + '/thumb.jpg'] == image
                assert all(fake.files[k] == v for k,v in before.items()); checks += 2
                assert run_thumbnail_jobs(db_path=job_db, writer_lock_path=lock, title_lock_dir=lock_dir, now=now, processor=lambda _: process()) == []
                assert len(fake.uploads) == 1; checks += 1
                assert process()['status'] == 'ATTENTION' and fake.files[folder + '/thumb.jpg'] == image; checks += 1
            with _media_transaction(job_db, lock) as db:
                row = db.execute('SELECT nfo_status,poster_status,jellyfin_notification_status FROM media_jobs').fetchone()
                assert tuple(row) == ('COMPLETE','PENDING','VISIBLE'); checks += 1
    print(f'THUMBNAIL_PROCESSOR={checks} PASS / 0 FAIL')

if __name__ == '__main__': main()
