from pathlib import Path
import hashlib
import os
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
        video_hash = hashlib.sha256(video.read_bytes()).hexdigest()
        nfo_path = movie_dir / "ABC-123.nfo"
        poster_path = movie_dir / "poster.jpg"
        assert nfo_path.stat().st_uid == video.stat().st_uid
        assert poster_path.stat().st_uid == video.stat().st_uid
        nfo_hash = hashlib.sha256(nfo_path.read_bytes()).hexdigest()
        nfo_mtime = nfo_path.stat().st_mtime_ns

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

        poster_path.write_bytes(
            b"DIFFERENT"
        )
        partial = mutator.publish_bundle(
            video_relative="ABC/ABC-123/ABC-123.mp4",
            bundle=bundle,
        )
        assert partial["status"] == "METADATA_PARTIAL"
        assert partial["nfo"]["status"] == "ALREADY_PRESENT"
        assert partial["poster"]["status"] == "ATTENTION"

        assert poster_path.read_bytes() == b"DIFFERENT"
        assert hashlib.sha256(nfo_path.read_bytes()).hexdigest() == nfo_hash
        assert nfo_path.stat().st_mtime_ns == nfo_mtime

        poster_path.unlink()
        resumed = mutator.publish_bundle(
            video_relative="ABC/ABC-123/ABC-123.mp4",
            bundle=bundle,
        )
        assert resumed["nfo"]["status"] == "ALREADY_PRESENT"
        assert resumed["poster"]["status"] == "CREATED"
        assert hashlib.sha256(nfo_path.read_bytes()).hexdigest() == nfo_hash
        assert nfo_path.stat().st_mtime_ns == nfo_mtime
        assert hashlib.sha256(video.read_bytes()).hexdigest() == video_hash

        second_video_dir = library / "XYZ" / "XYZ-789"
        second_video_dir.mkdir(parents=True)
        second_video = second_video_dir / "XYZ-789.mp4"
        second_video.write_bytes(b"VIDEO-2")
        nfo_collision = second_video_dir / "XYZ-789.nfo"
        nfo_collision.write_bytes(b"existing NFO")
        nfo_collision_bundle = MediaBundle(
            dvd_id="XYZ-789",
            nfo_filename="XYZ-789.nfo",
            nfo_data=b"different NFO",
            poster=None,
            poster_status="PENDING",
            poster_error="COVER_URL_MISSING",
        )
        try:
            mutator.publish_bundle(
                video_relative="XYZ/XYZ-789/XYZ-789.mp4",
                bundle=nfo_collision_bundle,
            )
        except MediaMetadataPublishError:
            pass
        else:
            raise AssertionError("different existing NFO was overwritten")
        assert nfo_collision.read_bytes() == b"existing NFO"
        assert second_video.read_bytes() == b"VIDEO-2"

        unsafe_dir = library / "QWE" / "QWE-456"
        unsafe_dir.mkdir(parents=True)
        unsafe_video = unsafe_dir / "QWE-456.mp4"
        unsafe_video.write_bytes(b"VIDEO-3")
        (unsafe_dir / "QWE-456.nfo").write_bytes(b"<movie/>")
        (unsafe_dir / "poster.jpg").symlink_to(nfo_collision)
        symlink_result = mutator.publish_bundle(
            video_relative="QWE/QWE-456/QWE-456.mp4",
            bundle=MediaBundle(
                dvd_id="QWE-456",
                nfo_filename="QWE-456.nfo",
                nfo_data=b"<movie/>",
                poster=PosterPayload(
                    filename="poster.jpg",
                    content_type="image/jpeg",
                    data=b"\xff\xd8\xffPOSTER",
                ),
            ),
        )
        assert symlink_result["poster"]["status"] == "ATTENTION"
        assert (unsafe_dir / "poster.jpg").is_symlink()
        assert unsafe_video.read_bytes() == b"VIDEO-3"

        special_dir = library / "LMN" / "LMN-777"
        special_dir.mkdir(parents=True)
        special_video = special_dir / "LMN-777.mp4"
        special_video.write_bytes(b"VIDEO-4")
        os.mkfifo(special_dir / "poster.jpg")
        special_result = mutator.publish_bundle(
            video_relative="LMN/LMN-777/LMN-777.mp4",
            bundle=MediaBundle(
                dvd_id="LMN-777",
                nfo_filename="LMN-777.nfo",
                nfo_data=b"<movie/>",
                poster=PosterPayload(
                    filename="poster.jpg",
                    content_type="image/jpeg",
                    data=b"\xff\xd8\xffPOSTER",
                ),
            ),
        )
        assert special_result["poster"]["status"] == "ATTENTION"
        assert (special_dir / "poster.jpg").is_fifo()
        assert special_video.read_bytes() == b"VIDEO-4"

        directory_case = library / "RST" / "RST-222"
        directory_case.mkdir(parents=True)
        (directory_case / "RST-222.mp4").write_bytes(b"VIDEO-6")
        (directory_case / "poster.jpg").mkdir()
        directory_result = mutator.publish_bundle(
            video_relative="RST/RST-222/RST-222.mp4",
            bundle=MediaBundle(
                dvd_id="RST-222",
                nfo_filename="RST-222.nfo",
                nfo_data=b"<movie/>",
                poster=PosterPayload(
                    filename="poster.jpg",
                    content_type="image/jpeg",
                    data=b"\xff\xd8\xffPOSTER",
                ),
            ),
        )
        assert directory_result["poster"]["status"] == "ATTENTION"
        assert (directory_case / "poster.jpg").is_dir()
        assert (directory_case / "RST-222.mp4").read_bytes() == b"VIDEO-6"

        redirected_dir = library / "DIV" / "DIV-888"
        redirected_dir.mkdir(parents=True)
        redirected_video = redirected_dir / "SYM-888.mp4"
        redirected_video.write_bytes(b"VIDEO-7")
        redirected_video_hash = hashlib.sha256(
            redirected_video.read_bytes()
        ).hexdigest()
        symlink_parent = library / "SYM" / "SYM-888"
        symlink_parent.parent.mkdir(parents=True)
        symlink_parent.symlink_to(
            redirected_dir,
            target_is_directory=True,
        )
        unsafe_parent_bundle = MediaBundle(
            dvd_id="SYM-888",
            nfo_filename="SYM-888.nfo",
            nfo_data=b"<movie><title>Expected</title></movie>",
            poster=None,
            poster_status="PENDING",
            poster_error="COVER_URL_MISSING",
        )
        try:
            mutator.publish_bundle(
                video_relative="SYM/SYM-888/SYM-888.mp4",
                bundle=unsafe_parent_bundle,
            )
        except MediaMetadataPublishError:
            pass
        else:
            raise AssertionError("symlinked video parent was accepted")
        assert symlink_parent.is_symlink()
        assert not (redirected_dir / "SYM-888.nfo").exists()
        assert hashlib.sha256(
            redirected_video.read_bytes()
        ).hexdigest() == redirected_video_hash

        nfo_only_dir = library / "NOP" / "NOP-111"
        nfo_only_dir.mkdir(parents=True)
        nfo_only_video = nfo_only_dir / "NOP-111.mp4"
        nfo_only_video.write_bytes(b"VIDEO-5")
        nfo_only = mutator.publish_bundle(
            video_relative="NOP/NOP-111/NOP-111.mp4",
            bundle=MediaBundle(
                dvd_id="NOP-111",
                nfo_filename="NOP-111.nfo",
                nfo_data=b"<movie><title>Real</title></movie>",
                poster=None,
                poster_status="PENDING",
                poster_error="COVER_URL_MISSING",
            ),
        )
        assert nfo_only["status"] == "NFO_READY"
        assert nfo_only["nfo"]["status"] == "CREATED"
        assert nfo_only["poster"]["status"] == "PENDING"
        assert not (nfo_only_dir / "poster.jpg").exists()
        assert nfo_only_video.read_bytes() == b"VIDEO-5"

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
