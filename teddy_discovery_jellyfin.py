from __future__ import annotations

from pathlib import Path, PurePosixPath
import json
import urllib.error
import urllib.request


class JellyfinError(RuntimeError):
    pass


def jellyfin_media_path(
    video_relative: str,
) -> str:
    path = PurePosixPath(
        str(video_relative or "")
    )

    if (
        path.is_absolute()
        or not path.parts
        or ".." in path.parts
        or "\\" in str(video_relative)
    ):
        raise JellyfinError(
            "invalid video relative path"
        )

    return (
        PurePosixPath(
            "/media/adult"
        )
        / path
    ).as_posix()


class JellyfinClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key_path: str | Path,
        opener=urllib.request.urlopen,
        timeout: int = 10,
    ):
        self.base_url = str(
            base_url
        ).rstrip("/")

        if not (
            self.base_url.startswith(
                "http://"
            )
            or self.base_url.startswith(
                "https://"
            )
        ):
            raise JellyfinError(
                "invalid Jellyfin URL"
            )

        self.api_key_path = Path(
            api_key_path
        )

        self.opener = opener
        self.timeout = int(timeout)

    def _api_key(self) -> str:
        try:
            value = (
                self.api_key_path
                .read_text(
                    encoding="utf-8"
                )
                .strip()
            )
        except OSError as exc:
            raise JellyfinError(
                "Jellyfin API key unavailable"
            ) from exc

        if (
            not value
            or "\r" in value
            or "\n" in value
            or '"' in value
        ):
            raise JellyfinError(
                "invalid Jellyfin API key"
            )

        return value

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload=None,
    ):
        if not path.startswith("/"):
            raise JellyfinError(
                "invalid Jellyfin API path"
            )

        key = self._api_key()

        data = None

        headers = {
            "Accept": "application/json",
            "Authorization":
                'MediaBrowser '
                'Token="'
                + key
                + '"',
        }

        if payload is not None:
            data = json.dumps(
                payload,
                separators=(",", ":"),
            ).encode("utf-8")

            headers[
                "Content-Type"
            ] = "application/json"

        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=headers,
            method=method,
        )

        try:
            with self.opener(
                request,
                timeout=self.timeout,
            ) as response:
                status = getattr(
                    response,
                    "status",
                    response.getcode(),
                )

                body = response.read()

        except urllib.error.HTTPError as exc:
            raise JellyfinError(
                "Jellyfin HTTP "
                + str(exc.code)
            ) from exc

        except urllib.error.URLError as exc:
            raise JellyfinError(
                "Jellyfin connection failed"
            ) from exc

        if not (
            200 <= int(status) < 300
        ):
            raise JellyfinError(
                "Jellyfin HTTP "
                + str(status)
            )

        if not body:
            return None

        try:
            return json.loads(
                body.decode("utf-8")
            )
        except Exception as exc:
            raise JellyfinError(
                "invalid Jellyfin response"
            ) from exc

    def system_info(self):
        return self._request(
            "GET",
            "/System/Info",
        )

    def virtual_folders(self):
        value = self._request(
            "GET",
            "/Library/VirtualFolders",
        )

        if not isinstance(
            value,
            list,
        ):
            raise JellyfinError(
                "invalid virtual folders response"
            )

        return value

    def resolve_library(
        self,
        *,
        name: str,
        location: str,
    ):
        matches = []

        for item in self.virtual_folders():
            if not isinstance(
                item,
                dict,
            ):
                continue

            locations = item.get(
                "Locations"
            ) or []

            if (
                item.get("Name") == name
                and location in locations
            ):
                matches.append(
                    item
                )

        if len(matches) != 1:
            raise JellyfinError(
                "Jellyfin library match count != 1"
            )

        item_id = str(
            matches[0].get(
                "ItemId"
            )
            or ""
        ).strip()

        if not item_id:
            raise JellyfinError(
                "Jellyfin library ItemId missing"
            )

        return matches[0]

    def notify_created(
        self,
        media_path: str,
    ):
        path = PurePosixPath(
            str(media_path or "")
        )

        adult = PurePosixPath(
            "/media/adult"
        )

        if (
            not path.is_absolute()
            or path == adult
            or adult
            not in path.parents
            or ".." in path.parts
        ):
            raise JellyfinError(
                "media path outside Adult library"
            )

        self._request(
            "POST",
            "/Library/Media/Updated",
            payload={
                "Updates": [
                    {
                        "Path":
                            path.as_posix(),
                        "UpdateType":
                            "Created",
                    }
                ]
            },
        )

        return {
            "status":
                "JELLYFIN_NOTIFIED",
            "path":
                path.as_posix(),
        }
