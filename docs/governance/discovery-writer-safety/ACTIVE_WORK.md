# Discovery Writer Safety workstream — active work

WORKSTREAM: discovery-writer-safety
TASK_ID: DWS-001
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: discovery-writer-safety

## OBJECTIVE

Investigate and address Discovery Writer Unix socket lifetime races under the explicitly user-approved B option: implement a systemd socket-activation code candidate and strictly isolated offline tests, retaining all operational safeguards. DWS-001 remains independent of DL-001 MP4 serialization and S11-WX011.

## APPROVED_SCOPE

- Read-only inspect the existing Writer Unix socket lifecycle code, existing smoke tests, and prior reported socket-identity/race failures.
- After Governance-only closure, use synthetic Unix sockets under a disposable isolated test-only directory to examine inode reuse, stale socket cleanup, active listener protection, replacement after probe, replacement immediately before unlink, and forced termination/restart.
- Preserve unrelated current source, the DL-001 implementation candidate, original failed-job fragments, and S11-WX011 artifacts.
- Distinguish reproducible observed failures from hypothetical risks, report PASS/FAIL/UNKNOWN case-by-case, and compare lifecycle lock versus socket activation or other safe designs.
- Following the user's explicit 2026-10-19 B-option approval, implement Writer systemd socket-activation handling and associated scoped test changes in an isolated candidate branch/worktree only, after remote task-scope readback; keep the currently deployed Writer untouched.
- Develop an offline socket-unit/service-integration candidate without applying it to systemd or assuming unknown live unit settings. Validate inherited listening fd type, PID/count/path, no unlink, active listener safety, and restart semantics using synthetic sockets only.
- Preserve existing direct-mode safety regressions and distinguish any remaining legacy race failure from B-mode success. Report incompatible or unknown deployment details as blocked for later separate approval.

## PROHIBITED_SCOPE

- Product Writer code and scoped Writer smoke/test edits are permitted only as a reviewable, isolated B-option systemd socket-activation candidate under the user's new explicit approval. No unrelated code changes, broad test bypass, automatic production selection, or deployment are permitted.
- No real Writer socket probe/unlink/replacement, service restart, Docker build, production deployment, or real download/retry/remux/recovery.
- No access or changes to operational .tasks/.settings, failed-job .parts/TS/MP4, databases, NAS/Jellyfin, operational files, or user data.
- No changes to Downloader/DL-001, Stage11/S11-WX011, model environments, or existing candidates; no changes to approved workstream contracts.
- No production execution of new socket activation or changes to existing installed systemd unit/service settings; no Git merge to the deployed release or CT108's dirty Stage11 worktree.

## ACCEPTANCE_CRITERIA

- Shared DWS-001 registration with Governance has exact remote readback before Governance-only closure; afterward this task alone is IN_PROGRESS in router and ACTIVE_WORK with REQUIRES_WORKSTREAMS: discovery-writer-safety.
- Read-only review identifies Writer liveness, identity and unlink boundaries and correlates them with existing evidence.
- The approved isolated synthetic cases are reproduced/tested in disposable test-only directories, with observed and unverified cases clearly distinguished and no claim of operational safety without supporting evidence.
- Original safe-design investigation evidence is preserved. Under the subsequent user-approved B scope, a candidate supports inherited systemd listener sockets without Writer-side unlink and has strictly isolated synthetic tests and fail-closed validation. Any live service configuration compatibility remains UNKNOWN until separately verified.
- DL-001 and S11-WX011, original evidence, operating state, and all production data remain unchanged.

## EVIDENCE

- This workstream was registered under user-approved GOV-005 on 2026-10-19.
- GOV-005 registers this workstream only; it does not activate DWS-001 or authorize product, socket, database, or production work.
- 2026-10-19: User explicitly approved shared DWS-001 registration with Governance and Discovery Writer Safety, canonical remote readback, Governance-only closure, then read-only Writer analysis and isolated synthetic socket reproduction. Product and operational changes remain prohibited.
- The user-approved shared DWS-001 registration commit `383d96606f5c727f0cef23eee35fbe06fc37edba` was read back from the canonical remote with matching Governance + Discovery Writer Safety task IDs and required-workstream sets. Governance participation then closed; DWS-001 remains IN_PROGRESS only under discovery-writer-safety, without any product-code, Writer-smoke, Docker or operational changes.

- 2026-10-19: The user asked whether DWS-001 relates to MP4 serialization, was informed DWS is an independent safety blocker surfaced in DL-001 Docker build smoke, and explicitly approved the recommended B option (systemd socket activation) for Writer product implementation and isolated offline testing only. Production service settings, actual socket, runtime/data, Docker build, and deployment remain prohibited. The pre-existing synthetic evidence includes normal kill/restart PASS, pre-unlink replacement FAIL (active pathname removed), and simulated identity collision FAIL; actual inode reuse was not observed in 16 trials. This evidence is not a production incident claim.

- 2026-10-19: B-option isolated source and synthetic smoke candidate was committed to `codex/dws001-systemd-socket-activation-20261019` at `dd36497ba5b7221fac1d9dd2c627bba685069e12`, with exact GitHub readback. This is an implementation candidate, NOT tested yet (`OFFLINE_SMOKE=NOT_RUN`). It changes only the candidate Writer source and adds a standalone synthetic smoke, non-installable socket unit template, and candidate note. Canonical Writer source, CT108 deployed service, DL-001 and S11-WX011 candidate and user data are unchanged. Live service unit users/groups and directory lifetime are UNKNOWN; rollout remains prohibited.

- 2026-10-19: User provided CT108 isolated detached worktree execution output pinned at candidate commit `dd36497ba5b7221fac1d9dd2c627bba685069e12`: Python `py_compile` exited successfully and `teddy_library_discovery_writer_socket_activation_smoke.py` reported `INVALID_ACTIVATION_FAIL_CLOSED=PASS`, `RESTART_1_PATH_PRESERVED=PASS`, `RESTART_2_PATH_PRESERVED=PASS`, `SYSTEMD_OWNED_PATH_UNLINKED=NO`, `SOCKET_ACTIVATION_RESTART=PASS`, `OPERATIONAL_WRITER_TOUCHED=NO`, and `PRODUCT_RELEASE_TOUCHED=NO`. This is user-supplied synthetic/offline smoke evidence only. Full regression smoke, Writer live unit compatibility, and deployment remain NOT_VERIFIED; product/operational changes remain prohibited.

- 2026-10-19: CT108 read-only `systemctl show` and `systemctl cat` supplied by the user confirm `User=root`, `Group=teddy-library-discovery-writer`, `RuntimeDirectory=teddy-library-discovery-writer`, `RuntimeDirectoryMode=0750`, `RuntimeDirectoryPreserve=restart`, and `Sockets=` empty. Service Type=simple, Restart=on-failure, RestartSec=3, UMask=0007; current drop-ins `10-runtime-directory-preserve.conf` and `20-execstart-d9e04ac.conf`. These are the current live service configuration values only; real `/run` path owner/group/mode, installed systemd version, socket unit installation, and client accessibility are not yet verified. Do NOT deploy or alter service/socket; socket-unit socket-node owner/group and parent directory lifecycle must be independently validated.

- 2026-10-19: CT108 read-only `stat` and `namei` output confirms socket parent `/run/teddy-library-discovery-writer` is `0750 root:teddy-library-discovery-writer`, and socket `/run/teddy-library-discovery-writer/writer.sock` is `0660 root:teddy-library-discovery-writer`. `/` and `/run` are `0755 root:root`. The suggested `systemd --version` command was invalid (`command not found`); this is NOT evidence systemd is missing because `systemctl show/cat` already work. Obtain version with `systemctl --version`. OFFLINE DESIGN RISK: systemd.socket `SocketUser=/SocketGroup=` and `SocketMode=` cover the node; `DirectoryMode=` controls newly created parent mode, not necessarily its ownership group. A fresh parent with `0750 root:root` could prevent the existing Writer client group from reaching the node; likewise the existing service's `RuntimeDirectoryPreserve=restart` does not guarantee directory retention on a plain stop. No live unit or socket modification is authorized.

- 2026-10-19: User executed `systemd-analyze verify` on `/tmp`-copied, exact Git object `e8a1dd24cb88ce75a3af34547a73968bd258a75f:deploy/systemd/teddy-library-discovery-writer.socket.candidate`, using the installed systemd 257.13 tooling, and reported `SYSTEMD_VERIFY_RC=0`. Socket-unit static syntax/dependency loading for the supplied isolated file: PASS; no console warnings. This does NOT verify installed service+socket integration, service drop-in, clean-boot parent lifecycle, full Writer regression, DL-001 Docker build, or production suitability. No operating service, user data, or protected workstream modifications.

- 2026-10-19: CT108 user-provided combined offline static unit test using B candidate `e8a1dd24cb88ce75a3af34547a73968bd258a75f` and source worktree `dd36497ba5b7221fac1d9dd2c627bba685069e12`: `CURRENT_CANDIDATE_PAIR_RC=0`, `CURRENT_CANDIDATE_PAIR_OUTPUT=NONE`, `TEST_ONLY_WIRED_PAIR_RC=0`, `TEST_ONLY_WIRED_PAIR_OUTPUT=NONE`, `TEST_ONLY_EXEC_WIRED=YES`, `LIVE_UNITS_INSTALLED=NO`, `LIVE_SERVICE_RESTARTED=NO`. The existing candidate still has `CURRENT_EXECSTART_WIRING=INCOMPLETE`; a 99-test-only ExecStart was applied solely to an isolated temporary service-unit copy for the second static verify. This is syntax/dependency validation, not a live activation test, full Writer regression, DL-001 Docker build, or production-readiness PASS.

## NEXT_DECISION

Review the B candidate for full service/socket ExecStart wiring and address the original unsafe legacy Writer smoke assumptions with scoped fail-closed tests, without bypassing the observed inode/path-replacement safety cases. Run isolated offline regression and static checks only; report remaining cold-start and socket-unit-stop lifecycle risks. No Docker build, CT108 live service/socket change or deployment without separate explicit approval.
