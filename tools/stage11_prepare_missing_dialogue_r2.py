"""Offline context-led R2 listening preparation; no recognizer or server calls.

Human labels are input data, never title/time/text rules. Existing ASR/JA and
conflict spans stay protected; acoustics only prioritize UNVERIFIED probes.
"""
import argparse
import csv
import hashlib
import html
import io
import json
import shutil
import tarfile
from collections import Counter
from pathlib import Path

import numpy as np

from stage11_prepare_whisper_missing_probes import (
    complement, file_sha, overlaps, pcm16, read, save, stamp, write_wav,
)


def manifest(root):
    (root / "SHA256SUMS").write_text("".join(
        file_sha(p) + "  " + str(p.relative_to(root)) + "\n"
        for p in sorted(root.rglob("*"))
        if p.is_file() and p != root / "SHA256SUMS" and "__pycache__" not in p.parts))


def verify_manifest(root):
    for line in (root / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        assert file_sha(root / name) == digest, name


def record_user_judgments(root, feedback_path):
    """Keep the original TSV schema and model cells; archive old SHA evidence."""
    feedback = read(feedback_path)
    assert feedback["actor"] == "USER"
    feedback_sha = file_sha(feedback_path)
    sidecar = root / "user-judgments-r2.json"
    verify_manifest(root)
    if sidecar.exists():
        existing = read(sidecar)
        assert existing["feedback_sha256"] == feedback_sha, "different feedback requires a new revision"
        assert file_sha(root / "judgment.tsv") == existing["updated_judgment_sha256"], "TSV differs from the recorded human revision"
        return existing
    original = (root / "judgment.tsv").read_bytes()
    reader = csv.DictReader(io.StringIO(original.decode()), delimiter="\t")
    fields, rows = reader.fieldnames, list(reader)
    required = {"id", "dialogue_presence", "Japanese_dialogue", "music", "effects",
                "groans_breathing", "verdict", "reviewer", "notes", "Reazon_new"}
    assert required <= set(fields)
    by_id = {r["id"]: r for r in rows}
    assert len(by_id) == len(rows)
    ids = [j["id"] for j in feedback["judgments"]]
    assert len(ids) == len(set(ids)) and set(ids) <= set(by_id)
    archive = root / "user-r2-evidence"
    archive.mkdir(mode=0o700)
    (archive / "judgment.before-user-r2.tsv").write_bytes(original)
    old_manifest = (root / "SHA256SUMS").read_bytes()
    (archive / "SHA256SUMS.before-user-r2").write_bytes(old_manifest)
    recorded = []
    for judgment in feedback["judgments"]:
        label = judgment["label"]
        assert label in {"NON_SPEECH_MOAN", "MUSIC", "NO_DIALOGUE"}
        row = by_id[judgment["id"]]
        before = dict(row)
        row.update(dialogue_presence="NO", Japanese_dialogue="NO",
                   music="YES" if label == "MUSIC" else "NOT_ASSESSED",
                   effects="NOT_ASSESSED",
                   groans_breathing="YES" if label == "NON_SPEECH_MOAN" else "NOT_ASSESSED",
                   verdict=label, reviewer="USER",
                   notes="USER original-audio judgment: " + label +
                   "; exact reviewed clip only; previous model/reference cells preserved")
        recorded.append(dict(id=row["id"], label=label, actor="USER",
                             source=feedback["source"], scope=feedback["scope"],
                             source_start=row["source_start"], source_end=row["source_end"],
                             wav_sha256=file_sha(row["wav_path"]),
                             before=before, after=dict(row), model_verdict="NOT_CHANGED",
                             original_model_review_state=before["verdict"]))
    with (root / "judgment.tsv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    journal = dict(actor="USER", feedback_sha256=feedback_sha, feedback=feedback,
                   original_judgment_sha256=hashlib.sha256(original).hexdigest(),
                   updated_judgment_sha256=file_sha(root / "judgment.tsv"),
                   original_manifest_sha256=hashlib.sha256(old_manifest).hexdigest(),
                   judgments=recorded, categorical_counts=dict(Counter(j["label"] for j in recorded)),
                   model_inferences=0, no_adjacent_scope_extrapolation=True)
    save(sidecar, journal)
    manifest(root)
    return journal


FEATURE_KEYS = ("flux_median", "flux_p90", "modulation_2_8_fraction",
                "envelope_crossing_rate_hz", "entropy_median", "band_motion")


def acoustic_pattern(samples):
    """Amplitude-invariant rhythm/spectral measurements, not voice detection."""
    x = np.asarray(samples, dtype=np.float64)
    assert len(x) >= 400 and np.isfinite(x).all()
    rms = float(np.sqrt(np.mean(x * x)))
    x = x / (rms + 1e-12)
    frames = np.lib.stride_tricks.sliding_window_view(x, 400)[::160]
    power = abs(np.fft.rfft(frames * np.hanning(400), axis=1)) ** 2
    freq = np.fft.rfftfreq(400, 1 / 16000)
    bands = np.stack([power[:, (freq >= a) & (freq < b)].sum(axis=1)
                      for a, b in ((200, 500), (500, 1000), (1000, 2000),
                                   (2000, 3400), (3400, 5000), (5000, 8001))], axis=1)
    normalized = bands / np.maximum(bands.sum(axis=1, keepdims=True), 1e-15)
    flux = abs(np.diff(normalized, axis=0)).sum(axis=1)
    envelope = np.sqrt(np.mean(frames * frames, axis=1))
    envelope = np.convolve(envelope, np.ones(5) / 5, mode="same")
    centered = envelope - envelope.mean()
    modulation = abs(np.fft.rfft(centered * np.hanning(len(centered)))) ** 2
    mfreq = np.fft.rfftfreq(len(centered), .01)
    fraction = modulation[(mfreq >= 2) & (mfreq <= 8)].sum() / max(
        modulation[(mfreq >= .5) & (mfreq <= 12)].sum(), 1e-15)
    entropy = -np.sum(normalized * np.log(np.maximum(normalized, 1e-15)), axis=1) / np.log(6)
    return dict(flux_median=float(np.median(flux)), flux_p90=float(np.percentile(flux, 90)),
                modulation_2_8_fraction=float(fraction),
                envelope_crossing_rate_hz=float(np.mean(np.diff(np.sign(centered)) != 0) / .01 / 2),
                entropy_median=float(np.median(entropy)),
                band_motion=float(np.mean(np.std(normalized, axis=0))),
                rms_dbfs=20 * float(np.log10(max(rms, 1e-12))),
                interpretation="NON_MODEL_ACOUSTIC_PATTERN_ONLY_NOT_LANGUAGE_PROOF")


def neighbors(rows, a, b, start="start_ms", end="end_ms"):
    before = max((r for r in rows if r[end] <= a), key=lambda r: r[end], default=None)
    after = min((r for r in rows if r[start] >= b), key=lambda r: r[start], default=None)
    return dict(before=before, after=after,
                before_distance_ms=None if before is None else a - before[end],
                after_distance_ms=None if after is None else after[start] - b)


def normalize_text(text):
    return "".join(text.split())


def prepare(args, journal):
    source, root = args.r1_bundle.resolve(), args.output.resolve()
    assert not root.exists(), "new output directory required"
    assert 0 <= args.max_candidates <= 8
    cfg = read(source / "preparation-config.json")
    pins = read(source / "input-pins.json")
    for path, digest in pins.items():
        assert file_sha(path) == digest, path
    assert str(args.positive_input.resolve()) in pins, "positive input must have historical SHA provenance"
    positive_input = read(args.positive_input)
    batch = read(source / "batch-plan.json")
    assert positive_input["PCM_sha256"] == batch["source_pcm_sha256"]
    pcm = np.memmap(batch["source_pcm_path"], dtype="<f4", mode="r")
    end_ms = len(pcm) / 16
    alignment = read(source / "source-alignment.json")
    rec, legacy = read(cfg["reconciliation"]), read(cfg["legacy_reconciliation"])
    supplementary = read(Path(cfg["reconciliation"]).with_name("supplemental-review-groups.json"))
    warning_by_record = {rid: g["quality_features"] for g in supplementary for rid in g["record_ids"]}
    whisper = [dict(r["segment"], record_id=r["record_id"], chunk_index=r["chunk_index"],
                    warnings=warning_by_record.get(r["record_id"], []),
                    timing="MODEL_ESTIMATE", language_verification="UNVERIFIED",
                    request_start_ms=r["provenance"]["request_lo"] / 16,
                    request_end_ms=r["provenance"]["request_hi"] / 16) for r in rec["records"]]
    spans = [(r["start_ms"], r["end_ms"]) for r in whisper]
    ja = alignment["external_JA"]
    ja_spans = [(r["start_ms"], r["end_ms"]) for r in ja]
    historical = read(cfg["historical_candidates"])
    historical_spans = [(r["start_ms"], r["end_ms"]) for r in historical]
    baseline = [(r["start_ms"], r["end_ms"]) for r in alignment["baseline_Whisper"]]
    conflicts = [(g["review_start_ms"], g["review_end_ms"]) for obj in (rec, legacy)
                 for g in obj["groups"] if g["conflicting_group_ids"]]
    positives = [r for r in positive_input["positives"] if r["presence_human_confirmed"]]
    positive_spans = [(r["start_ms"], r["end_ms"]) for r in positives]
    negative_spans = [(r["lo"] / 16, r["hi"] / 16) for r in batch["requests"]]
    previous = read(cfg["previous_batch"])
    old_clip_spans = [(r["original_lo"] / 16, r["original_hi"] / 16)
                      for r in previous["requests"] if r["kind"] == "SUPPLEMENTAL"]
    for path in cfg["prior_reazon_results"]:
        saved = read(path)
        requests = saved.get("case_requests", [r["request"] for r in saved["results"]
                                               if "request" in r and r["request"]["kind"] == "SUPPLEMENTAL"])
        old_clip_spans += [(r["original_lo"] / 16, r["original_hi"] / 16) if "original_lo" in r
                          else (r["clip_start_ms"], r["clip_end_ms"]) for r in requests]
    excluded = historical_spans + baseline + conflicts + positive_spans + negative_spans + old_clip_spans
    # Exclude whole gaps that intersect known readings/candidates. Do not slice
    # an existing utterance or a negative reference into an alleged new dialogue.
    gaps = complement(spans + ja_spans, end_ms)
    pool, screening = [], []
    for a, b in gaps:
        reasons = []
        if not 1000 <= b - a <= 8500:
            reasons.append("NOT_A_SHORT_DIALOGUE_GAP")
        if overlaps(a, b, excluded):
            reasons.append("INTERSECTS_EXISTING_READING_CANDIDATE_OR_REFERENCE")
        if reasons:
            screening.append(dict(start_ms=a, end_ms=b, withheld=reasons))
            continue
        jn, wn = neighbors(ja, a, b), neighbors(whisper, a, b)
        jp, jnext = jn["before_distance_ms"], jn["after_distance_ms"]
        wp, wnext = wn["before_distance_ms"], wn["after_distance_ms"]
        human_distance = min((min(abs(a - hi), abs(b - lo)) for lo, hi in positive_spans), default=float("inf"))
        context = []
        if jp is not None and jnext is not None and max(jp, jnext) <= 6000:
            context.append("BETWEEN_EXISTING_JA_WITHIN_6S")
        if human_distance <= 4000:
            context.append("NEAR_PRIOR_USER_CONFIRMED_DIALOGUE_SCOPE")
        if jp is not None and jnext is not None and min(jp, jnext) <= 4000 and wp is not None and wnext is not None and max(wp, wnext) <= 1000:
            context.append("SHORT_WHISPER_TURN_GAP_NEAR_EXISTING_JA")
        if not context:
            screening.append(dict(start_ms=a, end_ms=b, withheld=["INSUFFICIENT_DIALOGUE_CONTEXT"]))
            continue
        lo, hi = round((a + 200) * 16), round((b - 200) * 16)
        row = dict(gap_start_ms=a, gap_end_ms=b, lo=lo, hi=hi, start_ms=lo / 16, end_ms=hi / 16,
                   context_reasons=context, adjacent_JA=jn, adjacent_Whisper=wn,
                   confirmed_dialogue_scope_distance_ms=human_distance,
                   boundary_risk="200ms guard; ASR/affine estimates; adjacent existing speech may extend into gap",
                   acoustic_pattern=acoustic_pattern(pcm[lo:hi]),
                   existing_candidate_overlap_ids=[], current_or_legacy_conflict_overlap_ids=[],
                   Japanese_dialogue="UNVERIFIED", approved=False, publishable=False)
        row["same_adjacent_Whisper_reading"] = normalize_text(wn["before"]["text"]) == normalize_text(wn["after"]["text"])
        row["near_request_boundary"] = any(min(abs(t - edge) for edge in (r["request_start_ms"], r["request_end_ms"])) <= 100
                                           for r, t in ((wn["before"], a), (wn["after"], b)))
        pool.append(row)

    labels = {j["id"]: j["label"] for j in journal["judgments"]}
    references = [dict(id=r["case_id"], kind="NEGATIVE_CONTROL", label=labels[r["case_id"]],
                       lo=r["lo"], hi=r["hi"], source_WAV=r["wav_path"],
                       acoustic_pattern=acoustic_pattern(pcm[r["lo"]:r["hi"]])) for r in batch["requests"]]
    references += [dict(id=f"positive-{i:02d}", kind="POSITIVE_CONTROL", label="PRIOR_USER_CONFIRMED_DIALOGUE",
                        lo=r["start_ms"] * 16, hi=r["end_ms"] * 16,
                        prior_positive_index=r["positive_index"], confirmation_scope="CLIP_DIALOGUE_EXISTENCE_ONLY",
                        Japanese_transcript_accuracy="UNVERIFIED", source_evidence=str(args.positive_input.resolve()),
                        source_evidence_sha256=pins[str(args.positive_input.resolve())],
                        acoustic_pattern=acoustic_pattern(pcm[r["start_ms"] * 16:r["end_ms"] * 16]))
                   for i, r in enumerate(positives, 1)]
    matrix = np.array([[r["acoustic_pattern"][k] for k in FEATURE_KEYS] for r in references])
    scale = np.maximum(np.std(matrix, axis=0), 1e-6)
    positive_matrix = matrix[[r["kind"] == "POSITIVE_CONTROL" for r in references]]
    negative_matrix = matrix[[r["kind"] == "NEGATIVE_CONTROL" for r in references]]
    for row in pool:
        vector = np.array([row["acoustic_pattern"][k] for k in FEATURE_KEYS])
        pd = float(np.sqrt(np.mean(((positive_matrix - vector) / scale) ** 2, axis=1)).min())
        nd = float(np.sqrt(np.mean(((negative_matrix - vector) / scale) ** 2, axis=1)).min())
        row.update(positive_pattern_distance=pd, negative_pattern_distance=nd, pattern_margin=nd - pd)
        withheld = []
        if nd <= pd:
            withheld.append("NO_POSITIVE_OVER_NEGATIVE_PATTERN_PREFERENCE")
        if row["same_adjacent_Whisper_reading"]:
            withheld.append("IDENTICAL_ADJACENT_READING_REQUIRES_CONTINUATION_REVIEW")
        if row["acoustic_pattern"]["rms_dbfs"] < -60:
            withheld.append("NO_USABLE_SIGNAL_FOR_PATTERN_COMPARISON")
        row["withheld"] = withheld
    qualified = sorted((r for r in pool if not r["withheld"]),
                       key=lambda r: (-len(r["context_reasons"]), -r["pattern_margin"], r["lo"]))
    selected = []
    for row in qualified:
        if len(selected) >= args.max_candidates:
            break
        if any(abs((row["lo"] + row["hi"] - old["lo"] - old["hi"]) / 32) < 15000 for old in selected):
            row["withheld"].append("NEAR_AN_ALREADY_SELECTED_CONTEXT")
            continue
        selected.append(row)
    selected.sort(key=lambda r: r["lo"])
    root.mkdir(mode=0o700)
    (root / "clips").mkdir()
    (root / "contexts").mkdir()
    items = []
    for i, r in enumerate(selected, 1):
        item = dict(r, id=f"candidate-{i:02d}", kind="MISSING_DIALOGUE_PROBE", label="UNVERIFIED")
        item["probe_id"] = "r2-gap-" + hashlib.sha256(f"{batch['source_pcm_sha256']}:{r['lo']}:{r['hi']}".encode()).hexdigest()
        items.append(item)
    items += references
    for row in items:
        lo, hi = row["lo"], row["hi"]
        core = root / "clips" / (row["id"] + ".wav")
        raw = pcm16(pcm[lo:hi])
        if row["kind"] == "NEGATIVE_CONTROL":
            shutil.copyfile(row["source_WAV"], core)
            assert file_sha(core) == file_sha(row["source_WAV"])
        else:
            write_wav(core, raw)
        clo, chi = max(0, lo - 80000), min(len(pcm), hi + 80000)
        context = root / "contexts" / (row["id"] + "-context.wav")
        write_wav(context, pcm16(pcm[clo:chi]))
        row.update(start_ms=lo / 16, end_ms=hi / 16, core_file=str(core.relative_to(root)),
                   core_sha256=file_sha(core), core_pcm16_sha256=hashlib.sha256(raw).hexdigest(),
                   context_file=str(context.relative_to(root)), context_sha256=file_sha(context),
                   context_lo=clo, context_hi=chi, core_offset_seconds=(lo - clo) / 16000,
                   core_end_offset_seconds=(hi - clo) / 16000,
                   context_scope="ONLY_CORE_IS_CANDIDATE_OR_LABEL; SURROUNDING_SPEECH_NOT_NEW_DISCOVERY",
                   Japanese_dialogue="UNVERIFIED" if row["kind"] == "MISSING_DIALOGUE_PROBE" else
                   "PRIOR_CLIP_DIALOGUE_CONFIRMED" if row["kind"] == "POSITIVE_CONTROL" else "NO",
                   approved=False, publishable=False)
        if row["kind"] == "MISSING_DIALOGUE_PROBE":
            row["context_existing_candidate_ids"] = [r["cue_id"] for r in historical
                                                     if clo / 16 < r["end_ms"] and r["start_ms"] < chi / 16]
    audit = dict(status="PREPARED_SOURCE_LISTENING_PENDING", user_judgments=len(journal["judgments"]),
                 user_label_counts=journal["categorical_counts"], full_Whisper_cores=524, canonical_JA=313,
                 canonical_KO=296, absorption=17, no_output_JA_gap_count=len(gaps),
                 context_pool=len(pool), pattern_preference_count=sum(r["pattern_margin"] > 0 for r in pool),
                 selected_candidates=len(selected), positive_controls=len(positives), negative_controls=len(labels),
                 max_candidates=args.max_candidates, protected_input_pins=len(pins),
                 source_pcm_sha256=batch["source_pcm_sha256"], acoustic_feature_keys=FEATURE_KEYS,
                 reference_feature_standard_deviation=scale.tolist(), energy_ranking=False,
                 acoustic_method="25ms Hann frames/10ms hop; amplitude normalized six-band spectral flux, envelope 2..8Hz modulation fraction, envelope crossing rhythm, spectral entropy and band motion; standardized nearest reference distance, not a language classifier",
                 candidate_gate="whole 1..8.5s no-Whisper/no-JA gap; no existing/historical reading or conflict overlap; dialogue context; positive pattern closer than every negative; identical adjacent reading withheld; no minimum candidate count",
                 source_audio_listened_by_agent=False, verified_new_dialogues=0,
                 Whisper_calls=0, Reazon_calls=0, Hermes_calls=0, Gemini_calls=0, approvals=0, publications=0,
                 limitations=["Nearby JA and Whisper text are context clues, not human language ground truth",
                              "Three prior positive scopes confirm clip dialogue existence, not every frame or exact Japanese text",
                              "14 negative clips and 3 positive scopes are small, nonrandom and partly dependent; no probability/accuracy estimate",
                              "Acoustic rhythm/spectral differences can still be nonlinguistic sounds",
                              "ASR/affine boundaries are estimates; context playback must resolve continuation/duplicate ambiguity",
                              "Only exact negative cores excluded, no deletion of surrounding intervals",
                              "Whisper output-covered missed speech is outside this no-output test"])
    for path, digest in pins.items():
        assert file_sha(path) == digest, path
    save(root / "audit.json", audit)
    save(root / "review-manifest.json", dict(source_pcm_sha256=batch["source_pcm_sha256"], items=items))
    save(root / "selection-audit.json", dict(context_pool=pool, screening=screening))
    save(root / "user-judgments-r1.json", journal)
    shutil.copyfile(args.feedback, root / "user-feedback.json")
    save(root / "protected-input-pins.json", pins)
    save(root / "preparation.json", dict(r1_bundle=str(source), feedback=str(args.feedback.resolve()),
                                       positive_input=str(args.positive_input.resolve()), max_candidates=args.max_candidates))
    for script in (Path(__file__), Path(__file__).with_name("stage11_prepare_whisper_missing_probes.py")):
        shutil.copyfile(script, root / script.name)
    fields = ["kind", "id", "source_start", "source_end", "duration_seconds", "wav_path", "context_wav_path",
              "core_offset_seconds", "core_end_offset_seconds", "dialogue_presence", "Japanese_dialogue",
              "music", "effects", "groans_breathing", "human_JA_transcript", "human_absolute_start_ms",
              "human_absolute_end_ms", "Reazon_new", "verdict", "reviewer", "notes"]
    with (root / "judgment.tsv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in items:
            candidate = row["kind"] == "MISSING_DIALOGUE_PROBE"
            writer.writerow(dict(kind=row["kind"], id=row["id"], source_start=stamp(row["start_ms"]),
                                 source_end=stamp(row["end_ms"]), duration_seconds=(row["hi"]-row["lo"])/16000,
                                 wav_path=row["core_file"], context_wav_path=row["context_file"],
                                 core_offset_seconds=row["core_offset_seconds"], core_end_offset_seconds=row["core_end_offset_seconds"],
                                 dialogue_presence="PENDING" if candidate else "YES" if row["kind"] == "POSITIVE_CONTROL" else "NO",
                                 Japanese_dialogue="UNVERIFIED" if candidate else row["Japanese_dialogue"],
                                 music="YES" if row["label"] == "MUSIC" else "NOT_ASSESSED",
                                 effects="NOT_ASSESSED", groans_breathing="YES" if row["label"] == "NON_SPEECH_MOAN" else "NOT_ASSESSED",
                                 Reazon_new="NOT_EXECUTED", verdict="UNVERIFIED" if candidate else row["label"],
                                 reviewer="" if candidate else "USER_PRIOR_LISTENING", notes="Context audio is separate; judge core only"))
    make_page(root, items)
    manifest(root)
    print(json.dumps(audit, ensure_ascii=False, indent=2), flush=True)
    return root


def make_page(root, items):
    page = ['<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width">',
            '<title>일본어 누락 대사 R2 원음 판정</title><style>body{font:16px sans-serif;max-width:1000px;margin:24px auto;padding:12px}article{border:1px solid #bbb;border-radius:8px;margin:18px 0;padding:16px}audio{width:100%}label{display:inline-block;margin:8px}textarea{display:block;width:95%}button{padding:8px;margin:8px}small{display:block;color:#555}</style>',
            '<h1>일본어 누락 대사 R2 — 원음 판정</h1>',
            '<p>압축을 푼 뒤 이 파일을 Safari/Chrome에서 여세요. 새 STT는 실행하지 않았습니다. 후보는 모두 미확정입니다. 주변 대사와 신음을 포함한 문맥 WAV에서 <b>표시한 본문 범위만</b> 판정하세요. 앞뒤 기존 대사는 새 누락 대사로 세지 않습니다.</p>',
            '<p>후보 원음 → 문맥 원음 → 본문 다시 듣기 순서로 확인하세요. 일본어 대사 / 신음·호흡 / 음악 / 효과음 / 무대사 / 불명확을 구분하고, 대사가 있으면 들리는 문장과 실제 원본 시각을 적으세요. 아래 입력은 브라우저를 닫으면 사라질 수 있으니 TSV 저장 버튼을 누르세요.</p>',
            '<button onclick="downloadTSV()">판정 TSV 저장</button><a href="judgment.tsv" download>빈 판정표 다운로드</a>']
    for row in items:
        candidate = row["kind"] == "MISSING_DIALOGUE_PROBE"
        title = row["id"] + " · " + ("누락 의심 후보 / UNVERIFIED" if candidate else "양성 대조군 / 기존 대사 존재 확인" if row["kind"] == "POSITIVE_CONTROL" else "음성 대조군 / " + row["label"])
        page.append(f'<article data-id="{row["id"]}"><h2>{html.escape(title)}</h2><p>원본 본문 {stamp(row["start_ms"])}–{stamp(row["end_ms"])} / {(row["hi"]-row["lo"])/16000:.3f}초</p>')
        if candidate:
            reason = "; ".join(row["context_reasons"])
            jn = row["adjacent_JA"]
            page.append('<p>선정 이유: ' + html.escape(reason) +
                        f'. 인접 JA 거리: 앞 {jn["before_distance_ms"]}ms / 뒤 {jn["after_distance_ms"]}ms. 앞뒤 Whisper 출력 사이 공백이며 기존 후보 본문 중첩 0. 음향 패턴 비교는 언어 대사의 증거가 아닙니다.</p>')
            warnings = sorted({warning for side in ("before", "after")
                               for warning in row["adjacent_Whisper"][side]["warnings"]})
            if warnings:
                page.append('<p>인접 Whisper 문맥의 기존 검토 경고: ' + html.escape(", ".join(warnings)) +
                            '. 본문과의 중첩은 없으며 주변 모델 문장의 정확도도 미확정입니다.</p>')
        page.append(f'<p>본문 WAV</p><audio controls preload="none" src="{row["core_file"]}"></audio>')
        page.append(f'<p>앞뒤 5초 문맥 WAV — 본문은 {row["core_offset_seconds"]:.3f}–{row["core_end_offset_seconds"]:.3f}초</p><audio controls preload="none" src="{row["context_file"]}"></audio>')
        page.append(f'<button onclick="playCore(this,{row["core_offset_seconds"]},{row["core_end_offset_seconds"]})">문맥 WAV에서 본문만 재생</button>')
        if candidate:
            page.append('<label>판정 <select data-field="verdict">' + ''.join(f'<option>{x}</option>' for x in ('UNVERIFIED','JA_DIALOGUE','NON_SPEECH_MOAN','MUSIC','EFFECT','NO_DIALOGUE','AMBIGUOUS','EXISTING_UTTERANCE_CONTINUATION')) + '</select></label>')
            for field, label in [('dialogue_presence','대사 존재'),('Japanese_dialogue','일본어'),('music','음악'),('effects','효과음'),('groans_breathing','신음/호흡')]:
                page.append(f'<label>{label} <select data-field="{field}"><option>UNVERIFIED</option><option>YES</option><option>NO</option><option>AMBIGUOUS</option></select></label>')
            page.append('<textarea data-field="human_JA_transcript" placeholder="들리는 일본어 (추정 STT가 아닌 직접 청취) / 불명확하면 비워 두세요"></textarea>')
            for field, label in [('human_absolute_start_ms','실제 대사 원본 시작(ms)'),('human_absolute_end_ms','실제 대사 원본 종료(ms)'),('reviewer','판정자'),('notes','메모 / 기존 발화 연장 여부')]:
                page.append(f'<label>{label} <input data-field="{field}"></label>')
        page.append('<small>문맥은 본문 밖 소리도 포함하며 그 구간의 대사 여부를 자동으로 확정하지 않습니다. 모델 출력 합의로 승인하지 않습니다.</small></article>')
    page.append('''<script>
function playCore(button,start,end){const audios=button.closest('article').querySelectorAll('audio');const a=audios[1];a.currentTime=start;a.ontimeupdate=()=>{if(a.currentTime>=end){a.pause();a.ontimeupdate=null}};a.play()}
async function downloadTSV(){const response=await fetch('judgment.tsv');let raw;
try{raw=await response.text()}catch(e){alert('파일 접근을 허용하거나 빈 판정표에 직접 기록하세요.');return}
const lines=raw.trimEnd().split('\\n').map(l=>l.split('\\t'));const header=lines[0];
document.querySelectorAll('article[data-id]').forEach(article=>{const row=lines.slice(1).find(r=>r[header.indexOf('id')]===article.dataset.id);if(!row)return;article.querySelectorAll('[data-field]').forEach(input=>{row[header.indexOf(input.dataset.field)]=input.value.replace(/[\\t\\r\\n]/g,' ')})});
const blob=new Blob(['\\ufeff'+lines.map(r=>r.join('\\t')).join('\\n')+'\\n'],{type:'text/tab-separated-values;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='judgment.user.tsv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
</script></html>''')
    # Embed TSV data so Safari file:// does not need fetch/CORS or a local server.
    tsv_json = json.dumps((root / "judgment.tsv").read_text(), ensure_ascii=False).replace("<", "\\u003c")
    text = "\n".join(page)
    start = text.index("async function downloadTSV(){")
    stop = text.index("const lines=", start)
    text = text[:start] + "function downloadTSV(){const raw=" + tsv_json + ";\n" + text[stop:]
    (root / "listen.html").write_text(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r1-bundle", type=Path, required=True)
    parser.add_argument("--feedback", type=Path, required=True)
    parser.add_argument("--positive-input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-candidates", type=int, default=8)
    args = parser.parse_args()
    assert not args.output.exists(), "prepare a new output path"
    journal = record_user_judgments(args.r1_bundle, args.feedback)
    root = prepare(args, journal)
    archive = root.with_suffix(".tar.gz")
    assert not archive.exists()
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(root, arcname=root.name, filter=lambda info: None if "__pycache__" in Path(info.name).parts else info)
    print("OUTPUT=" + str(root))
    print("ARCHIVE=" + str(archive))


if __name__ == "__main__":
    main()
