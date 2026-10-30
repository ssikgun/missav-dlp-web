"""Narrow Synology File Station adapter for the dedicated Stage9 runner.

This adapter is intentionally limited to read-only media stat and create-only
NFO/poster publication below the configured Stage9 JAV library root. It does
not expose arbitrary File Station operations.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urlencode, urlsplit
import hashlib
import http.client
import json
import os
import re
import socket
import ssl
import stat
import uuid

from teddy_discovery_media_publish import (
    MediaMetadataPublishError,
    POSTER_FILENAMES,
    _safe_video_relative,
    canonical_nfo_filename,
)


NAS_CONNECT_IP = "192.168.1.201"
NAS_TLS_NAME = "synology"
NAS_TLS_PORT = 7001
NAS_ACCOUNT = "stage9_media"
PINNED_CA_SHA256 = "181608044438820f1c231f32ec122c2a598d06a058ca922d4136ca53c362d086"
REAL_LIBRARY_ROOT = "/volume1/video/video2/JAV"
API_LIBRARY_ROOT = "/video/video2/JAV"

CONNECT_TIMEOUT_SECONDS = 10
RESPONSE_TIMEOUT_SECONDS = 20
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_NFO_BYTES = 2 * 1024 * 1024
MAX_POSTER_BYTES = 25 * 1024 * 1024
MAX_API_REQUESTS = 64
LIST_PAGE_SIZE = 100
MAX_DIRECTORY_ENTRIES = 1000
MAX_DIRECTORY_PAGES = MAX_DIRECTORY_ENTRIES // LIST_PAGE_SIZE

API_NAMES = frozenset(
    {
        "SYNO.API.Auth",
        "SYNO.FileStation.List",
        "SYNO.FileStation.Upload",
        "SYNO.FileStation.Download",
    }
)
ADDITIONAL_FIELDS = [
    "real_path",
    "size",
    "owner",
    "time",
    "perm",
    "type",
    "mount_point_type",
]


class FileStationMediaError(MediaMetadataPublishError):
    """Sanitized error code safe to store in the media job record."""

    def __init__(self, code: str):
        self.code = str(code)
        super().__init__(self.code)


@dataclass(frozen=True)
class HTTPResult:
    status: int
    content_type: str
    body: bytes
    content_length: int | None = None


def _open_regular_file(path: str | Path) -> tuple[int, os.stat_result]:
    target = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(target, flags)
        info = os.fstat(fd)
    except OSError as exc:
        try:
            os.close(fd)
        except (UnboundLocalError, OSError):
            pass
        raise FileStationMediaError("CREDENTIAL_FILE_UNAVAILABLE") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        os.close(fd)
        raise FileStationMediaError("CREDENTIAL_FILE_INVALID")
    return fd, info


def _regular_file(path: str | Path, *, owner_required: bool = False) -> os.stat_result:
    fd, info = _open_regular_file(path)
    os.close(fd)
    if owner_required and info.st_uid != os.geteuid():
        raise FileStationMediaError("PASSWORD_FILE_OWNER_INVALID")
    return info


def validate_password_file(path: str | Path) -> None:
    info = _regular_file(path, owner_required=True)
    if stat.S_IMODE(info.st_mode) not in {0o400, 0o600}:
        raise FileStationMediaError("PASSWORD_FILE_MODE_INVALID")
    if info.st_size < 1 or info.st_size > 4096:
        raise FileStationMediaError("PASSWORD_FILE_SIZE_INVALID")


def _read_password(path: str | Path) -> str:
    fd, info = _open_regular_file(path)
    try:
        if info.st_uid != os.geteuid():
            raise FileStationMediaError("PASSWORD_FILE_OWNER_INVALID")
        if stat.S_IMODE(info.st_mode) not in {0o400, 0o600}:
            raise FileStationMediaError("PASSWORD_FILE_MODE_INVALID")
        if info.st_size < 1 or info.st_size > 4096:
            raise FileStationMediaError("PASSWORD_FILE_SIZE_INVALID")
        try:
            raw = os.read(fd, 4097)
        except OSError as exc:
            raise FileStationMediaError("PASSWORD_FILE_READ_FAILED") from exc
    finally:
        os.close(fd)
    if len(raw) > 4096:
        raise FileStationMediaError("PASSWORD_FILE_SIZE_INVALID")
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if not raw or b"\x00" in raw or b"\n" in raw or b"\r" in raw:
        raise FileStationMediaError("PASSWORD_FILE_FORMAT_INVALID")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FileStationMediaError("PASSWORD_FILE_FORMAT_INVALID") from exc


def validate_ca_file(path: str | Path) -> None:
    fd, info = _open_regular_file(path)
    try:
        if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise FileStationMediaError("CA_FILE_MODE_INVALID")
        if info.st_size < 1 or info.st_size > 65536:
            raise FileStationMediaError("CA_FILE_SIZE_INVALID")
    finally:
        os.close(fd)


def make_tls_context(ca_file: str | Path) -> ssl.SSLContext:
    fd, info = _open_regular_file(ca_file)
    try:
        if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise FileStationMediaError("CA_FILE_MODE_INVALID")
        raw = os.read(fd, 65537)
        if len(raw) > 65536:
            raise FileStationMediaError("CA_FILE_SIZE_INVALID")
        pem = raw.decode("ascii")
        der = ssl.PEM_cert_to_DER_cert(pem)
    except FileStationMediaError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise FileStationMediaError("CA_CERTIFICATE_INVALID") from exc
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    if hashlib.sha256(der).hexdigest().lower() != PINNED_CA_SHA256:
        raise FileStationMediaError("CA_FINGERPRINT_MISMATCH")
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=pem)
    except (OSError, ssl.SSLError) as exc:
        raise FileStationMediaError("TLS_CONTEXT_UNAVAILABLE") from exc
    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
        raise FileStationMediaError("TLS_VERIFICATION_DISABLED")
    return context


class _FixedIPHTTPSConnection(http.client.HTTPSConnection):
    """Connect to the pinned NAS IP while verifying/SNI using its cert name."""

    def __init__(self, context: ssl.SSLContext):
        super().__init__(NAS_TLS_NAME, NAS_TLS_PORT, timeout=CONNECT_TIMEOUT_SECONDS, context=context)

    def connect(self) -> None:
        raw = socket.create_connection((NAS_CONNECT_IP, NAS_TLS_PORT), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=NAS_TLS_NAME)
        except Exception:
            raw.close()
            raise


def _safe_api_relative(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise FileStationMediaError("INVALID_MEDIA_PATH")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise FileStationMediaError("INVALID_MEDIA_PATH")
    return path


def _video_paths(relative_path: str) -> tuple[str, str, str]:
    relative = _safe_api_relative(relative_path)
    dvd_id = relative.parent.name.upper()
    try:
        canonical = _safe_video_relative(relative.as_posix(), dvd_id)
    except (MediaMetadataPublishError, TypeError, ValueError) as exc:
        raise FileStationMediaError("VIDEO_IDENTITY_INVALID") from exc
    api_path = API_LIBRARY_ROOT + "/" + canonical
    real_path = REAL_LIBRARY_ROOT + "/" + canonical
    if not api_path.startswith(API_LIBRARY_ROOT + "/"):
        raise FileStationMediaError("API_PATH_OUTSIDE_LIBRARY")
    return canonical, api_path, real_path


def _api_to_real(api_path: str) -> str:
    if api_path == API_LIBRARY_ROOT:
        return REAL_LIBRARY_ROOT
    if not api_path.startswith(API_LIBRARY_ROOT + "/"):
        raise FileStationMediaError("API_PATH_OUTSIDE_LIBRARY")
    suffix = api_path[len(API_LIBRARY_ROOT):]
    if ".." in PurePosixPath(suffix).parts or "\\" in suffix:
        raise FileStationMediaError("API_PATH_OUTSIDE_LIBRARY")
    return REAL_LIBRARY_ROOT + suffix


def _safe_code(value: object) -> str:
    if type(value) is int and 0 <= value <= 999999:
        return str(value)
    return "UNKNOWN"


def _owner(item: dict) -> dict:
    additional = item.get("additional")
    owner = additional.get("owner") if isinstance(additional, dict) else None
    if not isinstance(owner, dict):
        raise FileStationMediaError("FILE_OWNER_UNKNOWN")
    user = owner.get("user")
    group = owner.get("group")
    if not isinstance(user, str) or not user or not isinstance(group, str) or not group:
        raise FileStationMediaError("FILE_OWNER_UNKNOWN")
    return owner


class SynologyFileStationMediaAdapter:
    """Implements the Stage9 pipeline's stat_library/publish_bundle interface."""

    def __init__(
        self,
        *,
        password_file: str | Path,
        ca_file: str | Path,
        transport=None,
        tls_context: ssl.SSLContext | None = None,
        max_requests: int = MAX_API_REQUESTS,
    ):
        self.password_file = Path(password_file)
        self.ca_file = Path(ca_file)
        self.transport = transport
        self.tls_context = tls_context
        self.max_requests = int(max_requests)
        if not 1 <= self.max_requests <= MAX_API_REQUESTS:
            raise FileStationMediaError("REQUEST_BUDGET_INVALID")
        self.request_count = 0
        self.apis: dict[str, dict] = {}
        self.sid: str | None = None
        self.syno_token: str | None = None
        self._login_post_active = False
        self._upload_post_active = False
        self._closed = False

    def __enter__(self):
        try:
            validate_password_file(self.password_file)
            if self.transport is None and self.tls_context is None:
                self.tls_context = make_tls_context(self.ca_file)
            self._discover()
            self._login()
            self._verify_library_root()
            return self
        except Exception:
            self.close()
            raise

    def __exit__(self, _kind, _value, _traceback):
        self.close()

    def _request(self, method: str, target: str, *, body: bytes | None = None,
                 content_type: str | None = None, max_bytes: int = MAX_JSON_BYTES) -> HTTPResult:
        method = str(method).upper()
        split = urlsplit(target)
        if (
            method not in {"GET", "POST"}
            or split.scheme
            or split.netloc
            or split.fragment
            or not split.path.startswith("/webapi/")
            or "\r" in target
            or "\n" in target
        ):
            raise FileStationMediaError("HTTP_REQUEST_OUTSIDE_ALLOWLIST")
        if method == "POST":
            allowed_auth = (
                self._login_post_active
                and split.path == self._api_endpoint("SYNO.API.Auth")
                and content_type == "application/x-www-form-urlencoded"
            )
            query = parse_qs(split.query, keep_blank_values=True)
            upload_auth = self.sid is not None and query.get("_sid") == [self.sid]
            if self.syno_token:
                upload_auth = upload_auth and query.get("SynoToken") == [self.syno_token]
            expected_auth_keys = {"_sid", "SynoToken"} if self.syno_token else {"_sid"}
            allowed_upload = (
                self._upload_post_active
                and split.path == self._api_endpoint("SYNO.FileStation.Upload")
                and upload_auth
                and set(query) == expected_auth_keys
                and content_type is not None
                and content_type.startswith("multipart/form-data; boundary=")
            )
            if not (allowed_auth or allowed_upload):
                raise FileStationMediaError("HTTP_POST_OUTSIDE_ALLOWLIST")
        elif body is not None:
            raise FileStationMediaError("HTTP_GET_BODY_PROHIBITED")
        else:
            values = parse_qs(split.query, keep_blank_values=True)
            if split.path == "/webapi/query.cgi":
                if (
                    values.get("api") != ["SYNO.API.Info"]
                    or values.get("version") != ["1"]
                    or values.get("method") != ["query"]
                    or not values.get("query")
                    or set(values) != {"api", "version", "method", "query"}
                ):
                    raise FileStationMediaError("API_DISCOVERY_REQUEST_INVALID")
            else:
                api = values.get("api", [""])[0]
                api_method = values.get("method", [""])[0]
                permitted = (
                    (api == "SYNO.API.Auth" and api_method == "logout")
                    or (api == "SYNO.FileStation.List" and api_method in {"getinfo", "list"})
                    or (api == "SYNO.FileStation.Download" and api_method == "download")
                )
                if not permitted or api not in API_NAMES:
                    raise FileStationMediaError("HTTP_GET_OUTSIDE_ALLOWLIST")
                if values.get("_sid") != [self.sid] or not self.sid:
                    raise FileStationMediaError("FILESTATION_SESSION_MISSING")
                if self.syno_token:
                    if values.get("SynoToken") != [self.syno_token]:
                        raise FileStationMediaError("FILESTATION_TOKEN_MISSING")
                elif "SynoToken" in values:
                    raise FileStationMediaError("FILESTATION_TOKEN_UNEXPECTED")
                if api == "SYNO.FileStation.List" and api_method == "getinfo":
                    try:
                        request_paths = json.loads(values.get("path", [""])[0])
                    except (TypeError, json.JSONDecodeError) as exc:
                        raise FileStationMediaError("GETINFO_PATH_INVALID") from exc
                    if not isinstance(request_paths, list) or not request_paths:
                        raise FileStationMediaError("GETINFO_PATH_INVALID")
                    for request_path in request_paths:
                        if not isinstance(request_path, str):
                            raise FileStationMediaError("GETINFO_PATH_INVALID")
                        _api_to_real(request_path)
                elif api == "SYNO.FileStation.List" and api_method == "list":
                    folder_path = values.get("folder_path", [""])[0]
                    _api_to_real(folder_path)
                elif api == "SYNO.FileStation.Download":
                    try:
                        download_paths = json.loads(values.get("path", [""])[0])
                        mode = json.loads(values.get("mode", [""])[0])
                    except (TypeError, json.JSONDecodeError) as exc:
                        raise FileStationMediaError("DOWNLOAD_REQUEST_INVALID") from exc
                    if not isinstance(download_paths, list) or len(download_paths) != 1 or mode != "download":
                        raise FileStationMediaError("DOWNLOAD_REQUEST_INVALID")
                    _api_to_real(download_paths[0])
                endpoint_name = api
                if split.path != self._api_endpoint(endpoint_name):
                    raise FileStationMediaError("API_ENDPOINT_MISMATCH")
        self.request_count += 1
        if self.request_count > self.max_requests:
            raise FileStationMediaError("FILESTATION_REQUEST_BUDGET_EXHAUSTED")
        headers = {"Connection": "close", "Accept": "application/json, application/octet-stream"}
        if content_type:
            headers["Content-Type"] = content_type
        try:
            if self.transport is not None:
                result = self.transport(method, target, headers, body, max_bytes)
                if not isinstance(result, HTTPResult):
                    raise FileStationMediaError("HTTP_TRANSPORT_RESPONSE_INVALID")
                response = result
            else:
                if self.tls_context is None:
                    raise FileStationMediaError("TLS_CONTEXT_UNAVAILABLE")
                connection = _FixedIPHTTPSConnection(self.tls_context)
                try:
                    connection.request(method, target, body=body, headers=headers)
                    incoming = connection.getresponse()
                    payload = incoming.read(max_bytes + 1)
                    if len(payload) > max_bytes:
                        raise FileStationMediaError("HTTP_RESPONSE_TOO_LARGE")
                    content_length_raw = incoming.getheader("Content-Length")
                    content_length = (
                        int(content_length_raw)
                        if content_length_raw is not None and content_length_raw.isdigit()
                        else None
                    )
                    response = HTTPResult(
                        incoming.status,
                        incoming.getheader("Content-Type", ""),
                        payload,
                        content_length,
                    )
                finally:
                    connection.close()
        except FileStationMediaError:
            raise
        except Exception as exc:
            code = "UPLOAD_OUTCOME_UNKNOWN" if method == "POST" and self._upload_post_active else "HTTP_REQUEST_FAILED"
            raise FileStationMediaError(code) from exc
        if len(response.body) > max_bytes:
            raise FileStationMediaError("HTTP_RESPONSE_TOO_LARGE")
        if response.content_length is not None and response.content_length != len(response.body):
            raise FileStationMediaError("HTTP_RESPONSE_LENGTH_MISMATCH")
        return response

    def _discover(self) -> None:
        target = "/webapi/query.cgi?" + urlencode(
            {
                "api": "SYNO.API.Info",
                "version": "1",
                "method": "query",
                "query": ",".join(sorted(API_NAMES)),
            }
        )
        response = self._request("GET", target)
        if response.status != 200:
            raise FileStationMediaError("API_DISCOVERY_HTTP_ERROR")
        result = self._json_body(response, "API_DISCOVERY_INVALID_RESPONSE")
        data = result.get("data")
        if result.get("success") is not True or not isinstance(data, dict):
            raise FileStationMediaError("API_DISCOVERY_FAILED")
        if not API_NAMES.issubset(data):
            raise FileStationMediaError("REQUIRED_FILESTATION_API_MISSING")
        self.apis = data
        for name in API_NAMES:
            self._api_endpoint(name)

    def _api_endpoint(self, name: str) -> str:
        if name not in API_NAMES:
            raise FileStationMediaError("API_NAME_OUTSIDE_ALLOWLIST")
        info = self.apis.get(name)
        if not isinstance(info, dict):
            raise FileStationMediaError("API_INFO_INVALID")
        path = info.get("path")
        version = info.get("maxVersion")
        if (
            not isinstance(path, str)
            or not path
            or path.startswith("/")
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or re.fullmatch(r"[A-Za-z0-9._/-]+", path) is None
            or type(version) is not int
            or version < 1
        ):
            raise FileStationMediaError("API_INFO_INVALID")
        return "/webapi/" + path

    def _version(self, name: str) -> int:
        self._api_endpoint(name)
        return int(self.apis[name]["maxVersion"])

    @staticmethod
    def _json_body(response: HTTPResult, error_code: str) -> dict:
        try:
            value = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FileStationMediaError(error_code) from exc
        if not isinstance(value, dict):
            raise FileStationMediaError(error_code)
        return value

    def _login(self) -> None:
        password = _read_password(self.password_file)
        payload = urlencode(
            {
                "api": "SYNO.API.Auth",
                "version": str(self._version("SYNO.API.Auth")),
                "method": "login",
                "account": NAS_ACCOUNT,
                "passwd": password,
                "session": "FileStation",
                "format": "sid",
                "enable_syno_token": "yes",
            }
        ).encode("utf-8")
        password = ""
        self._login_post_active = True
        try:
            response = self._request(
                "POST",
                self._api_endpoint("SYNO.API.Auth"),
                body=payload,
                content_type="application/x-www-form-urlencoded",
            )
        finally:
            self._login_post_active = False
            payload = b""
        if response.status != 200:
            raise FileStationMediaError("FILESTATION_LOGIN_HTTP_ERROR")
        value = self._json_body(response, "FILESTATION_LOGIN_RESPONSE_INVALID")
        if value.get("success") is not True:
            error = value.get("error")
            code = _safe_code(error.get("code")) if isinstance(error, dict) else "UNKNOWN"
            raise FileStationMediaError("FILESTATION_LOGIN_API_ERROR_" + code)
        data = value.get("data")
        sid = data.get("sid") if isinstance(data, dict) else None
        if not isinstance(sid, str) or not sid or len(sid) > 4096:
            raise FileStationMediaError("FILESTATION_SID_MISSING")
        self.sid = sid
        token = data.get("synotoken") if isinstance(data, dict) else None
        if token is not None:
            if not isinstance(token, str) or not token or len(token) > 4096:
                raise FileStationMediaError("FILESTATION_TOKEN_INVALID")
            self.syno_token = token

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        sid = self.sid
        if sid is None:
            return
        try:
            params = {
                "api": "SYNO.API.Auth",
                "version": str(self._version("SYNO.API.Auth")),
                "method": "logout",
                "session": "FileStation",
                "_sid": sid,
            }
            if self.syno_token:
                params["SynoToken"] = self.syno_token
            self._request(
                "GET",
                self._api_endpoint("SYNO.API.Auth") + "?" + urlencode(params),
            )
        except Exception:
            pass
        finally:
            self.sid = None
            self.syno_token = None

    def _session_query(self, values: dict) -> str:
        if not self.sid:
            raise FileStationMediaError("FILESTATION_SESSION_MISSING")
        result = dict(values)
        result.update({"_sid": self.sid})
        if self.syno_token:
            result["SynoToken"] = self.syno_token
        return urlencode(result)

    def _api_json(self, name: str, method: str, params: dict | None = None) -> dict:
        if name == "SYNO.API.Auth":
            allowed = {"logout"}
        elif name == "SYNO.FileStation.List":
            allowed = {"getinfo", "list"}
        else:
            allowed = set()
        if method not in allowed:
            raise FileStationMediaError("API_METHOD_OUTSIDE_ALLOWLIST")
        values = {
            "api": name,
            "version": str(self._version(name)),
            "method": method,
        }
        if params:
            values.update(params)
        if name == "SYNO.FileStation.List":
            if method == "getinfo":
                try:
                    paths = json.loads(values.get("path", ""))
                except (TypeError, json.JSONDecodeError) as exc:
                    raise FileStationMediaError("GETINFO_PATH_INVALID") from exc
                if not isinstance(paths, list) or not paths or any(not isinstance(path, str) for path in paths):
                    raise FileStationMediaError("GETINFO_PATH_INVALID")
                for path in paths:
                    _api_to_real(path)
            elif method == "list":
                folder = values.get("folder_path")
                if not isinstance(folder, str):
                    raise FileStationMediaError("PARENT_LIST_PATH_INVALID")
                _api_to_real(folder)
        target = self._api_endpoint(name) + "?" + self._session_query(values)
        response = self._request("GET", target)
        if response.status != 200:
            raise FileStationMediaError("FILESTATION_API_HTTP_ERROR")
        result = self._json_body(response, "FILESTATION_API_INVALID_JSON")
        if result.get("success") is not True:
            error = result.get("error")
            code = _safe_code(error.get("code")) if isinstance(error, dict) else "UNKNOWN"
            raise FileStationMediaError("FILESTATION_API_ERROR_" + code)
        if result.get("errors") not in (None, [], {}):
            raise FileStationMediaError("FILESTATION_API_PARTIAL_RESPONSE")
        return result

    def _api_getinfo(self, api_path: str) -> dict | None:
        _api_to_real(api_path)
        result = self._api_json(
            "SYNO.FileStation.List",
            "getinfo",
            {
                "path": json.dumps([api_path], separators=(",", ":")),
                "additional": json.dumps(ADDITIONAL_FIELDS, separators=(",", ":")),
            },
        )
        data = result.get("data")
        if not isinstance(data, dict) or data.get("errors") not in (None, [], {}):
            raise FileStationMediaError("GETINFO_RESPONSE_INCOMPLETE")
        files = data.get("files")
        if not isinstance(files, list) or len(files) != 1:
            raise FileStationMediaError("GETINFO_RESPONSE_INCOMPLETE")
        item = files[0]
        if not isinstance(item, dict) or item.get("path") != api_path:
            raise FileStationMediaError("GETINFO_PATH_MISMATCH")
        if "code" in item:
            if type(item.get("code")) is int and item.get("code") == 408 and set(item) == {"code", "path"}:
                return None
            code = _safe_code(item.get("code"))
            raise FileStationMediaError("GETINFO_ITEM_ERROR_" + code)
        if "error" in item:
            raise FileStationMediaError("GETINFO_ITEM_ERROR_UNKNOWN")
        return self._validate_object(item, api_path, expected_isdir=None)

    def _validate_object(self, item: dict, api_path: str, *, expected_isdir: bool | None) -> dict:
        expected_real = _api_to_real(api_path)
        isdir = item.get("isdir")
        if type(isdir) is not bool or (expected_isdir is not None and isdir is not expected_isdir):
            raise FileStationMediaError("FILE_TYPE_UNKNOWN_OR_UNEXPECTED")
        if item.get("path") != api_path or item.get("name") != PurePosixPath(api_path).name:
            raise FileStationMediaError("FILE_IDENTITY_MISMATCH")
        additional = item.get("additional")
        if not isinstance(additional, dict) or additional.get("real_path") != expected_real:
            raise FileStationMediaError("REAL_PATH_MISMATCH")
        if additional.get("mount_point_type") not in (None, ""):
            raise FileStationMediaError("MOUNT_POINT_PROHIBITED")
        owner = _owner(item)
        if not isdir:
            size = additional.get("size")
            if type(size) is not int or size < 0:
                raise FileStationMediaError("FILE_SIZE_UNKNOWN")
            expected_type = PurePosixPath(api_path).suffix.lstrip(".").lower()
            actual_type = additional.get("type")
            if (
                not expected_type
                or not isinstance(actual_type, str)
                or actual_type.lower() != expected_type
            ):
                raise FileStationMediaError("FILE_TYPE_UNKNOWN_OR_MISMATCH")
        return {
            "path": api_path,
            "real_path": expected_real,
            "name": item["name"],
            "isdir": isdir,
            "size": additional.get("size"),
            "owner": owner,
            "additional": additional,
            "raw": item,
        }

    def _parent_listing(self, api_parent: str) -> list[dict]:
        _api_to_real(api_parent)
        parent = self._api_getinfo(api_parent)
        if parent is None or parent["isdir"] is not True:
            raise FileStationMediaError("PARENT_DIRECTORY_UNAVAILABLE")
        offset = 0
        expected_total = None
        found: list[dict] = []
        seen: set[str] = set()
        for _ in range(MAX_DIRECTORY_PAGES):
            result = self._api_json(
                "SYNO.FileStation.List",
                "list",
                {
                    "folder_path": api_parent,
                    "offset": str(offset),
                    "limit": str(LIST_PAGE_SIZE),
                    "additional": json.dumps(ADDITIONAL_FIELDS, separators=(",", ":")),
                },
            )
            data = result.get("data")
            if not isinstance(data, dict) or data.get("errors") not in (None, [], {}):
                raise FileStationMediaError("PARENT_LIST_INCOMPLETE")
            page = data.get("files")
            total = data.get("total")
            returned_offset = data.get("offset")
            if (
                not isinstance(page, list)
                or type(total) is not int
                or total < 0
                or total > MAX_DIRECTORY_ENTRIES
                or type(returned_offset) is not int
                or returned_offset != offset
            ):
                raise FileStationMediaError("PARENT_LIST_INCOMPLETE")
            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                raise FileStationMediaError("PARENT_LIST_CHANGED")
            expected_count = min(LIST_PAGE_SIZE, max(0, total - offset))
            if len(page) != expected_count:
                raise FileStationMediaError("PARENT_LIST_INCOMPLETE")
            for raw_item in page:
                if not isinstance(raw_item, dict):
                    raise FileStationMediaError("PARENT_LIST_OBJECT_INVALID")
                name = raw_item.get("name")
                item_path = raw_item.get("path")
                if (
                    not isinstance(name, str)
                    or not name
                    or name in {".", ".."}
                    or "/" in name
                    or "\\" in name
                    or item_path != api_parent + "/" + name
                    or item_path in seen
                ):
                    raise FileStationMediaError("PARENT_LIST_IDENTITY_INVALID")
                seen.add(item_path)
                found.append(self._validate_object(raw_item, item_path, expected_isdir=None))
            offset += len(page)
            if offset >= total:
                return found
        raise FileStationMediaError("PARENT_LIST_PAGE_LIMIT_EXCEEDED")

    def _resolve(self, api_path: str) -> dict | None:
        _api_to_real(api_path)
        info = self._api_getinfo(api_path)
        parent_path = PurePosixPath(api_path).parent.as_posix()
        listing = self._parent_listing(parent_path)
        target_name = PurePosixPath(api_path).name
        listed = [item for item in listing if item["name"] == target_name or item["path"] == api_path]
        if len(listed) > 1:
            raise FileStationMediaError("PARENT_LIST_DUPLICATE_TARGET")
        if (info is None) != (not listed):
            raise FileStationMediaError("GETINFO_LIST_DISAGREEMENT")
        if info is None:
            return None
        if not listed:
            raise FileStationMediaError("GETINFO_LIST_DISAGREEMENT")
        listed_item = listed[0]
        if (
            info["path"] != listed_item["path"]
            or info["real_path"] != listed_item["real_path"]
            or info["isdir"] != listed_item["isdir"]
            or info["size"] != listed_item["size"]
            or info["owner"].get("user") != listed_item["owner"].get("user")
            or info["owner"].get("group") != listed_item["owner"].get("group")
            or info["additional"].get("type") != listed_item["additional"].get("type")
        ):
            raise FileStationMediaError("GETINFO_LIST_METADATA_DISAGREEMENT")
        return info

    def _verify_library_root(self) -> None:
        root = self._api_getinfo(API_LIBRARY_ROOT)
        if root is None or root["isdir"] is not True or root["real_path"] != REAL_LIBRARY_ROOT:
            raise FileStationMediaError("LIBRARY_ROOT_MAPPING_MISMATCH")

    def stat_library(self, relative_path: str) -> dict | None:
        _, api_path, _ = _video_paths(relative_path)
        item = self._resolve(api_path)
        if item is None:
            return None
        if item["isdir"] is not False:
            raise FileStationMediaError("VIDEO_NOT_REGULAR_FILE")
        expected_ext = PurePosixPath(relative_path).suffix.lower()
        if expected_ext not in {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v"}:
            raise FileStationMediaError("VIDEO_TYPE_INVALID")
        # File Station exposes isdir=false, extension/type, size, owner and the
        # resolved path; it does not expose POSIX S_IFREG. Keep the source size
        # check in the existing pipeline and fail if any of this API metadata
        # is missing or inconsistent.
        return {
            "size": int(item["size"]),
            "owner": item["owner"].get("user"),
            "group": item["owner"].get("group"),
            "real_path": item["real_path"],
            "file_type": expected_ext,
        }

    def _download(self, api_path: str, max_bytes: int) -> bytes:
        _api_to_real(api_path)
        values = {
            "api": "SYNO.FileStation.Download",
            "version": str(self._version("SYNO.FileStation.Download")),
            "method": "download",
            "path": json.dumps([api_path], separators=(",", ":")),
            "mode": json.dumps("download"),
        }
        target = self._api_endpoint("SYNO.FileStation.Download") + "?" + self._session_query(values)
        response = self._request("GET", target, max_bytes=max_bytes)
        if response.status != 200:
            raise FileStationMediaError("DOWNLOAD_HTTP_ERROR_" + str(response.status))
        if "json" in response.content_type.lower() or response.body.lstrip().startswith(b"{"):
            value = self._json_body(response, "DOWNLOAD_RESPONSE_INVALID")
            if value.get("success") is False:
                error = value.get("error")
                code = _safe_code(error.get("code")) if isinstance(error, dict) else "UNKNOWN"
                raise FileStationMediaError("DOWNLOAD_API_ERROR_" + code)
            raise FileStationMediaError("DOWNLOAD_RESPONSE_NOT_BINARY")
        return response.body

    def _publish_one(self, folder: str, filename: str, payload: bytes, expected_sha: str,
                     *, expected_max: int) -> dict:
        if (
            not isinstance(filename, str)
            or not filename
            or PurePosixPath(filename).name != filename
            or filename in {".", ".."}
            or filename.startswith(".")
            or "/" in filename
            or "\\" in filename
            or not isinstance(payload, bytes)
            or not payload
            or len(payload) > expected_max
            or hashlib.sha256(payload).hexdigest() != expected_sha
        ):
            raise FileStationMediaError("SIDECAR_INPUT_INVALID")
        folder_path = PurePosixPath(folder)
        if folder_path.is_absolute() or ".." in folder_path.parts:
            raise FileStationMediaError("API_PATH_OUTSIDE_LIBRARY")
        api_folder = API_LIBRARY_ROOT + "/" + folder_path.as_posix()
        _api_to_real(api_folder)
        parent = self._api_getinfo(api_folder)
        if parent is None or parent["isdir"] is not True:
            raise FileStationMediaError("SIDECAR_PARENT_INVALID")
        api_path = api_folder + "/" + filename
        _api_to_real(api_path)

        existing = self._resolve(api_path)
        if existing is not None:
            if existing["isdir"] is not False:
                raise FileStationMediaError("SIDECAR_TYPE_CONFLICT")
            current = self._download(api_path, expected_max)
            if len(current) == len(payload) and hashlib.sha256(current).hexdigest() == expected_sha:
                return {"status": "ALREADY_PRESENT", "size": len(current), "sha256": expected_sha}
            raise FileStationMediaError("SIDECAR_CONTENT_CONFLICT")

        # Recheck immediately before the create-only request. The server-side
        # collision rule is still authoritative for a concurrent creator.
        if self._resolve(api_path) is not None:
            current = self._download(api_path, expected_max)
            if len(current) == len(payload) and hashlib.sha256(current).hexdigest() == expected_sha:
                return {"status": "ALREADY_PRESENT", "size": len(current), "sha256": expected_sha}
            raise FileStationMediaError("SIDECAR_CONTENT_CONFLICT")

        response_value = self._upload_create_only(api_folder, filename, payload)
        if response_value.get("success") is not True:
            error = response_value.get("error")
            code = _safe_code(error.get("code")) if isinstance(error, dict) else "UNKNOWN"
            if code in {"414", "1805"}:
                raise FileStationMediaError("SIDECAR_CREATED_CONCURRENTLY")
            raise FileStationMediaError("UPLOAD_API_ERROR_" + code)

        final = self._resolve(api_path)
        if final is None or final["isdir"] is not False:
            raise FileStationMediaError("UPLOAD_POSTVERIFY_MISSING")
        if final["owner"].get("user") != NAS_ACCOUNT:
            raise FileStationMediaError("UPLOAD_POSTVERIFY_OWNER_MISMATCH")
        content = self._download(api_path, expected_max)
        if len(content) != len(payload) or hashlib.sha256(content).hexdigest() != expected_sha:
            raise FileStationMediaError("UPLOAD_POSTVERIFY_HASH_MISMATCH")
        return {"status": "CREATED", "size": len(content), "sha256": expected_sha}

    def _upload_create_only(self, folder: str, filename: str, payload: bytes) -> dict:
        api_name = "SYNO.FileStation.Upload"
        endpoint = self._api_endpoint(api_name)
        boundary = "----Stage9FileStation" + uuid.uuid4().hex
        values = (
            ("api", api_name),
            ("version", str(self._version(api_name))),
            ("method", "upload"),
            ("path", folder),
            ("create_parents", "false"),
        )
        chunks: list[bytes] = []
        for key, value in values:
            chunks.extend(
                [
                    ("--" + boundary + "\r\n").encode("ascii"),
                    (f'Content-Disposition: form-data; name="{key}"\r\n\r\n').encode("ascii"),
                    value.encode("utf-8"),
                    b"\r\n",
                ]
            )
        # Synology requires the binary file part to be the final multipart part.
        chunks.extend(
            [
                ("--" + boundary + "\r\n").encode("ascii"),
                (f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n').encode("ascii"),
                b"Content-Type: application/octet-stream\r\n\r\n",
                payload,
                b"\r\n",
                ("--" + boundary + "--\r\n").encode("ascii"),
            ]
        )
        auth = {"_sid": self.sid}
        if self.syno_token:
            auth["SynoToken"] = self.syno_token
        target = endpoint + "?" + urlencode(auth)
        self._upload_post_active = True
        try:
            response = self._request(
                "POST",
                target,
                body=b"".join(chunks),
                content_type="multipart/form-data; boundary=" + boundary,
                max_bytes=MAX_JSON_BYTES,
            )
        finally:
            self._upload_post_active = False
        if response.status != 200:
            raise FileStationMediaError("UPLOAD_OUTCOME_UNKNOWN_HTTP_" + str(response.status))
        result = self._json_body(response, "UPLOAD_OUTCOME_UNKNOWN_RESPONSE")
        return result

    def publish_bundle(self, *, video_relative: str, bundle) -> dict:
        canonical, video_api_path, _ = _video_paths(video_relative)
        if bundle.dvd_id is None or str(bundle.dvd_id).strip().upper() != PurePosixPath(canonical).parent.name.upper():
            raise FileStationMediaError("BUNDLE_DVD_ID_MISMATCH")
        if bundle.nfo_filename != canonical_nfo_filename(bundle.dvd_id):
            raise FileStationMediaError("NFO_FILENAME_INVALID")
        nfo_data = bytes(bundle.nfo_data)
        if not nfo_data or len(nfo_data) > MAX_NFO_BYTES:
            raise FileStationMediaError("NFO_SIZE_INVALID")
        video = self._resolve(video_api_path)
        if video is None or video["isdir"] is not False:
            raise FileStationMediaError("VIDEO_UNAVAILABLE_FOR_PUBLICATION")
        api_folder = PurePosixPath(video_api_path).parent.as_posix()
        relative_folder = PurePosixPath(api_folder).relative_to(API_LIBRARY_ROOT).as_posix()
        nfo_sha = hashlib.sha256(nfo_data).hexdigest()
        nfo = self._publish_one(
            relative_folder,
            bundle.nfo_filename,
            nfo_data,
            nfo_sha,
            expected_max=MAX_NFO_BYTES,
        )

        if bundle.poster is None:
            poster = {
                "status": "NOT_ATTEMPTED",
                "error": bundle.poster_error,
            }
            result_status = "NFO_READY"
        else:
            if bundle.poster.filename not in POSTER_FILENAMES:
                raise FileStationMediaError("POSTER_FILENAME_INVALID")
            poster_data = bytes(bundle.poster.data)
            if not poster_data or len(poster_data) > MAX_POSTER_BYTES:
                raise FileStationMediaError("POSTER_SIZE_INVALID")
            poster_sha = hashlib.sha256(poster_data).hexdigest()
            try:
                poster = self._publish_one(
                    relative_folder,
                    bundle.poster.filename,
                    poster_data,
                    poster_sha,
                    expected_max=MAX_POSTER_BYTES,
                )
                result_status = "METADATA_READY"
            except FileStationMediaError as exc:
                poster = {"status": "ATTENTION", "error": exc.code}
                result_status = "METADATA_PARTIAL"
        return {"status": result_status, "nfo": nfo, "poster": poster}


__all__ = [
    "API_LIBRARY_ROOT",
    "NAS_ACCOUNT",
    "PINNED_CA_SHA256",
    "REAL_LIBRARY_ROOT",
    "FileStationMediaError",
    "HTTPResult",
    "SynologyFileStationMediaAdapter",
    "make_tls_context",
    "validate_ca_file",
    "validate_password_file",
]
