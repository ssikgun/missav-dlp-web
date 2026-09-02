from types import SimpleNamespace

from teddy_discovery_completion_ssh import (
    CompletionSSH,
    CompletionSSHError,
)


calls = []


def fake_runner(
    command,
    *,
    input,
    stdout,
    stderr,
    text,
):
    calls.append(command)

    joined = " ".join(command)

    if "/video2/downloads" in joined:
        return SimpleNamespace(
            returncode=0,
            stdout=(
                '[{"name":"missav/ABC-123.mp4",'
                '"size":123,"modified":1000,\"mtime_ns\":1000000000000}]'
            ),
            stderr="",
        )

    return SimpleNamespace(
        returncode=0,
        stdout='{"size":123,"modified":1000,\"mtime_ns\":1000000000000}',
        stderr="",
    )


ssh = CompletionSSH(
    host="nas",
    user="tester",
    key="/key",
    known_hosts="/known_hosts",
    downloads_root="/video2/downloads",
    library_root="/video2/JAV",
    runner=fake_runner,
)

items = ssh.list_downloads()

assert items == [
    {
        "name": "missav/ABC-123.mp4",
        "size": 123,
        "modified": 1000,
        "mtime_ns": 1000000000000,
    }
]

stat = ssh.stat_library(
    "ABC/ABC-123/ABC-123.mp4"
)

assert stat["size"] == 123

try:
    ssh.stat_library(
        "../escape.mp4"
    )
except CompletionSSHError:
    pass
else:
    raise RuntimeError(
        "path escape was not blocked"
    )

assert len(calls) == 2

print(
    "STAGE9_COMPLETION_SSH_SMOKE=PASS"
)
