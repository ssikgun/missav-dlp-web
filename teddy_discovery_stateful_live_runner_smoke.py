from pathlib import Path
import tempfile

from teddy_discovery_hermes_v2 import (
    HermesV2CueInput,
    HermesV2CueOutput,
)
from teddy_discovery_stateful_controller import (
    build_stateful_part_query,
)
from teddy_discovery_stateful_parts import (
    StatefulSemanticPart,
    build_stateful_part_plan,
    parse_stateful_part,
    serialize_stateful_part,
)
from teddy_discovery_stateful_live_runner import (
    _install_validated_pending,
    _require_absolute_remote_task,
    build_parser,
)
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
    bind_stateful_semantic_policy,
    serialize_stateful_package,
)


passes = 0


def check(value, marker):
    global passes

    if not value:
        raise AssertionError(marker)

    passes += 1
    print("PASS=" + marker)


def package_for(count):
    return bind_stateful_semantic_policy(StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="GENERIC-SMOKE",
        generation_key=(
            "generic-live-runner-"
            + str(count)
        ),
        claim_token=1,
        cues=tuple(
            HermesV2CueInput(
                cue_id=f"ja-{index:06d}",
                external_ja="テスト",
                stt_ja=None,
                en=None,
                before_context=(),
                after_context=(),
            )
            for index in range(
                1,
                count + 1,
            )
        ),
    ))


for count, expected_parts in (
    (1, 1),
    (16, 1),
    (17, 1),
    (661, 11),
    (1000, 16),
):
    package = package_for(count)

    payload = serialize_stateful_package(
        package
    )

    plan = build_stateful_part_plan(
        package,
        payload,
    )

    check(
        plan.part_count == expected_parts,
        f"DYNAMIC_PARTS_{count}_{expected_parts}",
    )


package = package_for(100)

payload = serialize_stateful_package(
    package
)

plan = build_stateful_part_plan(
    package,
    payload,
)

expected = plan.parts[0]

part = StatefulSemanticPart(
    part_schema_version=1,
    session_id=plan.session_id,
    input_sha256=plan.input_sha256,
    part_index=1,
    first_cue_id=expected.first_cue_id,
    last_cue_id=expected.last_cue_id,
    cues=tuple(
        HermesV2CueOutput(
            cue_id=cue_id,
            repaired_ja=None,
            ko="테스트",
        )
        for cue_id in expected.cue_ids
    ),
)

part_payload = serialize_stateful_part(
    part
)

with tempfile.TemporaryDirectory() as directory:
    task = Path(directory)

    task.chmod(0o700)

    _install_validated_pending(
        task_directory=task,
        payload=part_payload,
        plan=plan,
        expected=expected,
    )

    pending = (
        task
        / expected.pending_filename
    )

    check(
        pending.exists(),
        "ATOMIC_PENDING_INSTALL",
    )

    check(
        (
            pending.stat().st_mode
            & 0o777
        )
        == 0o600,
        "PENDING_MODE_600",
    )

    parsed = parse_stateful_part(
        pending.read_bytes(),
        expected,
        plan,
    )

    check(
        parsed == part,
        "PENDING_ROUNDTRIP",
    )


query = build_stateful_part_query(
    package,
    payload,
    2,
)

check(
    "part 2 of 2" in query,
    "QUERY_DYNAMIC_TOTAL",
)

check(
    "semantic-part-0002.pending.json"
    in query,
    "QUERY_EXACT_PENDING_FILENAME",
)

check(
    _require_absolute_remote_task(
        "/home/teddy/task/test"
    )
    == "/home/teddy/task/test",
    "REMOTE_TASK_ABSOLUTE_ACCEPTED",
)


parser = build_parser()

args = parser.parse_args(
    [
        "--package",
        "/tmp/input.json",
        "--task-directory",
        "/tmp/task",
        "--final-result",
        "/tmp/result.json",
        "--remote",
        "user@example",
        "--remote-task",
        "/tmp/remote-task",
        "--ssh-key",
        "/tmp/key",
        "--known-hosts",
        "/tmp/known",
    ]
)

check(
    args.turn_timeout == 600,
    "DEFAULT_TURN_TIMEOUT",
)


source = Path(
    "teddy_discovery_stateful_live_runner.py"
).read_text(
    encoding="utf-8"
)

check(
    "JUR-750" not in source,
    "NO_TITLE_SPECIFIC_ID",
)

check(
    "part_count = 42" not in source
    and "range(42)" not in source
    and "range(1, 43)" not in source,
    "NO_FIXED_42_PART_COUNT",
)

check(
    "while True:" in source,
    "AUTOMATIC_LOOP_PRESENT",
)

check(
    "--resume" in source,
    "SAME_SESSION_RESUME_PRESENT",
)

print(
    "SMOKE_PASS_COUNT="
    + str(passes)
)

print("SMOKE_FAIL_COUNT=0")
