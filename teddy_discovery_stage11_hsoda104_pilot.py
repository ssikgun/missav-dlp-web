"""Isolated HSODA-104 V2-E pilot binding. Importing it starts no work."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
import uuid

import teddy_discovery_stage11_controller as controller
import teddy_discovery_stage11_regeneration as regeneration
import teddy_discovery_stage11_v2d as v2d
from teddy_discovery_alignment import AffineAnchorResidual, RobustAffineAlignment
from teddy_discovery_alignment_acceptance import (
    ACCEPT_HYBRID,
    AlignmentAcceptancePolicy,
    decide_alignment_acceptance,
)
from teddy_discovery_alignment_application import apply_alignment_acceptance
from teddy_discovery_asr_source import ASRMediaSourceReader
from teddy_discovery_hybrid_evidence import (
    ALIGNMENT_PROVENANCE_UNRESOLVED,
    HybridAlignmentProvenance,
    HybridCueIdentity,
    HybridEvidenceBundle,
)
from teddy_discovery_stage11_deployment import (
    SSHRemoteHermesBridge,
    _build_targeted_asr_transport,
)
from teddy_discovery_stage11_ja_master import build_ja_master_review_set
from teddy_discovery_stage11_normal_mode import NativeNormalFirstPass
from teddy_discovery_stage11_utterance_groups import build_utterance_review_plan
from teddy_discovery_stage12_rollout import build_nas_preflight_filesystem
from teddy_discovery_subtitle_external import ExternalSubtitlePayload
from teddy_title_exclusion import ACQUIRED, configured_lock_dir, try_acquire_title_lock

TITLE = "HSODA-104"
VIDEO_RELATIVE = "HSODA/HSODA-104/HSODA-104.mp4"
ASR_SHA256 = "c26efba4ddcb9fc0f062abb6e45825e85998280cb8578bdb6385e5ba35f3ac3e"
JA_SHA256 = "1c73b000e363e87e715a95f4b846a93cfec035edcb81eb0b73a591b509c33965"
SOURCE_RECORD_SHA256 = "75874bc61eb11f426fac895655e2ce310226226a063c8f769419fd2efa9392f7"
EXPECTED_RAW_GROUP_COUNT = 232
EXPECTED_ACTIVE_GROUP_COUNT = 225
EXPECTED_OUTSIDE_SPAN_GROUP_COUNT = 7
EXPECTED_OUTSIDE_SPAN_RECOVERY_WINDOWS = 4
EXPECTED_OUTSIDE_SPAN_RECOVERY_AUDIO_MS = 48625
EXPECTED_BATCH_GROUP_COUNTS = (31, 43, 45, 38, 38, 30)
EXPECTED_PROMPT_BYTES = (126258, 127771, 122995, 123221, 127232, 101621)


def _retained_plan(retained_dir: Path, snapshot):
    regeneration._check_directory_chain(retained_dir, private=True)
    source_raw = regeneration._read_optional_private_cache(
        retained_dir / "normal-mode-source-v1.json",
        field="retained alignment", max_bytes=16 * 1024 * 1024,
    )
    if source_raw is None or regeneration.sha256(source_raw) != SOURCE_RECORD_SHA256:
        raise regeneration.RegenerationError("retained alignment record differs")
    source = json.loads(source_raw)
    cached_asr = regeneration._read_cached_baseline(
        retained_dir / controller.BASELINE_ASR_FILENAME, ASR_SHA256, snapshot,
    )
    cached_ja = regeneration._read_cached_japanese(
        TITLE, retained_dir / "normal-external-ja.srt", JA_SHA256, source["source_id"],
    )
    if cached_asr is None or cached_ja is None or source["external_sha256"] != JA_SHA256:
        raise regeneration.RegenerationError("retained ASR or JA does not match the source")
    baseline, _ = cached_asr
    ja_raw, candidate = cached_ja
    payload = ExternalSubtitlePayload.from_bytes(
        dvd_id=TITLE, candidate=candidate, payload=ja_raw,
    )
    bundle = HybridEvidenceBundle.from_external_ja_and_asr(
        dvd_id=TITLE, external_ja_payload=payload, asr_result=baseline,
        alignment=HybridAlignmentProvenance(ALIGNMENT_PROVENANCE_UNRESOLVED, "affine"),
    )
    if len(baseline.segments) != 270 or len(bundle.external_ja_document.cues) != 204:
        raise regeneration.RegenerationError("retained ASR or JA coverage differs")

    alignment_fields = dict(source["alignment"])
    residuals = []
    for row in alignment_fields.pop("residuals"):
        fields = dict(row)
        for key in ("external_identity", "asr_identity"):
            fields[key] = HybridCueIdentity(**fields[key])
        residuals.append(AffineAnchorResidual(**fields))
    alignment = RobustAffineAlignment(residuals=tuple(residuals), **alignment_fields)
    decision = decide_alignment_acceptance(
        alignment, AlignmentAcceptancePolicy(**source["acceptance_policy"]),
    )
    if decision.verdict != ACCEPT_HYBRID:
        raise regeneration.RegenerationError("retained alignment is no longer accepted")
    application = apply_alignment_acceptance(bundle, decision, alignment=alignment)
    plan = build_utterance_review_plan(
        build_ja_master_review_set(bundle, alignment_application=application),
    )
    active_groups, outside_groups = v2d.split_outside_span_groups(plan)
    recovery_plan = v2d.plan_outside_span_recovery(plan)
    excluded_ids = recovery_plan.excluded_group_ids
    fingerprint = v2d._source_fingerprint(plan, exclude_group_ids=excluded_ids)
    payloads = tuple(
        (group.group_id, v2d._group_payload(plan, group, source_fingerprint=fingerprint))
        for group in active_groups
    )
    batches = v2d._pack_group_batches(fingerprint, payloads)
    if (len(plan.groups) != EXPECTED_RAW_GROUP_COUNT
            or len(active_groups) != EXPECTED_ACTIVE_GROUP_COUNT
            or len(outside_groups) != EXPECTED_OUTSIDE_SPAN_GROUP_COUNT
            or len(recovery_plan.windows) != EXPECTED_OUTSIDE_SPAN_RECOVERY_WINDOWS
            or recovery_plan.total_audio_ms != EXPECTED_OUTSIDE_SPAN_RECOVERY_AUDIO_MS
            or recovery_plan.exceeds_budget
            or tuple(len(batch[0]) for batch in batches) != EXPECTED_BATCH_GROUP_COUNTS
            or tuple(len(batch[3]) for batch in batches) != EXPECTED_PROMPT_BYTES
            or tuple(row[0] for batch in batches for row in batch[0])
            != tuple(group.group_id for group in active_groups)):
        raise regeneration.RegenerationError("retained V2-D trial batch plan differs")
    return plan, source["claim_token"]


def run_hsoda104_pilot_once(
    *, config, holding_resolver, retained_dir: Path, run_root: Path,
    execution_limits: v2d.V2DExecutionLimits, execution_approved: bool = False,
):
    """Bind one approved future invocation to a fresh, exclusive run root."""
    if execution_approved is not True:
        raise regeneration.RegenerationError("separate pilot execution approval is required")
    if type(execution_limits) is not v2d.V2DExecutionLimits:
        raise regeneration.RegenerationError("explicit V2-D execution limits are required")

    lock = try_acquire_title_lock(TITLE, configured_lock_dir())
    if lock.status != ACQUIRED:
        raise regeneration.RegenerationError("shared title lock is unavailable or busy")
    with lock:
        video, snapshot = controller._resolve_holding(TITLE, holding_resolver)
        if video.video_format != "mp4" or video.relative_path != VIDEO_RELATIVE:
            raise regeneration.RegenerationError("canonical pilot video differs")
        filesystem = build_nas_preflight_filesystem(
            nas_host=config.nas_host, nas_user=config.nas_user, nas_key=config.nas_key,
            nas_known_hosts=config.nas_known_hosts, nas_library_root=config.nas_library_root,
        )
        info = filesystem.lstat(video.relative_path)
        if (not stat.S_ISREG(info.st_mode) or info.st_size != snapshot.source_size
                or info.st_mtime_ns != snapshot.source_mtime_ns):
            raise regeneration.RegenerationError("NAS source snapshot differs")

        plan, claim_token = _retained_plan(retained_dir, snapshot)
        _, output, staging = regeneration._create_fresh_run_root(run_root)
        bridge = SSHRemoteHermesBridge(config)
        settings = bridge.resolve_stage11_hermes_settings()
        source_provider = ASRMediaSourceReader(
            host=config.nas_host, user=config.nas_user, key=config.nas_key,
            known_hosts=config.nas_known_hosts, library_root=config.nas_library_root,
            temp_root=config.asr_media_temp_root, require_disk_backed=True,
            reserve_bytes=config.asr_media_temp_reserve_bytes,
        )
        targeted = v2d.build_v2d_targeted_asr_adapter(
            holding_resolver=holding_resolver, source_provider=source_provider,
            targeted_transport=_build_targeted_asr_transport(config),
        )
        return v2d.run_v2d_pipeline(
            plan, invoke=NativeNormalFirstPass(bridge).invoke, hermes_settings=settings,
            staging_root=staging, output_directory=output, claim_token=claim_token,
            reuse_only=False, targeted_runner=targeted, execution_limits=execution_limits,
        )


@dataclass(frozen=True)
class HSODA104ContinuationResult:
    """Separates prior consumed counts from additional continuation usage."""

    pipeline_result: v2d.V2DPipelineResult
    prior_run_root: str
    continuation_run_root: str
    prior_consumed_hermes_attempts: int
    prior_consumed_targeted_asr_requests: int
    additional_hermes_attempts_started: int
    additional_targeted_asr_requests_started: int
    reused_initial_batches: int
    reused_initial_receipts: int
    reused_outside_span_windows: int
    reused_asr_targeted_windows: int
    reused_external_ja_windows: int
    reused_effective_groups: int
    targeted_readjudication_groups: int
    targeted_readjudication_batches: int
    reused_review_triage_chunks: int = 0
    reused_review_final_calls: int = 0
    vad_window_count: int = 0
    vad_total_audio_ms: int = 0
    vad_window_pass_evaluations: int = 0
    reused_vad_evidence: bool = False
    vad_reused_artifact_sha256: str | None = None
    gpu_diagnostic_requests_started: int = 0
    gpu_diagnostic_audio_ms: int = 0


class _ForbidNetworkBridge:
    """Read-only bridge that refuses any remote Hermes execution."""

    def _python(self, *args, **kwargs):
        raise regeneration.RegenerationError("live Hermes call is forbidden during continuation staging verification")


class _ReuseOnlyTargetedASRGuard:
    """Allows exact-match cached ASR validation while refusing any live ASR call."""

    def __init__(self, targeted_transport):
        self.runtime_identity = targeted_transport.runtime_identity
        self.engine_version = targeted_transport.engine_version

    def __call__(self, *args, **kwargs):
        raise v2d.V2DHold("CONTINUATION_TARGETED_ASR_REQUEST_MISMATCH")

    def targeted_external_ja(self, *args, **kwargs):
        raise v2d.V2DHold("CONTINUATION_TARGETED_ASR_REQUEST_MISMATCH")

    def targeted_outside_span(self, *args, **kwargs):
        raise v2d.V2DHold("CONTINUATION_TARGETED_ASR_REQUEST_MISMATCH")


@dataclass(frozen=True)
class ApprovedTargetedASRScope:
    """Explicit operator-approved bounds for fresh ordinary targeted ASR requests."""

    asr_context_sha256: str
    asr_window_count: int
    asr_total_audio_ms: int
    external_ja_context_sha256: str
    external_ja_window_count: int
    external_ja_total_audio_ms: int
    max_total_requests: int
    max_total_audio_ms: int

    def __post_init__(self):
        v2d._digest(self.asr_context_sha256, "asr_context_sha256")
        v2d._digest(self.external_ja_context_sha256, "external_ja_context_sha256")
        for name in (
            "asr_window_count", "asr_total_audio_ms",
            "external_ja_window_count", "external_ja_total_audio_ms",
            "max_total_requests", "max_total_audio_ms",
        ):
            val = getattr(self, name)
            if type(val) is not int or val <= 0:
                raise regeneration.RegenerationError(f"ApprovedTargetedASRScope.{name} must be a positive int")
        if self.asr_window_count + self.external_ja_window_count > self.max_total_requests:
            raise regeneration.RegenerationError("approved window counts exceed max_total_requests")
        if self.asr_total_audio_ms + self.external_ja_total_audio_ms > self.max_total_audio_ms:
            raise regeneration.RegenerationError("approved audio duration exceeds max_total_audio_ms")


class _CappedSessionProxy:
    """Enforces hard total request cap and single execution per window on an active ASR session."""

    def __init__(self, inner_session, *, tracker: dict[str, object], max_requests: int):
        self._inner = inner_session
        self._tracker = tracker
        self._max_requests = max_requests
        self.runtime_identity = inner_session.runtime_identity
        self.engine_version = inner_session.engine_version

    def transcribe_targeted_chunk(self, chunk):
        key = (self._tracker["active_route"], chunk.start_ms, chunk.end_ms)
        if key in self._tracker["seen_windows"]:
            raise v2d.V2DHold("CONTINUATION_DUPLICATE_TARGETED_ASR_WINDOW")
        if self._tracker["count"] >= self._max_requests:
            raise v2d.V2DHold("CONTINUATION_TARGETED_ASR_REQUEST_LIMIT_EXCEEDED")
        self._tracker["seen_windows"].add(key)
        self._tracker["count"] += 1
        return self._inner.transcribe_targeted_chunk(chunk)


class _RequestCappedTargetedTransport:
    """Wraps targeted_transport to enforce hard chunk cap and per-window uniqueness."""

    def __init__(self, inner_transport, *, tracker: dict[str, object], max_requests: int):
        self._inner = inner_transport
        self._tracker = tracker
        self._max_requests = max_requests
        self.runtime_identity = inner_transport.runtime_identity
        self.engine_version = inner_transport.engine_version
        self.request_timeout_seconds = inner_transport.request_timeout_seconds

    def session(self):
        from contextlib import contextmanager

        @contextmanager
        def _ctx():
            with self._inner.session() as active:
                yield _CappedSessionProxy(active, tracker=self._tracker, max_requests=self._max_requests)

        return _ctx()


class _BoundedApprovedTargetedASRAdapter:
    """Permits ONLY the two exact approved initial targeted ASR requests, once each."""

    def __init__(
        self,
        base_adapter,
        *,
        scope: ApprovedTargetedASRScope,
        expected_asr_windows: tuple[tuple[int, int], ...],
        expected_ext_windows: tuple[tuple[int, int], ...],
        tracker: dict[str, object],
    ):
        self._base = base_adapter
        self._scope = scope
        self._expected_asr_windows = expected_asr_windows
        self._expected_ext_windows = expected_ext_windows
        self._tracker = tracker
        self.runtime_identity = base_adapter.runtime_identity
        self.engine_version = base_adapter.engine_version
        self._asr_executed = False
        self._ext_executed = False

    def __call__(self, asr_result, plan):
        if self._asr_executed:
            raise v2d.V2DHold("CONTINUATION_UNAUTHORIZED_OR_LATE_TARGETED_ASR")
        actual_windows = tuple((w.start_ms, w.end_ms) for w in plan.windows)
        actual_audio_ms = sum(e - s for s, e in actual_windows)
        if (actual_windows != self._expected_asr_windows
                or len(actual_windows) != self._scope.asr_window_count
                or actual_audio_ms != self._scope.asr_total_audio_ms):
            raise v2d.V2DHold("CONTINUATION_TARGETED_ASR_SCOPE_MISMATCH")
        if self._tracker["count"] + len(actual_windows) > self._scope.max_total_requests:
            raise v2d.V2DHold("CONTINUATION_TARGETED_ASR_REQUEST_LIMIT_EXCEEDED")
        self._asr_executed = True
        self._tracker["active_route"] = "asr"
        return self._base(asr_result, plan)

    def targeted_external_ja(self, request):
        if self._ext_executed:
            raise v2d.V2DHold("CONTINUATION_UNAUTHORIZED_OR_LATE_TARGETED_ASR")
        actual_windows = tuple((w.start_ms, w.end_ms) for w in request.windows)
        actual_audio_ms = sum(e - s for s, e in actual_windows)
        if (request.context_sha256 != self._scope.external_ja_context_sha256
                or actual_windows != self._expected_ext_windows
                or len(actual_windows) != self._scope.external_ja_window_count
                or actual_audio_ms != self._scope.external_ja_total_audio_ms):
            raise v2d.V2DHold("CONTINUATION_TARGETED_ASR_SCOPE_MISMATCH")
        if self._tracker["count"] + len(actual_windows) > self._scope.max_total_requests:
            raise v2d.V2DHold("CONTINUATION_TARGETED_ASR_REQUEST_LIMIT_EXCEEDED")
        self._ext_executed = True
        self._tracker["active_route"] = "ext"
        return self._base.targeted_external_ja(request)

    def targeted_outside_span(self, *_args, **_kwargs):
        raise v2d.V2DHold("CONTINUATION_OUTSIDE_SPAN_ASR_ALREADY_REUSED")


def _copy_private_file_exclusive(src: Path, dst: Path) -> None:
    st = src.lstat()
    if not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode) != 0o600:
        raise regeneration.RegenerationError(f"reusable source file is not private regular 0600: {src.name}")
    raw = src.read_bytes()
    v2d._write_exclusive(dst, raw)


def _mkdir_private(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=False, exist_ok=False)
    os.chmod(path, 0o700)
    return path


def _validate_single_initial_batch(
    *,
    batch_rows,
    batch_id: str,
    prompt_bytes: bytes,
    effective_fp: str,
    expected_by_gid: dict[str, object],
    batch_dir: Path,
    hermes_settings,
):
    from types import SimpleNamespace

    expected_ids = tuple(gid for gid, _ in batch_rows)

    def validate_batch(raw, *, expected_ids=expected_ids, batch_id=batch_id):
        data = v2d._load_json(raw, "JA Master batch adjudication")
        if (type(data) is not dict or set(data) != {"batch_id", "source_fingerprint", "groups"}
                or data["batch_id"] != batch_id
                or data["source_fingerprint"] != effective_fp
                or type(data["groups"]) is not list):
            raise v2d.V2DError("JA Master batch envelope differs")
        observed = tuple(item.get("group_id") if type(item) is dict else None
                         for item in data["groups"])
        if observed != expected_ids:
            raise v2d.V2DError("JA Master batch group coverage/order differs")
        group_results = []
        for row, group_id in zip(data["groups"], expected_ids, strict=True):
            parsed = v2d._parse_group_response(
                v2d._wire(row), SimpleNamespace(group_id=group_id), require_audio_flag=True,
            )
            group = expected_by_gid[group_id]
            if (tuple(item.candidate_id for item in parsed.candidate_decisions)
                    != tuple(group.candidate_ids)
                    or tuple(item.source_key for item in parsed.source_decisions)
                    != tuple(member.source_reference.key for member in group.members)):
                raise v2d.V2DError("JA Master batch candidate/source coverage differs")
            v2d._validate_group_source_spans(group, parsed)
            group_results.append(parsed)
        return tuple(group_results)

    ro_native = NativeNormalFirstPass(_ForbidNetworkBridge())
    ro_invoke, _ = v2d._stage_bound_native_invoke(ro_native.invoke, hermes_settings)
    return ro_invoke(
        prompt_bytes,
        batch_dir,
        "ja-master-adjudication-batch",
        validate_batch,
        hermes_settings=hermes_settings,
        reuse_only=True,
    )


def prepare_verified_continuation_staging(
    plan,
    *,
    claim_token: int,
    hermes_settings,
    targeted_transport,
    prior_staging_root: Path,
    new_staging_root: Path,
    allow_missing_initial_batch_indices: tuple[int, ...] = (),
    allow_new_targeted_asr: bool = False,
    approved_targeted_asr_scope: ApprovedTargetedASRScope | None = None,
    reuse_verified_targeted_readjudication: bool = False,
    allow_limited_json_recovery: bool = False,
    use_short_id_mapping_for_uncached: bool = False,
    reuse_verified_translation: bool = False,
    private_provisional_completion: bool = False,
    preserve_legacy_supplemental_grouping: bool = False,
    reuse_verified_review_baseline: bool = False,
    reuse_verified_vad_evidence: bool = False,
) -> dict[str, object]:
    """Validate and clone ONLY verified reusable artifacts into a fresh staging dir.

    - Always validates and copies outside-span recovery ASR (4 windows).
    - Validates each initial JA Master batch (1..6) independently using the
      shared _validate_group_source_spans structural checks; copies ONLY valid
      batches and fails closed if any batch outside
      allow_missing_initial_batch_indices fails validation or is missing.
    - When allow_new_targeted_asr=False (default): validates and copies prior
      ordinary targeted ASR artifacts & linkages strictly as exact-match cache
      candidates.
    - When allow_new_targeted_asr=True (Option A refresh): requires all 6
      initial batches valid (allow_missing_initial_batch_indices=()) and an
      explicit ApprovedTargetedASRScope matching the exact rebuilt initial
      targeted requests; explicitly excludes stale ordinary ASR directories and
      empty mismatch directories without modifying prior_staging_root.
    - Explicitly excludes any prior targeted-readjudication-* directory.
    """
    prior_staging = v2d._private_dir(prior_staging_root)
    new_staging = v2d._private_dir(new_staging_root)
    if prior_staging.resolve() == new_staging.resolve():
        raise regeneration.RegenerationError("continuation staging must differ from prior staging")
    if any(new_staging.iterdir()):
        raise regeneration.RegenerationError("continuation staging directory must be empty")

    allowed_missing = set(allow_missing_initial_batch_indices)
    if any(type(i) is not int or i < 1 for i in allowed_missing):
        raise regeneration.RegenerationError("allow_missing_initial_batch_indices must be positive integers")
    if allow_new_targeted_asr:
        if allowed_missing:
            raise regeneration.RegenerationError(
                "allow_new_targeted_asr requires all initial batches valid (allow_missing_initial_batch_indices=())"
            )
        if type(approved_targeted_asr_scope) is not ApprovedTargetedASRScope:
            raise regeneration.RegenerationError(
                "allow_new_targeted_asr requires an explicit ApprovedTargetedASRScope"
            )
    if reuse_verified_targeted_readjudication:
        if allow_new_targeted_asr or allowed_missing:
            raise regeneration.RegenerationError(
                "reuse_verified_targeted_readjudication requires all initial batches valid and allow_new_targeted_asr=False"
            )
    if reuse_verified_review_baseline and not reuse_verified_translation:
        raise regeneration.RegenerationError(
            "reuse_verified_review_baseline requires reuse_verified_translation=True"
        )
    if reuse_verified_vad_evidence and not reuse_verified_review_baseline:
        raise regeneration.RegenerationError(
            "reuse_verified_vad_evidence requires reuse_verified_review_baseline=True"
        )

    active_groups, outside_span_groups = v2d.split_outside_span_groups(plan)
    excluded_ids = tuple(g.group_id for g in outside_span_groups)
    recovery_plan = v2d.plan_outside_span_recovery(plan)
    if recovery_plan.exceeds_budget or not recovery_plan.windows:
        raise regeneration.RegenerationError("continuation outside-span recovery plan is invalid")

    # 1. Validate outside-span recovery on prior_staging_root (reuse_only=True, 0 ASR calls)
    os_res = v2d._load_or_run_outside_span_recovery(
        recovery_plan, targeted_runner=None, staging_root=prior_staging, reuse_only=True,
    )
    if any(o.outcome != v2d.OUTSIDE_SPAN_OUTCOME_SPEECH_FOUND for o in os_res.window_outcomes):
        raise regeneration.RegenerationError("prior outside-span recovery has unresolved windows")
    supplemental_groups = v2d.build_supplemental_asr_groups(
        plan,
        os_res,
        deduplicate_similar_overlaps=not preserve_legacy_supplemental_grouping,
    )
    effective_groups = active_groups + supplemental_groups
    effective_fp = v2d._source_fingerprint(
        plan, exclude_group_ids=excluded_ids, supplemental_groups=supplemental_groups,
    )
    expected_by_gid = {g.group_id: g for g in effective_groups}

    # 2. Independently validate all 6 initial batches under shared source-span checks
    init_payloads = tuple(
        (g.group_id, v2d._group_payload(plan, g, source_fingerprint=effective_fp))
        for g in effective_groups
    )
    init_batches = v2d._pack_group_batches(effective_fp, init_payloads)
    session_id = str(uuid.uuid5(v2d.V2D_SESSION_NAMESPACE, effective_fp + ":" + str(claim_token)))
    src_session_dir = v2d._private_child(prior_staging, session_id, create=False)

    valid_batch_indices: list[int] = []
    invalid_batch_reasons: dict[int, str] = {}
    resolved_by_gid: dict[str, object] = {}
    for bi, (batch_rows, batch_id, _input_raw, prompt_bytes) in enumerate(init_batches, 1):
        src_bdir = src_session_dir / ("batch-" + batch_id)
        try:
            if not src_bdir.is_dir():
                raise regeneration.RegenerationError(f"initial batch {bi} directory missing")
            parsed_tuple = _validate_single_initial_batch(
                batch_rows=batch_rows,
                batch_id=batch_id,
                prompt_bytes=prompt_bytes,
                effective_fp=effective_fp,
                expected_by_gid=expected_by_gid,
                batch_dir=src_bdir,
                hermes_settings=hermes_settings,
            )
            valid_batch_indices.append(bi)
            for item in parsed_tuple:
                resolved_by_gid[item.group_id] = item
        except Exception as exc:
            invalid_batch_reasons[bi] = f"{type(exc).__name__}: {exc}"
            if bi not in allowed_missing:
                raise regeneration.RegenerationError(
                    f"unauthorized invalid or missing initial batch {bi}: {type(exc).__name__}: {exc}"
                ) from exc

    # 3. Clone outside-span recovery (4 windows) exclusively into new_staging
    os_context_sha = v2d._sha(v2d._wire({
        "schema_version": v2d.V2D_SCHEMA_VERSION,
        "baseline_asr_sha256": recovery_plan.baseline_asr_sha256,
        "external_ja_sha256": recovery_plan.external_ja_sha256,
        "windows": [[w.window_id, w.start_ms, w.end_ms, list(w.external_source_keys)]
                    for w in recovery_plan.windows],
    }))
    dst_os_dir = _mkdir_private(_mkdir_private(new_staging / "outside-span-targeted-asr") / os_context_sha)
    _copy_private_file_exclusive(
        prior_staging / "outside-span-targeted-asr" / os_context_sha / "outside-span-targeted-asr-v1.json",
        dst_os_dir / "outside-span-targeted-asr-v1.json",
    )

    # 4. Clone ONLY independently validated initial batches (excluding allowed_missing)
    dst_session_dir = _mkdir_private(new_staging / session_id)
    copied_receipts = 0
    reused_batches = 0
    for bi, (batch_rows, batch_id, _input_raw, prompt_bytes) in enumerate(init_batches, 1):
        if bi in allowed_missing or bi not in valid_batch_indices:
            continue
        src_bdir = src_session_dir / ("batch-" + batch_id)
        dst_bdir = _mkdir_private(dst_session_dir / ("batch-" + batch_id))
        batch_receipts = sorted(src_bdir.glob("ja-master-adjudication-batch-attempt-*.receipt.json"))
        if not batch_receipts:
            raise regeneration.RegenerationError(f"missing initial receipts in batch-{batch_id}")
        reused_batches += 1
        for rp in batch_receipts:
            copied_receipts += 1
            prefix = rp.name[:-len(".receipt.json")]
            for suffix in (".prompt.txt", ".receipt.json", ".stdout", ".stderr"):
                _copy_private_file_exclusive(src_bdir / (prefix + suffix), dst_bdir / (prefix + suffix))

    # 5. Ordinary targeted ASR handling: exact-cache copy OR Option A stale exclusion + scope verification
    asr_targeted_windows = 0
    ext_ja_windows = 0
    rebuilt_asr_ctx = None
    rebuilt_ext_ctx = None
    rebuilt_asr_windows: tuple[tuple[int, int], ...] = ()
    rebuilt_ext_windows: tuple[tuple[int, int], ...] = ()
    rebuilt_targeted_groups = 0

    if allow_new_targeted_asr:
        # All 6 initial batches are validated; rebuild exact initial targeted requests and match scope.
        audio_gids = tuple(
            g.group_id for g in effective_groups
            if resolved_by_gid[g.group_id].audio_evidence_needed
        )
        rebuilt_targeted_groups = len(audio_gids)
        rebuilt_reqs = v2d._build_initial_targeted_requests(plan, audio_gids)
        for req in rebuilt_reqs:
            if type(req) is v2d._V2DTargetedRequest:
                rebuilt_asr_ctx = req.context_sha256
                rebuilt_asr_windows = tuple((w.start_ms, w.end_ms) for w in req.plan.windows)
            elif type(req) is v2d._V2DExternalTargetedRequest:
                rebuilt_ext_ctx = req.context_sha256
                rebuilt_ext_windows = tuple((w.start_ms, w.end_ms) for w in req.windows)
            else:
                raise regeneration.RegenerationError("unsupported rebuilt targeted ASR request type")
        asr_audio_ms = sum(e - s for s, e in rebuilt_asr_windows)
        ext_audio_ms = sum(e - s for s, e in rebuilt_ext_windows)
        scope = approved_targeted_asr_scope
        if (rebuilt_asr_ctx != scope.asr_context_sha256
                or len(rebuilt_asr_windows) != scope.asr_window_count
                or asr_audio_ms != scope.asr_total_audio_ms
                or rebuilt_ext_ctx != scope.external_ja_context_sha256
                or len(rebuilt_ext_windows) != scope.external_ja_window_count
                or ext_audio_ms != scope.external_ja_total_audio_ms
                or (asr_audio_ms + ext_audio_ms) > scope.max_total_audio_ms):
            raise regeneration.RegenerationError(
                "rebuilt targeted ASR requests do not match ApprovedTargetedASRScope"
            )
    else:
        t2_root = prior_staging / "targeted-second-evidence"
        ext_root = prior_staging / "targeted-external-ja-evidence"
        t2_dirs = sorted(p for p in t2_root.iterdir() if p.is_dir()) if t2_root.is_dir() else []
        ext_dirs = sorted(p for p in ext_root.iterdir() if p.is_dir()) if ext_root.is_dir() else []
        if len(t2_dirs) != 1 or len(ext_dirs) != 1:
            raise regeneration.RegenerationError("expected exactly one prior ASR-based and one external-JA targeted artifact")

        t2_src = t2_dirs[0]
        t2_art_raw = v2d._read_private_owned(t2_src / "targeted-second-evidence-v1.json", max_bytes=v2d.MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_BYTES)
        t2_link_raw = v2d._read_private_owned(t2_src / "v2d-targeted-linkage-v1.json", max_bytes=v2d.V2D_MAX_JSON_BYTES)
        t2_art = v2d.parse_targeted_second_evidence_artifact_bytes(t2_art_raw)
        if v2d.serialize_targeted_second_evidence_artifact(t2_art) != t2_art_raw:
            raise regeneration.RegenerationError("prior targeted-second-evidence artifact is noncanonical")
        t2_link = v2d._load_json(t2_link_raw, "prior targeted-second-evidence linkage")
        if t2_link.get("artifact_sha256") != v2d._sha(t2_art_raw) or t2_link.get("context_sha256") != t2_src.name:
            raise regeneration.RegenerationError("prior targeted-second-evidence linkage mismatch")
        asr_targeted_windows = len(t2_art.windows)
        dst_t2_dir = _mkdir_private(_mkdir_private(new_staging / "targeted-second-evidence") / t2_src.name)
        for fname in ("targeted-second-evidence-v1.json", "v2d-targeted-linkage-v1.json"):
            _copy_private_file_exclusive(t2_src / fname, dst_t2_dir / fname)

        ext_src = ext_dirs[0]
        ext_art_raw = v2d._read_private_owned(ext_src / "targeted-external-ja-asr-v1.json", max_bytes=v2d.MAX_TARGETED_ASR_ARTIFACT_BYTES)
        ext_link_raw = v2d._read_private_owned(ext_src / "v2d-targeted-linkage-v1.json", max_bytes=v2d.V2D_MAX_JSON_BYTES)
        ext_art = v2d.parse_targeted_asr_artifact_bytes(ext_art_raw)
        if v2d.serialize_targeted_asr_artifact(ext_art) != ext_art_raw:
            raise regeneration.RegenerationError("prior targeted-external-ja artifact is noncanonical")
        ext_link = v2d._load_json(ext_link_raw, "prior targeted-external-ja linkage")
        if ext_link.get("artifact_sha256") != v2d._sha(ext_art_raw) or ext_link.get("context_sha256") != ext_src.name:
            raise regeneration.RegenerationError("prior targeted-external-ja linkage mismatch")
        ext_ja_windows = len(ext_art.windows)
        dst_ext_dir = _mkdir_private(_mkdir_private(new_staging / "targeted-external-ja-evidence") / ext_src.name)
        for fname in ("targeted-external-ja-asr-v1.json", "v2d-targeted-linkage-v1.json"):
            _copy_private_file_exclusive(ext_src / fname, dst_ext_dir / fname)

    # 6. Re-validate cloned outside-span recovery and all copied initial batches on new_staging
    v2d._load_or_run_outside_span_recovery(
        recovery_plan, targeted_runner=None, staging_root=new_staging, reuse_only=True,
    )
    for bi, (batch_rows, batch_id, _input_raw, prompt_bytes) in enumerate(init_batches, 1):
        if bi in allowed_missing or bi not in valid_batch_indices:
            continue
        _validate_single_initial_batch(
            batch_rows=batch_rows,
            batch_id=batch_id,
            prompt_bytes=prompt_bytes,
            effective_fp=effective_fp,
            expected_by_gid=expected_by_gid,
            batch_dir=dst_session_dir / ("batch-" + batch_id),
            hermes_settings=hermes_settings,
        )

    reused_readj_indices: list[int] = []
    recovered_readj_indices: list[int] = []
    readj_recovery_records: list[dict[str, object]] = []
    total_readj_batches = 0

    if reuse_verified_targeted_readjudication:
        from types import SimpleNamespace
        # Re-load all 6 validated initial batches and 39 targeted ASR windows on new_staging (0 network calls).
        forbid_invoke = NativeNormalFirstPass(_ForbidNetworkBridge()).invoke
        init_adj = v2d.adjudicate_ja_master(
            plan, invoke=forbid_invoke, hermes_settings=hermes_settings,
            staging_root=new_staging, claim_token=claim_token, reuse_only=True,
            batch_groups=True, exclude_group_ids=excluded_ids,
            supplemental_groups=supplemental_groups,
        )
        audio_gids = tuple(
            g.group_id for g, r in zip(effective_groups, init_adj.groups, strict=True)
            if r.audio_evidence_needed
        )
        rebuilt_targeted_groups = len(audio_gids)
        rebuilt_reqs = v2d._build_initial_targeted_requests(plan, audio_gids)
        guard_runner = _ReuseOnlyTargetedASRGuard(targeted_transport)
        early_items = []
        for req in rebuilt_reqs:
            if type(req) is v2d._V2DTargetedRequest:
                rebuilt_asr_ctx = req.context_sha256
                rebuilt_asr_windows = tuple((w.start_ms, w.end_ms) for w in req.plan.windows)
                early_items.append(v2d._load_or_run_targeted_evidence(
                    req, targeted_runner=guard_runner, staging_root=new_staging, reuse_only=True,
                ))
            else:
                rebuilt_ext_ctx = req.context_sha256
                rebuilt_ext_windows = tuple((w.start_ms, w.end_ms) for w in req.windows)
                early_items.append(v2d._load_or_run_external_targeted_evidence(
                    req, targeted_runner=guard_runner, staging_root=new_staging, reuse_only=True,
                ))
        targeted_ev = v2d._combine_targeted_evidence(tuple(early_items))
        readj_ctx_sha = v2d._sha(v2d._wire({
            "source_fingerprint": effective_fp,
            "artifact_sha256": targeted_ev.artifact_sha256,
            "linkage_sha256": targeted_ev.linkage_sha256,
            "claim_token": claim_token,
        }))
        src_readj_dir = prior_staging / ("targeted-readjudication-" + readj_ctx_sha)
        if not src_readj_dir.is_dir():
            raise regeneration.RegenerationError("matching prior targeted-readjudication directory is missing")
        ev_by_gid = dict(targeted_ev.group_payloads)
        readj_payloads = []
        for g in effective_groups:
            if g.group_id in ev_by_gid:
                p = v2d._group_payload(plan, g, source_fingerprint=effective_fp)
                p["targeted_second_evidence"] = ev_by_gid[g.group_id]
                readj_payloads.append((g.group_id, p))
        readj_batches = v2d._pack_group_batches(
            effective_fp, tuple(readj_payloads),
            instruction=v2d.SEMANTIC_TARGETED_READJUDICATION_BATCH_INSTRUCTION,
        )
        total_readj_batches = len(readj_batches)
        dst_readj_dir = _mkdir_private(new_staging / ("targeted-readjudication-" + readj_ctx_sha))
        for rbi, (rbatch, rbid, _rinp, rprompt) in enumerate(readj_batches, 1):
            src_rbdir = src_readj_dir / ("batch-" + rbid)
            if not src_rbdir.is_dir():
                continue
            r_receipts = sorted(src_rbdir.glob("ja-master-targeted-readjudication-batch-attempt-*.receipt.json"))
            if not r_receipts:
                continue
            expected_ids = tuple(gid for gid, _ in rbatch)
            batch_rec_log: list[dict[str, object]] = []

            def _validate_readj_batch(raw, *, _expected_ids=expected_ids, _rbid=rbid, _rec_log=batch_rec_log):
                rec = None
                if allow_limited_json_recovery:
                    data, rec = v2d.recover_limited_trailing_json(raw, "JA Master batch adjudication")
                else:
                    data = v2d._load_json(raw, "JA Master batch adjudication")
                if (type(data) is not dict or set(data) != {"batch_id", "source_fingerprint", "groups"}
                        or data["batch_id"] != _rbid
                        or data["source_fingerprint"] != effective_fp
                        or type(data["groups"]) is not list):
                    raise v2d.V2DError("JA Master batch envelope differs")
                observed = tuple(item.get("group_id") if type(item) is dict else None for item in data["groups"])
                if observed != _expected_ids:
                    raise v2d.V2DError("JA Master batch group coverage/order differs")
                results = []
                for row, gid in zip(data["groups"], _expected_ids, strict=True):
                    parsed = v2d._parse_group_response(
                        v2d._wire(row), SimpleNamespace(group_id=gid), require_audio_flag=True,
                    )
                    group = expected_by_gid[gid]
                    if (tuple(item.candidate_id for item in parsed.candidate_decisions)
                            != tuple(group.candidate_ids)
                            or tuple(item.source_key for item in parsed.source_decisions)
                            != tuple(member.source_reference.key for member in group.members)):
                        raise v2d.V2DError("JA Master batch candidate/source coverage differs")
                    v2d._validate_group_source_spans(group, parsed)
                    results.append(parsed)
                if rec is not None:
                    _rec_log.append({**rec, "batch_id": _rbid, "batch_index": rbi})
                return tuple(results)

            # Validate on prior_staging (earliest eligible attempt in actual attempt order)
            active_rprompt = rprompt
            active_rval = _validate_readj_batch
            if use_short_id_mapping_for_uncached:
                short_mat = v2d._build_short_id_batch_material(
                    rbatch, batch_id=rbid, source_fingerprint=effective_fp,
                    instruction=v2d.SEMANTIC_TARGETED_READJUDICATION_BATCH_INSTRUCTION,
                )
                first_p = src_rbdir / "ja-master-targeted-readjudication-batch-attempt-1.prompt.txt"
                if first_p.is_file() and first_p.read_bytes() == short_mat["prompt"]:
                    active_rprompt = short_mat["prompt"]

                    def _validate_short_readj(raw, *, _sm=short_mat, _rbid=rbid, _val=_validate_readj_batch):
                        if allow_limited_json_recovery:
                            data, _ = v2d.recover_limited_trailing_json(raw, "JA Master batch adjudication")
                        else:
                            data = v2d._load_json(raw, "JA Master batch adjudication")
                        restored = v2d._restore_short_id_batch_response(
                            data,
                            short_batch_id=_sm["short_batch_id"],
                            short_fp=_sm["short_fp"],
                            real_batch_id=_rbid,
                            real_fp=effective_fp,
                            expected_short_gids=_sm["expected_short_gids"],
                            short_to_real_gid=_sm["short_to_real_gid"],
                            expected_short_cids_by_gid=_sm["expected_short_cids_by_gid"],
                            short_to_real_cid_by_gid=_sm["short_to_real_cid_by_gid"],
                        )
                        return _val(v2d._wire(restored))

                    active_rval = _validate_short_readj

            try:
                forbid_invoke(
                    active_rprompt, src_rbdir, "ja-master-targeted-readjudication-batch",
                    active_rval, hermes_settings=hermes_settings, reuse_only=True,
                )
            except Exception:
                continue
            dst_rbdir = _mkdir_private(dst_readj_dir / ("batch-" + rbid))
            for rp in r_receipts:
                prefix = rp.name[:-len(".receipt.json")]
                for suffix in (".prompt.txt", ".receipt.json", ".stdout", ".stderr"):
                    _copy_private_file_exclusive(src_rbdir / (prefix + suffix), dst_rbdir / (prefix + suffix))
                verr_path = src_rbdir / (prefix + ".validation-error.json")
                if verr_path.exists():
                    _copy_private_file_exclusive(verr_path, dst_rbdir / (prefix + ".validation-error.json"))
            # Re-validate on cloned dst_rbdir
            verify_log: list[dict[str, object]] = []
            if active_rprompt == rprompt:
                forbid_invoke(
                    rprompt, dst_rbdir, "ja-master-targeted-readjudication-batch",
                    lambda raw, _e=expected_ids, _b=rbid, _l=verify_log: _validate_readj_batch(
                        raw, _expected_ids=_e, _rbid=_b, _rec_log=_l,
                    ),
                    hermes_settings=hermes_settings, reuse_only=True,
                )
            else:
                forbid_invoke(
                    active_rprompt, dst_rbdir, "ja-master-targeted-readjudication-batch",
                    active_rval, hermes_settings=hermes_settings, reuse_only=True,
                )
            reused_readj_indices.append(rbi)
            if verify_log:
                recovered_readj_indices.append(rbi)
                readj_recovery_records.extend(verify_log)

        reused_translation_parts = 0
        reused_review_triage_chunks = 0
        reused_review_final_calls = 0
        reused_vad_evidence = False
        vad_reused_artifact_sha256 = None
        if reuse_verified_translation:
            if len(reused_readj_indices) != total_readj_batches:
                raise regeneration.RegenerationError(
                    "reuse_verified_translation requires all targeted readjudication batches reused"
                )
            final_adj = v2d._readjudicate_targeted_groups(
                plan, init_adj, targeted_ev,
                invoke=forbid_invoke, hermes_settings=hermes_settings,
                staging_root=new_staging, claim_token=claim_token, reuse_only=True,
                batch_groups=True, exclude_group_ids=excluded_ids,
                supplemental_groups=supplemental_groups,
                allow_limited_json_recovery=allow_limited_json_recovery,
                use_short_id_mapping_for_uncached=use_short_id_mapping_for_uncached,
            )
            prov_master = v2d.materialize_ja_master(
                plan, final_adj,
                targeted_evidence_sha256=targeted_ev.linkage_sha256,
                outside_span_recovery_sha256=os_res.artifact_sha256,
                exclude_group_ids=excluded_ids,
                supplemental_groups=supplemental_groups,
                allow_private_provisional_unresolved=private_provisional_completion,
            )
            tr_ev = v2d._targeted_translation_evidence(prov_master, targeted_ev)
            pkg = v2d._build_translation_package(
                prov_master, claim_token,
                targeted_evidence_by_cue=tr_ev,
                targeted_evidence_sha256=(targeted_ev.linkage_sha256 if tr_ev else None),
            )
            tr_session_id = v2d.stateful_session_id_for_package(pkg)
            src_tr_dir = prior_staging / tr_session_id
            if not src_tr_dir.is_dir():
                raise regeneration.RegenerationError("matching prior translation session directory is missing")
            # Validate on prior_staging first (reuse_only=True, 0 Hermes calls)
            v2d.translate_ja_master(
                prov_master, invoke=forbid_invoke, hermes_settings=hermes_settings,
                staging_root=prior_staging, claim_token=claim_token, reuse_only=True,
                targeted_evidence_by_cue=tr_ev,
                targeted_evidence_sha256=(targeted_ev.linkage_sha256 if tr_ev else None),
            )
            dst_tr_dir = _mkdir_private(new_staging / tr_session_id)
            for jf in sorted(f for f in src_tr_dir.iterdir() if f.is_file() and f.suffix == ".json"):
                _copy_private_file_exclusive(jf, dst_tr_dir / jf.name)
            for pdir in sorted(p for p in src_tr_dir.glob("part-stage-*") if p.is_dir()):
                dst_pdir = _mkdir_private(dst_tr_dir / pdir.name)
                reused_translation_parts += 1
                for subf in sorted(f for f in pdir.iterdir() if f.is_file()):
                    _copy_private_file_exclusive(subf, dst_pdir / subf.name)
            # Re-validate cloned translation session on new_staging (reuse_only=True, 0 Hermes calls)
            _, cloned_tr = v2d.translate_ja_master(
                prov_master, invoke=forbid_invoke, hermes_settings=hermes_settings,
                staging_root=new_staging, claim_token=claim_token, reuse_only=True,
                targeted_evidence_by_cue=tr_ev,
                targeted_evidence_sha256=(targeted_ev.linkage_sha256 if tr_ev else None),
            )
            reused_review_triage_chunks = 0
            reused_review_final_calls = 0
            reused_vad_evidence = False
            vad_reused_artifact_sha256 = None
            if reuse_verified_review_baseline:
                extra_rev_ids = tuple(
                    c.cue_id for c in cloned_tr.cues if getattr(c, "needs_audio_evidence", False)
                )
                prior_rev = v2d.run_targeted_review(
                    prov_master, pkg, cloned_tr,
                    invoke=forbid_invoke, hermes_settings=hermes_settings,
                    staging_root=prior_staging, reuse_only=True,
                    extra_target_cue_ids=extra_rev_ids,
                    allow_limited_json_recovery=allow_limited_json_recovery,
                )
                req_sha = v2d.review_request_sha256(prior_rev.request)
                src_req_dir = prior_staging / req_sha
                dst_req_dir = _mkdir_private(new_staging / req_sha)
                src_triage_dir = src_req_dir / "triage"
                dst_triage_dir = _mkdir_private(dst_req_dir / "triage")
                chunk_dirs = sorted(p for p in src_triage_dir.glob("chunk-*") if p.is_dir())
                if chunk_dirs:
                    for cdir in chunk_dirs:
                        dst_cdir = _mkdir_private(dst_triage_dir / cdir.name)
                        reused_review_triage_chunks += 1
                        for subf in sorted(f for f in cdir.iterdir() if f.is_file()):
                            _copy_private_file_exclusive(subf, dst_cdir / subf.name)
                else:
                    reused_review_triage_chunks = 1
                    for subf in sorted(f for f in src_triage_dir.iterdir() if f.is_file()):
                        _copy_private_file_exclusive(subf, dst_triage_dir / subf.name)
                src_final_dir = src_req_dir / "targeted-final"
                if src_final_dir.is_dir():
                    dst_final_dir = _mkdir_private(dst_req_dir / "targeted-final")
                    reused_review_final_calls = 1
                    for subf in sorted(f for f in src_final_dir.iterdir() if f.is_file()):
                        _copy_private_file_exclusive(subf, dst_final_dir / subf.name)
                v2d.run_targeted_review(
                    prov_master, pkg, cloned_tr,
                    invoke=forbid_invoke, hermes_settings=hermes_settings,
                    staging_root=new_staging, reuse_only=True,
                    extra_target_cue_ids=extra_rev_ids,
                    allow_limited_json_recovery=allow_limited_json_recovery,
                )
                if reuse_verified_vad_evidence:
                    vad_plan = v2d.plan_targeted_vad_windows(
                        prov_master, request=prior_rev.request, limits=v2d.TargetedVADLimits(),
                    )
                    _, _, vad_art_sha, _ = v2d._load_or_run_targeted_vad_evidence(
                        prov_master, prior_rev.request, vad_plan,
                        vad_evidence_runner=None, staging_root=prior_staging, reuse_only=True,
                    )
                    vad_ctx_sha = v2d._vad_context_sha256(
                        prov_master.review_set._source_bundle.asr_result.source_snapshot,
                        vad_plan,
                    )
                    src_vad_dir = prior_staging / "vad-evidence" / vad_ctx_sha
                    dst_vad_root = _mkdir_private(new_staging / "vad-evidence")
                    dst_vad_dir = _mkdir_private(dst_vad_root / vad_ctx_sha)
                    for fname in (v2d.V2D_TARGETED_VAD_SIDECAR_FILENAME, "v2d-vad-linkage-v1.json"):
                        _copy_private_file_exclusive(src_vad_dir / fname, dst_vad_dir / fname)
                    vad_followup_name = "targeted-final-vad-" + vad_art_sha[:16]
                    src_vad_followup = src_req_dir / vad_followup_name
                    if src_vad_followup.is_dir():
                        dst_vad_followup = _mkdir_private(dst_req_dir / vad_followup_name)
                        for subf in sorted(f for f in src_vad_followup.iterdir() if f.is_file()):
                            _copy_private_file_exclusive(subf, dst_vad_followup / subf.name)
                    v2d.run_targeted_review(
                        prov_master, pkg, cloned_tr,
                        invoke=forbid_invoke, hermes_settings=hermes_settings,
                        staging_root=new_staging, reuse_only=True,
                        extra_target_cue_ids=extra_rev_ids,
                        allow_limited_json_recovery=allow_limited_json_recovery,
                        reuse_verified_review_baseline=True,
                        targeted_vad_limits=v2d.TargetedVADLimits(),
                        reuse_verified_vad_evidence=True,
                    )
                    reused_vad_evidence = True
                    vad_reused_artifact_sha256 = vad_art_sha
    else:
        reused_translation_parts = 0
        reused_review_triage_chunks = 0
        reused_review_final_calls = 0
        reused_vad_evidence = False
        vad_reused_artifact_sha256 = None
        if reuse_verified_translation:
            raise regeneration.RegenerationError(
                "reuse_verified_translation requires reuse_verified_targeted_readjudication=True"
            )
        if list(new_staging.glob("targeted-readjudication-*")):
            raise regeneration.RegenerationError("prior targeted-readjudication artifacts must not be copied")
    if allow_new_targeted_asr and (
        (new_staging / "targeted-second-evidence").exists()
        or (new_staging / "targeted-external-ja-evidence").exists()
    ):
        raise regeneration.RegenerationError("stale ordinary targeted ASR directories must not be copied")

    return {
        "reused_initial_batches": reused_batches,
        "reused_initial_batch_indices": tuple(i for i in valid_batch_indices if i not in allowed_missing),
        "excluded_initial_batch_indices": tuple(sorted(allowed_missing)),
        "invalid_initial_batch_reasons": invalid_batch_reasons,
        "reused_initial_receipts": copied_receipts,
        "reused_outside_span_windows": len(os_res.window_outcomes),
        "reused_asr_targeted_windows": asr_targeted_windows,
        "reused_external_ja_windows": ext_ja_windows,
        "reused_total_asr_windows": len(os_res.window_outcomes) + asr_targeted_windows + ext_ja_windows,
        "reused_effective_groups": len(effective_groups),
        "effective_source_fingerprint": effective_fp,
        "stale_ordinary_asr_excluded": bool(allow_new_targeted_asr),
        "rebuilt_targeted_groups": rebuilt_targeted_groups,
        "rebuilt_asr_context_sha256": rebuilt_asr_ctx,
        "rebuilt_asr_windows": rebuilt_asr_windows,
        "rebuilt_external_ja_context_sha256": rebuilt_ext_ctx,
        "rebuilt_external_ja_windows": rebuilt_ext_windows,
        "total_readjudication_batches": total_readj_batches,
        "reused_readjudication_batches": len(reused_readj_indices),
        "reused_readjudication_batch_indices": tuple(reused_readj_indices),
        "recovered_readjudication_batch_indices": tuple(recovered_readj_indices),
        "json_recovery_evidence": tuple(readj_recovery_records),
        "reused_translation_parts": reused_translation_parts,
        "reused_review_triage_chunks": reused_review_triage_chunks,
        "reused_review_final_calls": reused_review_final_calls,
        "reused_vad_evidence": reused_vad_evidence,
        "vad_reused_artifact_sha256": vad_reused_artifact_sha256,
    }


def run_hsoda104_pilot_continue(
    *,
    config,
    holding_resolver,
    retained_dir: Path,
    prior_run_root: Path,
    run_root: Path,
    execution_limits: v2d.V2DExecutionLimits,
    prior_consumed_hermes_attempts: int = 9,
    prior_consumed_targeted_asr_requests: int = 43,
    allow_missing_initial_batch_indices: tuple[int, ...] = (1,),
    allow_new_targeted_asr: bool = False,
    approved_targeted_asr_scope: ApprovedTargetedASRScope | None = None,
    reuse_verified_targeted_readjudication: bool = False,
    allow_limited_json_recovery: bool = False,
    private_provisional_completion: bool = False,
    use_short_id_mapping_for_uncached: bool = False,
    reuse_verified_translation: bool = False,
    preserve_legacy_supplemental_grouping: bool = False,
    reuse_verified_review_baseline: bool = False,
    enable_local_vad_evidence: bool = False,
    targeted_vad_limits: v2d.TargetedVADLimits | None = None,
    reuse_verified_vad_evidence: bool = False,
    enable_whisper_diagnostics: bool = False,
    targeted_diagnostic_limits: v2d.TargetedDiagnosticLimits | None = None,
    correct_review_source_labels: bool = True,
    continuation_approved: bool = False,
) -> HSODA104ContinuationResult:
    """Continue into a fresh exclusive run root reusing ONLY verified prior artifacts."""
    if continuation_approved is not True:
        raise regeneration.RegenerationError("separate pilot continuation approval is required")
    if type(execution_limits) is not v2d.V2DExecutionLimits:
        raise regeneration.RegenerationError("explicit V2-D additional execution limits are required")
    if (type(prior_consumed_hermes_attempts) is not int or prior_consumed_hermes_attempts < 0
            or type(prior_consumed_targeted_asr_requests) is not int or prior_consumed_targeted_asr_requests < 0):
        raise regeneration.RegenerationError("prior consumed execution counts must be non-negative integers")
    if allow_new_targeted_asr and type(approved_targeted_asr_scope) is not ApprovedTargetedASRScope:
        raise regeneration.RegenerationError("allow_new_targeted_asr requires an explicit ApprovedTargetedASRScope")

    prior_root = Path(prior_run_root)
    new_root = Path(run_root)
    if prior_root.resolve() == new_root.resolve():
        raise regeneration.RegenerationError("continuation run_root must differ from prior_run_root")

    lock = try_acquire_title_lock(TITLE, configured_lock_dir())
    if lock.status != ACQUIRED:
        raise regeneration.RegenerationError("shared title lock is unavailable or busy")
    with lock:
        video, snapshot = controller._resolve_holding(TITLE, holding_resolver)
        if video.video_format != "mp4" or video.relative_path != VIDEO_RELATIVE:
            raise regeneration.RegenerationError("canonical pilot video differs")
        filesystem = build_nas_preflight_filesystem(
            nas_host=config.nas_host, nas_user=config.nas_user, nas_key=config.nas_key,
            nas_known_hosts=config.nas_known_hosts, nas_library_root=config.nas_library_root,
        )
        info = filesystem.lstat(video.relative_path)
        if (not stat.S_ISREG(info.st_mode) or info.st_size != snapshot.source_size
                or info.st_mtime_ns != snapshot.source_mtime_ns):
            raise regeneration.RegenerationError("NAS source snapshot differs")

        plan, claim_token = _retained_plan(retained_dir, snapshot)
        bridge = SSHRemoteHermesBridge(config)
        settings = bridge.resolve_stage11_hermes_settings()
        targeted_transport = _build_targeted_asr_transport(config)
        _, output, staging = regeneration._create_fresh_run_root(new_root)
        summary = prepare_verified_continuation_staging(
            plan,
            claim_token=claim_token,
            hermes_settings=settings,
            targeted_transport=targeted_transport,
            prior_staging_root=prior_root / "staging",
            new_staging_root=staging,
            allow_missing_initial_batch_indices=allow_missing_initial_batch_indices,
            allow_new_targeted_asr=allow_new_targeted_asr,
            approved_targeted_asr_scope=approved_targeted_asr_scope,
            reuse_verified_targeted_readjudication=reuse_verified_targeted_readjudication,
            allow_limited_json_recovery=allow_limited_json_recovery,
            use_short_id_mapping_for_uncached=use_short_id_mapping_for_uncached,
            reuse_verified_translation=reuse_verified_translation,
            private_provisional_completion=private_provisional_completion,
            preserve_legacy_supplemental_grouping=preserve_legacy_supplemental_grouping,
            reuse_verified_review_baseline=reuse_verified_review_baseline,
            reuse_verified_vad_evidence=reuse_verified_vad_evidence,
        )
        if allow_new_targeted_asr:
            tracker = {"count": 0, "seen_windows": set(), "active_route": None}
            capped_transport = _RequestCappedTargetedTransport(
                targeted_transport,
                tracker=tracker,
                max_requests=approved_targeted_asr_scope.max_total_requests,
            )
            source_provider = ASRMediaSourceReader(
                host=config.nas_host, user=config.nas_user, key=config.nas_key,
                known_hosts=config.nas_known_hosts, library_root=config.nas_library_root,
                temp_root=config.asr_media_temp_root, require_disk_backed=True,
                reserve_bytes=config.asr_media_temp_reserve_bytes,
            )
            base_targeted = v2d.build_v2d_targeted_asr_adapter(
                holding_resolver=holding_resolver, source_provider=source_provider,
                targeted_transport=capped_transport,
            )
            targeted = _BoundedApprovedTargetedASRAdapter(
                base_targeted,
                scope=approved_targeted_asr_scope,
                expected_asr_windows=summary["rebuilt_asr_windows"],
                expected_ext_windows=summary["rebuilt_external_ja_windows"],
                tracker=tracker,
            )
        else:
            targeted = _ReuseOnlyTargetedASRGuard(targeted_transport)
        vad_runner = None
        active_vad_limits = None
        if enable_local_vad_evidence:
            vad_source_provider = ASRMediaSourceReader(
                host=config.nas_host, user=config.nas_user, key=config.nas_key,
                known_hosts=config.nas_known_hosts, library_root=config.nas_library_root,
                temp_root=config.asr_media_temp_root, require_disk_backed=True,
                reserve_bytes=config.asr_media_temp_reserve_bytes,
            )
            vad_runner = v2d.build_v2d_targeted_vad_runner(
                holding_resolver=holding_resolver, source_provider=vad_source_provider,
            )
            active_vad_limits = (
                v2d.TargetedVADLimits() if targeted_vad_limits is None else targeted_vad_limits
            )
        elif reuse_verified_vad_evidence:
            active_vad_limits = (
                v2d.TargetedVADLimits() if targeted_vad_limits is None else targeted_vad_limits
            )
        diag_runner = None
        active_diag_limits = None
        if enable_whisper_diagnostics:
            diag_source_provider = ASRMediaSourceReader(
                host=config.nas_host, user=config.nas_user, key=config.nas_key,
                known_hosts=config.nas_known_hosts, library_root=config.nas_library_root,
                temp_root=config.asr_media_temp_root, require_disk_backed=True,
                reserve_bytes=config.asr_media_temp_reserve_bytes,
            )
            diag_runner = v2d.build_v2d_targeted_diagnostic_runner(
                holding_resolver=holding_resolver,
                source_provider=diag_source_provider,
                targeted_transport=targeted_transport,
            )
            active_diag_limits = (
                v2d.TargetedDiagnosticLimits()
                if targeted_diagnostic_limits is None else targeted_diagnostic_limits
            )
        pipeline_result = v2d.run_v2d_pipeline(
            plan, invoke=NativeNormalFirstPass(bridge).invoke, hermes_settings=settings,
            staging_root=staging, output_directory=output, claim_token=claim_token,
            reuse_only=False, targeted_runner=targeted, execution_limits=execution_limits,
            allow_limited_json_recovery=allow_limited_json_recovery,
            private_provisional_completion=private_provisional_completion,
            use_short_id_mapping_for_uncached=use_short_id_mapping_for_uncached,
            reuse_verified_translation=reuse_verified_translation,
            preserve_legacy_supplemental_grouping=preserve_legacy_supplemental_grouping,
            reuse_verified_review_baseline=reuse_verified_review_baseline,
            vad_evidence_runner=vad_runner,
            targeted_vad_limits=active_vad_limits,
            reuse_verified_vad_evidence=reuse_verified_vad_evidence,
            whisper_diagnostic_runner=diag_runner,
            targeted_diagnostic_limits=active_diag_limits,
            correct_review_source_labels=correct_review_source_labels,
        )
        vad_summary = (
            pipeline_result.review.vad_evidence_summary
            if pipeline_result.review is not None else None
        ) or {}
        return HSODA104ContinuationResult(
            pipeline_result=pipeline_result,
            prior_run_root=str(prior_root),
            continuation_run_root=str(new_root),
            prior_consumed_hermes_attempts=prior_consumed_hermes_attempts,
            prior_consumed_targeted_asr_requests=prior_consumed_targeted_asr_requests,
            additional_hermes_attempts_started=pipeline_result.hermes_attempts_started,
            additional_targeted_asr_requests_started=pipeline_result.targeted_asr_requests_started,
            reused_initial_batches=int(summary["reused_initial_batches"]),
            reused_initial_receipts=int(summary["reused_initial_receipts"]),
            reused_outside_span_windows=int(summary["reused_outside_span_windows"]),
            reused_asr_targeted_windows=int(summary["reused_asr_targeted_windows"]),
            reused_external_ja_windows=int(summary["reused_external_ja_windows"]),
            reused_effective_groups=int(summary["reused_effective_groups"]),
            targeted_readjudication_groups=int(summary["rebuilt_targeted_groups"]),
            targeted_readjudication_batches=int(summary["reused_readjudication_batches"]),
            reused_review_triage_chunks=int(summary["reused_review_triage_chunks"]),
            reused_review_final_calls=int(summary["reused_review_final_calls"]),
            vad_window_count=int(vad_summary.get("window_count", 0)),
            vad_total_audio_ms=int(vad_summary.get("total_audio_ms", 0)),
            vad_window_pass_evaluations=int(vad_summary.get("vad_window_pass_evaluations", 0)),
            reused_vad_evidence=bool(summary["reused_vad_evidence"]),
            vad_reused_artifact_sha256=summary["vad_reused_artifact_sha256"],
            gpu_diagnostic_requests_started=pipeline_result.gpu_diagnostic_requests_started,
            gpu_diagnostic_audio_ms=pipeline_result.gpu_diagnostic_audio_ms,
        )
