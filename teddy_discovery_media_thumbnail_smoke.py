"""Synthetic data only; no network or operational state."""
import unittest
from teddy_discovery_media_thumbnail import extract_thumbnail


class ThumbnailSmoke(unittest.TestCase):
    def fixture(self, dvd='ABC-123', **changes):
        page='https://missav123.com/ko/'+dvd.lower()
        image='https://missav123.com/image/'+dvd.lower()+'.jpg'
        html=f'<link rel="canonical" href="{page}"><meta property="og:image" content="{image}">'.encode()
        responses={page:(200,page,'text/html',html),image:(200,image,'image/jpeg',b'\xff\xd8\xfffixture')}
        responses.update(changes)
        calls=[]
        def fetch(url, maximum):
            calls.append((url,maximum))
            return responses[url]
        return page,image,responses,calls,fetch

    def test_two_ids(self):
        for dvd in ('ABC-123','XYZ-456'):
            page,image,_,calls,fetch=self.fixture(dvd)
            result=extract_thumbnail(dvd_id=dvd,page_url=page,fetcher=fetch)
            self.assertEqual(result.filename,'thumb.jpg');self.assertEqual(result.image_url,image);self.assertEqual(len(calls),2)

    def test_fourhoi_exact_id_and_twitter(self):
        for dvd in ('ABC-123', 'XYZ-456'):
            page, _, responses, _, fetch = self.fixture(dvd)
            image = 'https://fourhoi.com/' + dvd.lower() + '/cover-n.jpg'
            responses[page] = (200, page, 'text/html', f'<link rel="canonical" href="{page}"><meta property="og:image" content="{image}"><meta name="twitter:image" content="{image}">'.encode())
            responses[image] = (200, image, 'image/jpeg', b'\xff\xd8\xfffixture')
            self.assertEqual(extract_thumbnail(dvd_id=dvd, page_url=page, fetcher=fetch).image_url, image)
            for bad in ('https://fourhoi.com/other-1/cover-n.jpg', 'https://fourhoi.com/'+dvd.lower()+'/cover-t.jpg', 'https://fourhoi.com/'+dvd.lower()+'/cover-n.jpg?x=1', 'https://evil.invalid/'+dvd.lower()+'/cover-n.jpg', 'https://fourhoi.com/%61bc-123/cover-n.jpg'):
                responses[page] = (200, page, 'text/html', f'<link rel="canonical" href="{page}"><meta property="og:image" content="{bad}">'.encode())
                with self.assertRaises(ValueError): extract_thumbnail(dvd_id=dvd, page_url=page, fetcher=fetch)
            responses[page] = (200, page, 'text/html', f'<link rel="canonical" href="{page}"><meta property="og:image" content="{image}"><meta name="twitter:image" content="https://fourhoi.com/other-1/cover-n.jpg">'.encode())
            with self.assertRaises(ValueError): extract_thumbnail(dvd_id=dvd, page_url=page, fetcher=fetch)
            responses[page] = (200, page, 'text/html', f'<link rel="canonical" href="{page}"><meta property="og:image" content="{image}">'.encode())
            responses[image] = (200, image + '?redirect', 'image/jpeg', b'\xff\xd8\xfffixture')
            with self.assertRaises(ValueError): extract_thumbnail(dvd_id=dvd, page_url=page, fetcher=fetch)

    def test_wrong_identity(self):
        page,_,_,calls,fetch=self.fixture()
        with self.assertRaises(ValueError):extract_thumbnail(dvd_id='XYZ-456',page_url=page,fetcher=fetch)
        self.assertFalse(calls)

    def test_wrong_canonical(self):
        page,image,responses,_,fetch=self.fixture()
        responses[page]=(200,page,'text/html',f'<link rel="canonical" href="https://missav123.com/ko/xyz-456"><meta property="og:image" content="{image}">'.encode())
        with self.assertRaises(ValueError):extract_thumbnail(dvd_id='ABC-123',page_url=page,fetcher=fetch)

    def test_untrusted_image_host(self):
        page,_,responses,_,fetch=self.fixture()
        responses[page]=(200,page,'text/html',f'<link rel="canonical" href="{page}"><meta property="og:image" content="https://evil.invalid/x.jpg">'.encode())
        with self.assertRaises(ValueError):extract_thumbnail(dvd_id='ABC-123',page_url=page,fetcher=fetch)

    def test_403_and_redirect(self):
        page,_,responses,_,fetch=self.fixture()
        for result in ((403,page,'text/html',b'denied'),(200,page+'?redirect','text/html',b'ok')):
            responses[page]=result
            with self.assertRaises(ValueError):extract_thumbnail(dvd_id='ABC-123',page_url=page,fetcher=fetch)

    def test_bad_magic(self):
        page,image,responses,_,fetch=self.fixture();responses[image]=(200,image,'image/jpeg',b'not jpeg')
        with self.assertRaises(ValueError):extract_thumbnail(dvd_id='ABC-123',page_url=page,fetcher=fetch)

    def test_fetcher_required(self):
        with self.assertRaises(ValueError):extract_thumbnail(dvd_id='ABC-123',page_url='https://missav123.com/ko/abc-123',fetcher=None)

class StorageConnectionSmoke(unittest.TestCase):
    fixture = ThumbnailSmoke.fixture
    def test_injected_to_filestation(self):
        from pathlib import Path
        import tempfile
        from teddy_discovery_media_thumbnail import store_injected_thumbnail
        from teddy_discovery_media_filestation_smoke import FakeFileStation, _adapter, API_LIBRARY_ROOT, VIDEO_BYTES
        from teddy_discovery_media_filestation import FileStationMediaError
        with tempfile.TemporaryDirectory() as temp:
            for dvd, prefix in (("ABC-123", "ABC"), ("XYZ-456", "XYZ")):
                page, image, responses, calls, fetch = self.fixture(dvd)
                fake = FakeFileStation()
                folder = API_LIBRARY_ROOT + "/" + prefix + "/" + dvd
                fake.directories.update({API_LIBRARY_ROOT + "/" + prefix, folder})
                fake.files[folder + "/" + dvd + ".mp4"] = VIDEO_BYTES
                rel = prefix + "/" + dvd + "/" + dvd + ".mp4"
                with _adapter(Path(temp), fake) as adapter:
                    def run(**kw):
                        args = dict(dvd_id=dvd, video_relative=rel, page_url=page, fetcher=fetch, file_station=adapter, official_poster_verified=False)
                        args.update(kw)
                        return store_injected_thumbnail(**args)
                    self.assertEqual(run(page_url=None)['status'], 'PENDING')
                    self.assertEqual(run(official_poster_verified=True)['status'], 'POSTER_PRESENT')
                    self.assertFalse(calls)
                    with self.assertRaises(ValueError): run(official_poster_verified=None)
                    with self.assertRaises(ValueError): run(dvd_id='BAD-1')
                    original = responses[image]
                    responses[image] = (200, image, 'image/jpeg', b'invalid')
                    with self.assertRaises(ValueError): run()
                    responses[image] = original
                    before = dict(fake.files)
                    self.assertEqual(run()['status'], 'CREATED')
                    with self.assertRaises(FileStationMediaError): run()
                    self.assertTrue(all(fake.files[k] == v for k, v in before.items()))
                    self.assertEqual(len(fake.uploads), 1)


class CandidateSmoke(unittest.TestCase):
    def test_candidate_storage(self):
        from pathlib import Path
        import tempfile
        from teddy_discovery_media_thumbnail import candidate_thumbnail_url, store_candidate_thumbnail
        from teddy_discovery_media_filestation_smoke import FakeFileStation, _adapter, API_LIBRARY_ROOT, VIDEO_BYTES
        from teddy_discovery_media_filestation import FileStationMediaError
        with tempfile.TemporaryDirectory() as tmp:
            for dvd, prefix in (("ABC-123", "ABC"), ("XYZ-456", "XYZ")):
                url = candidate_thumbnail_url(dvd)
                self.assertEqual(url, 'https://fourhoi.com/' + dvd.lower() + '/cover-n.jpg')
                fake = FakeFileStation(); folder = API_LIBRARY_ROOT + '/' + prefix + '/' + dvd
                fake.directories.update({API_LIBRARY_ROOT + '/' + prefix, folder})
                fake.files[folder + '/' + dvd + '.mp4'] = VIDEO_BYTES
                rel = prefix + '/' + dvd + '/' + dvd + '.mp4'
                data = b'\xff\xd8\xffsynthetic\xff\xd9'
                with _adapter(Path(tmp), fake) as adapter:
                    def run(fetch, poster=False):
                        return store_candidate_thumbnail(dvd_id=dvd, video_relative=rel, fetcher=fetch, file_station=adapter, official_poster_verified=poster)
                    def good(u, m): return (200, u, 'image/jpeg', data)
                    self.assertEqual(run(good, True)['status'], 'POSTER_PRESENT')
                    with self.assertRaises(ValueError): run(good, None)
                    for response in ((403,url,'image/jpeg',data),(404,url,'image/jpeg',data),(200,url+'?redirect','image/jpeg',data),(200,url,'image/png',data),(200,url,'image/jpeg',b'bad')):
                        self.assertEqual(run(lambda u,m: response)['status'], 'PENDING')
                    before = dict(fake.files)
                    self.assertEqual(run(good)['status'], 'CREATED')
                    self.assertEqual(fake.files[folder + '/thumb.jpg'], data)
                    with self.assertRaises(FileStationMediaError): run(good)
                    self.assertTrue(all(fake.files[k] == v for k,v in before.items()))
                    self.assertEqual(len(fake.uploads), 1)

    def test_proxy_transport(self):
        from unittest.mock import patch
        from teddy_discovery_media_thumbnail import make_candidate_proxy_fetcher, candidate_thumbnail_url, MAX_POSTER_BYTES
        from teddy_discovery_media_metadata import _PosterOnlyProxyHandler
        class Response:
            status = 200
            headers = {'Content-Type': 'image/jpeg'}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def geturl(self): return candidate_thumbnail_url('ABC-123')
            def read(self, count):
                assert count == MAX_POSTER_BYTES + 1
                return b'bytes'
        class Opener:
            def open(self, request, timeout):
                assert request.full_url == candidate_thumbnail_url('ABC-123') and timeout == 20
                return Response()
        with patch('urllib.request.build_opener', return_value=Opener()) as build:
            fetch = make_candidate_proxy_fetcher('http://127.0.0.1:58888')
            self.assertIsInstance(build.call_args.args[0], _PosterOnlyProxyHandler)
            self.assertIsNone(build.call_args.args[1].redirect_request(None, None, 302, '', {}, 'https://evil.invalid'))
            self.assertEqual(fetch(candidate_thumbnail_url('ABC-123'), MAX_POSTER_BYTES)[0], 200)
            for bad in ('https://fourhoi.com/xyz-1/cover-n.jpg?x=1', 'https://fourhoi.com:443/abc-123/cover-n.jpg', 'https://evil.invalid/abc-123/cover-n.jpg', 'https://fourhoi.com/abc-123/cover-t.jpg'):
                with self.assertRaises(ValueError): fetch(bad, MAX_POSTER_BYTES)
        with self.assertRaises(ValueError): make_candidate_proxy_fetcher('http://example.com:8888')


class CanaryGateSmoke(unittest.TestCase):
    def test_single_get_and_hash(self):
        import hashlib
        from teddy_discovery_media_thumbnail import one_shot_verified_fetch
        url='https://fourhoi.com/abc-123/cover-n.jpg'; data=b'\xff\xd8\xfffixture\xff\xd9'; calls=[]
        def fetch(u,m): calls.append(u); return 200,u,'image/jpeg',data
        gate=one_shot_verified_fetch(fetch,exact_url=url,expected_size=len(data),expected_sha256=hashlib.sha256(data).hexdigest())
        self.assertEqual(gate(url,100)[3],data)
        with self.assertRaises(ValueError): gate(url,100)
        self.assertEqual(len(calls),1)
        bad=one_shot_verified_fetch(fetch,exact_url=url,expected_size=len(data),expected_sha256='0'*64)
        with self.assertRaises(ValueError): bad(url,100)

class DiagnosticCodesSmoke(unittest.TestCase):
    def test_errors_reach_db_and_runner_without_upload(self):
        import hashlib, tempfile, sqlite3
        from pathlib import Path
        from urllib.error import HTTPError, URLError
        from teddy_discovery_media_thumbnail import candidate_thumbnail_url, store_candidate_thumbnail, one_shot_verified_fetch
        from teddy_discovery_media_jobs import _media_transaction, run_thumbnail_jobs
        from teddy_discovery_media_only_runner import _summarize_thumbnail
        from unittest.mock import Mock
        url=candidate_thumbnail_url('ABC-123'); data=b'\xff\xd8\xfffixture\xff\xd9'
        secret='https://user:SECRET@invalid/?token=SECRET'
        cases=[
            (URLError(secret),'CANDIDATE_NETWORK_ERROR'),
            (ConnectionRefusedError(secret),'CANDIDATE_NETWORK_ERROR'),
            (HTTPError(secret,403,secret,{},None),'CANDIDATE_HTTP_403'),
            (HTTPError(secret,302,secret,{},None),'CANDIDATE_REDIRECT_REJECTED'),
            ((302,url,'image/jpeg',data),'CANDIDATE_REDIRECT_REJECTED'),
            ((200,url+'?secret','image/jpeg',data),'CANDIDATE_REDIRECT_REJECTED'),
            ((200,url,'text/html',data),'CANDIDATE_MIME_MISMATCH'),
            ((200,url,'image/jpeg',data+b'x'),'CANDIDATE_SIZE_MISMATCH'),
            ((200,url,'image/jpeg',b'\xff\xd8\xffotherxx\xff\xd9'),'CANDIDATE_SHA256_MISMATCH'),
            ((200,url,'image/jpeg',b'x'*len(data)),'CANDIDATE_RESPONSE_INVALID'),
            ((200,url),'CANDIDATE_RESPONSE_INVALID'),
            (RuntimeError(secret),'CANDIDATE_UNKNOWN_ERROR'),
        ]
        for status, code in ((403,'CANDIDATE_HTTP_403'), (404,'CANDIDATE_HTTP_404'),
                             (429,'CANDIDATE_HTTP_429'), (500,'CANDIDATE_HTTP_5XX'),
                             (599,'CANDIDATE_HTTP_5XX'), (418,'CANDIDATE_HTTP_ERROR')):
            cases.extend(((HTTPError(secret,status,secret,{},None),code),
                          ((status,url,'image/jpeg',data),code)))
        for index,(response,expected) in enumerate(cases):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp); locks=p/'titles';locks.mkdir();db=p/'media.sqlite'
                with _media_transaction(db,p/'writer.lock') as c:
                    c.execute("INSERT INTO media_jobs(dvd_id,status,nfo_status,created_at,updated_at) VALUES('ABC-123','COMPLETED','COMPLETE','2026-11-03','2026-11-03')")
                calls=[]; storage=Mock()
                def fetch(u,m):
                    calls.append(u)
                    if isinstance(response,Exception): raise response
                    return response
                gate=one_shot_verified_fetch(fetch,exact_url=url,expected_size=len(data),expected_sha256=hashlib.sha256(data).hexdigest())
                def process(dvd):return store_candidate_thumbnail(dvd_id=dvd,video_relative='ABC/ABC-123/ABC-123.mp4',fetcher=gate,file_station=storage,official_poster_verified=False)
                result=run_thumbnail_jobs(db_path=db,writer_lock_path=p/'writer.lock',title_lock_dir=locks,processor=process)
                self.assertEqual(result[0]['error'],expected)
                summary=_summarize_thumbnail(result)
                self.assertEqual(summary['error_codes'],{expected:1});self.assertNotIn('SECRET',str(summary))
                c=sqlite3.connect(db);self.assertEqual(c.execute('select thumbnail_error from media_jobs').fetchone()[0],expected);c.close()
                self.assertEqual(len(calls),1);storage.create_thumbnail.assert_not_called()
                second=process('ABC-123');self.assertEqual(second['error'],'CANDIDATE_REQUEST_LIMIT');self.assertEqual(len(calls),1)
        self.assertEqual(_summarize_thumbnail([{'status':'PENDING','error':secret}])['error_codes'],{'CANDIDATE_UNKNOWN_ERROR':1})
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); (p/'titles').mkdir()
            with _media_transaction(p/'media.sqlite',p/'writer.lock') as c:
                c.execute("INSERT INTO media_jobs(dvd_id,status,nfo_status,created_at,updated_at) VALUES('ABC-123','COMPLETED','COMPLETE','2026-11-03','2026-11-03')")
            result=run_thumbnail_jobs(db_path=p/'media.sqlite',writer_lock_path=p/'writer.lock',title_lock_dir=p/'titles',processor=lambda dvd: {'status':'PENDING','error':secret})
            c=sqlite3.connect(p/'media.sqlite')
            self.assertEqual(c.execute('select thumbnail_error from media_jobs').fetchone()[0],'CANDIDATE_UNKNOWN_ERROR');c.close()


if __name__ == '__main__': unittest.main(verbosity=2)
