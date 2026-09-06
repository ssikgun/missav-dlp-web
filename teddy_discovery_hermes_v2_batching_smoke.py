"""Offline deterministic smoke tests for frozen Hermes v2 batching."""

import ast
from pathlib import Path

from teddy_discovery_hermes_v2 import (
    HermesV2CueInput,
    HermesV2CueOutput,
    HermesV2Request,
    HermesV2Result,
)
from teddy_discovery_hermes_v2_batching import (
    HERMES_V2_LIVE_BATCH_CUES,
    HermesV2BatchingError,
    invoke_hermes_v2_batched,
)


def require(condition: bool, marker: str):
    if not condition:
        raise AssertionError(marker)


def expect_raises(exception_type, callback, marker: str):
    try:
        callback()
    except exception_type:
        return
    except Exception as error:
        raise AssertionError(
            marker + ": wrong exception " + type(error).__name__
        ) from error
    raise AssertionError(marker)


def request(count: int) -> HermesV2Request:
    return HermesV2Request(
        cues=tuple(
            HermesV2CueInput(
                cue_id=f"asr-{index + 1:06d}",
                external_ja=None,
                stt_ja=f"日本語-{index + 1}",
                en=None,
                before_context=(
                    (f"前-{index}",)
                    if index > 0
                    else ()
                ),
                after_context=(
                    (f"後-{index + 2}",)
                    if index + 1 < count
                    else ()
                ),
            )
            for index in range(count)
        )
    )


class RecordingBoundary:
    def __init__(self, *, fail_call=None, mode=None):
        self.calls = 0
        self.requests = []
        self.fail_call = fail_call
        self.mode = mode

    def __call__(self, batch):
        self.calls += 1
        self.requests.append(batch)

        if self.fail_call == self.calls:
            raise RuntimeError("synthetic failure")

        outputs = tuple(
            HermesV2CueOutput(
                cue_id=cue.cue_id,
                repaired_ja=None,
                ko=f"한국어-{cue.cue_id}",
            )
            for cue in batch.cues
        )

        if self.mode == "missing" and self.calls == 2:
            outputs = outputs[:-1]

        if self.mode == "reordered" and self.calls == 2:
            outputs = tuple(reversed(outputs))

        return HermesV2Result(cues=outputs)


def main():
    require(
        HERMES_V2_LIVE_BATCH_CUES == 16,
        "FROZEN_BATCH_SIZE_16",
    )

    for count, expected_sizes in (
        (1, (1,)),
        (16, (16,)),
        (17, (16, 1)),
        (32, (16, 16)),
        (33, (16, 16, 1)),
        (166, (16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 6)),
    ):
        original = request(count)
        boundary = RecordingBoundary()

        result = invoke_hermes_v2_batched(
            original,
            boundary,
        )

        require(
            tuple(len(item.cues) for item in boundary.requests)
            == expected_sizes,
            f"BATCH_SIZES_{count}",
        )

        require(
            boundary.calls == len(expected_sizes),
            f"EXACT_CALL_COUNT_{count}",
        )

        require(
            tuple(cue.cue_id for cue in result.cues)
            == tuple(cue.cue_id for cue in original.cues),
            f"FULL_ORDER_{count}",
        )

        flattened_inputs = tuple(
            cue
            for batch in boundary.requests
            for cue in batch.cues
        )

        require(
            len(flattened_inputs) == len(original.cues)
            and all(
                actual is expected
                for actual, expected in zip(
                    flattened_inputs,
                    original.cues,
                )
            ),
            f"ORIGINAL_CUE_OBJECTS_PRESERVED_{count}",
        )

    context_request = request(17)
    context_boundary = RecordingBoundary()

    invoke_hermes_v2_batched(
        context_request,
        context_boundary,
    )

    require(
        context_boundary.requests[0].cues[-1]
        is context_request.cues[15]
        and context_boundary.requests[1].cues[0]
        is context_request.cues[16]
        and context_boundary.requests[0].cues[-1].after_context
        == context_request.cues[15].after_context
        and context_boundary.requests[1].cues[0].before_context
        == context_request.cues[16].before_context,
        "CROSS_BATCH_CONTEXT_PRESERVED_UNCHANGED",
    )

    fail_boundary = RecordingBoundary(fail_call=2)

    expect_raises(
        HermesV2BatchingError,
        lambda: invoke_hermes_v2_batched(
            request(40),
            fail_boundary,
        ),
        "SECOND_BATCH_FAILURE_FAILS_WHOLE_BOUNDARY",
    )

    require(
        fail_boundary.calls == 2,
        "FAILURE_HAS_NO_RETRY_AND_NO_LATER_BATCH",
    )

    missing_boundary = RecordingBoundary(mode="missing")

    expect_raises(
        HermesV2BatchingError,
        lambda: invoke_hermes_v2_batched(
            request(32),
            missing_boundary,
        ),
        "MISSING_BATCH_CUE_REJECTED",
    )

    require(
        missing_boundary.calls == 2,
        "MISSING_BATCH_CUE_NO_RETRY",
    )

    reordered_boundary = RecordingBoundary(mode="reordered")

    expect_raises(
        HermesV2BatchingError,
        lambda: invoke_hermes_v2_batched(
            request(32),
            reordered_boundary,
        ),
        "REORDERED_BATCH_REJECTED",
    )

    require(
        reordered_boundary.calls == 2,
        "REORDERED_BATCH_NO_RETRY",
    )

    wrong_type_calls = {"count": 0}

    def wrong_type(_batch):
        wrong_type_calls["count"] += 1
        return object()

    expect_raises(
        HermesV2BatchingError,
        lambda: invoke_hermes_v2_batched(
            request(17),
            wrong_type,
        ),
        "INVALID_RESULT_TYPE_REJECTED",
    )

    require(
        wrong_type_calls["count"] == 1,
        "INVALID_RESULT_TYPE_NO_RETRY",
    )

    expect_raises(
        HermesV2BatchingError,
        lambda: invoke_hermes_v2_batched(
            request(1),
            None,
        ),
        "NONCALLABLE_BOUNDARY_REJECTED",
    )

    source = Path(
        "teddy_discovery_hermes_v2_batching.py"
    ).read_text(encoding="utf-8")

    tree = ast.parse(source)

    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    imports.update(
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        for alias in node.names
    )

    require(
        not imports.intersection(
            {
                "subprocess",
                "sqlite3",
                "socket",
                "requests",
                "urllib",
            }
        ),
        "BATCH_ADAPTER_HAS_NO_EFFECTFUL_IMPORTS",
    )

    require(
        "teddy_discovery_hermes_v2_transport"
        not in source,
        "BATCH_ADAPTER_DOES_NOT_OWN_TRANSPORT",
    )

    print("HERMES_V2_BATCHING_SMOKE_PASS")


if __name__ == "__main__":
    main()
