"""Isolated, audio-only YAMNet pilot. Prepare evidence, infer, then evaluate.

No imports/calls to production STT, translation, workers or subtitle writers.
All corpus paths, identities and time scopes come from evidence, not rules.
"""
import argparse
import csv
import hashlib
import json
import os
import shutil
import time
import wave
from collections import Counter
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False,
                                    indent=2) + "\n")


def verify_manifest(root):
    root = Path(root)
    count = 0
    for line in (root / "SHA256SUMS").read_text().splitlines():
        digest, relative = line.split(None, 1)
        p = (root / relative.lstrip("*")).resolve()
        assert p.is_relative_to(root.resolve()) and sha(p) == digest, str(p)
        count += 1
    return count


def samples(path):
    import numpy as np
    with wave.open(str(path)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 16000)
        assert w.getcomptype() == "NONE"
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").copy()
    assert len(x) > 0
    return x


def pcm16(x):
    import numpy as np
    # Match historical listening-WAV encoding exactly (truncation, not rounding).
    return (np.clip(x, -1, 1) * 32767).astype("<i2")


def prepare(args):
    import numpy as np
    cfg, root = read(args.config), args.root
    assert not (root / "dataset.json").exists(), "Do not overwrite an existing pilot"
    assert read(root / "protocol.json")["fixed_before_inference"]
    evidence = {p: verify_manifest(p) for p in cfg["manifest_roots"]}
    pins = read(cfg["protected_pins"])
    for p, digest in pins.items():
        assert sha(p) == digest, p
    save(root / "protected-input-pins.json", pins)
    source = read(cfg["negative_plan"])
    assert sha(source["source_pcm_path"]) == source["source_pcm_sha256"]
    pcm = np.memmap(source["source_pcm_path"], dtype="<f4", mode="r")
    positive = read(cfg["positive_manifest"])["groups"]
    notes = read(cfg["positive_notes"])
    labels = {r["group_id"]: r for r in notes["rows"]}
    assert len(positive) == len(labels) == 13
    negative = read(cfg["negative_journal"])
    with open(cfg["negative_tsv"]) as f:
        rows = {r["id"]: r for r in csv.DictReader(f, delimiter="\t")}
    assert sha(cfg["negative_tsv"]) == negative["updated_judgment_sha256"]
    plan = {r["case_id"]: r for r in source["requests"]}
    dataset, blind, auxiliary = [], [], []
    (root / "clips").mkdir()
    (root / "short-parts").mkdir()

    def append(original, start_ms, label, provenance):
        case_id = f"clip-{len(dataset)+1:03d}"
        dest = root / "clips" / (case_id + ".wav")
        shutil.copyfile(original, dest)
        x = samples(dest)
        b = dict(id=case_id, wav_path=str(dest), wav_sha256=sha(dest),
                 start_ms=start_ms, samples=len(x))
        blind.append(b)
        dataset.append(dict(**b, label=label, provenance=provenance))
        return case_id, x

    for g in positive:
        n = labels[g["group_id"]]
        assert n["speech_presence"] == "CONFIRMED_SPEECH" and n["reviewer"] == "user"
        p = Path(cfg["positive_manifest"]).parent / g["clip_relative"]
        assert sha(p) == g["clip_sha256"]
        s = g["source_audio"]
        assert sha(s["source_npy"]) == s["source_sha256"]
        origin = np.load(s["source_npy"], allow_pickle=False).reshape(-1)
        a = round((g["clip_start_ms"] - s["start_ms"]) * 16)
        b = round((g["clip_end_ms"] - s["start_ms"]) * 16)
        assert np.array_equal(samples(p), pcm16(origin[a:b])), str(p)
        case, x = append(p, g["clip_start_ms"], "SPEECH", dict(
            original_wav=str(p), group_id=g["group_id"], review_order=g["review_order"],
            human_note=n, source_audio=s, core_start_ms=g["group_start_ms"],
            core_end_ms=g["group_end_ms"], core_truth="UNVERIFIED_STT_ESTIMATED_BOUNDARIES"))
        a = round((g["group_start_ms"] - g["clip_start_ms"]) * 16)
        b = round((g["group_end_ms"] - g["clip_start_ms"]) * 16)
        core = root / "short-parts" / (case + ".wav")
        with wave.open(str(core), "wb") as w:
            w.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            w.writeframes(x[a:b].tobytes())
        auxiliary.append(dict(id=case, wav_path=str(core), wav_sha256=sha(core),
                              samples=b-a, start_ms=g["group_start_ms"]))
    for j in negative["judgments"]:
        row, request = rows[j["id"]], plan[j["id"]]
        assert row == j["after"] and row["reviewer"] == "USER"
        assert row["dialogue_presence"] == "NO" and row["verdict"] == j["label"]
        p = Path(row["wav_path"])
        assert sha(p) == j["wav_sha256"] == request["wav_sha256"]
        assert np.array_equal(samples(p), pcm16(pcm[request["lo"]:request["hi"]]))
        append(p, request["lo"]/16, j["label"], dict(original_wav=str(p),
               original_id=j["id"], human_judgment=j))
    assert Counter(r["label"] for r in dataset) == dict(
        SPEECH=13, NON_SPEECH_MOAN=11, MUSIC=2, NO_DIALOGUE=1)
    assert len({r["wav_sha256"] for r in dataset}) == 27
    save(root / "dataset.json", dataset)
    save(root / "inference-input.json", dict(clips=blind, short_parts=auxiliary))
    r2 = read(cfg["r2_manifest"])
    unverified = [r for r in r2["items"] if r["kind"] == "MISSING_DIALOGUE_PROBE"
                  and r["label"] == "UNVERIFIED"]
    assert len(unverified) == 2
    (root / "unverified-r2").mkdir()
    for r in unverified:
        p = Path(cfg["r2_manifest"]).parent / r["core_file"]
        assert sha(p) == r["core_sha256"]
        shutil.copyfile(p, root / "unverified-r2" / p.name)
    save(root / "unverified-r2/manifest.json", dict(items=unverified,
         inference="NOT_EXECUTED", ground_truth="UNVERIFIED", included_in_metrics=False))
    save(root / "input-audit.json", dict(manifests=evidence, protected_pins=len(pins),
         source_pcm_sha256=source["source_pcm_sha256"], positive_source_pcm_equality=True,
         negative_source_pcm_equality=True, positive_count=13, negative_count=14,
         shared_positive_context=notes["shared_audio_review"],
         japanese_transcript_truth=notes["transcript_verification"],
         config=cfg, config_sha256=sha(args.config), protocol_sha256=sha(root/"protocol.json")))
    print("PREPARE_VERIFIED: 27 clips / 13 auxiliary short parts / 2 R2 excluded", flush=True)


def infer(args):
    # CPU restriction is applied before TensorFlow import/model load.
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    os.environ["TF_NUM_INTRAOP_THREADS"] = "1"
    os.environ["TF_NUM_INTEROP_THREADS"] = "1"
    os.environ["OMP_NUM_THREADS"] = "1"
    import numpy as np
    import tensorflow as tf
    tf.config.set_visible_devices([], "GPU")
    tf.config.threading.set_intra_op_parallelism_threads(1)
    tf.config.threading.set_inter_op_parallelism_threads(1)
    root = args.root
    output = root / "inference"
    assert not output.exists(), "Never overwrite scores"
    protocol = read(root / "protocol.json")
    assert sha(root / "protocol.json") == read(root / "input-audit.json")["protocol_sha256"]
    inputs = read(root / "inference-input.json")
    allowed = {"id", "wav_path", "wav_sha256", "samples", "start_ms"}
    assert all(set(r) == allowed for v in inputs.values() for r in v)
    with open(args.model / "assets/yamnet_class_map.csv") as f:
        classes = list(csv.DictReader(f))
    assert len(classes) == 521 and [int(c["index"]) for c in classes] == list(range(521))
    names = [c["display_name"] for c in classes]
    speech = {names.index(c) for c in protocol["speech_classes"]}
    monitored = protocol["speech_classes"] + ["Wail, moan", "Groan", "Music", "Breathing", "Pant", "Silence"]
    model_pins = {str(p): sha(p) for p in sorted(args.model.rglob("*")) if p.is_file()}
    load_start = time.monotonic()
    with tf.device("/CPU:0"):
        model = tf.saved_model.load(str(args.model))
    load_seconds = time.monotonic() - load_start
    output.mkdir()
    shutil.copyfile(args.model / "assets/yamnet_class_map.csv", output / "class-map.csv")
    results = {}
    for arm in ("clips", "short_parts"):
        (output / arm).mkdir()
        results[arm] = []
        for row in inputs[arm]:
            assert sha(row["wav_path"]) == row["wav_sha256"]
            x = samples(row["wav_path"]).astype(np.float32) / np.float32(32768.0)
            assert len(x) == row["samples"] and np.isfinite(x).all()
            started = time.monotonic()
            with tf.device("/CPU:0"):
                scores, embeddings, spectrogram = model(tf.constant(x))
            scores = scores.numpy()
            elapsed = time.monotonic() - started
            assert scores.dtype == np.float32 and scores.shape[1] == 521
            assert np.isfinite(scores).all() and ((scores >= 0) & (scores <= 1)).all()
            # 96 STFT frames require 0.975s waveform; final pad is official.
            expected = 1 + max(0, int(np.ceil((len(x)-15600)/7680)))
            assert len(scores) == expected, (row["id"], scores.shape, expected)
            dest = output / arm / row["id"]
            np.savez_compressed(str(dest)+".scores.npz", scores=scores,
                                mean=scores.mean(axis=0), maximum=scores.max(axis=0))
            top = scores.argmax(axis=1)
            frames = []
            for i, score in enumerate(scores):
                a = i * 480
                frames.append(dict(index=i, local_start_ms=a, nominal_patch_end_ms=a+960,
                    waveform_support_end_ms=a+975, real_audio_end_ms=min(a+975, len(x)/16),
                    padding_ms=max(0, a+975-len(x)/16),
                    source_start_ms=row["start_ms"]+a,
                    source_real_end_ms=row["start_ms"]+min(a+975,len(x)/16),
                    top1=names[int(top[i])], top1_score=float(score[top[i]]),
                    speech_top1=int(top[i]) in speech,
                    top5=[dict(index=int(k), label=names[k], score=float(score[k]))
                          for k in np.argsort(-score, kind="stable")[:5]],
                    monitored_scores={c:float(score[names.index(c)]) for c in monitored}))
            mean, maximum = scores.mean(axis=0), scores.max(axis=0)
            record = dict(**row, inference_seconds=elapsed, frames=len(scores),
                primary_detected=any(int(i) in speech for i in top),
                pooled_top1=names[int(mean.argmax())],
                pooled_top1_score=float(mean.max()),
                pooled_detected=int(mean.argmax()) in speech,
                frame_top1_counts=dict(Counter(names[int(i)] for i in top)),
                monitored_mean={c:float(mean[names.index(c)]) for c in monitored},
                monitored_max={c:float(maximum[names.index(c)]) for c in monitored},
                mean_scores_521=[float(v) for v in mean],
                max_scores_521=[float(v) for v in maximum],
                top10_mean=[dict(index=int(k),label=names[k],score=float(mean[k]))
                            for k in np.argsort(-mean,kind="stable")[:10]],
                raw_scores_file=str(dest)+".scores.npz",
                raw_scores_sha256=sha(str(dest)+".scores.npz"))
            save(str(dest)+".frames.json", frames)
            save(str(dest)+".result.json", record)
            results[arm].append(record)
            print(arm, row["id"], "COMPLETE",len(scores),"frames",flush=True)
    save(output / "results.json", results)
    save(output / "execution.json", dict(status="COMPLETE", tensorflow=tf.__version__,
        devices=[d.name for d in tf.config.get_visible_devices()], gpu_visible=[],
        model_url="https://tfhub.dev/google/yamnet/1", model_pins=model_pins,
        model_load_seconds=load_seconds, clip_calls=27, auxiliary_calls=13,
        inference_input_sha256=sha(root/"inference-input.json"),
        protocol_sha256=sha(root/"protocol.json"), runner_sha256=sha(__file__),
        model_receives="ONLY normalized mono PCM float32 Tensor, 16000 Hz"))


def evaluate(args):
    root = args.root
    assert not (root / "evaluation.json").exists(), "Do not overwrite evaluation"
    execution = read(root / "inference/execution.json")
    assert execution["status"] == "COMPLETE"
    assert execution["protocol_sha256"] == sha(root / "protocol.json")
    assert execution["inference_input_sha256"] == sha(root / "inference-input.json")
    results = read(root / "inference/results.json")
    labels = read(root / "dataset.json")
    prediction = {r["id"]: r for r in results["clips"]}
    assert len(labels) == len(prediction) == 27
    rows = []
    for r in labels:
        p = prediction[r["id"]]
        assert r["wav_sha256"] == p["wav_sha256"] == sha(r["wav_path"])
        assert sha(p["raw_scores_file"]) == p["raw_scores_sha256"]
        rows.append(dict(id=r["id"], label=r["label"], original_id=r["provenance"].get(
            "original_id", str(r["provenance"].get("review_order"))),
            detected=p["primary_detected"], pooled_detected=p["pooled_detected"],
            pooled_top1=p["pooled_top1"], monitored_mean=p["monitored_mean"],
            monitored_max=p["monitored_max"], frame_top1_counts=p["frame_top1_counts"],
            model_mixed_speech_nonlexical=bool(p["primary_detected"] and set(
                p["frame_top1_counts"]) & {"Wail, moan", "Groan", "Breathing", "Pant"}),
            model_mixed_speech_music=bool(p["primary_detected"] and "Music" in p["frame_top1_counts"]),
            ambiguous_model_interpretation=(r["label"] != "SPEECH" and p["primary_detected"])
                or p["primary_detected"] != p["pooled_detected"]))
    metrics = {}
    for field in ("detected", "pooled_detected"):
        metrics[field] = {label:dict(total=sum(r["label"]==label for r in rows),
            detected=sum(r["label"]==label and r[field] for r in rows))
            for label in ("SPEECH", "NON_SPEECH_MOAN", "MUSIC", "NO_DIALOGUE")}
    tp = metrics["detected"]["SPEECH"]["detected"]
    fp = sum(metrics["detected"][l]["detected"] for l in ("NON_SPEECH_MOAN", "MUSIC", "NO_DIALOGUE"))
    pins = read(root / "protected-input-pins.json")
    for p, digest in pins.items():
        assert sha(p) == digest, p
    audit = read(root / "input-audit.json")
    for p in audit["manifests"]:
        verify_manifest(p)
    save(root / "evaluation.json", dict(status="EVALUATED", true_positive=tp,
        false_negative=13-tp, false_positive=fp, true_negative=14-fp,
        provisional_pass=tp>=10 and fp<=1, metrics=metrics, rows=rows,
        short_parts_detected=sum(r["primary_detected"] for r in results["short_parts"]),
        short_part_ground_truth="UNVERIFIED_BOUNDARIES_NOT_A_RECALL_METRIC",
        protected_pins_verified_after=len(pins), human_labels_changed=False,
        model_scores_are_dialogue_probabilities=False, r2_in_metrics=False))
    print(f"ACTUAL YAMNET: speech {tp}/13, missed {13-tp}/13, false speech {fp}/14; "
          f"{'PASS' if tp>=10 and fp<=1 else 'FAIL'}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "infer", "evaluate"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--model", type=Path)
    args = parser.parse_args()
    {"prepare": prepare, "infer": infer, "evaluate": evaluate}[args.action](args)


if __name__ == "__main__":
    main()
