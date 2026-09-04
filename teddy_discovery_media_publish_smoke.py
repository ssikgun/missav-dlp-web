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
    canonical_ko_subtitle_filename,
    is_library_sidecar,
)


def test_library_sidecar_allowlist():
    dvd_id = "ABC-123"

    assert (
        canonical_ko_subtitle_filename(dvd_id)
        == "ABC-123.ko.srt"
    )

    for filename in (
        "ABC-123.nfo",
        "movie.nfo",
        "poster.jpg",
        "poster.png",
        "poster.webp",
        "ABC-123.ko.srt",
        "ABC-123.ja.srt",
        "ABC-123.ja.vtt",
        "ABC-123.jpn.srt",
        "ABC-123.jpn.vtt",
        "ABC-123.japanese.srt",
        "ABC-123.japanese.vtt",
        "ABC-123.en.srt",
        "ABC-123.en.vtt",
        "ABC-123.eng.srt",
        "ABC-123.eng.vtt",
        "ABC-123.english.srt",
        "ABC-123.english.vtt",
        "ABC-123.JPN.SRT",
        "ABC-123.ENGLISH.VTT",
    ):
        assert is_library_sidecar(
            filename,
            dvd_id,
        )

    for filename in (
        "abc-123.ko.srt",
        "ABC-124.ko.srt",
        "random.ko.srt",
        "ABC-123.srt",
        "ABC-123.vtt",
        "ABC-123.ko.vtt",
        "ABC-123.fr.srt",
        "ABC-123.es.vtt",
        "ABC-123.ja.txt",
        "ABC-123.ja.srt.bak",
        "ABC-123.ja.extra.srt",
        "ABC-124.ja.srt",
        "abc-123.ja.srt",
        "subtitle.srt",
        "subtitle.vtt",
    ):
        assert not is_library_sidecar(
            filename,
            dvd_id,
        )


def main():
    test_library_sidecar_allowlist()

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
    print(
        "STAGE11_KO_SIDECAR_ALLOWLIST=PASS"
    )


if __name__ == "__main__":
    main()
