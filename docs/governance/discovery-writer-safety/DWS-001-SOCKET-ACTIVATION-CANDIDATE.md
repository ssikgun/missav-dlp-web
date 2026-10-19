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
