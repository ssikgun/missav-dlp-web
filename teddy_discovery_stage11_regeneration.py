"""Explicit one-title private subtitle regeneration; never changes rollout state.

Valid source-bound ASR and Japanese subtitle caches are reused independently.
If either cache is absent or fails identity validation, the existing Normal
Mode baseline and external-Japanese acquisition callbacks provide that input.
Existing Korean subtitles are deliberately not an input to this module.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import stat

import teddy_discovery_stage11_controller as controller
import teddy_discovery_stage11_normal_mode as normal
from teddy_discovery_asr import ASRError
from teddy_discovery_subtitle import SubtitleCandidate
from teddy_discovery_subtitle_external import (
    ExternalSubtitleError,
    ExternalSubtitlePayload,
)
from teddy_title_exclusion import ACQUIRED, configured_lock_dir, try_acquire_title_lock


EXECUTE_ENV = "TEDDY_STAGE11_REGENERATION_EXECUTE"
EXECUTE_VALUE = "YES_I_HAVE_REVIEWED_THIS_ONE_TITLE"
CANONICAL_ORIGIN = "https://github.com/ssikgun/missav-dlp-web.git"


class RegenerationError(RuntimeError):
    """Fail-closed error without subtitle content or private paths."""


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _bounded_targeted_runner(dependencies):
    runner = getattr(dependencies, "bounded_hybrid_targeted_runner", None)
    if callable(runner):
        return runner

    def unavailable(*_args, **_kwargs):
        raise RegenerationError(
            "bounded targeted ASR worker lifecycle is not configured"
        )
    return unavailable


def _absolute_path(value, field: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute() or ".." in path.parts or path == Path("/"):
        raise RegenerationError(field + " path is not a safe absolute path")
    return path


def _check_directory_chain(path: Path, *, private: bool = False) -> os.stat_result:
    path = _absolute_path(path, "directory")
    current = Path(path.anchor)
    info = None
    for part in path.parts[1:]:
        current /= part
        try:
            info = os.lstat(current)
        except OSError as error:
            raise RegenerationError("directory is unavailable") from error
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise RegenerationError("directory path contains a non-directory or link")
    if info is None:
        raise RegenerationError("directory is invalid")
    if private and (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700):
        raise RegenerationError("private directory ownership or mode is invalid")
    if not private and info.st_mode & stat.S_IWOTH:
        raise RegenerationError("directory is world writable")
    return info


def _read_optional_private_cache(value, *, field: str, max_bytes: int):
    if value is None:
        return None
    path = _absolute_path(value, field)
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise RegenerationError(field + " cache is unavailable") from error
    if (stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1 or info.st_size <= 0
            or info.st_size > max_bytes):
        raise RegenerationError(field + " cache is not a private regular file")
    return controller._read_private_file(path, max_bytes=max_bytes)


def _read_cached_baseline(path, expected_sha256, snapshot):
    if path is None or type(expected_sha256) is not str:
        return None
    raw = _read_optional_private_cache(
        path, field="baseline ASR", max_bytes=controller.MAX_ASR_ARTIFACT_BYTES)
    if raw is None:
        return None
    if sha256(raw) != expected_sha256:
        return None
    try:
        baseline = controller.parse_asr_result_bytes(raw)
        if (baseline.source_snapshot != snapshot
                or controller.serialize_asr_result(baseline) != raw):
            return None
        controller.require_matching_asr_source(baseline, snapshot)
    except (ASRError, controller.Stage11ControllerError, TypeError, ValueError):
        return None
    return baseline, raw


def _read_cached_japanese(title, path, expected_sha256, source_id):
    if path is None or type(expected_sha256) is not str:
        return None
    raw = _read_optional_private_cache(
        path, field="Japanese subtitle", max_bytes=normal.MAX_SUBTITLE_BYTES)
    if (raw is None
            or sha256(raw) != expected_sha256
            or type(source_id) is not str or not source_id.strip()):
        return None
    try:
        candidate = SubtitleCandidate.validated_external_text(
            source_id, dvd_id=title, language="ja", text_format="srt")
        ExternalSubtitlePayload.from_bytes(
            dvd_id=title, candidate=candidate, payload=raw)
    except (ExternalSubtitleError, TypeError, ValueError):
        return None
    return raw, candidate


def _create_fresh_run_root(value: Path) -> tuple[Path, Path, Path]:
    root = _absolute_path(value, "run root")
    _check_directory_chain(root.parent)
    try:
        os.mkdir(root, 0o700)
    except FileExistsError as error:
        raise RegenerationError("private output root already exists") from error
    except OSError as error:
        raise RegenerationError("private output root could not be created") from error
    _check_directory_chain(root, private=True)
    artifacts = root / "artifacts"
    staging = root / "staging"
    os.mkdir(artifacts, 0o700)
    os.mkdir(staging, 0o700)
    _check_directory_chain(artifacts, private=True)
    _check_directory_chain(staging, private=True)
    return root, artifacts, staging


def regenerate_one_title(
    dvd_id: str,
    *,
    run_root: str | Path,
    baseline_path: str | Path | None = None,
    baseline_sha256: str | None = None,
    japanese_srt_path: str | Path | None = None,
    japanese_srt_sha256: str | None = None,
    japanese_srt_source_id: str | None = None,
    dependencies,
    acceptance_policy,
    source_verifier,
    claim_token: int,
    alignment_budget_profile: str | None = None,
):
    """Generate one new private result under the shared title lock.

    `source_verifier(video, snapshot)` must be the existing read-only NAS
    source-fingerprint check. This path does not seed or mutate Stage12 state.
    """
    title = controller._canonical_title(dvd_id)
    if not callable(source_verifier):
        raise RegenerationError("source verifier is required")
    if alignment_budget_profile not in (None, normal.DUAL_BUDGET_PROVENANCE["mode"]):
        raise RegenerationError("unsupported alignment budget profile")
    lock_dir = configured_lock_dir()
    attempt = try_acquire_title_lock(title, lock_dir)
    if attempt.status != ACQUIRED:
        raise RegenerationError("shared title lock is unavailable or busy")

    with attempt:
        kwargs = dependencies.controller_kwargs()
        kwargs["hermes_settings_resolver"] = dependencies.resolve_hermes_settings
        resolver = kwargs["holding_resolver"]
        video, snapshot = controller._resolve_holding(title, resolver)
        if video.video_format != "mp4":
            raise RegenerationError("canonical MP4 source is required")
        source_verifier(video, snapshot)
        baseline_cache = _read_cached_baseline(
            baseline_path, baseline_sha256, snapshot)
        japanese_cache = _read_cached_japanese(
            title, japanese_srt_path, japanese_srt_sha256,
            japanese_srt_source_id)

        root, artifacts, staging = _create_fresh_run_root(Path(run_root))

        if baseline_cache is not None:
            baseline, baseline_raw = baseline_cache

            def cached_baseline(current_video):
                current_video, current_snapshot = controller._resolve_holding(
                    title, resolver)
                if current_video != video or current_snapshot != snapshot:
                    raise RegenerationError("source snapshot changed before generation")
                parsed = controller.parse_asr_result_bytes(baseline_raw)
                controller.require_matching_asr_source(parsed, current_snapshot)
                return parsed

            kwargs["baseline_transcriber"] = cached_baseline

        if japanese_cache is not None:
            ja_raw, candidate = japanese_cache

            def local_external(current_video, current_baseline):
                if (current_video != video or current_baseline.source_snapshot != snapshot):
                    raise RegenerationError("retained inputs detached from current title")
                payload = ExternalSubtitlePayload.from_bytes(
                    dvd_id=title, candidate=candidate, payload=ja_raw)
                return normal._align_external_payload(
                    payload, title, current_baseline, acceptance_policy, 1000,
                    **({"_dual_resource_budget": True}
                       if alignment_budget_profile is not None else {}))

            kwargs["external_ja_attempt"] = dependencies.capture_external_ja_attempt(
                local_external)
            if alignment_budget_profile is not None:
                kwargs["external_ja_attempt"]._stage11_alignment_budget_profile = alignment_budget_profile

        # Never route targeted evidence through an unbounded callback.
        kwargs["hybrid_targeted_runner"] = _bounded_targeted_runner(dependencies)
        first_pass = normal.NativeNormalFirstPass(dependencies.remote_bridge)
        kwargs["first_pass_runner"] = dependencies.capture_first_pass_runner(first_pass)

        result = normal.run_one_title_normal_mode(
            title,
            artifact_root=artifacts,
            stateful_staging_root=staging,
            claim_token=claim_token,
            acceptance_policy=acceptance_policy,
            alignment_budget_profile=alignment_budget_profile,
            **kwargs,
        )
        if result.title != title or result.route != "HYBRID":
            raise RegenerationError("private regeneration returned an invalid result")
        source_verifier(video, snapshot)
        return result


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dvd-id", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--baseline-asr", type=Path)
    parser.add_argument("--baseline-asr-sha256")
    parser.add_argument("--external-ja", type=Path)
    parser.add_argument("--external-ja-sha256")
    parser.add_argument("--external-ja-source-id")
    parser.add_argument("--alignment-budget-profile", choices=(
        normal.DUAL_BUDGET_PROVENANCE["mode"],))
    parser.add_argument("--execute", action="store_true",
                        help="Run one private Normal Mode regeneration; requires the operator token.")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if (args.baseline_asr is None) != (args.baseline_asr_sha256 is None):
        parser.error("--baseline-asr and its SHA256 must be supplied together")
    ja_values = (args.external_ja, args.external_ja_sha256,
                 args.external_ja_source_id)
    if any(value is not None for value in ja_values) and not all(
            value is not None for value in ja_values):
        parser.error("Japanese subtitle path, SHA256, and source ID must be supplied together")
    if not args.execute or os.environ.get(EXECUTE_ENV) != EXECUTE_VALUE:
        print("STAGE11_REGENERATION=BLOCKED_EXECUTE_AUTHORIZATION", flush=True)
        return 2
    import teddy_discovery_stage12_bulk_runner as bulk
    bulk.require_production_interpreter()
    bulk.check_repo(args.expected_head)
    if bulk.git_query("remote", "get-url", "origin") != CANONICAL_ORIGIN:
        raise RegenerationError("canonical repository origin differs")
    config = bulk.build_deployment_config()
    dependencies = bulk.build_dependencies(config)
    from teddy_discovery_stage12_rollout import build_nas_preflight_filesystem
    nas_filesystem = build_nas_preflight_filesystem(**bulk.NAS)

    def verify_source(video, snapshot):
        info = nas_filesystem.lstat(video.relative_path)
        if (not stat.S_ISREG(info.st_mode)
                or info.st_size != snapshot.source_size
                or info.st_mtime_ns != snapshot.source_mtime_ns):
            raise RegenerationError("NAS source snapshot differs")

    result = regenerate_one_title(
        args.dvd_id,
        run_root=args.run_root,
        baseline_path=args.baseline_asr,
        baseline_sha256=args.baseline_asr_sha256,
        japanese_srt_path=args.external_ja,
        japanese_srt_sha256=args.external_ja_sha256,
        japanese_srt_source_id=args.external_ja_source_id,
        dependencies=dependencies,
        acceptance_policy=bulk.acceptance_policy(),
        source_verifier=verify_source,
        claim_token=bulk.CLAIM_TOKEN,
        alignment_budget_profile=args.alignment_budget_profile,
    )
    print("STAGE11_REGENERATION=PRIVATE_CLEAN_VALIDATED", flush=True)
    print("DVD_ID=" + result.title, flush=True)
    print("CLEAN_SHA256=" + result.clean_sha256, flush=True)
    print("PUBLICATION=NOT_PERFORMED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
