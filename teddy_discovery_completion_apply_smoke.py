from types import SimpleNamespace

from teddy_discovery_completion_apply import (
    CompletionApplyError,
    CompletionSSHMutator,
)
from teddy_discovery_completion_ssh import (
    CompletionSSH,
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
    calls.append({
        "command": command,
        "script": input,
    })

    if "source_preserved" in input:
        return SimpleNamespace(
            returncode=0,
            stdout=(
                '{"status":"PUBLISHED",'
                '"size":123,'
                '"mtime_ns":2000,'
                '"source_preserved":true}'
            ),
            stderr="",
        )

    return SimpleNamespace(
        returncode=0,
        stdout="CLEANED\n",
        stderr="",
    )


ssh = CompletionSSH(
    host="fake-nas",
    user="tester",
    key="/fake/key",
    known_hosts="/fake/known_hosts",
    downloads_root="/video2/downloads",
    library_root="/video2/JAV",
    runner=fake_runner,
)

mutator = CompletionSSHMutator(
    ssh
)

result = mutator.publish_to_library(
    source_relative=(
        "missav/ABC-123.mp4"
    ),
    destination_relative=(
        "ABC/ABC-123/ABC-123.mp4"
    ),
    expected_size=123,
    expected_mtime_ns=1000,
)

assert (
    result["status"]
    == "PUBLISHED"
)

assert (
    result["source_preserved"]
    is True
)

assert len(calls) == 1

try:
    mutator.publish_to_library(
        source_relative="../escape.mp4",
        destination_relative=(
            "ABC/ABC-123/ABC-123.mp4"
        ),
        expected_size=123,
        expected_mtime_ns=1000,
    )
except CompletionApplyError:
    pass
else:
    raise RuntimeError(
        "source path escape not blocked"
    )

assert len(calls) == 1

mutator.cleanup_source(
    source_relative=(
        "missav/ABC-123.mp4"
    ),
    expected_size=123,
    expected_mtime_ns=1000,
)

assert len(calls) == 2

print(
    "STAGE9_COMPLETION_APPLY_SMOKE=PASS"
)
