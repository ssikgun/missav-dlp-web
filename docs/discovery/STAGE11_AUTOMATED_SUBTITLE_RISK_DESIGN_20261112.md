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

## 4. Options for the user (not yet selected)

| Option | Concept | Benefit | Main downside / approval needed |
| --- | --- | --- | --- |
| **A. Observation-only risk sidecar** | Independently note evidence gaps and suspect context-only candidates; produce diagnostics without editing subtitles | Small, safe first step; reuse frozen code/provenance and avoid wrong deletion | Does **not** solve missed dialogue or false text in actual Korean subtitles; requires a subsequent decision to act |
| **B. Bounded second-evidence path for suspicious gaps** | *Future* acquisition of an independent signal for candidate-free intervals, optional targeted no-VAD hypothesis in bounded audio regions, then proof of ownership/timing and conservative decision | Could address cases a cue-only repetition classifier cannot catch | New audio/model runs, cost, VAD and context false-positives, duplication risk; **not currently authorized**; no automatic text acceptance |
| **C. Risk-conditioned insertion/suppression in real subtitle output** | Only after a separate, validated source-of-truth policy and semantic ownership test would a confirmed case affect the Japanese/KO text path | Could improve final visible subtitles rather than only logs | Highest false insertion/deletion and semantic spill risk; **requires new design choices, testing, thresholds/acceptance approval, product implementation and release authorization** |

**Non-binding sequencing proposal:** A → independently validate if B is viable → decide whether C is safe. This ordering is a suggestion, **not an approved implementation roadmap**. Do **not** auto-enable no-VAD model calls or suppress text merely because a segment overlaps silence/music reported in six chosen clips.

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

For design review, a proportionate first choice is whether to **record risks only (A)** or pursue a new separately approved **audio-evidence acquisition protocol (B)**. Converting evidence into automatic subtitle repair/filtering (C) must remain blocked until the user chooses how it interacts with Japanese-master versus whole-title-primary translation and a credible reference/validation method exists.

**Status:** `PROPOSAL_ONLY`; no product code, model inference, audio transfer, deployed settings, thresholds, published subtitles or external systems were changed to produce this document. `STAGE11_PRODUCT_QUALITY=INCONCLUSIVE`.
