"""Prepare an offline, source-pinned missing-output experiment. Never run ASR.

Inputs are retained Stage11 artifacts supplied by --config; selection contains
no title, lexical, transcript, or manually chosen positive-time rules.
Requires numpy in an existing environment. Writes only to a new --output folder.
"""
import argparse
import csv
import hashlib
import html
import json
import math
import shutil
import wave
from pathlib import Path

import numpy as np


def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False,
                                    indent=2) + "\n")


def merge(intervals, end):
    result = []
    for a, b in sorted(intervals):
        a, b = max(0, a), min(end, b)
        if a >= b:
            continue
        if result and a <= result[-1][1]:
            result[-1][1] = max(b, result[-1][1])
        else:
            result.append([a, b])
    return result


def complement(intervals, end):
    result, cursor = [], 0
    for a, b in merge(intervals, end):
        if cursor < a:
            result.append([cursor, a])
        cursor = b
    if cursor < end:
        result.append([cursor, end])
    return result


def overlaps(lo, hi, spans):
    return [row for row in spans if lo < row[1] and row[0] < hi]


def acoustic_features(samples):
    """Non-model measurements; no VAD, voice classification or speech truth."""
    x = np.asarray(samples, dtype=np.float64)
    assert np.isfinite(x).all()
    frames = x[:len(x) // 1600 * 1600].reshape(-1, 1600)
    assert len(frames)
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    db = 20 * np.log10(np.maximum(rms, 1e-12))
    power = abs(np.fft.rfft(frames * np.hanning(1600), axis=1)) ** 2
    frequency = np.fft.rfftfreq(1600, 1 / 16000)
    band = power[:, (frequency >= 300) & (frequency <= 3400)]
    fraction = band.sum(axis=1) / np.maximum(power.sum(axis=1), 1e-24)
    flatness = np.exp(np.mean(np.log(np.maximum(band, 1e-24)), axis=1)) / np.maximum(band.mean(axis=1), 1e-24)
    active = (db >= -45) & (fraction >= .15)
    modulation = float(np.percentile(db, 90) - np.percentile(db, 10))
    median_flatness = float(np.median(flatness))
    active_fraction = float(active.mean())
    return dict(rms_dbfs=float(20 * np.log10(max(np.sqrt(np.mean(x ** 2)), 1e-12))),
                band_power_fraction_median=float(np.median(fraction)),
                band_flatness_median=median_flatness,
                frame_energy_modulation_db=modulation,
                acoustic_active_fraction=active_fraction,
                measured_frame_count=len(frames),
                score=active_fraction * (1 - median_flatness) * (1 + min(modulation, 20) / 20),
                interpretation="ACOUSTIC_ACTIVITY_ONLY_NOT_VAD_OR_DIALOGUE")


def pcm16(samples):
    return (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()


def write_wav(path, raw):
    with wave.open(str(path), "wb") as f:
        f.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        f.writeframes(raw)


def stamp(ms):
    milliseconds = round(ms)
    seconds, milli = divmod(milliseconds, 1000)
    minutes, second = divmod(seconds, 60)
    hour, minute = divmod(minutes, 60)
    return f"{hour:02d}:{minute:02d}:{second:02d}.{milli:03d}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cfg, root = read(args.config), args.output.resolve()
    assert not root.exists(), "output must be a new directory"
    count = cfg["count"]
    assert 8 <= count <= 12
    pins = read(cfg["preserved_pins"])
    for path, digest in read(cfg["previous_input_pins"]).items():
        assert path not in pins or pins[path] == digest, path
        pins[path] = digest
    for path, digest in cfg["task_input_pins"].items():
        assert path not in pins or pins[path] == digest, path
        pins[path] = digest
    pins[str(args.config.resolve())] = file_sha(args.config)
    pins[str(Path(__file__).resolve())] = file_sha(__file__)
    for path, digest in pins.items():
        assert file_sha(path) == digest, path
    print(f"INPUT_PINS=PASS ({len(pins)})", flush=True)

    alignment = read(cfg["alignment"])
    assert pins[alignment["trusted_seed"]] == alignment["trusted_seed_sha256"]
    execution = Path(cfg["execution_root"])
    plan = read(execution / "whole-short-plan.json")
    summary = read(execution / "results.json")
    assert summary["status"] == "COMPLETE_CANDIDATES_ONLY"
    assert summary["completed"] == len(plan["windows"]) == 524
    pcm = np.memmap(cfg["source_pcm_path"], dtype="<f4", mode="r")
    pcm_sha = pins[cfg["source_pcm_path"]]
    assert pcm_sha == plan["source_pcm_sha256"] == alignment["source_pcm_sha256"]
    end = len(pcm) / 16
    cursor, segments, empty = 0, [], []
    for row in plan["windows"]:
        assert row["core_lo"] == cursor
        cursor = row["core_hi"]
        prefix = execution / f"core-{row['index']:04d}"
        done = read(prefix.with_suffix(".done.json"))
        assert done["status"] in ("SUCCEEDED", "SUCCEEDED_EMPTY")
        assert all(done[k] == row[k] for k in ("index", "core_lo", "core_hi") if k in done)
        for suffix, key in ((".request.npy", "request_sha256"), (".wire.json", "response_sha256"),
                            (".segments.json", "segments_sha256")):
            assert file_sha(prefix.with_suffix(suffix)) == done[key]
        request = np.load(prefix.with_suffix(".request.npy"), allow_pickle=False)
        assert request.dtype == np.dtype("<f4") and request.ndim == 1
        assert np.array_equal(request, pcm[row["audio_lo"]:row["audio_hi"]])
        absolute = read(prefix.with_suffix(".segments.json"))
        assert len(absolute) == done["segment_count"]
        if not absolute:
            empty.append(row["index"])
        segments.extend((s["start_ms"], s["end_ms"]) for s in absolute)
    assert cursor == len(pcm)
    rec = read(cfg["reconciliation"])
    assert sorted(segments) == sorted((r["segment"]["start_ms"], r["segment"]["end_ms"])
                                     for r in rec["records"])
    ja = [(s["start_ms"], s["end_ms"]) for s in alignment["external_JA"]]
    assert len(ja) == 313
    whisper_gaps = complement(segments, end)
    both_gaps = complement(segments + ja, end)

    legacy = read(cfg["legacy_reconciliation"])
    conflict_ids = {rid for pair in legacy["overlapping_pairs"]
                    if pair["kind"] == "AMBIGUOUS_CONFLICT" for rid in pair["record_ids"]}
    old_conflicts = [(r["segment"]["start_ms"], r["segment"]["end_ms"])
                     for r in legacy["records"] if r["record_id"] in conflict_ids]
    # Current conflicting alternatives are already blocked by ALL raw segments.
    baseline = [(s["start_ms"], s["end_ms"]) for s in alignment["baseline_Whisper"]]
    previous = read(cfg["previous_batch"])
    prior_clips = [(r["original_lo"] / 16, r["original_hi"] / 16) for r in previous["requests"]]
    for path in cfg["prior_reazon_results"]:
        assert path in pins
        saved = read(path)
        requests = saved.get("case_requests", [r["request"] for r in saved["results"] if "request" in r])
        for row in requests:
            prior_clips.append((row["original_lo"] / 16, row["original_hi"] / 16) if "original_lo" in row
                               else (row["clip_start_ms"], row["clip_end_ms"]))
    excluded = segments + ja + baseline + old_conflicts + prior_clips
    historical = read(cfg["historical_candidates"])
    historical_spans = [(s["start_ms"], s["end_ms"], s["cue_id"]) for s in historical]
    audio_features = read(cfg["historical_audio_features"])
    feature_spans = [(s["start_ms"], s["end_ms"], s) for s in audio_features]
    pool = []
    guard = cfg["boundary_guard_ms"]
    for a, b in complement(excluded, end):
        left, right = a + guard, b - guard
        if right - left < cfg["min_probe_ms"]:
            continue
        mid = (left + right) / 2
        lo = math.ceil(max(left, mid - cfg["max_probe_ms"] / 2) * 16)
        hi = math.floor(min(right, mid + cfg["max_probe_ms"] / 2) * 16)
        assert not overlaps(lo / 16, hi / 16, excluded)
        features = acoustic_features(pcm[lo:hi])
        row = dict(lo=lo, hi=hi, eligible_gap_start_ms=a, eligible_gap_end_ms=b,
                   timeline_bin=min(count - 1, int(mid / end * count)) + 1,
                   acoustic_features=features,
                   historical_long_candidate_overlap_ids=[s[2] for s in overlaps(lo / 16, hi / 16, historical_spans)],
                   historical_feature_windows=[s[2] for s in overlaps(lo / 16, hi / 16, feature_spans)])
        pool.append(row)
    selected = []
    populations = []
    for index in range(1, count + 1):
        eligible = [r for r in pool if r["timeline_bin"] == index and r["acoustic_features"]["acoustic_active_fraction"] >= .25]
        populations.append(dict(timeline_bin=index,guarded_gaps=sum(r["timeline_bin"] == index for r in pool),
                                acoustic_eligible=len(eligible)))
        assert eligible, f"no acoustic probe in bin {index}; do not invent speech evidence"
        selected.append(max(eligible, key=lambda r: (r["acoustic_features"]["score"], -r["lo"])))

    root.mkdir(mode=0o700)
    (root / "clips").mkdir(mode=0o700)
    shutil.copyfile(args.config, root / "preparation-config.json")
    shutil.copyfile(cfg["alignment"], root / "source-alignment.json")
    shutil.copyfile(__file__, root / "prepare.py")
    requests = []
    for index, row in enumerate(selected, 1):
        lo, hi = row["lo"], row["hi"]
        case_id = f"missing-{index:02d}"
        raw = pcm16(pcm[lo:hi])
        wav = root / "clips" / f"{case_id}.wav"
        write_wav(wav, raw)
        identity = hashlib.sha256(f"{pcm_sha}:{lo}:{hi}".encode()).hexdigest()
        requests.append(dict(row, kind="WHISPER_MISSING_PROBE", case_id=case_id,
                             probe_id="missing-probe-" + identity, review_order=index,
                             original_lo=lo, original_hi=hi, wav_path=str(wav), wav_sha256=file_sha(wav),
                             speech_presence="UNCONFIRMED", Whisper_readings=[],
                             overlap_external_cue_ids=[], conflicting_group_ids=[],
                             dialogue_existence="PENDING_ORIGINAL_AUDIO_REVIEW",
                             Japanese_accuracy="UNVERIFIED", semantic_decision="AMBIGUOUS",
                             approved=False, publishable=False,
                             input_pcm16_subset_sha256=hashlib.sha256(raw).hexdigest(),
                             input_float32_sha256=hashlib.sha256((np.frombuffer(raw, dtype="<i2").astype("<f4") / 32768).tobytes()).hexdigest()))
    controls = [r for r in previous["requests"] if r["kind"] == "NEGATIVE_CONTROL"]
    assert len(controls) == 4
    for old in controls:
        row = dict(old)
        assert row["speech_presence"] == "NO_SPEECH_CONFIRMED_BY_USER"
        assert file_sha(row["wav_path"]) == row["wav_sha256"]
        reference = root / "clips" / (row["case_id"] + "-reference30.wav")
        shutil.copyfile(row["wav_path"], reference)
        assert file_sha(reference) == row["wav_sha256"]
        lo, hi = row["lo"], row["hi"]
        raw = pcm16(pcm[lo:hi])
        assert hashlib.sha256(raw).hexdigest() == row["previous_input_pcm16_subset_sha256"]
        wav = root / "clips" / (row["case_id"] + "-core20.wav")
        write_wav(wav, raw)
        row.update(original_lo=lo, original_hi=hi, wav_path=str(wav), wav_sha256=file_sha(wav),
                   reference30_wav_path=str(reference), reference30_wav_sha256=file_sha(reference),
                   acoustic_features=acoustic_features(pcm[lo:hi]), approved=False, publishable=False)
        requests.append(row)
    for row in requests:
        with wave.open(row["wav_path"]) as w:
            assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 16000, row["hi"] - row["lo"])
            raw = w.readframes(w.getnframes())
        assert raw == pcm16(pcm[row["lo"]:row["hi"]])
        assert hashlib.sha256(raw).hexdigest() == row["input_pcm16_subset_sha256"]
        assert hashlib.sha256((np.frombuffer(raw, dtype="<i2").astype("<f4") / 32768).tobytes()).hexdigest() == row["input_float32_sha256"]
    batch = {k: previous[k] for k in ("installed_path", "model_id", "revision")}
    batch.update(requests=requests, source_pcm_path=cfg["source_pcm_path"], source_pcm_sha256=pcm_sha,
                 duration_ms=end, purpose="INDEPENDENT_WHISPER_MISSING_OUTPUT_PROBES",
                 approved=0, publishable=False, Whisper_calls=0, Reazon_calls=0, Hermes_calls=0, Gemini_calls=0)
    save(root / "batch-plan.json", batch)
    save(root / "input-pins.json", pins)
    save(root / "gap-ledger.json", dict(decoded_end_ms=end, Whisper_no_output=whisper_gaps,
                                      Whisper_and_JA_no_output=both_gaps, guarded_probe_pool=pool))
    audit = dict(status="PREPARED_UNVERIFIED_AUDIO", completed_Whisper_cores=524,
                 raw_Whisper_observations=len(segments), empty_response_cores=empty,
                 decoded_end_ms=end, requested_video_end_ms=plan["duration_ms"],
                 terminal_quantization_ms=plan["duration_ms"] - end,
                 Whisper_gap_count=len(whisper_gaps), Whisper_gap_ms=sum(b-a for a,b in whisper_gaps),
                 Whisper_and_JA_gap_count=len(both_gaps), Whisper_and_JA_gap_ms=sum(b-a for a,b in both_gaps),
                 guarded_probe_gaps=len(pool), selection_population=populations,
                 probe_count=count, negative_controls=4, independent_VAD_intervals="NOT_AVAILABLE",
                 independent_speech_presence_evidence="NOT_ESTABLISHED",
                 independent_acoustic_activity="EXACT_SOURCE_PCM_NON_MODEL_MEASUREMENTS",
                 historical_audio_feature_rows=len(audio_features),
                 historical_features_provenance="NO_SOURCE_SHA_OR_METHOD_IN_OLD_JSON; CONTEXT_ONLY",
                 existing_conflict_pairs=len([p for p in rec["overlapping_pairs"] if p["kind"] == "AMBIGUOUS_CONFLICT"]),
                 legacy_conflict_record_spans_excluded=len(old_conflicts),
                 selection_policy="one highest acoustic score per equal-duration bin; 1s boundary guard; 4..12s exact gaps; acoustic active fraction >=.25; not a random accuracy sample",
                 acoustic_method="100ms nonoverlapping frames, Hann rFFT, 300..3400Hz power/flatness; active RMS>=-45dBFS and band fraction>=.15; score=active_fraction*(1-flatness)*(1+min(p90-p10 RMS dB,20)/20)",
                 boundary_guard_ms=guard, inferred_verified_dialogues=0, audio_listened_by_agent=False,
                 run_readiness="INPUTS_READY; HUMAN_DIALOGUE_GROUND_TRUTH_PENDING; NO_INFERENCE_EXECUTED",
                 canonical_JA=313, canonical_KO=296, absorption=17, approvals=0, publications=0,
                 Whisper_calls=0, Reazon_calls=0, Hermes_calls=0, Gemini_calls=0,
                 preserved_input_pins=len(pins), source_pcm_sha256=pcm_sha,
                 limitations=["Segment and affine JA boundaries are estimates; guard does not certify a missing utterance",
                              "Whisper hallucinations may cover real missed speech; uncovered-time search is incomplete",
                              "Acoustic activity can be music, sound effects, groans, breathing or dialogue",
                              "Historical non-conflicting long candidates may overlap; retained IDs prohibit claims of first-ever discovery",
                              "Ground truth must be recorded before revealing new Reazon text; disagreement is not automatic accuracy",
                              "Four known negatives are case controls, not a whole-video false-recognition-rate sample"])
    save(root / "audit.json", audit)
    original_runner = Path(cfg["previous_runner"]).read_text()
    runner = original_runner
    replacements = {
        "assert len(requests)==16 and sum(c['kind']=='NEGATIVE_CONTROL' for c in requests)==4":
        f"assert len(requests)=={count+4} and sum(c['kind']=='NEGATIVE_CONTROL' for c in requests)==4",
        "assert len(set(c['group_id'] for c in requests if c['kind']=='SUPPLEMENTAL'))==12":
        f"assert len(set(c['probe_id'] for c in requests if c['kind']=='WHISPER_MISSING_PROBE'))=={count}",
        "PREFLIGHT=PASS; candidates=12; controls=4; approvals=0":
        f"PREFLIGHT=PASS; missing-probes={count}; controls=4; approvals=0",
        "prefix='stage11-reazon-full12-controls-result-'": "prefix='stage11-reazon-missing-probes-result-'"}
    for before, after in replacements.items():
        assert runner.count(before) == 1
        runner = runner.replace(before, after)
    inference_marker = "load_start=time.monotonic();"
    assert runner[runner.index(inference_marker):] == original_runner[original_runner.index(inference_marker):]
    (root / "run-batch.py").write_text(runner)
    # Intentionally offer only a preflight command in this preparation task.
    (root / "preflight.sh").write_text('#!/bin/bash\nset -euo pipefail\ncd -- "$(dirname -- "$0")"\nexport CUDA_VISIBLE_DEVICES="" OMP_NUM_THREADS=1 MKL_NUM_THREADS=1\n' +
                                      f'{batch["installed_path"]}/venv/bin/python run-batch.py --preflight\n')
    fields = ["kind", "id", "source_start", "source_end", "duration_seconds", "wav_path", "Whisper", "JA", "rms_dbfs",
              "dialogue_presence", "Japanese_dialogue", "music", "effects", "groans_breathing", "human_JA_transcript",
              "human_absolute_start_ms", "human_absolute_end_ms", "Reazon_new", "previous_Reazon", "verdict", "reviewer", "notes"]
    with (root / "judgment.tsv").open("w") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(fields)
        for row in requests:
            writer.writerow([row["kind"], row["case_id"], stamp(row["lo"]/16), stamp(row["hi"]/16), (row["hi"]-row["lo"])/16000,
                             row["wav_path"], "NO_OUTPUT" if row["kind"] == "WHISPER_MISSING_PROBE" else "EXISTING_FALSE_TEXT_REFERENCE",
                             "NO_ALIGNED_JA" if row["kind"] == "WHISPER_MISSING_PROBE" else "CONTROL_REFERENCE",
                             round(row["acoustic_features"]["rms_dbfs"], 3),
                             "PENDING" if row["kind"] == "WHISPER_MISSING_PROBE" else "USER_CONFIRMED_NO_DIALOGUE",
                             "PENDING" if row["kind"] == "WHISPER_MISSING_PROBE" else "NO",
                             "PENDING", "PENDING", "PENDING", "", "", "", "NOT_EXECUTED", row.get("previous_Reazon_text", ""),
                             "AMBIGUOUS", "", ""])
    page = ['<!doctype html><meta charset="utf-8"><title>Whisper 누락 독립 탐지 청취</title>',
            '<style>body{font:16px sans-serif;max-width:1100px;margin:30px auto}table{border-collapse:collapse;width:100%}td,th{border:1px solid #aaa;padding:8px}audio{width:280px}</style>',
            '<h1>Whisper 미출력 구간 독립 탐지 — 원음 청취</h1>',
            '<p>선정 10개는 음향 활동이 있는 미확정 시험 구간입니다. VAD 결과나 실제 대사로 확정하지 않았습니다. WAV 전체가 시험 입력이며 문맥 대사가 섞이지 않도록 기존 출력 경계에서 1초를 띄웠습니다. 시각은 원본 타임라인 기준입니다.</p>',
            '<p>새 STT 결과를 보기 전에 judgment.tsv에 대사 존재·일본어 여부·음악·효과음·신음/호흡을 각각 기록하세요. 실제 대사가 있으면 원음에서 대사 시각·청취문을 적습니다. 불분명하면 AMBIGUOUS를 유지하세요. 이후 Reazon의 존재 탐지·문장 정확도·시각을 따로 평가하며, 문맥/기존 후보 중복은 새 대사로 세지 않습니다.</p>',
            '<table><tr><th>ID</th><th>원본 시각</th><th>원음</th><th>상태</th></tr>']
    for row in requests:
        label = "원음 판정 대기" if row["kind"] == "WHISPER_MISSING_PROBE" else "기존 사용자 확인 무대사 대조군"
        page.append(f'<tr><td>{html.escape(row["case_id"])}</td><td>{stamp(row["lo"]/16)}–{stamp(row["hi"]/16)}</td><td><audio controls preload="none" src="clips/{Path(row["wav_path"]).name}"></audio></td><td>{label}</td></tr>')
    page.append('</table><p>대조군 입력은 이전과 동일한 20초 PCM입니다. clips/control-*-reference30.wav에는 당시 청취한 30초 원음도 바이트 그대로 보존했습니다. 신규 모델 호출·승인·게시 0회.</p>')
    (root / "listen.html").write_text("\n".join(page))
    for path, digest in pins.items():
        assert file_sha(path) == digest, path
    (root / "SHA256SUMS").write_text("".join(file_sha(p) + "  " + str(p.relative_to(root)) + "\n"
                                            for p in sorted(root.rglob("*")) if p.is_file()))
    print("OUTPUT=" + str(root), flush=True)
    print(json.dumps(audit, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
