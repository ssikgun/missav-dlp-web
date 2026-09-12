"""Controller callables around native Stage11 APIs; connection owners are injected.

The first-pass preparer owns remote input staging and native session setup.
The Hybrid originals provider supplies caller-held builder evidence, never
reconstructed evidence from the review payload. No database path is opened by
the session adapters and no publisher is accepted.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Mapping
import os
from pathlib import Path

from teddy_discovery_availability import canonical_dvd_id
from teddy_discovery_organizer import load_db_state
from teddy_discovery_subtitle import validate_canonical_holding
from teddy_discovery_asr import ASRSourceSnapshot
from teddy_discovery_asr_transcriber import FullTitleASRTranscriber
from teddy_discovery_asr_audio import iter_audio_chunks
from teddy_discovery_alignment import (
    AlignmentLimitError,
    generate_monotonic_anchor_candidates, select_monotonic_anchors,
    infer_robust_affine_alignment,
)
from teddy_discovery_alignment_acceptance import ACCEPT_HYBRID, decide_alignment_acceptance
from teddy_discovery_alignment_application import apply_alignment_acceptance
from teddy_discovery_hybrid_evidence import (
    HybridEvidenceBundle, HybridAlignmentProvenance,
    ALIGNMENT_PROVENANCE_UNRESOLVED,
)
from teddy_discovery_subtitlecat_discovery import SubtitleCatSearchError
from teddy_discovery_subtitle_external import ExternalSubtitleValidationError
from teddy_discovery_targeted_second_evidence_runner import (
    run_targeted_second_evidence_v1_from_local_source,
)
from teddy_discovery_stateful_translator import (
    create_stateful_staging_directory, stateful_session_id_for_package,
    stateful_staging_paths, write_stateful_input, serialize_stateful_package,
    read_stateful_result, _atomic_private_write, _read_private_result_bytes,
)
from teddy_discovery_stateful_live_runner import build_parser, run
from teddy_discovery_quality_review_session import new_review_execution_session_id
from teddy_discovery_stateful_asr_quality_review import (
    serialize_asr_quality_review_request, parse_asr_quality_review_result,
)
from teddy_discovery_stateful_asr_quality_review_direct_runner import (
    run_asr_quality_review, _read_local_input,
)
from teddy_discovery_stateful_quality_review import (
    serialize_review_request,
)
from teddy_discovery_stateful_quality_review_runner import (
    run_quality_review, read_quality_review_result,
)


class Stage11LiveAdapterError(ValueError):
    """Invalid connection/provider output or detached caller evidence."""


def build_holding_resolver(*, environ=None, state_loader=load_db_state):
    """Use the existing read-only loader without importing the Flask runtime."""
    environment = os.environ if environ is None else environ

    def resolve(title):
        if type(title) is not str or canonical_dvd_id(title) != title:
            raise Stage11LiveAdapterError("exact canonical DVD-ID required")
        path = environment.get("TEDDY_DISCOVERY_DB", "").strip()
        if not path:
            raise Stage11LiveAdapterError("TEDDY_DISCOVERY_DB is unset or empty")
        holdings = state_loader(Path(path)).get("holdings")
        if type(holdings) is not list:
            raise Stage11LiveAdapterError("invalid holdings state")
        matches = [row for row in holdings
                   if isinstance(row, Mapping) and row.get("dvd_id") == title]
        if len(matches) != 1:
            raise Stage11LiveAdapterError("holding must match exactly once")
        row = dict(matches[0])
        _snapshot(row, title)
        return row
    return resolve


def _snapshot(row, title):
    video = validate_canonical_holding(row, title)
    snapshot = ASRSourceSnapshot.from_holding(
        video, source_size=row.get("size_bytes"),
        source_mtime_ns=row.get("mtime_ns"),
    )
    return video, snapshot


def build_baseline_adapter(*, holding_resolver, source_provider, whisper,
                           audio_chunk_iterator=iter_audio_chunks):
    def baseline(canonical_video):
        video, snapshot = _snapshot(holding_resolver(canonical_video.dvd_id),
                                    canonical_video.dvd_id)
        if video != canonical_video:
            raise Stage11LiveAdapterError("baseline holding detached")
        return FullTitleASRTranscriber(
            source_provider=source_provider, whisper=whisper,
            max_media_bytes=snapshot.source_size,
            expected_source_snapshot=snapshot,
            audio_chunk_iterator=audio_chunk_iterator,
        )(video)
    return baseline


def build_targeted_adapter(*, holding_resolver, source_provider, targeted_transport,
                           audio_chunk_iterator=iter_audio_chunks):
    def targeted(asr_result, source_quality_decisions):
        asr_result.__post_init__()
        snapshot = asr_result.source_snapshot
        video, current = _snapshot(holding_resolver(snapshot.dvd_id), snapshot.dvd_id)
        if current != snapshot:
            raise Stage11LiveAdapterError("targeted holding snapshot detached")
        with source_provider.copy_to_temp(
            video, max_media_bytes=snapshot.source_size,
        ) as local_source:
            if local_source.source_snapshot != snapshot:
                raise Stage11LiveAdapterError("targeted local source detached")
            execution = run_targeted_second_evidence_v1_from_local_source(
                asr_result, source_quality_decisions, local_source=local_source,
                targeted_transport=targeted_transport,
                audio_chunk_iterator=audio_chunk_iterator,
            )
            execution.__post_init__()
            return execution
    return targeted


def build_external_ja_adapter(*, discovery, provider, acceptance_policy,
                              residual_threshold_ms):
    def external(canonical_video, asr_result):
        asr_result.__post_init__()
        if ASRSourceSnapshot.from_holding(
            canonical_video, source_size=asr_result.source_snapshot.source_size,
            source_mtime_ns=asr_result.source_snapshot.source_mtime_ns,
        ) != asr_result.source_snapshot:
            raise Stage11LiveAdapterError("external baseline source detached")
        title = canonical_video.dvd_id
        found = discovery.discover(dvd_id=title)
        if found.dvd_id != title:
            raise Stage11LiveAdapterError("discovery source detached")
        if not found.candidates:
            return None
        if len(found.candidates) != 1:
            raise SubtitleCatSearchError("external candidate is not unique")
        payload = provider.fetch_original_japanese_payload(
            dvd_id=title, detail_url=found.candidates[0].detail_url,
        )
        bundle = HybridEvidenceBundle.from_external_ja_and_asr(
            dvd_id=title, external_ja_payload=payload, asr_result=asr_result,
            alignment=HybridAlignmentProvenance(
                ALIGNMENT_PROVENANCE_UNRESOLVED, "lexical-affine",
            ),
        )
        try:
            alignment = infer_robust_affine_alignment(
                select_monotonic_anchors(
                    generate_monotonic_anchor_candidates(bundle)
                ),
                residual_threshold_ms=residual_threshold_ms,
            )
        except AlignmentLimitError as error:
            raise ExternalSubtitleValidationError(
                "external subtitle alignment exceeded bounded lexical comparison limit"
            ) from error
        decision = decide_alignment_acceptance(alignment, acceptance_policy)
        return apply_alignment_acceptance(
            bundle, decision,
            alignment=alignment if decision.verdict == ACCEPT_HYBRID else None,
        )
    return external


def build_first_pass_adapter(*, remote, ssh_key, known_hosts,
                             prepare_remote, native_run=run):
    """prepare_remote(package, paths, route=...) ensures input/session, returns task.

    This explicit native-owner hook must be idempotent on resume. Connection
    setup is not inferred from a local path or a native SessionDB filename.
    """
    def first_pass(package, *, route, staging_root):
        if route not in {"ASR_ONLY", "HYBRID"}:
            raise Stage11LiveAdapterError("unsupported first-pass route")
        session = stateful_session_id_for_package(package)
        directory = Path(staging_root) / session
        if not directory.exists() and not directory.is_symlink():
            create_stateful_staging_directory(staging_root, session)
        paths = stateful_staging_paths(directory)
        if paths.input_path.exists() or paths.input_path.is_symlink():
            if _read_private_result_bytes(paths.input_path) != serialize_stateful_package(package):
                raise Stage11LiveAdapterError("existing first-pass input detached")
        else:
            write_stateful_input(directory, package)
        if paths.result_path.exists() or paths.result_path.is_symlink():
            return read_stateful_result(directory, package, process_finished=True)
        remote_task = prepare_remote(package, paths, route=route)
        args = build_parser().parse_args([
            "--package", str(paths.input_path), "--task-directory", str(directory),
            "--final-result", str(paths.result_path), "--remote", remote,
            "--remote-task", remote_task, "--ssh-key", ssh_key,
            "--known-hosts", known_hosts,
        ])
        code = native_run(args)
        if type(code) is not int or code != 0:
            raise Stage11LiveAdapterError("native first-pass runner failed")
        return read_stateful_result(directory, package, process_finished=True)
    return first_pass


def build_asr_review_adapter(*, remote_task_for_session, runner_options):
    """runner_options are native connection/executor inputs owned by the caller."""
    options = dict(runner_options)
    if {"fresh_review_session", "remote_task"} & options.keys():
        raise Stage11LiveAdapterError("review task/fresh mode is adapter-owned")

    def asr_review(review_request, *, staging_root):
        raw = serialize_asr_quality_review_request(review_request)
        session = new_review_execution_session_id()
        directory = create_stateful_staging_directory(staging_root, session)
        input_path = directory / "stage11-asr-review-input.json"
        output_path = directory / "stage11-asr-review-result.json"
        _atomic_private_write(input_path, raw)
        if _read_local_input(input_path) != raw:
            raise Stage11LiveAdapterError("ASR review input readback mismatch")
        run_asr_quality_review(
            input_path, output_path, session,
            remote_task=remote_task_for_session(session),
            fresh_review_session=True, **options,
        )
        return parse_asr_quality_review_result(
            _read_local_input(output_path), review_request,
        )
    return asr_review


def build_hybrid_review_adapter(*, originals_provider, runner_options):
    """Supply exact caller originals to the native parser's trust boundary."""
    options = dict(runner_options)
    if {"fresh_review_session", "review_execution_session_id", "session_id"} & options.keys():
        raise Stage11LiveAdapterError("review execution identity is adapter-owned")

    def hybrid_review(review_request, *, staging_root):
        raw = serialize_review_request(review_request)
        originals = originals_provider(review_request)
        session = new_review_execution_session_id()
        directory = create_stateful_staging_directory(staging_root, session)
        result = run_quality_review(
            directory, raw, review_execution_session_id=session,
            fresh_review_session=True, **options, **originals,
        )
        parsed = read_quality_review_result(
            directory, review_request, process_finished=True, returncode=0,
            review_execution_session_id=session,
        )
        if parsed != result:
            raise Stage11LiveAdapterError("Hybrid review result readback mismatch")
        return parsed
    return hybrid_review


@dataclass(frozen=True)
class Stage11LiveDependencies:
    holding_resolver: Callable
    baseline_transcriber: Callable
    external_ja_attempt: Callable
    targeted_runner: Callable
    first_pass_runner: Callable
    asr_review_runner: Callable
    hybrid_review_runner: Callable


def build_stage11_live_dependencies(*, source_provider, whisper, targeted_transport,
                                    discovery, provider, acceptance_policy,
                                    residual_threshold_ms, first_pass_options,
                                    asr_review_options, hybrid_review_options,
                                    holding_resolver=None,
                                    audio_chunk_iterator=iter_audio_chunks):
    resolver = holding_resolver if holding_resolver is not None else build_holding_resolver()
    return Stage11LiveDependencies(
        resolver,
        build_baseline_adapter(holding_resolver=resolver, source_provider=source_provider,
                               whisper=whisper, audio_chunk_iterator=audio_chunk_iterator),
        build_external_ja_adapter(discovery=discovery, provider=provider,
                                  acceptance_policy=acceptance_policy,
                                  residual_threshold_ms=residual_threshold_ms),
        build_targeted_adapter(holding_resolver=resolver, source_provider=source_provider,
                               targeted_transport=targeted_transport,
                               audio_chunk_iterator=audio_chunk_iterator),
        build_first_pass_adapter(**first_pass_options),
        build_asr_review_adapter(**asr_review_options),
        build_hybrid_review_adapter(**hybrid_review_options),
    )
