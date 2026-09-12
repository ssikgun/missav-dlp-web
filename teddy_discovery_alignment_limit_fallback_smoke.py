"""Offline regression smoke for bounded external-alignment fallback."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import teddy_discovery_stage11_controller_smoke as controller_fixture
import teddy_discovery_stage11_live_adapters as adapters
from teddy_discovery_alignment import (
    AlignmentLimitError,
    MAX_LEXICAL_PAIR_COMPARISONS,
)
from teddy_discovery_alignment_acceptance import AlignmentAcceptancePolicy
from teddy_discovery_stage11_controller import (
    ALIGNMENT_NOT_ATTEMPTED,
    EXTERNAL_JA_VALIDATION_FAILURE,
    run_one_title_stage11,
)
from teddy_discovery_subtitle_external import (
    ExternalSubtitleValidationError,
    SubtitleCatDetailPage,
    SubtitleCatProvider,
)
from teddy_discovery_subtitlecat_discovery import (
    SubtitleCatDiscovery,
    SubtitleCatSearchResponse,
)
from teddy_discovery_subtitle_v2_orchestrator import V2_ROUTE_ASR_ONLY


def _capture(error_type, callback):
    try:
        callback()
    except error_type as error:
        return error
    raise AssertionError("expected " + error_type.__name__)


def _external_adapter(baseline):
    candidate_url = "https://subtitlecat.com/subs/1/GEN-123.html"
    discovery = SubtitleCatDiscovery(
        fetch=lambda request, timeout: SubtitleCatSearchResponse(
            200,
            request.full_url,
            (
                f'<html><a href="{candidate_url}">GEN-123</a></html>'
            ).encode(),
        )
    )
    provider = SubtitleCatProvider(
        fetch_detail=lambda url: SubtitleCatDetailPage(
            url,
            '<html><a href="gen-123-ja.srt">Japanese</a></html>',
        ),
        payload_fetcher=lambda candidate: controller_fixture.fixture.srt_bytes(
            tuple(
                (segment.start_ms, segment.end_ms, segment.text)
                for segment in baseline.segments
            )
        ),
    )
    return adapters.build_external_ja_adapter(
        discovery=discovery,
        provider=provider,
        acceptance_policy=AlignmentAcceptancePolicy(
            3, 3, 0.8, 100.0, 0, 0.9, 1.1
        ),
        residual_threshold_ms=100,
    )


def _run_controller(artifact_root: Path, staging_root: Path, runtime, external):
    return run_one_title_stage11(
        controller_fixture.TITLE,
        artifact_root=artifact_root,
        stateful_staging_root=staging_root,
        claim_token=7,
        baseline_transcriber=runtime.baseline,
        external_ja_attempt=external,
        first_pass_runner=runtime.first_pass,
        asr_review_runner=runtime.asr_review,
        hybrid_review_runner=runtime.hybrid_review,
        holding_resolver=runtime.holding,
        targeted_runner=None,
    )


def main():
    baseline = controller_fixture.fixture.asr_result()
    holding = controller_fixture.fixture.holding()
    external = _external_adapter(baseline)
    limit_error = AlignmentLimitError(
        "lexical pair comparison count exceeds MAX_LEXICAL_PAIR_COMPARISONS"
    )

    with patch.object(
        adapters,
        "generate_monotonic_anchor_candidates",
        side_effect=limit_error,
    ):
        mapped = _capture(
            ExternalSubtitleValidationError,
            lambda: external(holding, baseline),
        )
    assert type(mapped) is ExternalSubtitleValidationError
    assert isinstance(mapped.__cause__, AlignmentLimitError)
    assert str(mapped) == (
        "external subtitle alignment exceeded bounded lexical comparison limit"
    )
    print("PASS adapter maps AlignmentLimitError to validation failure")

    with TemporaryDirectory(prefix="alignment-limit-fallback-smoke-") as raw:
        artifact_root, staging_root = controller_fixture._roots(Path(raw))
        baseline_path = controller_fixture._prepopulate_baseline(
            artifact_root, baseline
        )
        baseline_raw = baseline_path.read_bytes()
        runtime = controller_fixture.FakeRuntime(baseline)
        with patch.object(
            adapters,
            "generate_monotonic_anchor_candidates",
            side_effect=limit_error,
        ):
            result = _run_controller(
                artifact_root,
                staging_root,
                runtime,
                external,
            )
        report = json.loads(result.report_path.read_text(encoding="utf-8"))
        assert result.route == V2_ROUTE_ASR_ONLY
        assert result.external_ja_outcome == EXTERNAL_JA_VALIDATION_FAILURE
        assert result.alignment_outcome == ALIGNMENT_NOT_ATTEMPTED
        assert result.baseline_reused is True
        assert baseline_path.read_bytes() == baseline_raw
        assert report["baseline_reused"] is True
        assert report["baseline_sha256"]
        assert runtime.hybrid_review_calls == 0
        assert runtime.asr_review_calls == 1
    print(
        "PASS controller fallback preserves baseline; "
        "ASR_ONLY and Hybrid review calls 0"
    )

    accepted = external(holding, baseline)
    assert accepted.decision.verdict == "ACCEPT_HYBRID"
    assert MAX_LEXICAL_PAIR_COMPARISONS == 1_048_576
    print("PASS normal alignment unchanged; lexical pair cap unchanged")

    for unexpected in (
        controller_fixture.AlignmentAcceptanceValidationError("detached alignment"),
        RuntimeError("unexpected programmer failure"),
    ):
        with TemporaryDirectory(prefix="alignment-limit-fail-closed-") as raw:
            artifact_root, staging_root = controller_fixture._roots(Path(raw))
            runtime = controller_fixture.FakeRuntime(baseline, unexpected)
            try:
                controller_fixture._run(
                    artifact_root,
                    staging_root,
                    runtime,
                    targeted_runner=False,
                )
            except type(unexpected):
                pass
            else:
                raise AssertionError(
                    "unexpected external exception was incorrectly converted: "
                    + type(unexpected).__name__
                )
            assert runtime.first_pass_calls == 0
    print("PASS existing validation and unexpected exceptions remain fail-closed")

    source = inspect.getsource(adapters.build_external_ja_adapter)
    assert "AT-099" not in source
    assert "GEN-123" not in source
    print("PASS no title-specific production logic")
    print("ALIGNMENT_LIMIT_FALLBACK_SMOKE_PASS")


if __name__ == "__main__":
    main()
