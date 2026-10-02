"""Deterministic HYBRID triage scope and target-only review composition.

No model, timing mutation, or publication ownership is introduced here. The
full conservative review is only a selector; CLEAN consumes the merged final
result, whose non-target decisions are constructed locally.
"""
from dataclasses import replace

from teddy_discovery_stateful_quality_review import (
    KEEP, QualityReviewError, QualityReviewResult, QualityReviewResultCue,
    review_request_sha256, validate_review_result, validate_review_target_ids,
)
from teddy_discovery_targeted_asr_artifact import require_matching_targeted_asr_source


HYBRID_SUSPECT_REVIEW_VERSION = "hybrid-suspect-targeted-v1"


def select_suspect_cue_ids(request, triage_result) -> tuple[str, ...]:
    validate_review_result(triage_result, request)
    return tuple(cue.cue_id for cue in triage_result.cues if cue.action != KEEP)


def validate_suspect_artifact(artifact, *, source_snapshot, windows):
    validated = require_matching_targeted_asr_source(artifact, source_snapshot)
    expected = tuple((w.start_ms, w.end_ms, w.external_cue_ids) for w in windows)
    actual = tuple((w.window_start_ms, w.window_end_ms, w.external_cue_ids)
                   for w in validated.windows)
    if not expected or actual != expected:
        raise QualityReviewError("suspect targeted artifact differs from affine window plan")
    return validated


def merge_target_review_result(request, target_cue_ids, target_result=None):
    """Expand only validated target decisions to the original full contract.

    AMBIGUOUS remains raw audit evidence; the existing CLEAN contract applies
    it as KEEP. Non-target text cannot be model-owned because those decisions
    are never accepted from the model.
    """
    if target_cue_ids:
        validate_review_target_ids(request, target_cue_ids)
        validate_review_result(target_result, request, target_cue_ids=target_cue_ids)
        decisions = {cue.cue_id: cue for cue in target_result.cues}
    else:
        if type(target_cue_ids) is not tuple or target_result is not None:
            raise QualityReviewError("empty target scope cannot have model decisions")
        decisions = {}
    full = tuple(decisions.get(cue.cue_id) or QualityReviewResultCue(
        cue.cue_id, KEEP, "DIALOGUE", "Deterministic non-target KEEP; preserve first pass.",
        None, None,
    ) for cue in request.cues)
    if target_result is None:
        result = QualityReviewResult(request.schema_version, review_request_sha256(request), full)
    else:
        result = replace(target_result, cues=full)
    return validate_review_result(result, request)
