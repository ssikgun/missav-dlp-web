"""Offline smoke coverage for the Stage11 Korean subtitle publisher."""

from pathlib import Path
import hashlib
import json
import subprocess
import tempfile
import threading
from types import SimpleNamespace

from teddy_discovery_completion_ssh import CompletionSSH
from teddy_discovery_ko_srt import (
    GENERATED_SRT_READY,
    GeneratedKoreanSRT,
    generate_korean_srt,
)
from teddy_discovery_subtitle import CanonicalVideoHolding
from teddy_discovery_subtitle_text import SubtitleCue
from teddy_discovery_subtitle_publish import (
    REMOTE_SUBTITLE_PUBLISH_SCRIPT,
    SUBTITLE_NO_ARTIFACT,
    SUBTITLE_PUBLISHED,
    SUBTITLE_SKIPPED_EXISTING_KO,
    SubtitlePublishCollisionError,
    SubtitlePublishError,
    SubtitlePublishTransportError,
    SubtitlePublishValidationError,
    SubtitlePublishResult,
    SubtitleSSHMutator,
)


def _canonical_video():
    return CanonicalVideoHolding(
        dvd_id="ABC-123",
        relative_path="ABC/ABC-123/ABC-123.mp4",
        video_format="mp4",
    )


def _artifact(text="한국어 대사"):
    return generate_korean_srt(
        (
            SubtitleCue(
                start_ms=1_234,
                end_ms=5_678,
                text=text,
            ),
        )
    )


def _make_library(base):
    library = Path(base) / "library"
    movie_dir = library / "ABC" / "ABC-123"
    movie_dir.mkdir(parents=True)
    (movie_dir / "ABC-123.mp4").write_bytes(b"MP4-PATH-WITNESS")
    return library, movie_dir


def _ssh(library, runner):
    return CompletionSSH(
        host="fake",
        user="fake",
        key="/fake/key",
        known_hosts="/fake/known_hosts",
        downloads_root="/fake/downloads",
        library_root=str(library),
        runner=runner,
    )


class LocalScriptRunner:
    def __init__(self):
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append(
            {
                "command": tuple(command),
                "input": kwargs.get("input"),
            }
        )
        return subprocess.run(
            [
                "/bin/sh",
                "-c",
                command[-1],
            ],
            **kwargs,
        )


class ResponseRunner:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append(
            {
                "command": tuple(command),
                "input": kwargs.get("input"),
            }
        )
        return self.response


def _force_artifact(
    payload,
    *,
    cue_count=1,
    sha256=None,
    byte_size=None,
):
    value = object.__new__(GeneratedKoreanSRT)
    object.__setattr__(value, "state", GENERATED_SRT_READY)
    object.__setattr__(value, "payload", payload)
    object.__setattr__(value, "cue_count", cue_count)
    object.__setattr__(
        value,
        "sha256",
        hashlib.sha256(payload).hexdigest()
        if sha256 is None
        else sha256,
    )
    object.__setattr__(
        value,
        "byte_size",
        len(payload) if byte_size is None else byte_size,
    )
    return value


def _assert_publish_error(callable_value, expected_type):
    try:
        callable_value()
    except expected_type:
        return
    except SubtitlePublishError as error:
        raise RuntimeError(
            "unexpected subtitle publish error type: "
            + type(error).__name__
        ) from error
    raise RuntimeError(
        "subtitle publish call unexpectedly succeeded"
    )


def test_no_artifact_zero_remote_calls():
    runner = ResponseRunner(
        SimpleNamespace(
            returncode=99,
            stdout=b"",
            stderr=b"must not run",
        )
    )

    with tempfile.TemporaryDirectory(
        prefix="teddy-stage11-publish-no-artifact-"
    ) as temp:
        library, _movie_dir = _make_library(temp)
        publisher = SubtitleSSHMutator(
            _ssh(library, runner)
        )
        result = publisher.publish_korean_srt(
            canonical_video=_canonical_video(),
            artifact=generate_korean_srt(()),
        )

    assert result.state == SUBTITLE_NO_ARTIFACT
    assert result.sha256 is None
    assert result.byte_size == 0
    assert runner.calls == []


def test_local_remote_publish_lifecycle():
    runner = LocalScriptRunner()

    with tempfile.TemporaryDirectory(
        prefix="teddy-stage11-publish-local-"
    ) as temp:
        library, movie_dir = _make_library(temp)
        artifact = _artifact()
        publisher = SubtitleSSHMutator(
            _ssh(library, runner)
        )

        first = publisher.publish_korean_srt(
            canonical_video=_canonical_video(),
            artifact=artifact,
        )

        final = movie_dir / "ABC-123.ko.srt"
        assert first.state == SUBTITLE_PUBLISHED
        assert first.target_relative == (
            "ABC/ABC-123/ABC-123.ko.srt"
        )
        assert first.sha256 == artifact.sha256
        assert first.byte_size == artifact.byte_size
        assert final.read_bytes() == artifact.payload
        assert not list(
            movie_dir.glob(
                ".ABC-123.ko.srt.stage11-partial.*"
            )
        )

        second = publisher.publish_korean_srt(
            canonical_video=_canonical_video(),
            artifact=artifact,
        )
        assert second.state == SUBTITLE_SKIPPED_EXISTING_KO
        assert final.read_bytes() == artifact.payload

        divergent = b"human-authored-existing-file"
        final.write_bytes(divergent)
        _assert_publish_error(
            lambda: publisher.publish_korean_srt(
                canonical_video=_canonical_video(),
                artifact=artifact,
            ),
            SubtitlePublishCollisionError,
        )
        assert final.read_bytes() == divergent

        assert runner.calls
        first_call = runner.calls[0]
        ssh = _ssh(library, runner)
        assert first_call["command"][: len(ssh._base())] == tuple(
            ssh._base()
        )
        assert first_call["input"] == artifact.payload
        command_text = " ".join(first_call["command"])
        assert "한국어 대사" not in command_text


def test_remote_unsafe_final_objects():
    artifact = _artifact()

    with tempfile.TemporaryDirectory(
        prefix="teddy-stage11-publish-unsafe-"
    ) as temp:
        library, movie_dir = _make_library(temp)
        outside = Path(temp) / "outside.srt"
        outside.write_bytes(b"outside")
        final = movie_dir / "ABC-123.ko.srt"
        final.symlink_to(outside)
        runner = LocalScriptRunner()
        publisher = SubtitleSSHMutator(
            _ssh(library, runner)
        )
        _assert_publish_error(
            lambda: publisher.publish_korean_srt(
                canonical_video=_canonical_video(),
                artifact=artifact,
            ),
            SubtitlePublishValidationError,
        )
        assert outside.read_bytes() == b"outside"

    with tempfile.TemporaryDirectory(
        prefix="teddy-stage11-publish-directory-"
    ) as temp:
        library, movie_dir = _make_library(temp)
        (movie_dir / "ABC-123.ko.srt").mkdir()
        publisher = SubtitleSSHMutator(
            _ssh(library, LocalScriptRunner())
        )
        _assert_publish_error(
            lambda: publisher.publish_korean_srt(
                canonical_video=_canonical_video(),
                artifact=artifact,
            ),
            SubtitlePublishValidationError,
        )


def test_local_validation_before_remote():
    valid = _artifact()
    bad_payload = b"not an SRT payload\n"

    for malformed in (
        _force_artifact(
            valid.payload,
            sha256="0" * 64,
        ),
        _force_artifact(
            valid.payload,
            byte_size=valid.byte_size + 1,
        ),
        _force_artifact(
            bad_payload,
        ),
        _force_artifact(
            valid.payload.replace(b"\n", b"\r\n"),
        ),
    ):
        runner = ResponseRunner(
            SimpleNamespace(
                returncode=0,
                stdout=(
                    b'{"status":"CREATED","size":1,"sha256":"'
                    + b"0" * 64
                    + b'"}'
                ),
                stderr=b"",
            )
        )
        with tempfile.TemporaryDirectory(
            prefix="teddy-stage11-publish-local-validation-"
        ) as temp:
            library, _movie_dir = _make_library(temp)
            publisher = SubtitleSSHMutator(
                _ssh(library, runner)
            )
            _assert_publish_error(
                lambda: publisher.publish_korean_srt(
                    canonical_video=_canonical_video(),
                    artifact=malformed,
                ),
                SubtitlePublishValidationError,
            )
        assert runner.calls == []

    response_runner = ResponseRunner(
        SimpleNamespace(
            returncode=1,
            stdout=b"",
            stderr="한국어 대사 must not leak".encode("utf-8"),
        )
    )
    with tempfile.TemporaryDirectory(
        prefix="teddy-stage11-publish-transport-"
    ) as temp:
        library, _movie_dir = _make_library(temp)
        publisher = SubtitleSSHMutator(
            _ssh(library, response_runner)
        )
        try:
            publisher.publish_korean_srt(
                canonical_video=_canonical_video(),
                artifact=valid,
            )
        except SubtitlePublishTransportError as error:
            assert "한국어 대사" not in str(error)
        else:
            raise RuntimeError(
                "remote nonzero response unexpectedly succeeded"
            )


def test_target_and_holding_validation():
    artifact = _artifact()
    runner = ResponseRunner(
        SimpleNamespace(
            returncode=0,
            stdout=(
                b'{"status":"CREATED","size":1,"sha256":"'
                + b"0" * 64
                + b'"}'
            ),
            stderr=b"",
        )
    )

    wrong_targets = (
        "../ABC/ABC-123/ABC-123.ko.srt",
        "ABC/OTHER/ABC-123.ko.srt",
        "ABC/ABC-123/ABC-123.ja.srt",
        "/ABC/ABC-123/ABC-123.ko.srt",
        "ABC/ABC-123/random.ko.srt",
    )

    with tempfile.TemporaryDirectory(
        prefix="teddy-stage11-publish-path-"
    ) as temp:
        library, _movie_dir = _make_library(temp)
        publisher = SubtitleSSHMutator(
            _ssh(library, runner)
        )
        for wrong_target in wrong_targets:
            _assert_publish_error(
                lambda wrong_target=wrong_target: publisher.publish_korean_srt(
                    canonical_video=_canonical_video(),
                    artifact=artifact,
                    target_relative=wrong_target,
                ),
                SubtitlePublishValidationError,
            )

        malformed_holding = CanonicalVideoHolding(
            dvd_id="ABC-123",
            relative_path="OTHER/ABC-123/ABC-123.mp4",
            video_format="mp4",
        )
        _assert_publish_error(
            lambda: publisher.publish_korean_srt(
                canonical_video=malformed_holding,
                artifact=artifact,
            ),
            SubtitlePublishValidationError,
        )

    assert runner.calls == []


def test_remote_response_contract():
    artifact = _artifact()
    responses = (
        SimpleNamespace(
            returncode=0,
            stdout=b"{}",
            stderr=b"",
        ),
        SimpleNamespace(
            returncode=0,
            stdout=b'{"status":[]}',
            stderr=b"",
        ),
        SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "status": "CREATED",
                    "size": artifact.byte_size + 1,
                    "sha256": artifact.sha256,
                }
            ).encode("utf-8"),
            stderr=b"",
        ),
    )

    for response in responses:
        runner = ResponseRunner(response)
        with tempfile.TemporaryDirectory(
            prefix="teddy-stage11-publish-response-"
        ) as temp:
            library, _movie_dir = _make_library(temp)
            publisher = SubtitleSSHMutator(
                _ssh(library, runner)
            )
            _assert_publish_error(
                lambda: publisher.publish_korean_srt(
                    canonical_video=_canonical_video(),
                    artifact=artifact,
                ),
                SubtitlePublishError,
            )


def test_result_invariants_and_remote_script_contract():
    target = "ABC/ABC-123/ABC-123.ko.srt"
    invalid_results = (
        {
            "state": SUBTITLE_PUBLISHED,
            "target_relative": target,
            "sha256": None,
            "byte_size": 1,
        },
        {
            "state": SUBTITLE_NO_ARTIFACT,
            "target_relative": target,
            "sha256": "0" * 64,
            "byte_size": 1,
        },
        {
            "state": "UNKNOWN",
            "target_relative": target,
            "sha256": None,
            "byte_size": 0,
        },
    )
    for kwargs in invalid_results:
        _assert_publish_error(
            lambda kwargs=kwargs: SubtitlePublishResult(**kwargs),
            SubtitlePublishValidationError,
        )

    for required in (
        'open(candidate, "xb")',
        "os.fsync(handle.fileno())",
        "os.link(partial, target)",
        "FileExistsError",
        "os.lstat",
        "read(expected_size + 1)",
        "os.unlink(partial)",
    ):
        assert required in REMOTE_SUBTITLE_PUBLISH_SCRIPT

    assert "os.rename(" not in REMOTE_SUBTITLE_PUBLISH_SCRIPT
    assert "os.replace(" not in REMOTE_SUBTITLE_PUBLISH_SCRIPT


def test_concurrent_publishers():
    with tempfile.TemporaryDirectory(
        prefix="teddy-stage11-publish-concurrent-"
    ) as temp:
        library, movie_dir = _make_library(temp)
        artifact = _artifact("동시 publish")
        barrier = threading.Barrier(2)
        calls = []
        lock = threading.Lock()

        def concurrent_runner(command, **kwargs):
            with lock:
                calls.append(tuple(command))
            barrier.wait(timeout=5)
            return subprocess.run(
                [
                    "/bin/sh",
                    "-c",
                    command[-1],
                ],
                **kwargs,
            )

        publisher = SubtitleSSHMutator(
            _ssh(library, concurrent_runner)
        )
        results = []
        errors = []

        def worker():
            try:
                results.append(
                    publisher.publish_korean_srt(
                        canonical_video=_canonical_video(),
                        artifact=artifact,
                    )
                )
            except BaseException as error:
                errors.append(error)

        threads = [
            threading.Thread(target=worker),
            threading.Thread(target=worker),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert not any(thread.is_alive() for thread in threads)
        assert not errors
        assert len(results) == 2
        assert sorted(result.state for result in results) == sorted(
            (
                SUBTITLE_PUBLISHED,
                SUBTITLE_SKIPPED_EXISTING_KO,
            )
        )
        assert (
            movie_dir / "ABC-123.ko.srt"
        ).read_bytes() == artifact.payload
        assert not list(
            movie_dir.glob(
                ".ABC-123.ko.srt.stage11-partial.*"
            )
        )
        assert len(calls) == 2


def main():
    test_no_artifact_zero_remote_calls()
    test_local_remote_publish_lifecycle()
    test_remote_unsafe_final_objects()
    test_local_validation_before_remote()
    test_target_and_holding_validation()
    test_remote_response_contract()
    test_result_invariants_and_remote_script_contract()
    test_concurrent_publishers()

    print("STAGE11_SUBTITLE_PUBLISH_SMOKE=PASS")
    print("STAGE11_SUBTITLE_PUBLISH_REMOTE_LOCAL_INTEGRATION=PASS")
    print("STAGE11_SUBTITLE_PUBLISH_CONCURRENCY=PASS")


if __name__ == "__main__":
    main()
