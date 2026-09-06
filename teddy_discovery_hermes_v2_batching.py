"""Pure bounded batching adapter for the frozen Stage11 Hermes v2 boundary.

This module performs no transport, model, filesystem, database, publication,
or source-lifecycle I/O.  It adapts one full HermesV2Request to a sequence of
bounded per-batch semantic calls and reconstructs one exact HermesV2Result.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from teddy_discovery_hermes_v2 import (
    HermesV2Request,
    HermesV2Result,
    validate_hermes_v2_result,
)


HERMES_V2_LIVE_BATCH_CUES: Final[int] = 16


class HermesV2BatchingError(RuntimeError):
    """Base class for fail-closed batching-boundary failures."""


class HermesV2BatchingValidationError(HermesV2BatchingError, ValueError):
    """The supplied full request or batch callable is invalid."""


class HermesV2BatchingExecutionError(HermesV2BatchingError):
    """A single bounded semantic batch failed or returned invalid output."""


HermesV2BatchCallable = Callable[[HermesV2Request], HermesV2Result]


def _validated_full_request(value: object) -> HermesV2Request:
    if not isinstance(value, HermesV2Request):
        raise HermesV2BatchingValidationError(
            "request must be a HermesV2Request"
        )

    try:
        return HermesV2Request(cues=value.cues)
    except Exception as error:
        raise HermesV2BatchingValidationError(
            "request is invalid or detached"
        ) from error


def invoke_hermes_v2_batched(
    request: HermesV2Request,
    batch_boundary: HermesV2BatchCallable,
) -> HermesV2Result:
    """Invoke contiguous frozen-size batches exactly once and reassemble.

    The original cue objects are sliced into contiguous tuples unchanged.
    Any failed or invalid batch aborts the whole semantic boundary.  No retry,
    fallback, partial result, context reconstruction, or cue rematching occurs.
    """

    full_request = _validated_full_request(request)

    if not callable(batch_boundary):
        raise HermesV2BatchingValidationError(
            "batch_boundary must be callable"
        )

    outputs = []

    for start in range(
        0,
        len(full_request.cues),
        HERMES_V2_LIVE_BATCH_CUES,
    ):
        batch_request = HermesV2Request(
            cues=full_request.cues[
                start : start + HERMES_V2_LIVE_BATCH_CUES
            ]
        )

        try:
            batch_result = batch_boundary(batch_request)
        except Exception as error:
            raise HermesV2BatchingExecutionError(
                "Hermes batch execution failed"
            ) from error

        if not isinstance(batch_result, HermesV2Result):
            raise HermesV2BatchingExecutionError(
                "Hermes batch returned invalid result type"
            )

        try:
            validated_batch = validate_hermes_v2_result(
                batch_result,
                batch_request,
            )
        except Exception as error:
            raise HermesV2BatchingExecutionError(
                "Hermes batch result failed exact validation"
            ) from error

        outputs.extend(validated_batch.cues)

    try:
        complete_result = HermesV2Result(
            cues=tuple(outputs)
        )
        return validate_hermes_v2_result(
            complete_result,
            full_request,
        )
    except Exception as error:
        raise HermesV2BatchingExecutionError(
            "reconstructed Hermes result failed full-request validation"
        ) from error


__all__ = [
    "HERMES_V2_LIVE_BATCH_CUES",
    "HermesV2BatchCallable",
    "HermesV2BatchingError",
    "HermesV2BatchingExecutionError",
    "HermesV2BatchingValidationError",
    "invoke_hermes_v2_batched",
]
