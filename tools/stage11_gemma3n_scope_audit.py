"""Offline Pilot B scope audit; never loads or calls a model/service.

Preserve clip-level human truth without promoting estimated core boundaries.
Prepare anonymous audio-only arms and a fixed prompt; NOT an inference runner.
"""
import argparse
import csv
import hashlib
import html
import json
import shutil
import wave
from collections import Counter
from pathlib import Path


PROMPT = """Analyze only the attached audio. Distinguish intelligible spoken words
from non-linguistic moaning, groaning, breathing, panting, music and other sounds.
Do not turn non-linguistic vocalizations into words or invent missing speech.
Use DIALOGUE for intelligible speech, NON_DIALOGUE for no intelligible speech,
MIXED for intelligible speech together with non-dialogue sounds, and AMBIGUOUS
when the audio does not support a reliable decision. Non-dialogue vocal sounds
alone are NON_DIALOGUE. Quote Japanese only when actually audible; otherwise
leave japanese_transcript empty. Do not translate other languages into Japanese.
Return one JSON object with exactly these keys:
{"verdict":"DIALOGUE|NON_DIALOGUE|MIXED|AMBIGUOUS",
 "japanese_transcript":"", "reason":"brief acoustic evidence",
 "utterances":[{"start_s":0.0,"end_s":0.0,"language":"","text":""}]}
Times are approximate seconds relative to this attached audio, not video time.
Use an empty utterances list when there are no heard words. If heard speech
cannot be localized, use null for its start_s and end_s. Do not infer dialogue
from presumed surrounding context. Output JSON only."""


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1048576), b""):
            h.update(b)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False,
                                    indent=2) + "\n")


def wav(path):
    with wave.open(str(path)) as f:
        assert (f.getnchannels(), f.getsampwidth(), f.getframerate()) == (1, 2, 16000)
        return f.getnframes(), f.readframes(f.getnframes())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pilot-a", type=Path, required=True)
    p.add_argument("--human-notes", type=Path, required=True)
    p.add_argument("--r2", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    assert not args.output.exists(), "Use a new output directory"
    original = read(args.pilot_a / "dataset.json")
    evidence = read(args.pilot_a / "input-audit.json")
    pins = read(args.pilot_a / "protected-input-pins.json")
    for path, digest in pins.items():
        assert sha(path) == digest, path
    for root in evidence["manifests"]:
        root = Path(root)
        for line in (root / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split(None, 1)
            assert sha(root / name.lstrip("*")) == digest, name
    notes = read(args.human_notes)
    human = {r["group_id"]: r for r in notes["rows"]}
    r2 = {r["id"]: r for r in read(args.r2 / "review-manifest.json")["items"]}
    assert Counter(r["label"] for r in original) == dict(
        SPEECH=13, NON_SPEECH_MOAN=11, MUSIC=2, NO_DIALOGUE=1)
    args.output.mkdir(parents=True)
    (args.output / "core").mkdir()
    (args.output / "context").mkdir()
    scope, blind, truth = [], dict(core=[], context=[]), []
    for row in original:
        prov, case = row["provenance"], row["id"]
        assert sha(row["wav_path"]) == row["wav_sha256"]
        if row["label"] == "SPEECH":
            note = human[prov["group_id"]]
            assert note == prov["human_note"] and note["speech_presence"] == "CONFIRMED_SPEECH"
            a, b = prov["core_start_ms"], prov["core_end_ms"]
            core = args.pilot_a / "short-parts" / (case + ".wav")
            context = Path(row["wav_path"])
            frames, pcm = wav(context)
            lo, hi = round((a-row["start_ms"])*16), round((b-row["start_ms"])*16)
            assert wav(core) == (hi-lo, pcm[lo*2:hi*2])
            scope.append(dict(id=case, review_order=prov["review_order"],
                group_id=prov["group_id"], core_start_ms=a, core_end_ms=b,
                core_seconds=(b-a)/1000, context_start_ms=row["start_ms"],
                context_end_ms=row["start_ms"]+frames/16,
                core_boundary_source="HISTORICAL_STT_ESTIMATE",
                human_truth_scope="ORIGINAL_LISTENING_CLIP_WITH_CONTEXT",
                core_truth="UNCONFIRMED", context_truth="CONFIRMED_SPEECH",
                human_absolute_speech_times=None, human_transcript=note["confirmed_ja"],
                original_user_note=note["notes"], core_wav_sha256=sha(core),
                context_wav_sha256=sha(context)))
            core_truth, context_truth = None, "SPEECH"
        else:
            core = Path(row["wav_path"])
            item = r2[prov["original_id"]]
            context = args.r2 / item["context_file"]
            assert sha(context) == item["context_sha256"]
            frames, pcm = wav(context)
            lo, hi = item["lo"]-item["context_lo"], item["hi"]-item["context_lo"]
            assert wav(core) == (hi-lo, pcm[lo*2:hi*2])
            a, b = row["start_ms"], row["start_ms"]+row["samples"]/16
            core_truth, context_truth = row["label"], None
        for arm, path in (("core", core), ("context", context)):
            dest = args.output / arm / (case + ".wav")
            shutil.copyfile(path, dest)
            frames, _ = wav(dest)
            assert frames <= 30*16000
            blind[arm].append(dict(id=case, audio=str(Path(arm) / dest.name),
                                  wav_sha256=sha(dest), samples=frames, sample_rate=16000))
        truth.append(dict(id=case, original_label=row["label"],
                          original_wav_sha256=row["wav_sha256"],
                          core_label=core_truth, context_label=context_truth,
                          core_start_ms=a, core_end_ms=b))
    assert len(scope) == 13 and all(r["core_truth"] == "UNCONFIRMED" for r in scope)
    save(args.output / "scope-audit.json", dict(positives=scope,
        verified_core_positives=0, unconfirmed_core_positives=13,
        scope_transfer_allowed=False, shared_context=notes["shared_audio_review"],
        no_core_negatives_inferred_from_yamnet=True, protected_sha_verified=len(pins)))
    save(args.output / "truth.json", truth)
    save(args.output / "audio-only-inputs.json", blind)
    (args.output / "fixed-prompt.txt").write_text(PROMPT + "\n")
    save(args.output / "protocol.json", dict(model="google/gemma-3n-E2B-it",
        fallback="E4B feasibility only; no substitution with Gemma 4",
        prompt_sha256=sha(args.output / "fixed-prompt.txt"),
        prompt_applied_to_model=False, input_arms=dict(core=27, context=27),
        output_verdicts=["DIALOGUE", "NON_DIALOGUE", "MIXED", "AMBIGUOUS"],
        generation=dict(do_sample=False, max_new_tokens=512),
        pass_criteria=dict(core_detection_minimum=10, negative_false_positive_maximum=1),
        context_only_speech_counts_as_core_success=False,
        unconfirmed_core_truth_excluded_from_success=True,
        ambiguous_count_separate=True, all_model_outputs_unverified_until_comparison=True,
        inference_status="NOT_EXECUTED", actual_model_used=False))
    fields = ["id", "core_dialogue", "Japanese_dialogue", "heard_Japanese",
              "absolute_start_ms", "absolute_end_ms", "context_only_dialogue",
              "reviewer", "notes"]
    with (args.output / "core-judgment.template.tsv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(dict(id=r["id"], core_dialogue="PENDING",
                             Japanese_dialogue="PENDING") for r in scope)
    page = ['<!doctype html><html lang="ko"><meta charset="utf-8">',
            '<title>Pilot B 본문 원음 판정</title>',
            '<h1>Pilot B: 양성 13개 본문 범위 확인</h1>',
            '<p>Gemma 추론은 실행되지 않았습니다. 기존 정답은 문맥 포함 클립의 대사 존재 확인입니다. '
            '본문만 → 문맥 → 본문만 순서로 듣고 core-judgment.template.tsv에 판정을 적으세요. '
            '본문 경계는 기존 STT 추정이며, 문맥에만 들리는 대사를 본문 양성으로 옮기지 마세요. '
            '들린 일본어와 실제 발화 원본 시각을 기록하고 불분명하면 AMBIGUOUS를 유지하세요.</p>',
            '<table><tr><th>ID</th><th>본문 원본 시각(ms)</th><th>본문만</th><th>문맥 포함</th></tr>']
    for r in scope:
        case = html.escape(r["id"])
        page.append(f'<tr><td>{case}</td><td>{r["core_start_ms"]}–{r["core_end_ms"]}</td>'
                    f'<td><audio controls preload="none" src="core/{case}.wav"></audio></td>'
                    f'<td><audio controls preload="none" src="context/{case}.wav"></audio></td></tr>')
    page.append('</table></html>')
    (args.output / "listen-core.html").write_text("\n".join(page))
    print("SCOPE AUDIT: 13 context positives, 0 verified core positives; model calls 0")


if __name__ == "__main__":
    main()
