# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: S11-WX011
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: stage11

## OBJECTIVE

Use a small, independently labeled sample to compare completed S11-WX010 outputs with independent Japanese transcript, speech/non-speech, timing, and speaker references, and report measured accuracy and remaining uncertainty.

## APPROVED_SCOPE

- Read-only inspection of existing S11-WX010 evidence and model outputs.
- Select and freeze at most 16 short evaluation windows using the approved categories and existing verified core/time mappings.
- Verify the source and independence of transcript, speech/non-speech, speaker, and timing references.
- Compare only items with verified independent references; report unavailable dimensions as UNKNOWN.
- Record evaluation uncertainty, regressions, and resource evidence in a new private WX011 location.

## PROHIBITED_SCOPE

- No model inference, model replacement, Demucs rerun, or audio re-extraction.
- No changes to production models, services, caches, Qwen, Whisper Worker, or Stage11/Stage12 product code.
- No Hermes, Korean translation, subtitle generation, modification, or publication.
- No NAS, Jellyfin, or production database writes.
- No product threshold/default changes.
- No private Japanese transcripts, audio, personal review records, or detailed speaker results in Git.

## ACCEPTANCE_CRITERIA

- S11-WX011 registration and canonical remote readback pass.
- Existing WX010 source and output hashes and provenance links pass read-only verification and remain unchanged.
- A reproducible, non-duplicated sample of at most 16 windows is selected and frozen with source/core/time references.
- Each proposed independent reference has a verified source and independence assessment; unavailable references remain explicitly unavailable.
- Evaluations, denominators, unknown items, regressions, and uncertainty are reported from evidence only.
- No model execution, extraction/Demucs rerun, production change, or subtitle publication occurs.

## EVIDENCE

- User approved S11-WX011 on 2026-10-16 after S11-WX010's independently verified 1,050/1,050 outputs.
- Existing locks: parent R6 protocol `fe580bea7b7c8cc27828e5af8e24dc8c766bb064e075607cfafb0614cc8f0e22`; successor-004 environment `838740b33f35403c6c76698eab87dc25e5959a8b6e713814d4720977ecbe6591`.
- Frozen WX010 core plan `6343c841d07b9f04e79967b3d406f2d3d35efef260967a08fddbe6e449d68752`; JA index `b63745df3a9bfa3f7ec895b289c12d6b069f7e8d2024355e13e24c63ef21d270`.
- WX010 outputs, models, and locks remain read-only. `R5_MANIFEST_PROVENANCE=UNRESOLVED`; no inference or private WX011 artifact is authorized before canonical registration readback.

## NEXT_DECISION

Report which independent references are actually available and whether each accuracy dimension can be measured; seek a separate decision only if new human judgments or external resources are required.
