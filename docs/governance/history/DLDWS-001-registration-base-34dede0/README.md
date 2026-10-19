# DLDWS-001 registration source records

These four files are byte-for-byte copies of the active routing and task records at canonical base commit `34dede0af5bc205ff11af4275727e11627de680b` on `teddy-subtitle-stage11`. They preserve the full pre-registration GOV-006, DL-001, and DWS-001 records and the router state from which DLDWS-001 was registered.

The original active records remain available in the base commit. To restore an individual original record in a future isolated worktree, use `git restore --source=34dede0af5bc205ff11af4275727e11627de680b -- <original-path>`. Do not treat an archived status or task ID as current authorization.

| Original path | Archived path | Base Git blob SHA |
|---|---|---|
| `docs/governance/ACTIVE_WORK.md` | `router-ACTIVE_WORK.md` | `f29d99b0bc0725cd755da0f5aaefd695b86fa759` |
| `docs/governance/governance/ACTIVE_WORK.md` | `governance-ACTIVE_WORK.md` | `39c001bd3ab564959edd74c3c615d5c854354ab2` |
| `docs/governance/downloader/ACTIVE_WORK.md` | `downloader-ACTIVE_WORK.md` | `c336f560c6759cb6447309d0bac5826af0f5dac9` |
| `docs/governance/discovery-writer-safety/ACTIVE_WORK.md` | `discovery-writer-safety-ACTIVE_WORK.md` | `d1d6316280cac5b87ad3de4a0c4dfacf10298d91` |

Stage11 files are intentionally not included or changed.
