"""Isolated HSODA-104 V2-E pilot binding. Importing it starts no work."""
from __future__ import annotations

import json
from pathlib import Path
import stat

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
EXPECTED_BATCH_GROUP_COUNTS = (32, 44, 46, 39, 40, 31)
EXPECTED_PROMPT_BYTES = (126366, 124429, 126556, 123323, 126795, 103344)


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
    payloads = tuple((group.group_id, v2d._group_payload(plan, group)) for group in plan.groups)
    batches = v2d._pack_group_batches(v2d._source_fingerprint(plan), payloads)
    if (len(plan.groups) != 232
            or tuple(len(batch[0]) for batch in batches) != EXPECTED_BATCH_GROUP_COUNTS
            or tuple(len(batch[3]) for batch in batches) != EXPECTED_PROMPT_BYTES
            or tuple(row[0] for batch in batches for row in batch[0])
            != tuple(group.group_id for group in plan.groups)):
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
