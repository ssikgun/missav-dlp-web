"""Small offline contract test for the Stage9 File Station adapter."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urlsplit
import hashlib
import json
import os
import tempfile

from teddy_discovery_media_filestation import (
    API_LIBRARY_ROOT,
    HTTPResult,
    REAL_LIBRARY_ROOT,
    FileStationMediaError,
    SynologyFileStationMediaAdapter,
)
from teddy_discovery_media_metadata import MediaBundle


VIDEO_PATH = API_LIBRARY_ROOT + "/ABC/ABC-123/ABC-123.mp4"
NFO_PATH = API_LIBRARY_ROOT + "/ABC/ABC-123/ABC-123.nfo"
VIDEO_BYTES = b"synthetic video bytes; no real media"
NFO_BYTES = b"<?xml version=\"1.0\"?><movie><title>Fixture</title></movie>\n"
POSTER_BYTES = b"synthetic canonical poster payload"


def _json_response(value, status=200):
    raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
    return HTTPResult(status, "application/json", raw, len(raw))


def _api_real(path: str) -> str:
    if path == API_LIBRARY_ROOT:
        return REAL_LIBRARY_ROOT
    if not path.startswith(API_LIBRARY_ROOT + "/"):
        raise AssertionError("fake received a path outside the JAV share")
    return REAL_LIBRARY_ROOT + path[len(API_LIBRARY_ROOT):]


class FakeFileStation:
    def __init__(self, *, existing_nfo: bytes | None = None):
        self.directories = {
            API_LIBRARY_ROOT,
            API_LIBRARY_ROOT + "/ABC",
            API_LIBRARY_ROOT + "/ABC/ABC-123",
        }
        self.files = {VIDEO_PATH: VIDEO_BYTES}
        self.owners = {VIDEO_PATH: "admin"}
        self.type_overrides: dict[str, str] = {}
        if existing_nfo is not None:
            self.files[NFO_PATH] = existing_nfo
            self.owners[NFO_PATH] = "stage9_media"
        self.calls: list[tuple[str, str, dict, bytes | None]] = []
        self.uploads: list[tuple[str, bytes]] = []
        self.upload_error_code: int | None = None
        self.upload_http_status: int | None = None
        self.upload_commit_before_http_error = False
        self.getinfo_error_path: str | None = None
        self.download_overrides: dict[str, bytes] = {}

    def _metadata(self, path: str) -> dict:
        if path in self.directories:
            isdir = True
            size = 0
        else:
            isdir = False
            size = len(self.files[path])
        owner = self.owners.get(path, "admin")
        return {
            "path": path,
            "name": PurePosixPath(path).name,
            "isdir": isdir,
            "additional": {
                "real_path": _api_real(path),
                "size": size,
                "owner": {"user": owner, "group": "users", "uid": 1026, "gid": 100},
                "time": {"mtime": 1700000000},
                "perm": {"posix": 644},
                "type": self.type_overrides.get(path, PurePosixPath(path).suffix.lstrip(".")),
                "mount_point_type": "",
            },
        }

    def _children(self, folder: str) -> list[dict]:
        result = []
        for path in sorted(self.directories | set(self.files)):
            if PurePosixPath(path).parent.as_posix() == folder:
                result.append(self._metadata(path))
        return result

    @staticmethod
    def _multipart(body: bytes, content_type: str) -> tuple[dict[str, str], str, bytes, list[str]]:
        marker = "boundary="
        assert marker in content_type
        boundary = content_type.split(marker, 1)[1]
        pieces = body.split(("--" + boundary).encode("ascii"))
        fields: dict[str, str] = {}
        filenames: list[str] = []
        file_name = ""
        file_data = b""
        for piece in pieces:
            piece = piece.removeprefix(b"\r\n")
            if piece.endswith(b"\r\n"):
                piece = piece[:-2]
            if piece == b"--":
                continue
            if not piece:
                continue
            headers, sep, value = piece.partition(b"\r\n\r\n")
            assert sep
            disposition = headers.split(b"\r\n", 1)[0].decode("ascii")
            if 'name="file"' in disposition:
                filename = disposition.split('filename="', 1)[1].split('"', 1)[0]
                file_name = filename
                file_data = value
                filenames.append("file")
            else:
                key = disposition.split('name="', 1)[1].split('"', 1)[0]
                fields[key] = value.rstrip(b"\r\n").decode("utf-8")
                filenames.append(key)
        return fields, file_name, file_data, filenames

    def __call__(self, method, target, headers, body, max_bytes):
        split = urlsplit(target)
        query = parse_qs(split.query, keep_blank_values=True)
        self.calls.append((method, target, dict(headers), body))
        assert "Cookie" not in headers

        if split.path == "/webapi/query.cgi":
            return _json_response(
                {
                    "success": True,
                    "data": {
                        "SYNO.API.Auth": {"path": "auth.cgi", "maxVersion": 7},
                        "SYNO.FileStation.List": {"path": "entry.cgi", "maxVersion": 2},
                        "SYNO.FileStation.Upload": {"path": "entry.cgi", "maxVersion": 3},
                        "SYNO.FileStation.Download": {"path": "entry.cgi", "maxVersion": 2},
                    },
                }
            )

        if method == "POST" and split.path == "/webapi/auth.cgi":
            form = parse_qs((body or b"").decode("utf-8"), keep_blank_values=True)
            assert form.get("account") == ["stage9_media"]
            assert form.get("format") == ["sid"]
            assert form.get("session") == ["FileStation"]
            assert form.get("enable_syno_token") == ["yes"]
            assert query == {}
            return _json_response({"success": True, "data": {"sid": "fake-sid", "synotoken": "fake-token"}})

        assert query.get("_sid") == ["fake-sid"]
        if "SynoToken" in query:
            assert query["SynoToken"] == ["fake-token"]
        api = query.get("api", [""])[0]
        api_method = query.get("method", [""])[0]

        if split.path == "/webapi/auth.cgi" and api_method == "logout":
            return _json_response({"success": True})

        if api == "SYNO.FileStation.List" and api_method == "getinfo":
            paths = json.loads(query["path"][0])
            assert isinstance(paths, list) and len(paths) == 1
            path = paths[0]
            assert path == API_LIBRARY_ROOT or path.startswith(API_LIBRARY_ROOT + "/")
            if path == self.getinfo_error_path:
                return _json_response({"success": False, "error": {"code": 407}})
            if path in self.directories or path in self.files:
                item = self._metadata(path)
            else:
                item = {"code": 408, "path": path}
            return _json_response({"success": True, "data": {"files": [item]}})

        if api == "SYNO.FileStation.List" and api_method == "list":
            folder = query["folder_path"][0]
            assert folder == API_LIBRARY_ROOT or folder.startswith(API_LIBRARY_ROOT + "/")
            offset = int(query["offset"][0])
            limit = int(query["limit"][0])
            all_items = self._children(folder)
            page = all_items[offset:offset + limit]
            return _json_response(
                {"success": True, "data": {"offset": offset, "total": len(all_items), "files": page}}
            )

        if api == "SYNO.FileStation.Download" and api_method == "download":
            path_values = json.loads(query["path"][0])
            mode = json.loads(query["mode"][0])
            assert len(path_values) == 1 and mode == "download"
            path = path_values[0]
            assert path.startswith(API_LIBRARY_ROOT + "/")
            if path not in self.files:
                return _json_response({"success": False, "error": {"code": 408}}, status=404)
            data = self.download_overrides.get(path, self.files[path])
            assert len(data) <= max_bytes
            return HTTPResult(200, "application/octet-stream", data, len(data))

        if method == "POST" and split.path == "/webapi/entry.cgi":
            assert api == "" and set(query) in ({"_sid", "SynoToken"}, {"_sid"})
            content_type = headers["Content-Type"]
            fields, filename, data, order = self._multipart(body or b"", content_type)
            assert order[-1:] == ["file"]
            assert "overwrite" not in fields
            assert fields.get("api") == "SYNO.FileStation.Upload"
            assert fields.get("method") == "upload"
            assert fields.get("create_parents") == "false"
            folder = fields.get("path", "")
            assert folder.startswith(API_LIBRARY_ROOT + "/")
            target_path = folder + "/" + filename
            if self.upload_http_status is not None:
                if self.upload_commit_before_http_error:
                    self.files[target_path] = data
                    self.owners[target_path] = "stage9_media"
                return HTTPResult(self.upload_http_status, "text/plain", b"", 0)
            if self.upload_error_code is not None:
                return _json_response({"success": False, "error": {"code": self.upload_error_code}})
            if target_path in self.files or target_path in self.directories:
                return _json_response({"success": False, "error": {"code": 414}})
            self.files[target_path] = data
            self.owners[target_path] = "stage9_media"
            self.uploads.append((target_path, data))
            return _json_response({"success": True})

        raise AssertionError("fake rejected an unlisted File Station API call")


def _bundle(*, poster=None):
    return MediaBundle(
        dvd_id="ABC-123",
        nfo_filename="ABC-123.nfo",
        nfo_data=NFO_BYTES,
        poster=poster,
        poster_status="PENDING" if poster is None else "COMPLETE",
        poster_error="COVER_URL_MISSING" if poster is None else None,
    )


def _adapter(root: Path, fake: FakeFileStation):
    password = root / "stage9-password"
    password.write_text("synthetic-password\n", encoding="utf-8")
    os.chmod(password, 0o600)
    return SynologyFileStationMediaAdapter(
        password_file=password,
        ca_file=root / "unused-ca.pem",
        transport=fake,
    )


def test_nfo_only_create_and_verified_stat(root: Path):
    fake = FakeFileStation()
    with _adapter(root, fake) as adapter:
        before_video = hashlib.sha256(fake.files[VIDEO_PATH]).hexdigest()
        stat_result = adapter.stat_library("ABC/ABC-123/ABC-123.mp4")
        assert stat_result == {
            "size": len(VIDEO_BYTES),
            "owner": "admin",
            "real_path": REAL_LIBRARY_ROOT + "/ABC/ABC-123/ABC-123.mp4",
            "file_type": ".mp4",
        }
        published = adapter.publish_bundle(
            video_relative="ABC/ABC-123/ABC-123.mp4",
            bundle=_bundle(),
        )
        assert published["status"] == "NFO_READY"
        assert published["nfo"]["status"] == "CREATED"
        assert published["poster"]["status"] == "NOT_ATTEMPTED"
        assert fake.files[NFO_PATH] == NFO_BYTES
        assert hashlib.sha256(fake.files[VIDEO_PATH]).hexdigest() == before_video
        assert fake.uploads == [(NFO_PATH, NFO_BYTES)]
    assert any("_sid=fake-sid" in target for method, target, _, _ in fake.calls if method == "POST")
    assert any("mode=%22download%22" in target for _, target, _, _ in fake.calls if "Download" in target)
    assert any("method=logout" in target for _, target, _, _ in fake.calls)


def test_identical_existing_reused_and_poster_create(root: Path):
    fake = FakeFileStation(existing_nfo=NFO_BYTES)
    poster = type("Poster", (), {"filename": "poster.jpg", "data": POSTER_BYTES})()
    with _adapter(root, fake) as adapter:
        result = adapter.publish_bundle(
            video_relative="ABC/ABC-123/ABC-123.mp4",
            bundle=_bundle(poster=poster),
        )
    poster_path = API_LIBRARY_ROOT + "/ABC/ABC-123/poster.jpg"
    assert result["nfo"]["status"] == "ALREADY_PRESENT"
    assert result["poster"]["status"] == "CREATED"
    assert fake.uploads == [(poster_path, POSTER_BYTES)]
    assert fake.files[NFO_PATH] == NFO_BYTES


def test_different_existing_nfo_is_collision(root: Path):
    fake = FakeFileStation(existing_nfo=b"different previous NFO")
    with _adapter(root, fake) as adapter:
        try:
            adapter.publish_bundle(
                video_relative="ABC/ABC-123/ABC-123.mp4",
                bundle=_bundle(),
            )
        except FileStationMediaError as exc:
            assert exc.code == "SIDECAR_CONTENT_CONFLICT"
        else:
            raise AssertionError("different existing NFO must be preserved as a conflict")
    assert not fake.uploads
    assert fake.files[NFO_PATH] == b"different previous NFO"


def test_api_error_and_invalid_path_fail_closed(root: Path):
    fake = FakeFileStation()
    fake.getinfo_error_path = VIDEO_PATH
    with _adapter(root, fake) as adapter:
        try:
            adapter.stat_library("ABC/ABC-123/ABC-123.mp4")
        except FileStationMediaError as exc:
            assert exc.code == "FILESTATION_API_ERROR_407"
        else:
            raise AssertionError("API permission error must not become missing")
    assert not fake.uploads

    fake = FakeFileStation()
    fake.type_overrides[VIDEO_PATH] = "nfo"
    with _adapter(root, fake) as adapter:
        try:
            adapter.stat_library("ABC/ABC-123/ABC-123.mp4")
        except FileStationMediaError as exc:
            assert exc.code == "FILE_TYPE_UNKNOWN_OR_MISMATCH"
        else:
            raise AssertionError("API file type mismatch must be rejected")
    assert not fake.uploads

    fake = FakeFileStation()
    with _adapter(root, fake) as adapter:
        try:
            adapter.stat_library("../video/OTHER-001/OTHER-001.mp4")
        except FileStationMediaError as exc:
            assert exc.code == "INVALID_MEDIA_PATH"
        else:
            raise AssertionError("path outside the fixed library must be rejected")
    for _method, target, _headers, _body in fake.calls:
        query = parse_qs(urlsplit(target).query)
        for key in ("path", "folder_path"):
            for value in query.get(key, []):
                try:
                    paths = json.loads(value) if key == "path" else [value]
                except json.JSONDecodeError:
                    continue
                assert all(path == API_LIBRARY_ROOT or path.startswith(API_LIBRARY_ROOT + "/") for path in paths)


def test_uncertain_upload_is_not_retried(root: Path):
    fake = FakeFileStation()
    fake.upload_http_status = 502
    fake.upload_commit_before_http_error = True
    with _adapter(root, fake) as adapter:
        try:
            adapter.publish_bundle(
                video_relative="ABC/ABC-123/ABC-123.mp4",
                bundle=_bundle(),
            )
        except FileStationMediaError as exc:
            assert exc.code == "UPLOAD_OUTCOME_UNKNOWN_HTTP_502"
        else:
            raise AssertionError("an uncertain HTTP result must fail closed")
    assert len([call for call in fake.calls if call[0] == "POST" and "entry.cgi" in call[1]]) == 1
    assert fake.files[NFO_PATH] == NFO_BYTES
    assert fake.uploads == []


def test_postupload_content_mismatch_fails(root: Path):
    fake = FakeFileStation()
    fake.download_overrides[NFO_PATH] = NFO_BYTES[:-1] + b"!"
    with _adapter(root, fake) as adapter:
        try:
            adapter.publish_bundle(
                video_relative="ABC/ABC-123/ABC-123.mp4",
                bundle=_bundle(),
            )
        except FileStationMediaError as exc:
            assert exc.code == "UPLOAD_POSTVERIFY_HASH_MISMATCH"
        else:
            raise AssertionError("a post-upload byte mismatch must fail")
    assert fake.uploads == [(NFO_PATH, NFO_BYTES)]
    assert fake.files[NFO_PATH] == NFO_BYTES


def main():
    with tempfile.TemporaryDirectory(prefix="stage9-filestation-smoke-") as temp:
        root = Path(temp)
        for name, test in [
            ("nfo-only-create-and-stat", test_nfo_only_create_and_verified_stat),
            ("identical-reuse-and-poster-create", test_identical_existing_reused_and_poster_create),
            ("different-sidecar-collision", test_different_existing_nfo_is_collision),
            ("api-error-and-path-boundary", test_api_error_and_invalid_path_fail_closed),
            ("uncertain-upload-no-retry", test_uncertain_upload_is_not_retried),
            ("postupload-content-mismatch", test_postupload_content_mismatch_fails),
        ]:
            case = root / name
            case.mkdir()
            test(case)
            print("PASS " + name)
    print("RESULT 6 PASS / 0 FAIL")


if __name__ == "__main__":
    main()
