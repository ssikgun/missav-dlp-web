# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: S11-WX010
STATUS: BLOCKED
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
- Canonical registration and private pre-inference protocol lock revision 5 are verified. Protocol SHA-256: `1459a287a03a16d4b925b19a01812bcbae3f9a5d01cec360e0eed989335d9905`; core plan: `6343c841d07b9f04e79967b3d406f2d3d35efef260967a08fddbe6e449d68752`; model assets: `04f5fd33a8c393636f8f721d682a5e5c7c322f87e909c24f4254cd840c1c4c63`; runner: `8f950f4799f8be3b1bdddce3adc159b717ad0ea12de298687e27ef852bca5ecf`; lock: `6aaa95cb04f978d41f51d83dccdbc22f4b048b083b1d501e9b34b56d694afce7`. The 175-core plan selects 28 stratified random cores and 30 regression-sentinel cores (53 combined evaluation cores). Source SHA and all 13 prior evidence manifest references passed revalidation.
- Three failed decode attempts are preserved in the private manifest/history: the first stopped before source decoding due to FFmpeg's missing private library path; the second used `async=0` and emitted 165,024,427 frames / 10,314.0266875 seconds; the third used timestamp-preserving resampling and emitted 167,365,545 frames / 10,460.3465625 seconds, 875 frames short of the 167,366,420-frame PTS-derived target. Both mismatched WAVs and their manifests are archived privately with SHA-256. Revision 5 pins exactly 875 zero-valued samples at the stream tail, records that the last 54.7 ms are padded and their speech content is UNKNOWN, and retains the exact frame-count gate.
- The third decode passed: 175/175 original cores are complete, and the full 16 kHz mono PCM has 167,366,420 frames / 10,460.40125 seconds and SHA-256 `33b7adea820004cfbaba24a2f42e187f7bfe36c4363b729a9845598d778a8325`; the extraction manifest SHA-256 is `05c701eb7dbb71006b8321472c9da2dd2387ee6a0f6ea81c483c18bf9e892e69`. Demucs completed 175/175 cores with no failures. Independent read-only verification of every original input link/SHA, stem SHA, 16 kHz mono float geometry, planned frame count, and time-mapping flag passed. The Demucs manifest SHA-256 is `b97f463b53a11d55cc28b106427f65ac22e827a05fa514b9e795aeb3dc8ca82f`; processing time totals 9,353.188 seconds, CPU time 18,384.869 seconds, and maximum process RSS 2,136.2 MiB.
- The controller stopped with `PARTIAL` after 2/9 workloads when the first WhisperX condition failed before model loading: the runner accessed `whisperx.__version__`, which is absent in the installed module even though the distribution metadata reports version 3.8.6. WhisperX output files and manifests are 0; pyannote did not start and has 0 outputs. The revision-5 runner and protocol are hash-bound to the completed Demucs outputs, so changing the runner/environment cannot be treated as a same-lock resume. No safe continuation under the frozen lock is available; S11-WX010 is `BLOCKED` pending the user's decision on how to proceed. Do not create another task or resume automatically.
- At the failure check Qwen PID 1005 remained active, available RAM was 8,717.1 MiB, and free VRAM was 7,595 MiB. Whisper Worker port 8091 remained in its pre-existing not-listening state. The runner/controller stopped without changing protected services. `PRODUCTION_CHANGES=0`, `NAS_JELLYFIN_WRITES=0`, and `SUBTITLE_PUBLICATION=0`. Japanese accuracy, speaker accuracy/DER, and boundary accuracy remain `UNKNOWN`.

## NEXT_DECISION

The user must decide whether to authorize a safe continuation path that preserves the revision-5 Demucs provenance while correcting the isolated runner's version check, or to leave S11-WX010 incomplete. Do not create a new task ID or resume model execution automatically. Translation, integration, operational changes, publication, or product-quality claims require separate scope and authorization.
