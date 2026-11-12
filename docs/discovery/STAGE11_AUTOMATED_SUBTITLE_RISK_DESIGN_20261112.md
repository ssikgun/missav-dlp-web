# Stage11 automatic subtitle risk handling — alternatives and design boundaries

**Document status:** `PROPOSED / DESIGN_ONLY / NOT_IMPLEMENTED`  
**Task:** `S11-DESIGN001 / IN_PROGRESS`  
**Canonical branch:** `teddy-subtitle-stage11`  
**Evidence baseline:** S11-WX011 frozen 16-window scorecard and S11-RISK001 six-sample saved-evidence trial, as documented before this task.

## 1. Why this design is needed

Stage11 aims to make natural Korean subtitles automatically, combining trusted Japanese external subtitles with audio evidence while recovering missed dialogue **without inserting invented dialogue or requiring per-title human review**. The currently approved design contract explicitly keeps the following **unresolved**: (a) the integration/priority between a coverage-complete Japanese master and whole-title primary Korean translation, (b) semantic accuracy, exact utterance boundaries and speaker quality, and (c) numeric acceptance thresholds.

Prior **risk-selected** samples suggest two different failure possibilities, without establishing objective error rates:

| Class | Illustrative frozen cases | Saved-evidence observation | Not established |
| --- | --- | --- | --- |
| Potential omission | S03, S11, S15 | A reported later speech period outlasts stored candidate intervals (S03); or user speech report with zero candidate intersections in four saved conditions (S11/S15) | Independently located/correct Japanese utterance, exact boundary, why the first model missed it |
| Potential ungrounded Japanese candidate | S04, S08, S13 | Non-dialogue user reports coincide with **broad context-scale** candidate intervals, sometimes originating in an adjacent core; S13 has candidates in Demucs conditions only | That any particular Japanese word occurs in the short WAV, confirmed hallucination or downstream published SRT contamination |

The six were chosen **because** they appeared suspicious; technical 3/3 + 3/3 labeling is **not** population precision/recall. Stored JSON validity proves stored evidence integrity, not transcription correctness. There is no independently validated Japanese transcript truth (0/16 frozen windows). Original source-core WAV provenance was **not rechecked** in the last risk task.

## 2. Verified implementation facts (canonical repository, not installed runtime)

- `teddy_discovery_asr_gpu_worker.py`: regular `process_request` detects speech regions with Silero before transcribing; `process_targeted_request` accepts one bounded whole window **without running Silero**. This is an available code path, **not** permission to run it or proof it helps.
- `teddy_discovery_asr_source_quality.py`: examines validated **existing** ASR segments for narrow nonlexical/repetition signs; `REQUIRE_SECOND_EVIDENCE` is actionable for structural intra-cue repetition. A completely absent cue does not enter this classifier.
- `teddy_discovery_targeted_second_evidence.py` and `teddy_discovery_stage11_controller.py`: targeted second-evidence planning uses existing sources with `REQUIRE_SECOND_EVIDENCE`; it cannot by itself manufacture a detection source for a zero-cue interval.
- `teddy_discovery_stage11_normal_mode.py`: normal HYBRID mode requires accepted external Japanese evidence and records `supplemental_status = DISABLED_UNVERIFIED_ACCURACY`. Existing speculative supplemental candidates must not silently enter published subtitles.
- `teddy_discovery_subtitle_publish.py` preserves a separate Stage12 publication boundary; the verified source does **not** grant Stage11 risk heuristics ownership over subtitle publication or replacements.

**VERIFY_REQUIRED:** installed VM122/production revisions versus the canonical repository and any effect of these rules on real deployed outputs have not been shown by this source inspection.

## 3. Proposed boundary: risk observation is not text authority

Conceptual information flow, **not implementation**:

1. **Source identity / accepted time map:** immutable source IDs, hash, source core, candidate ownership, sample interval, existing cue IDs, and exact source provenance.
2. **Acoustic candidate/coverage observations:** trusted external Japanese availability (if any), existing ASR hypotheses, speech-region metadata (if authorized later), candidate coverage/gaps, and all confidence/independence limits.
3. **Risk record (separate sidecar):** `MISSING_DIALOGUE_POSSIBLE`, `UNSUPPORTED_CANDIDATE_POSSIBLE`, or `UNRESOLVED`; carries source IDs, reason, evidence references, and `not_ground_truth=true`. **No Japanese text edit**, cue deletion, timestamp shift, or automatic subtitle insertion.
4. **Separate evidence and decision gate:** only if authorized and actually supported; escalate unsupported cases to abstention. No global policy or numerical cutoffs in this document.
5. **Existing semantic/materialization and Stage12:** Hermes remains semantic/translation owner under approved contract; deterministic code retains identity, mapping, validation and safe publication ownership. Stage12's no-overwrite/collision protections remain unchanged.

Candidate segment overlap must be represented as **temporal intersection of a broad context output**, not verified dialogue inside the short clip. A fully absent ASR cue must be represented as **absence of ASR evidence**, not absence of speech. User/Gemini reports stay separate from independent ground truth.

## 4. Options and user-selected design priority (B)

| Option | Concept | Benefit | Main downside / approval needed |
| --- | --- | --- | --- |
| **A. Observation-only risk sidecar (supporting B only)** | Independently note evidence gaps and suspect context-only candidates; produce diagnostics without editing subtitles | Small, safe first step; reuse frozen code/provenance and avoid wrong deletion | Does **not** solve missed dialogue or false text in actual Korean subtitles; requires a subsequent decision to act |
| **B. Bounded second-evidence path for suspicious gaps (USER-SELECTED DESIGN PRIORITY)** | *Future* acquisition of an independent signal for candidate-free intervals, optional targeted no-VAD hypothesis in bounded audio regions, then proof of ownership/timing and conservative decision | Could address cases a cue-only repetition classifier cannot catch | New audio/model runs, cost, VAD and context false-positives, duplication risk; **not currently authorized**; no automatic text acceptance |
| **C. Risk-conditioned insertion/suppression in real subtitle output** | Only after a separate, validated source-of-truth policy and semantic ownership test would a confirmed case affect the Japanese/KO text path | Could improve final visible subtitles rather than only logs | Highest false insertion/deletion and semantic spill risk; **requires new design choices, testing, thresholds/acceptance approval, product implementation and release authorization** |

**User clarification (2026-11-12): B is the primary Stage11 improvement direction.** A is a protective diagnostics/abstention feature **within** B, not the destination. C is a future controlled integration/publishing outcome after separate evidence, architecture, implementation and release approval. The user has approved prioritizing **B for design discussion**, not performing B's audio/model inference now. Do **not** auto-enable no-VAD model calls or suppress text merely because a segment overlaps silence/music reported in six chosen clips.

## 4a. B-primary design: candidate-free speech discovery and bounded evidence

**Status: PROPOSED DESIGN ONLY. The user selected B as the objective, NOT authorization to execute B.**

### Core distinction

**Discovery** must identify a possibly spoken interval even when first-pass ASR emits **zero segments**. The currently implemented ASR source-quality classifier inspects only **existing segments**, and the existing targeted second-evidence planner selects only `REQUIRE_SECOND_EVIDENCE` *source cues*. A zero-cue interval therefore cannot enter the current planner; simply invoking its present API again, changing text filters, or lowering a fixed VAD setting **does not solve the zero-cue discovery problem**. Why S11/S15 originally lacked candidates is **unverified**; do not assign blame to Silero, WhisperX, Demucs, source mapping or an acoustic condition without new evidence.

**Verification** then uses an explicitly bounded, source-owned audio interval to request a separate hypothesis (where separately authorized), never assuming the response is a Japanese fact. **Acceptance** of dialogue into the Japanese/KO path is an entirely different, higher-authority question for later user decision.

### Candidate-free interval discovery — alternatives within B

| Candidate discovery signal | Could detect absent ASR cues? | Limitation / treatment |
| --- | --- | --- |
| Trusted external Japanese cue mapped to source audio with no matching ASR cue | Only for speech already represented in validated external text | External JA may be incomplete, misaligned or itself non-dialogue; cannot prove coverage of totally missing dialogue |
| Retained acoustic speech-region observations, computed independently of ASR candidate *text* and mapped to the audio source | Potentially, **if** they contain the missed interval | If the same first-pass VAD omitted the region, its stored output alone is insufficient; voice activity includes noises and vocalizations |
| Bounded candidate-free audio gaps inferred from accepted source coverage / first-pass intervals | Can **nominate** unexamined portions of audio even if no ASR text exists | Absence of text is not evidence of speech; without another acoustic/linguistic signal, blindly checking every gap can waste resources or generate fabricated dialogue |
| Separate local-only acoustic/speech-likelihood observation not tied to initial ASR cue creation (new future evidence) | May supply a truly independent trigger where the first VAD was blind | Model choice, compute cost, independence, false-alarm behavior, privacy and implementation are **VERIFY_REQUIRED**, not selected or authorized |

**Proposed feasibility ordering:** First check which *already retained* source-coverage/VAD metadata exist for a target and whether each signal would nominate candidate-free intervals. If all signals depend on the same missed region, document a **detection blind spot** rather than claiming the issue is solved; a future, independently approved bounded audio-based trigger would be needed. Do **not** use the prior hand-picked six cases' listening classifications as an automatic production trigger.

### B evidence lifecycle (conceptual only; no current execution)

1. **Establish source ownership**: verified video/audio source identity, core/time mapping, immutable existing external-JA and ASR source indexes. Invalid provenance means `INCONCLUSIVE`, no new candidate.
2. **Nominate gap**: a specific independent-ish observation says `SPEECH_POSSIBLE_WITHOUT_ASR_CUE`, or the system records only `UNOBSERVED_GAP` if there is no speech-supporting signal. Keep these states distinct. Do not infer silence from no ASR text.
3. **Bound and deduplicate**: future offline caller defines a deterministic, source-anchored region with conservative limits and a stable interval ID. Trim to accepted source bounds, avoid duplicate re-requests/overlap with existing accepted cue ownership; preserve ability to abstain. **No numeric window sizes, thresholds or retry limits are approved here.**
4. **Request second evidence** (new future task only): prefer reusing the implemented `process_targeted_request` no-Silero bounded transcription interface if independent feasibility evidence supports it. Its existence does not verify quality or authorize an inference. Alternative models are not automatically selected.
5. **Bind hypothesis, not truth**: keep source hash, interval/core/time offsets, runtime/model version, ASR result hash, origin and contradictory evidence. Require precise ownership before any hypothesis can be considered; support speech-present/no-text, no-candidate, non-lexical and conflict outcomes without synthesizing Japanese words.
6. **Conservative cross-check**: compare accepted external-JA evidence and existing original ASR with a bounded second hypothesis, avoiding a context-wide sentence crossing a tiny interval. A second model's agreement is still **not independent Japanese ground truth**. If ambiguous, no text insertion/deletion.
7. **Defer Japanese/KO integration**: only a later approved authority policy may create/reassign source cues and decide whether to repair a Japanese master before Hermes's whole-title/partitioned translation. Hermes cannot own source time/cue IDs or Stage12 publishing. No automatically recovered text reaches CLEAN/Stage12 under this design review.

### Safe result states (example, unimplemented)

| Future risk outcome | Interpretation | Current permitted action |
| --- | --- | --- |
| `GAP_UNOBSERVED` | No ASR cue, no independently supported speech signal | Record only; cannot assert no dialogue or trigger unbounded transcription |
| `SPEECH_POSSIBLE_NO_CUE` | Separate observation indicates possible speech despite no ASR cue | Record a bounded follow-up candidate **only after future authorization**; not Japanese source truth |
| `SECOND_HYPOTHESIS_ONLY` | Bounded recheck offers a Japanese text candidate or remains empty | Hold as hypothesis; requires provenance and decision evidence |
| `CONTEXT_ONLY_NON_DIALOGUE_RISK` | Broad candidate crosses interval reported as music/non-lexical | Preserve candidate context ownership, do not attribute or delete spoken text automatically |
| `EVIDENCE_CONFLICT_OR_UNKNOWN` | Model/text/acoustic reports disagree or provenance is missing | Abstain, preserve existing approved sources and publication protections |

These states are illustrative and **do not create production enum values, thresholds or authority**. A sidecar/A-style risk record is used for traceability **inside B**, not a replacement for dialogue-recovery work.

### Minimum future B feasibility test — another user approval required

- Validate the installed, actual Stage11 source-to-audio identity and pinned prior artifacts before comparing any new output; source-core input provenance recheck is still `NOT_PERFORMED`.
- Predeclare a tiny, bounded trial with **both expected-speech and expected-non-dialogue controls**. Previously saved S03/S11/S15 and S04/S08/S13 can be exploratory probes only; they are **not** independent accuracy ground truth. Do not select arbitrary new user files or expand the frozen WX011 set in this design task.
- Compare **normal-ASR, candidate-free nomination, and proposed bounded no-VAD** outputs separately. Record additional calls, time/CPU/GPU cost and unsupported hypotheses without publishing subtitles. User/Gemini labels remain suggestive, not independent Japanese references.
- **Feasibility reporting**: Could an evidence source nominate zero-cue gaps? Did bounded second evidence produce audio-source-bound hypotheses? Were non-dialogue spans conservatively rejected or abstained? Did provenance/no-overwrite pass? Note failures and unknown Japanese accuracy; do not convert technical PASS into product PASS.
- If credible independent speech/transcript labels cannot be obtained, explicitly report `PRODUCT_QUALITY=INCONCLUSIVE` and avoid inventing a false-dialogue detection rate or deploying automatic acceptance/suppression. Do not repeatedly rerun the same six model tests merely to manufacture confidence.

### Future design-approval questions (not answered here)

1. What **independent speech-supporting trigger** is available to nominate candidate-free audio regions without scanning the entire title with a heavy model?
2. What is the acceptable bound on additional audio work/compute and privacy exposure for everyday unattended operation? **Numerical values are not approved.**
3. When and under what evidence can a second hypothesis change trusted external Japanese source cues, given the unresolved **coverage-complete Japanese master versus Hermes whole-title primary translation** integration? The user must approve any architecture/authority conflict.
4. How should an unresolved gap be reported without pretending it was recovered, silently inventing speech, or blocking unrelated Stage9 completion?

## 4b. Prior-model evidence and bounded feasibility precheck (2026-11-12)

**Authorization:** user approved preparing the next *small isolated B trial's scope and acceptance criteria*. The present `S11-DESIGN001` is **documentation-only**; model/audio execution has **not** been approved by that task.

### Historical experiments — do not repeat as if new

- **YAMNet Pilot A (2026-10-10): technical execution succeeded, trigger acceptance FAIL.** On 27 historically user-labeled clips, the predeclared frame-top-1 speech rule flagged **13/13 context-containing speech clips**, but **13/14 non-dialogue clips** were also flagged (including moans/music/no-dialogue); alternate predeclared mean-top-1 detected only **10/13** speech clips and still flagged **4/14** non-dialogue. There was no independently validated Japanese wording or exact core speech timing. These are **historical pilot-specific denominators**, not the WX011 16-window population. **Do not use YAMNet as a sole Japanese dialogue trigger** or retrofit thresholds to make its previous failure look like a pass.
- **Pilot B Gemma 3n (2026-10-10): `BLOCKED_SAFE_STOP / MODEL_NOT_EVALUATED`.** Lacking compatible audio-capable runtime, access or suitable resources, **no inference occurred**. It offers no evidence of speech-detection quality. Do not substitute Gemma 4 or a text-only GGUF and call the previous pilot validated; current VM122 state must be checked separately before any later new execution.
- **Core STT evaluation (2026-10-11):** historical Whisper hypotheses intersected 13/13 *user-labeled* candidate cores, Reazon localized tokens in 11/13, but **confirmed correct Japanese dialogue recoveries remained 0/13**. Multiple systems producing text does not demonstrate correct wording or ownership, and archived historical audio-to-WX011 PCM bridging remains unresolved when original archived WAVs are unavailable. Do not restart searches for the lost archive.
- **Canonical current GPU worker output contract:** `process_request` invokes Silero internally, but its response contains `vad_region_count` and ASR segments; it **does not return each VAD region's beginning/end**. The persisted baseline ASR artifact schema contains segments, not independent VAD region geometry. Whether **other already-saved, source-hash-bound** VAD/acoustic observations exist for the relevant WX011 source is still **VERIFY_REQUIRED**. The no-VAD targeted method already exists but **cannot choose the missing interval by itself**.

### B preflight outcomes, separated by evidence level

| Proposed step | Read-only now? | Result / next boundary |
| --- | --- | --- |
| Reuse saved six-window WX011 WAV/manifest/WhisperX hashes and risk-selected reports | Yes; previous task already verified these, **do not repeat unchanged checks** | Technically pinned for six; source-core provenance outside that pinned bridge remains `NOT_PERFORMED` |
| Review historical Pilot A score/protocol and Pilot B feasibility conclusions | Yes; canonical document evidence | `PASS / REVIEWED`; YAMNet sole trigger **REJECTED for current design**, Pilot B `MODEL_NOT_EVALUATED` |
| Derive candidate-free **language** intervals from baseline ASR segment strings or VAD count alone | No, insufficient information | `UNRESOLVED` by current contracts; zero cue is not proof of silence or language |
| Inventory existing independent acoustic region records attached to **the same verified audio source** | Future bounded **read-only** check | `VERIFY_REQUIRED`; no unrelated archive searches or guessing based on matching timestamps |
| Run an independent trigger / no-VAD second ASR hypothesis on bounded archived audio | Requires separate approval for a **new isolated model/audio trial** | `NOT_RUN` now; no deployment or accepted text |
| Insert, delete, translate, publish, or replace subtitles | Not within this design task | `NOT_AUTHORIZED` |

### Proposed minimum future isolated trial (not executed)

1. **Entry gate:** check current actual VM122 resource availability without changing running services; verify the exact pinned source/audio identity, original source/core mapping and saved output IDs. Missing identity => `VERIFY_REQUIRED` and stop for that sample; do not equate identical timestamp with identical waveform.
2. **Small fixed probes:** use existing, user-selected **S03/S11/S15** suspected dialogue and **S04/S08/S13** suspected non-dialogue only as preliminary probes; the preceding six-case stored-evidence heuristic is already complete and **must not be rerun as a new accuracy test**. Any extra independent control set would need separately approved scope/verified existing private source identities; no broad scan or new arbitrary media inputs.
3. **Trigger feasibility gate:** first determine if a speech-supporting signal **not derived solely from existing ASR text** can nominate the zero-cue interval. If only YAMNet's historical false-positive-prone rule or a count without region times is available, document `TRIGGER_NOT_VALIDATED`; do **not** invent speech windows from model output.
4. **Optional bounded second inference**, *only after new task registration and explicit permission*: compare the existing VAD-first path with the already implemented targeted no-VAD path on strictly source-owned windows; retain both empty results and competing hypotheses with input/model/engine SHA and time provenance. Avoid running text generators on all blank audio and avoid changing the current worker/config.
5. **Evaluation contract:** report separately (a) whether candidate-free regions were **nominated**, (b) whether second hypotheses were produced and bound to those regions, (c) non-dialogue false-alarm/unsupported-text examples, (d) CPU/GPU/time/resource cost, and (e) the frequency of `UNKNOWN/ABSTAIN` without claiming validated Japanese text. A **technical feasibility PASS** may be supported by correct provenance and bounded behavior; **Japanese text accuracy / full automatic subtitle quality remain `UNKNOWN / INCONCLUSIVE`** without independent references.
6. **Safety gate:** no overwrites of frozen WAV/results, no external uploads, no source/cue/time identity shifts, no sample-specific production rules, no Japanese text promoted to a master/KO subtitle, no Stage12 publication. If evidence or compute budget is inadequate, stop safely rather than adjusting model thresholds ad hoc.

**Next decision:** propose a separate, specifically scoped `B` feasibility task and have the user approve its source-bound audio work, model invocation and resource budget **before** any execution. The design review does **not** pre-authorize those operations. Source-of-truth/whole-title architecture decision remains open.

## 5. Important failure modes to decide against

- **Zero-cue blind spot:** repeat-text quality scoring cannot find real dialogue that produced no ASR cue; a new audio-coverage observation would be needed. Silero may be involved, but cause is **not verified**.
- **Long-context spill:** an output segment spanning a different core or 20–30 seconds can overlap a 4-second listening clip without proving its text belongs there; naive overlap-to-text assignment can fabricate a subtitle.
- **Wrong deletion:** absence of another model's candidate or a Gemini non-dialogue classification is not sufficient to delete a real line, especially where a trusted Japanese external subtitle exists.
- **Wrong insertion:** Gemini/WhisperX text agreeing with a user speech-present report does not make the particular Japanese words or timing correct. No automatic inclusion from unverified hypotheses.
- **Boundary/speaker drift:** changes to source cue ownership or sentence cuts can move meaning across neighbors or confuse speakers; preserve existing deterministic boundary authority.
- **Exposure and sampling bias:** the 6 selected cases were flagged beforehand and compared with user/Gemini; none can demonstrate general error rates, independent Japanese WER/CER or production readiness.
- **Operational independence:** ordinary titles should complete without a person listening to every title; uncertainty must not invent text or silently compromise Stage9 completion, Stage12 identity, or existing subtitles.

## 6. Future verification proposal (requires another authorization)

Use a very small **independent** evaluation protocol with both positive and negative examples, preferably existing, without copying private media to public Git or requiring every-title manual review. Before enabling any product logic, independently validate speech presence and a limited Japanese transcription/timing reference where available. Compare separate measures for omission risk, unsupported-candidate risk, invalid abstentions, semantic cue drift, and no-overwrite safety. If reference data are unavailable, explicitly use `UNKNOWN` instead of a fabricated PASS or rate.

Do not prescribe numerical thresholds, trigger counts, production default settings, whole-title scanning frequency, an outside model provider, or runtime CPU/GPU changes until a separately approved task confirms legitimate independent references and product risk/cost trade-offs.

## 7. User-owned architecture choice still open

The Stage11 contract records both:

- **Coverage-complete Japanese master**: external-JA + supported ASR evidence → repaired/coverage-complete Japanese master → Hermes → Korean.
- **Whole-title-primary Korean translation**: Hermes whole-title-first semantic process with bounded fallback, with accepted boundary ownership.

These are **not automatically reconciled** by this memo. The user must approve the integration/order/authority if the eventual risk-handling implementation depends on choosing one. This document does **not** change that contract or select a final architecture.

## 8. Next design decision

**B is already the user-selected design priority** (2026-11-12), so do not re-present A vs B as an unresolved target choice. Next, review the proposed zero-cue discovery sources and bounded B gates in section 4a, then prepare a **separately scoped proposal** for isolated audio-evidence feasibility validation with model execution clearly disclosed for explicit user approval. The crucial unresolved decision remains what evidence can justify automatic Japanese source repair and how the approved coverage-complete-JA goal integrates with whole-title Hermes translation; no product architecture or thresholds are selected here. A is only a conservative support function; C, operational integration, publication and any actual audio/model run remain unauthorized.

**Status:** `PROPOSAL_ONLY`; no product code, model inference, audio transfer, deployed settings, thresholds, published subtitles or external systems were changed to produce this document. `STAGE11_PRODUCT_QUALITY=INCONCLUSIVE`.
