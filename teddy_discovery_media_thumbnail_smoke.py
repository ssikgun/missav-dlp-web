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


if __name__ == '__main__': unittest.main(verbosity=2)
