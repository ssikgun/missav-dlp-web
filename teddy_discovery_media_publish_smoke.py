from pathlib import Path
import subprocess
import tempfile

from teddy_discovery_completion_ssh import (
    CompletionSSH,
)
from teddy_discovery_media_metadata import (
    MediaBundle,
    PosterPayload,
)
from teddy_discovery_media_publish import (
    MediaMetadataPublishError,
    MediaMetadataSSHMutator,
)


def main():
    with tempfile.TemporaryDirectory(
        prefix="teddy-stage9-media-publish-"
    ) as temp:

        root = Path(temp)

        library = (
            root
            / "library"
        )

        movie_dir = (
            library
            / "ABC"
            / "ABC-123"
        )

        movie_dir.mkdir(
            parents=True
        )

        video = (
            movie_dir
            / "ABC-123.mp4"
        )

        video.write_bytes(
            b"VIDEO"
        )

        def fake_runner(
            command,
            **kwargs,
        ):
            return subprocess.run(
                [
                    "/bin/sh",
                    "-c",
                    command[-1],
                ],
                **kwargs,
            )

        ssh = CompletionSSH(
            host="fake",
            user="fake",
            key="/fake/key",
            known_hosts="/fake/known_hosts",
            downloads_root=str(
                root / "downloads"
            ),
            library_root=str(
                library
            ),
            runner=fake_runner,
        )

        mutator = (
            MediaMetadataSSHMutator(
                ssh
            )
        )

        bundle = MediaBundle(
            dvd_id="ABC-123",
            nfo_filename="ABC-123.nfo",
            nfo_data=(
                b"<?xml version='1.0'?>"
                b"<movie>"
                b"<title>Test</title>"
                b"</movie>"
            ),
            poster=PosterPayload(
                filename="poster.jpg",
                content_type="image/jpeg",
                data=(
                    b"\xff\xd8\xff"
                    b"FAKEJPEG"
                ),
            ),
        )

        first = mutator.publish_bundle(
            video_relative=(
                "ABC/ABC-123/"
                "ABC-123.mp4"
            ),
            bundle=bundle,
        )

        assert (
            first["status"]
            == "METADATA_READY"
        )

        assert (
            first["nfo"]["status"]
            == "CREATED"
        )

        assert (
            first["poster"]["status"]
            == "CREATED"
        )

        assert (
            (
                movie_dir
                / "ABC-123.nfo"
            ).read_bytes()
            == bundle.nfo_data
        )

        assert (
            (
                movie_dir
                / "poster.jpg"
            ).read_bytes()
            == bundle.poster.data
        )

        second = mutator.publish_bundle(
            video_relative=(
                "ABC/ABC-123/"
                "ABC-123.mp4"
            ),
            bundle=bundle,
        )

        assert (
            second["nfo"]["status"]
            == "ALREADY_PRESENT"
        )

        assert (
            second["poster"]["status"]
            == "ALREADY_PRESENT"
        )

        (
            movie_dir
            / "poster.jpg"
        ).write_bytes(
            b"DIFFERENT"
        )

        collision = False

        try:
            mutator.publish_bundle(
                video_relative=(
                    "ABC/ABC-123/"
                    "ABC-123.mp4"
                ),
                bundle=bundle,
            )

        except MediaMetadataPublishError:
            collision = True

        assert collision

        assert (
            (
                movie_dir
                / "poster.jpg"
            ).read_bytes()
            == b"DIFFERENT"
        )

        bad_path = False

        try:
            mutator.publish_bundle(
                video_relative=(
                    "WRONG/ABC-123/"
                    "ABC-123.mp4"
                ),
                bundle=bundle,
            )

        except MediaMetadataPublishError:
            bad_path = True

        assert bad_path

    print(
        "STAGE9_MEDIA_PUBLISH_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
