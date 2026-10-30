"""Synthetic-only end-to-end tests; no network or operational databases."""
import hashlib
import sqlite3
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from teddy_discovery_media_nfo_only import create_nfo_only
from teddy_discovery_media_filestation import FileStationMediaError, MAX_NFO_BYTES
from teddy_discovery_media_filestation_smoke import (
    FakeFileStation, _adapter, VIDEO_PATH, VIDEO_BYTES, NFO_PATH, API_LIBRARY_ROOT,
)
from teddy_discovery_media_metadata import build_nfo_bytes, load_media_metadata
from teddy_discovery_media_publish import MediaMetadataPublishError


def fixture(path):
    with sqlite3.connect(path) as db:
        db.executescript('''
        CREATE TABLE titles (dvd_id TEXT, title TEXT, release_date TEXT, maker TEXT, cover_url TEXT, raw_metadata TEXT, metadata_source TEXT);
        CREATE TABLE genres (genre_id INTEGER, name TEXT);
        CREATE TABLE title_genres (dvd_id TEXT, genre_id INTEGER);
        CREATE TABLE people (person_id INTEGER, name TEXT);
        CREATE TABLE title_people (dvd_id TEXT, person_id INTEGER, role TEXT);
        CREATE TABLE holdings (storage_root TEXT, relative_path TEXT, dvd_id TEXT, parse_status TEXT, size_bytes INTEGER, present INTEGER, discovered_by TEXT);
        CREATE TABLE organizer_jobs (job_id INTEGER PRIMARY KEY, dvd_id TEXT, status TEXT);
        CREATE TABLE media_jobs (value TEXT);
        INSERT INTO titles VALUES ('ABC-123','[ABC-123] Fixture', '', '', '', '{"source":"javdatabase-weekly","item":{"dvd_id":"ABC-123","title":"Fixture"}}', 'javdatabase-weekly');
        INSERT INTO holdings VALUES ('jav','ABC/ABC-123/ABC-123.mp4','ABC-123','MATCHED', 36, 1, 'library-inventory');
        INSERT INTO organizer_jobs VALUES (1, 'ABC-123', 'COMPLETED'); INSERT INTO media_jobs VALUES ('untouched');
        ''')
        db.execute('UPDATE holdings SET size_bytes=?', (len(VIDEO_BYTES),))


def run(case):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d); db = root / 'synthetic.sqlite'; fixture(db)
        fake = FakeFileStation()
        poster = API_LIBRARY_ROOT + '/ABC/ABC-123/poster.jpg'
        subtitle = API_LIBRARY_ROOT + '/ABC/ABC-123/ABC-123.srt'
        fake.files[subtitle] = b'subtitle'
        if case == 'poster_present': fake.files[poster] = b'poster'
        with sqlite3.connect(db) as conn:
            if case == 'organizer_provenance': conn.execute("UPDATE holdings SET discovered_by='organizer-apply'")
            if case == 'wrong_provenance': conn.execute("UPDATE holdings SET discovered_by='completion-stage9'")
            if case == 'organizer_incomplete': conn.execute("UPDATE organizer_jobs SET status='PENDING'")
            if case == 'organizer_missing': conn.execute('DELETE FROM organizer_jobs')
            if case == 'organizer_other': conn.execute("UPDATE organizer_jobs SET dvd_id='OTHER-1'")
            if case == 'raw_source_mismatch': conn.execute("UPDATE titles SET raw_metadata=replace(raw_metadata, 'javdatabase-weekly', 'javdatabase-movie')")
            if case == 'raw_missing_id': conn.execute("UPDATE titles SET raw_metadata='{\"source\":\"javdatabase-weekly\",\"item\":{\"title\":\"Fixture\"}}'")
            if case == 'raw_missing_title': conn.execute("UPDATE titles SET raw_metadata='{\"source\":\"javdatabase-weekly\",\"item\":{\"dvd_id\":\"ABC-123\"}}'")
            if case == 'invalid_json': conn.execute("UPDATE titles SET raw_metadata='{'")
            if case == 'missing_source': conn.execute("UPDATE titles SET metadata_source=''")
            if case == 'wrong_source': conn.execute("UPDATE titles SET metadata_source='unknown'")
            if case == 'title_mismatch': conn.execute("UPDATE titles SET title='different title'")
            if case == 'missing_holding': conn.execute('DELETE FROM holdings')
            if case == 'multiple': conn.execute("INSERT INTO holdings SELECT storage_root, relative_path || '2', dvd_id, parse_status, size_bytes, present, discovered_by FROM holdings")
            if case == 'wrong_root': conn.execute("UPDATE holdings SET storage_root='other'")
            if case == 'wrong_path': conn.execute("UPDATE holdings SET relative_path='../bad.mp4'")
            if case == 'wrong_size': conn.execute('UPDATE holdings SET size_bytes=1')
            if case == 'empty_title': conn.execute("UPDATE titles SET title=''")
            if case == 'wrong_id': conn.execute("UPDATE titles SET raw_metadata='{\"source\":\"javdatabase-weekly\",\"item\":{\"dvd_id\":\"BAD-1\",\"title\":\"Fixture\"}}'")
        if case == 'existing_same': fake.files[NFO_PATH] = build_nfo_bytes(load_media_metadata(db, 'ABC-123'))
        if case == 'existing_different': fake.files[NFO_PATH] = b'old NFO'
        if case in ('race_1805', 'race_414'): fake.upload_error_code = int(case.split('_')[1])
        if case == 'uncertain': fake.upload_http_status = 503; fake.upload_commit_before_http_error = True
        if case == 'budget': pass
        if case == 'hash': fake.download_overrides[NFO_PATH] = b'bad'
        if case == 'owner_post':
            original = fake._metadata
            def bad_owner(path):
                result = original(path)
                if path == NFO_PATH: result['additional']['owner']['user'] = 'wrong'
                return result
            fake._metadata = bad_owner
        before_db = hashlib.sha256(db.read_bytes()).digest()
        before = dict(fake.files)
        expected = {'create', 'poster_present', 'organizer_provenance'}
        owner = 'wrong' if case == 'owner' else 'admin'
        group = 'wrong' if case == 'group' else 'users'
        with _adapter(root, fake) as adapter:
            try:
                if case == 'budget': adapter.max_requests = adapter.request_count
                with patch('teddy_discovery_media_nfo_only.build_nfo_bytes', return_value=b'x' * (MAX_NFO_BYTES + 1)) if case == 'size_cap' else patch('teddy_discovery_media_nfo_only.MAX_NFO_BYTES', MAX_NFO_BYTES):
                    result = create_nfo_only(db, 'bad' if case == 'invalid_id' else 'ABC-123', expected_owner=owner, expected_group=group, adapter=adapter)
                assert case in expected and result['nfo']['status'] == 'CREATED'
                title = ET.fromstring(fake.files[NFO_PATH]).findtext('title')
                assert title == '[ABC-123] Fixture'
            except (ValueError, MediaMetadataPublishError) as exc:
                assert case not in expected, (case, exc)
                if case.startswith('race_'): assert exc.code == 'SIDECAR_CREATED_CONCURRENTLY'
                if case == 'existing_same': assert exc.code == 'NFO_ALREADY_PRESENT'
                if case == 'budget': assert exc.code == 'FILESTATION_REQUEST_BUDGET_EXHAUSTED'
                if case == 'hash': assert exc.code == 'UPLOAD_POSTVERIFY_HASH_MISMATCH'
                if case == 'owner_post': assert exc.code == 'UPLOAD_POSTVERIFY_OWNER_MISMATCH'
            assert adapter.request_count <= 64
        assert hashlib.sha256(db.read_bytes()).digest() == before_db
        for name, data in before.items(): assert fake.files[name] == data
        assert len(fake.uploads) <= 1
        assert all(path == NFO_PATH for path, _ in fake.uploads)
        posts = [c for c in fake.calls if c[0] == 'POST' and c[3] is not None
                 and b'name="api"\r\n\r\nSYNO.FileStation.Upload\r\n' in c[3]]
        one_attempt = expected | {'race_1805', 'race_414', 'uncertain', 'hash', 'owner_post'}
        assert len(posts) == (1 if case in one_attempt else 0), (case, len(posts))
        assert set(fake.files) - set(before) <= {NFO_PATH}


def main():
    cases = ['create','poster_present','missing_holding','multiple','wrong_root','wrong_path','wrong_size','empty_title','wrong_id','invalid_id','owner','group','existing_same','existing_different','race_1805','race_414','uncertain','hash','owner_post','size_cap','budget','organizer_provenance','wrong_provenance','organizer_incomplete','organizer_missing','organizer_other','invalid_json','missing_source','wrong_source','title_mismatch','raw_source_mismatch','raw_missing_id','raw_missing_title']
    for case in cases:
        run(case)
        print('PASS', case)
    print(f'OFFLINE_SMOKE: {len(cases)} PASS / 0 FAIL')

if __name__ == '__main__': main()
