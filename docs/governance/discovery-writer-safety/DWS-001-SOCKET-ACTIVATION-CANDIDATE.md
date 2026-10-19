# DWS-001 socket-activation candidate (NOT deployable)

This isolated branch implements the user-approved B direction without touching
CT108, the DL-001 candidate, the Stage11 worktree, or operational data.

- New Writer flag: `--systemd-socket`. Without it, the new Writer entrypoint
  fails closed. With it, exactly one named systemd listener (`writer`, fd 3,
  matching `LISTEN_PID`, `LISTEN_FDS=1`, AF_UNIX, SOCK_STREAM, listening,
  expected socket pathname) is adopted, never probed, rebound, chmodded or
  unlinked by Writer.
- The existing `_UnixServer` legacy constructor and historical Writer smoke
  remain unchanged to preserve evidence. This means legacy direct binding is
  **not** newly certified safe; product entrypoint is activation-only.
- Synthetic forked child restart smoke tests invalid activation metadata and
  two forced restarts while an independent parent retains ownership of a
  temporary listening socket.
- `deploy/systemd/teddy-library-discovery-writer.socket.candidate` is a
  NON-INSTALLABLE review template (not a deployed .socket unit).
- No live service unit body, `User`/`Group`, `RuntimeDirectory`, socket
  clients' credentials, current activation/connection ordering, and permissions
  have yet been verified on CT108. A complete migration plan MUST first verify
  these and address `RuntimeDirectoryPreserve=restart` interactions. Neither
  systemd configuration nor Docker image is to be changed or deployed now.
- The original legacy inode collision and pre-unlink safety flaws remain
  observed/known. Candidate activation avoids the legacy cleanup path but no
  offline PASS is a production safety guarantee.

Offline test (on an isolated fully checked out candidate):
`python3 teddy_library_discovery_writer_socket_activation_smoke.py`

## CT108 systemd 257.13 permissions/ownership candidate checkpoint

- Verified from user-supplied read-only CT108 commands: systemd 257.13; service User=root, Group=teddy-library-discovery-writer, RuntimeDirectory=teddy-library-discovery-writer, RuntimeDirectoryMode=0750, RuntimeDirectoryPreserve=restart.
- Actual parent path /run/teddy-library-discovery-writer is root:teddy-library-discovery-writer 0750; writer.sock is root:teddy-library-discovery-writer 0660.
- The revised NON-INSTALLABLE socket template explicitly sets socket user/group, node and directory modes, and ExecStartPre=/usr/bin/install -d ... before ListenStream binds. This guards the cold-start parent group but is untested under PID1.
- The accompanying NON-INSTALLABLE service drop-in candidate clears RuntimeDirectory and records socket ordering, protecting the directory from service-owned cleanup on stop. A later approval must safely change the pinned ExecStart to the validated release with --systemd-socket.
- Socket unit stop/restart stale pathname, actual new parent ownership under PID1, final systemd-analyze verify, full smoke regression and any live migration are NOT VERIFIED; operation remains prohibited.

## DWS-001 legacy smoke inode-inequality correction (isolated candidate)

- Three assertions that newly bound Unix sockets must have a different
  `dev/inode` identity were removed because POSIX filesystems may reuse inodes.
- Each affected case now requires an actual socket type. The associated
  live health checks, database restart/replay invariants, active-socket
  `expect_writer_unavailable` rejection, direct `connect()/accept()`
  liveness check and replacement pathname identity preservation remain.
- **Known legacy bug is NOT fixed or bypassed**: if the old direct-mode
  cleanup unlinks a replacement listener on an identity collision, the
  active-listener safety test still fails. The previous isolated
  pre-unlink-delete and simulated identity-collision FAILs remain evidence.
- The B-option systemd-owned listener path avoids Writer-side unlink;
  this smoke change does not make unsafe direct mode production-approved.
- Remote-only code review can confirm the intended source edit;
  Python syntax and execution regression remain `NOT_RUN` until a fresh
  SHA-pinned isolated worktree test on CT108.

## 2026-10-19: Restore previous permission and ownership assertions

CT108 user read-only comparison with the independent DL-001 candidate revealed the preceding DWS-001 test edit unintentionally removed the existing `0660` socket-mode and `os.geteuid()` owner checks in two legacy smoke cases. This isolated DWS-001 correction reinstates those exact checks while keeping the invalid inode-inequality assumptions removed. The active replacement rejection and direct connect/accept invariants remain unchanged. No changes to the DL-001 candidate or its build context, Stage11, deployed Writer, or production data. This revised commit requires a new SHA-pinned offline smoke run; earlier PASS does not certify the restored assertions.
