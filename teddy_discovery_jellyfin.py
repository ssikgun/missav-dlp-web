from __future__ import annotations

from pathlib import Path, PurePosixPath
import json
import urllib.error
import urllib.parse
import urllib.request


class JellyfinError(RuntimeError):
    pass


class JellyfinResponseError(JellyfinError):
    """Jellyfin returned a successful but malformed response."""


class JellyfinPathError(JellyfinError):
    """A path is outside the canonical Adult media tree."""


def validate_adult_media_path(media_path: str) -> PurePosixPath:
    raw = str(media_path or "")
    path = PurePosixPath(raw)
    if (
        not path.is_absolute()
        or path.as_posix() != raw
        or path.parts[:3] != ("/", "media", "adult")
        or len(path.parts) != 6
        or any(part in {"", ".", ".."} for part in path.parts[1:])
        or "\\" in raw
    ):
        raise JellyfinPathError("invalid canonical Adult media path")
    return path


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
            raise JellyfinResponseError(
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
            raise JellyfinResponseError(
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
                raise JellyfinResponseError(
                    "invalid virtual folder entry"
                )

            locations = item.get(
                "Locations"
            ) or []
            if (
                not isinstance(locations, list)
                or any(not isinstance(path, str) for path in locations)
            ):
                raise JellyfinResponseError(
                    "invalid virtual folder locations"
                )

            if (
                item.get("Name") == name
                and location in locations
            ):
                matches.append(
                    item
                )

        if len(matches) != 1:
            raise JellyfinResponseError(
                "Jellyfin library match count != 1"
            )

        item_id = str(
            matches[0].get(
                "ItemId"
            )
            or ""
        ).strip()

        if not item_id:
            raise JellyfinResponseError(
                "Jellyfin library ItemId missing"
            )

        return matches[0]

    def items_by_parent(
        self,
        parent_id: str,
        *,
        limit: int = 1000,
    ):
        parent_id = str(parent_id or "").strip()
        limit = int(limit)
        if not parent_id or limit < 1 or limit > 1000:
            raise JellyfinError("invalid Jellyfin child query")
        query = urllib.parse.urlencode({
            "ParentId": parent_id,
            "Recursive": "false",
            "Fields": "Path,ParentId",
            "StartIndex": 0,
            "Limit": limit,
            "EnableImages": "false",
            "EnableUserData": "false",
        })
        value = self._request("GET", "/Items?" + query)
        if not isinstance(value, dict):
            raise JellyfinResponseError("invalid Jellyfin items response")
        items = value.get("Items")
        total = value.get("TotalRecordCount")
        if (
            not isinstance(items, list)
            or isinstance(total, bool)
            or not isinstance(total, int)
            or total < 0
            or len(items) > limit
            or total != len(items)
            or any(not isinstance(item, dict) for item in items)
        ):
            raise JellyfinResponseError("incomplete Jellyfin child response")
        for item in items:
            if (
                not isinstance(item.get("Id"), str)
                or not item["Id"].strip()
                or not isinstance(item.get("Type"), str)
                or not isinstance(item.get("Path"), str)
                or not isinstance(item.get("ParentId"), str)
            ):
                raise JellyfinResponseError("malformed Jellyfin child item")
        return items

    def exact_media_visibility(self, media_path: str) -> dict:
        """Read-only, bounded lookup of one exact Adult Movie path."""
        path = validate_adult_media_path(media_path)
        library = self.resolve_library(
            name="Adult",
            location="/media/adult",
        )
        root_id = str(library.get("ItemId") or "").strip()
        if not root_id:
            raise JellyfinResponseError("Adult library ItemId missing")

        family_path = path.parents[1].as_posix()
        family_items = self.items_by_parent(root_id, limit=1000)
        family_matches = [item for item in family_items if item.get("Path") == family_path]
        if len(family_matches) > 1:
            return {"status": "ATTENTION", "reason": "AMBIGUOUS_FAMILY_FOLDER"}
        if not family_matches:
            return {"status": "PENDING", "reason": None}
        family = family_matches[0]
        if family.get("Type") != "Folder" or not str(family.get("Id") or "").strip():
            return {"status": "ATTENTION", "reason": "INVALID_FAMILY_FOLDER"}
        if str(family.get("ParentId") or "") != root_id:
            return {"status": "ATTENTION", "reason": "AMBIGUOUS_FAMILY_PARENT"}

        children = self.items_by_parent(str(family["Id"]), limit=1000)
        exact = [item for item in children if item.get("Path") == path.as_posix()]
        if len(exact) > 1:
            return {"status": "ATTENTION", "reason": "DUPLICATE_EXACT_PATH"}
        if not exact:
            return {"status": "PENDING", "reason": None}
        item = exact[0]
        if item.get("Type") != "Movie":
            return {"status": "ATTENTION", "reason": "WRONG_ITEM_TYPE"}
        if not str(item.get("Id") or "").strip():
            return {"status": "ATTENTION", "reason": "MOVIE_ID_MISSING"}
        if str(item.get("ParentId") or "") != str(family["Id"]):
            return {"status": "ATTENTION", "reason": "AMBIGUOUS_MOVIE_PARENT"}
        return {"status": "VISIBLE", "reason": None, "item_id": str(item["Id"])}

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

    def notify_deleted(
        self,
        media_path: str,
    ):
        """Tell Jellyfin that one exact external media path was deleted."""
        path = PurePosixPath(str(media_path or ""))
        adult = PurePosixPath("/media/adult")
        if (
            not path.is_absolute()
            or path == adult
            or adult not in path.parents
            or ".." in path.parts
            or "*" in path.name
            or path.name in {"", "."}
        ):
            raise JellyfinError("media path outside Adult library")

        self._request(
            "POST",
            "/Library/Media/Updated",
            payload={"Updates": [{"Path": path.as_posix(), "UpdateType": "Deleted"}]},
        )
        return {"status": "JELLYFIN_DELETE_NOTIFIED", "path": path.as_posix()}
