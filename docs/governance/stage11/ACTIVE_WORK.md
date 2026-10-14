# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: S11-WX005
STATUS: READY_FOR_USER_REVIEW
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: stage11

## OBJECTIVE

Prepare a private, offline listening and judgment package for ten fixed FNS-247 clips using only integrity-checked saved S11-WX003/S11-WX004 evidence and existing audio. Human listening is allowed only to collect development/evaluation reference judgments; ordinary Stage11 operation must not require per-title human listening, subtitle review, or manual approval.

## APPROVED_SCOPE

- Reuse the user-specified VM122 private S11-WX004 review packet, its referenced saved result manifests, and existing source/core/context WAVs at their manifest-identified paths; verify clip identity, SHA-256, absolute source times, core/context ranges, and padding before use. Do not guess a missing source path.
- Prepare exactly `clip-003`, `clip-005`, `clip-006`, `clip-008`, `clip-014`, `clip-015`, `clip-017`, `clip-020`, `clip-002`, and `clip-011`; keep core and context playback distinct and preserve existing user labels without changing them.
- Copy only the necessary existing WAVs into the VM122 private S11-WX005 package, after verifying source hashes. Create an offline HTML review page, provenance manifest, blank judgment template, short instructions, and one ZIP package; keep directories 0700 and files 0600.
- Show core/context audio before model hypotheses; make model output disclosure user-controlled. Include existing Whisper, WhisperX raw/aligned, and ReazonSpeech evidence only where saved and present, with source ranges and title-absolute times. Do not copy model output into user judgments.
- Allow local-only judgment entry and JSON export for dialogue presence, optional transcript comparison and heard Japanese text, the two requested boundary cases, confidence, notes, actual-listening flag, reviewer USER, and audio/source provenance.
- Verify all ten clip/audio links and source hashes, relative offline playback markup, local JSON export behavior, source/time references, and absence of external resources or transmission. Save the private ZIP at a path reported to the user.
- Update the canonical handoff with readiness, verification, limits, and the next user decision. Leave routing and Stage11 task metadata at `READY_FOR_USER_REVIEW / S11-WX005` until the user returns the judgment JSON; the user may listen after this Codex session ends.

## PROHIBITED_SCOPE

- Do not run WhisperX, Whisper, ReazonSpeech, pyannote, Hermes, any LLM, or any new STT/acoustic/model call; do not install/download packages or models.
- Do not process FNS-247 beyond these ten existing clips or create subtitle output, corrections, publication, or sample-specific production logic.
- Do not modify original audio, prior results, manifests, or user judgments. Do not claim human listening or transcript/boundary/speaker truth before the user supplies it.
- Do not change Stage11/Stage12 product code, production services/GPU settings, databases, queues, timers, NAS, Jellyfin, subtitles, deployments, or public/private service exposure.
- Do not use external CDN/scripts, external network, telemetry, or data transmission. Do not upload audio, Japanese text, review JSON, private paths, credentials, or experiment artifacts to GitHub.
- Do not add a per-title human-review requirement to ordinary Stage11 operation; preserve `HUMAN_REVIEW_REQUIRED_PER_TITLE=NO` as the product goal without claiming it is implemented or quality-validated.

## ACCEPTANCE_CRITERIA

- The task is registered consistently in the router and Stage11 active-work file; both required registration governance checks pass and the activation commit is confirmed on the canonical remote before inspecting VM evidence.
- All ten items identify the correct existing core/context WAVs and cross-link verified SHA-256, source clip, absolute times, padding, and saved evidence provenance; original inputs remain unchanged.
- The private offline package provides two separate audio players per item, initially concealed model text, usable judgment fields, and local JSON download without external dependencies or transmission; the ZIP contains only the requested review package.
- Review JSON is a blank user-authored template; unresolved transcript, boundary, and speaker truth remain UNKNOWN. Human listening remains PENDING until reported by the user.
- No model calls, production writes, full-title ASR, product code changes, external publication, or Git inclusion of private material occurs.
- Canonical handoff records the package readiness and limits; governance checks pass; final canonical remote records `READY_FOR_USER_REVIEW / S11-WX005`.

## EVIDENCE

- User explicitly approved S11-WX005 for offline review package creation from stored results and ten existing clips, with zero model execution.
- Canonical branch `teddy-subtitle-stage11` was at `74b58451f976b3d6933f145f2f33ded458c575b2`; Stage11 contract is APPROVED v1.0.0 and initially INACTIVE/NONE.
- S11-WX003 saved 27/27 WhisperX outputs and 9/9 alignments; S11-WX004 verified the saved context set and paired core/context audit. Transcript and boundary truth remain unresolved pending user listening.
- The approved product goal is automated ordinary operation without per-title human review; this task collects evaluation references only and does not claim product quality.
- Registration commit `7b1bb7f42423a96699f7d6c1451d5ccd516c807c` passed both required governance checks and was confirmed on the canonical remote before VM122 evidence access.
- The private package contains exactly the ten approved items, twenty core/context WAVs, a provenance manifest, blank judgment template, offline HTML, short README, and one ZIP. All ten context SHA-256 values match; each lossless core crop matches the previously recorded original core SHA-256; ten result JSON hashes and both selected alignment source hashes match.
- The HTML uses twenty relative WAV references, hides prior labels and model hypotheses until the user marks the core listened, and contains no external resource or transmission code. The actual inline export script executed in isolated V8 with a mock DOM; JSON preserved ten blank/user judgment entries and `UNKNOWN` truth without model text.
- No GUI browser was available in the build environment, so browser file-open and audible playback were not exercised (`OFFLINE_PLAYER=PARTIAL`). WAV format, relative links, ZIP CRC, file modes, and offline HTML structure passed. No human listening occurred; user judgments remain pending.
- Existing Whisper/ReazonSpeech text was reused from the verified WX004 private review packet; WX004 records no baseline outputs for the four non-dialogue controls. This task made no new model call.

## NEXT_DECISION

The user listens to the ten core/context pairs in the private offline package and submits the exported judgment JSON; after that, validate the returned judgments and report evidence-based findings within S11-WX005.
