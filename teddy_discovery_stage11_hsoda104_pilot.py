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
) -> dict[str, object]:
    """Validate and clone ONLY verified reusable artifacts into a fresh staging dir.

    - Always validates and copies outside-span recovery ASR (4 windows).
    - Validates each initial JA Master batch (1..6) independently using the
      shared _validate_group_source_spans structural checks; copies ONLY valid
      batches and fails closed if any batch outside
      allow_missing_initial_batch_indices fails validation or is missing.
    - Validates and copies prior ordinary targeted ASR artifacts & linkages
      strictly as exact-match cache candidates (never mutates linkage; mismatch
      during continuation is blocked by _ReuseOnlyTargetedASRGuard).
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
    supplemental_groups = v2d.build_supplemental_asr_groups(plan, os_res)
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

    # 5. Validate and copy prior ordinary targeted ASR artifacts (19 + 20 = 39w) as exact-match cache
    asr_targeted_windows = 0
    ext_ja_windows = 0
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

    if list(new_staging.glob("targeted-readjudication-*")):
        raise regeneration.RegenerationError("prior targeted-readjudication artifacts must not be copied")

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
        )
        if allow_new_targeted_asr:
            source_provider = ASRMediaSourceReader(
                host=config.nas_host, user=config.nas_user, key=config.nas_key,
                known_hosts=config.nas_known_hosts, library_root=config.nas_library_root,
                temp_root=config.asr_media_temp_root, require_disk_backed=True,
                reserve_bytes=config.asr_media_temp_reserve_bytes,
            )
            targeted = v2d.build_v2d_targeted_asr_adapter(
                holding_resolver=holding_resolver, source_provider=source_provider,
                targeted_transport=targeted_transport,
            )
        else:
            targeted = _ReuseOnlyTargetedASRGuard(targeted_transport)
        pipeline_result = v2d.run_v2d_pipeline(
            plan, invoke=NativeNormalFirstPass(bridge).invoke, hermes_settings=settings,
            staging_root=staging, output_directory=output, claim_token=claim_token,
            reuse_only=False, targeted_runner=targeted, execution_limits=execution_limits,
        )
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
            targeted_readjudication_groups=0,
            targeted_readjudication_batches=0,
        )
