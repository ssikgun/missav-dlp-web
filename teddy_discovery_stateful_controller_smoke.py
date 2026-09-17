from pathlib import Path
import math
import os
import tempfile

from teddy_discovery_hermes_v2 import HermesV2CueInput
from teddy_discovery_stateful_controller import (
    REQUEST_PART,
    build_stateful_part_query,
    decide_stateful_controller_step,
)
from teddy_discovery_stateful_parts import build_stateful_part_plan
from teddy_discovery_stateful_parts import STATEFUL_PART_BATCH_SIZE
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


def make_package(count):
    cues = tuple(
        HermesV2CueInput(
            cue_id=f"ja-{index:06d}",
            external_ja=f"テスト{index}",
            stt_ja=None,
            en=None,
            before_context=(),
            after_context=(),
        )
        for index in range(1, count + 1)
    )

    return bind_stateful_semantic_policy(StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="GENERIC-TEST",
        generation_key=f"generic-controller-{count}",
        claim_token=1,
        cues=cues,
    ))


for count in (1, 16, 17, 33, 100, 661, 1000):
    package = make_package(count)
    payload = serialize_stateful_package(package)

    plan = build_stateful_part_plan(
        package,
        payload,
    )

    expected_count = math.ceil(count / STATEFUL_PART_BATCH_SIZE)

    check(
        plan.part_count == expected_count,
        f"DYNAMIC_PART_COUNT_{count}_{expected_count}",
    )

    with tempfile.TemporaryDirectory() as tmp:
        os.chmod(tmp, 0o700)

        decision = decide_stateful_controller_step(
            Path(tmp),
            package,
            payload,
        )

        check(
            decision.action == REQUEST_PART,
            f"EMPTY_TASK_REQUESTS_FIRST_PART_{count}",
        )

        check(
            decision.part_index == 1
            and decision.part_count == expected_count,
            f"DECISION_USES_DYNAMIC_PLAN_{count}",
        )


package = make_package(100)
payload = serialize_stateful_package(package)

query = build_stateful_part_query(
    package,
    payload,
    2,
)

check(
    "part 2 of 2" in query,
    "QUERY_DYNAMIC_PART_COUNT",
)

check(
    "semantic-part-0002.pending.json" in query,
    "QUERY_DYNAMIC_PENDING_FILENAME",
)

check(
    "ja-000100" in query,
    "QUERY_DYNAMIC_LAST_RANGE",
)

check(
    "excessive non-semantic repetition" in query,
    "QUERY_HAS_NON_SEMANTIC_REPEAT_POLICY",
)

check(
    "Never increase the number of repeated units" in query,
    "QUERY_PREVENTS_REPEAT_AMPLIFICATION",
)

check(
    "Do not reconstruct a longer repetition" in query,
    "QUERY_PREVENTS_HISTORY_REPEAT_RECONSTRUCTION",
)

source = Path(
    "teddy_discovery_stateful_controller.py"
).read_text(encoding="utf-8")

check(
    "JUR-750" not in source,
    "NO_TITLE_SPECIFIC_ID",
)

check(
    "part_count=42" not in source
    and "range(42)" not in source,
    "NO_FIXED_PART_COUNT",
)

print("SMOKE_PASS_COUNT=" + str(passes))
print("SMOKE_FAIL_COUNT=0")
