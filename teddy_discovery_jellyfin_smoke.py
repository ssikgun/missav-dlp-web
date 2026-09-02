from pathlib import Path
import json
import tempfile

from teddy_discovery_jellyfin import (
    JellyfinClient,
    JellyfinError,
    jellyfin_media_path,
)


class FakeResponse:
    def __init__(
        self,
        status,
        payload=None,
    ):
        self.status = status

        if payload is None:
            self.data = b""
        else:
            self.data = json.dumps(
                payload
            ).encode("utf-8")

    def getcode(self):
        return self.status

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ):
        return False


def main():
    with tempfile.TemporaryDirectory(
        prefix="teddy-stage9-jellyfin-"
    ) as temp:

        temp = Path(temp)

        key = (
            temp
            / "jellyfin_api_key"
        )

        key.write_text(
            "FAKE_API_KEY_123456",
            encoding="utf-8",
        )

        calls = []

        def fake_opener(
            request,
            timeout=None,
        ):
            body = (
                request.data
                if request.data
                is not None
                else b""
            )

            headers = dict(
                request.header_items()
            )

            calls.append(
                {
                    "method":
                        request.get_method(),
                    "url":
                        request.full_url,
                    "headers":
                        headers,
                    "body":
                        body,
                    "timeout":
                        timeout,
                }
            )

            if request.full_url.endswith(
                "/System/Info"
            ):
                return FakeResponse(
                    200,
                    {
                        "Version":
                            "10.11.11",
                        "ServerName":
                            "Fake Jellyfin",
                    },
                )

            if request.full_url.endswith(
                "/Library/VirtualFolders"
            ):
                return FakeResponse(
                    200,
                    [
                        {
                            "Name":
                                "Adult",
                            "ItemId":
                                "adult-item-id",
                            "Locations": [
                                "/media/adult"
                            ],
                        },
                        {
                            "Name":
                                "Movie",
                            "ItemId":
                                "movie-item-id",
                            "Locations": [
                                "/media/movie"
                            ],
                        },
                    ],
                )

            if request.full_url.endswith(
                "/Library/Media/Updated"
            ):
                return FakeResponse(
                    204
                )

            return FakeResponse(
                404
            )

        client = JellyfinClient(
            base_url=(
                "http://192.168.1.205:8096"
            ),
            api_key_path=key,
            opener=fake_opener,
        )

        info = client.system_info()

        assert (
            info["Version"]
            == "10.11.11"
        )

        adult = client.resolve_library(
            name="Adult",
            location="/media/adult",
        )

        assert (
            adult["ItemId"]
            == "adult-item-id"
        )

        media_path = (
            jellyfin_media_path(
                "ABC/ABC-123/"
                "ABC-123.mp4"
            )
        )

        assert (
            media_path
            == "/media/adult/"
               "ABC/ABC-123/"
               "ABC-123.mp4"
        )

        result = (
            client.notify_created(
                media_path
            )
        )

        assert (
            result["status"]
            == "JELLYFIN_NOTIFIED"
        )

        assert len(calls) == 3

        for call in calls:
            auth = call[
                "headers"
            ].get(
                "Authorization"
            )

            assert auth == (
                'MediaBrowser '
                'Token="'
                'FAKE_API_KEY_123456'
                '"'
            )

            lower = {
                key.lower()
                for key
                in call["headers"]
            }

            assert (
                "x-emby-token"
                not in lower
            )

            assert (
                "x-mediabrowser-token"
                not in lower
            )

        notify = calls[2]

        assert (
            notify["method"]
            == "POST"
        )

        payload = json.loads(
            notify["body"].decode(
                "utf-8"
            )
        )

        assert payload == {
            "Updates": [
                {
                    "Path":
                        "/media/adult/"
                        "ABC/ABC-123/"
                        "ABC-123.mp4",
                    "UpdateType":
                        "Created",
                }
            ]
        }

        refused = False

        try:
            client.notify_created(
                "/media/movie/"
                "ABC-123.mp4"
            )
        except JellyfinError:
            refused = True

        assert refused

    print(
        "STAGE9_JELLYFIN_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
