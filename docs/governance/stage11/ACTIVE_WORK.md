# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: S11-WX010
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: stage11

## OBJECTIVE

Run the separately approved, isolated FNS-247 whole-title audio evidence evaluation to compare original and Demucs inputs across the four frozen WhisperX conditions and two pyannote conditions. Report measured evidence and uncertainty without generating subtitles or changing production.

## APPROVED_SCOPE

- FNS-247 only, using the verified source SHA-256 `442e19dd0c45df924ecac28c76f4b3c18b19f53f0e5a00e3abd76bb650a84651` and approximately 02:54:20.40 runtime. Reuse validated WX007–WX009 evidence, JA index/mapping, model snapshots, and isolated environments where hashes and settings match.
- Cover the title with 60-second ownership cores, up to 5 seconds of context on each side, 60-second hop, and clipped context at title edges. Freeze exact core/sample mapping, ownership, overlap handling, evaluation strata/seed, manifests, and resume rules before any WX010 model output.
- Generate Demucs 4.1.0 `htdemucs` vocals once per verified source interval (7-second segment, one shift, 0.25 overlap); reuse each identical validated stem for both VAD settings. Validate source time origin, sample rate, channels, frame count, duration, and SHA.
- Run WhisperX 3.8.6 / large-v3 / Japanese / float16 / batch 1 / beam 5 / best-of 5 / temperature 0 / no prompt or hotwords / Silero 30-second VAD chunks / offset 0.363 in four conditions: original at onset 0.50 and 0.45, and Demucs vocals at onset 0.50 and 0.45. Pin and record actual model revisions and all settings.
- Run pyannote.audio 4.0.7 `pyannote/speaker-diarization-community-1` revision `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee` on original and Demucs inputs. Preserve regular and exclusive diarization; speaker IDs remain local to each core.
- Compare Japanese ASR candidates with the 313-cue external JA index using raw JA times and the existing affine video-time mapping separately. Evaluate candidate recovery, omission, repeated/conflicting output, non-speech false dialogue, transcript and boundary evidence, speaker turns, cross-core edges, candidate-to-turn linkage, and resource cost. Use independent references where available; otherwise report `UNKNOWN`.
- Store audio, Japanese text, detailed turns, and evaluation artifacts only under VM122 `/home/teddy/stage11-whisperx-ab-private/analysis/S11-WX010/`. Use a dedicated isolated environment/cache and an independent resumable runner. Keep Qwen and Whisper Worker running and meet at least 4096 MiB free VRAM and 6144 MiB available RAM before each new model workload.
- Preserve the final product goal of ordinary-operation Korean subtitle generation without per-title manual review. This task collects audio evidence only; Hermes, Korean translation, subtitle generation, and publication remain outside scope.

## PROHIBITED_SCOPE

- No other title, full-title Hermes or translation, Japanese master creation for operation, or Korean subtitle generation/editing/publication.
- No Stage11/Stage12 production code, service, queue, model, shared cache, database, timer, deployment, or operating environment changes. Do not stop or restart Qwen or Whisper Worker.
- No NAS/Jellyfin/production DB writes, external audio APIs, unauthorized model substitution, title/cue/text-specific hardcoding, or treating JA/ASR/diarization output as ground truth.
- No private audio, Japanese text, detailed speaker results, credentials, or user judgments in Git or public handoff. Do not overwrite WX001–WX009 private evidence.
- Preserve Stage12 ownership, collision protection, and no-overwrite boundaries. Do not resolve the contract's open JA-master versus whole-title Hermes priority.

## ACCEPTANCE_CRITERIA

- Registration is committed to and verified on canonical `teddy-subtitle-stage11` before extraction, model execution, or creation of experiment artifacts.
- Before inference, verify FNS-247 identity, duration/audio stream, source and prior-evidence hashes, actual VM122 environment/model snapshots, and freeze a private protocol SHA covering all core intervals, sample/seed algorithm, time origins, conditions, ownership/deduplication policy, metrics, failure/retry/resume behavior, and resource gates.
- Produce resumable per-core manifests and SHA-256 evidence. Report planned/completed/failed core counts for Demucs, each of four WhisperX conditions, and each of two pyannote conditions; validate all outputs and exact source-time mapping. Retain partial work safely on abort and retry only failed cores without changing settings.
- Report JA coverage separately from verified transcription. Separate candidate recovery, candidate loss, repeat/conflict risk, false dialogue on non-speech, speaker-count/turn risks, linkage status (`SUCCESS`/`AMBIGUOUS`/`FAILURE`), boundary evidence, and resource cost. Japanese accuracy, speaker accuracy/DER, and boundary accuracy remain `UNKNOWN` unless their corresponding independent references exist.
- Document regressions as well as improvements, include known WX007 failures/repeats/non-dialogue cases as frozen regression evidence, and do not invent numerical product-quality thresholds. Technical completion is not product-quality PASS.
- Keep `PRODUCTION_CHANGES=0`, `NAS_JELLYFIN_WRITES=0`, and `SUBTITLE_PUBLICATION=0`. Close only when all approved conditions and reporting are complete; otherwise keep the real state `IN_PROGRESS` or `BLOCKED` and preserve partial evidence.

## EVIDENCE

- User approved S11-WX010 after WX009's whole-title proposal; canonical base is `2d67ac1fe3a5379d627fcba1a0dd91325858296c`. Stage11 contract v1.0.0 is APPROVED.
- WX007–WX009 protocols, source/evidence hashes, JA timing, saved STT outputs, pyannote evidence, and WX009 listening judgment are recorded in the canonical handoff and private VM122 manifests. Reuse only after the live source files and hashes are reverified.
- Canonical registration and private pre-inference protocol lock revision 3 are verified. Protocol SHA-256: `cfddf18ff6833cdbc9cd07fc2d2225dd631b90c8f5aaa4941deb14dea3678e88`; core plan: `6343c841d07b9f04e79967b3d406f2d3d35efef260967a08fddbe6e449d68752`; runner: `9c86a4dcfb5a3e0d1267d299e4abd5cc6e306f522e1ab4483559dbeab6845b66`; lock: `516e476b04a656d5baeac29637726991e21cc9c566696d7ed8510db06770a0b2`. The 175-core plan selects 28 stratified random cores and 30 regression-sentinel cores (53 combined evaluation cores). Source SHA and all 13 prior evidence manifest references passed revalidation.
- Revision 2's first controller attempt stopped at FFmpeg process startup with return code 127 because the private FFmpeg shared-library directory was absent from `LD_LIBRARY_PATH`; the source audio was not decoded and there were no model outputs. The exact failed extraction manifest is preserved privately (SHA-256 `7ef634f3fa8fd30a7482788dced26574152b0df7d1c094346a1245357d836741`). Revision 3 records hashes for all 21 private FFmpeg library entries, prepends that isolated library path in the runner, and resets the current extraction manifest to `PENDING` while linking the archived failure. The corrected private runner, lock, source hash, protocol/core-plan linkage, and FFmpeg loader preflight all verify; no audio or model output existed at this checkpoint.
- At the revision-3 pre-run gate, Qwen PID 1005 remained active, available RAM was 8,766.9 MiB, and free VRAM was 7,595 MiB. Whisper Worker port 8091 remained in its pre-existing not-listening state. No protected service was changed. The runner will still check the approved 6,144 MiB RAM / 4,096 MiB free-VRAM thresholds before starting each workload.

## NEXT_DECISION

After the evidence report, the user decides whether any further isolated validation is warranted. Any translation, integration, operational change, publication, or product-quality claim requires separate scope and authorization.
