from __future__ import annotations

from collections import Counter
from datetime import (
    datetime,
    timezone,
)
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from typing import Any

from teddy_discovery_availability import (
    AVAILABILITY_SOURCES,
    AVAILABILITY_STATUSES,
    STATUS_UNKNOWN,
    canonical_dvd_id,
    canonical_page_url,
)

from teddy_discovery_availability_batch import (
    DEFAULT_MAX_REQUESTS,
    build_due_request_plan,
)

from teddy_discovery_availability_collector import (
    collect_availability_page,
)

from teddy_discovery_availability_store import (
    persist_availability_result,
)


ARTIFACT_PURPOSE = (
    "stage4-availability-batch-runner-v1"
)

DEFAULT_INTER_REQUEST_DELAY_SECONDS = 1.0


def _text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    value = str(
        value
    ).strip()

    return value or None


def _parse_timestamp(
    value: Any,
    *,
    field: str,
) -> datetime:
    raw = _text(
        value
    )

    if not raw:
        raise ValueError(
            field
            + " missing"
        )

    try:
        parsed = datetime.fromisoformat(
            raw
        )

    except ValueError as exc:
        raise ValueError(
            field
            + " must be ISO-8601"
        ) from exc

    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
    ):
        raise ValueError(
            field
            + " must be timezone-aware"
        )

    return (
        parsed.astimezone(
            timezone.utc
        )
        .replace(
            microsecond=0
        )
    )


def _format_timestamp(
    value: datetime,
) -> str:
    return (
        value.astimezone(
            timezone.utc
        )
        .replace(
            microsecond=0
        )
        .isoformat()
    )


def _validated_delay(
    value: Any,
) -> float:
    if (
        isinstance(
            value,
            bool,
        )
        or not isinstance(
            value,
            (
                int,
                float,
            ),
        )
    ):
        raise ValueError(
            "inter-request delay "
            "must be numeric"
        )

    value = float(
        value
    )

    if (
        value < 0.0
        or value > 60.0
    ):
        raise ValueError(
            "inter-request delay "
            "must be 0..60 seconds"
        )

    return value


def _status_counts(
    results,
) -> dict:
    return dict(
        sorted(
            Counter(
                item[
                    "classification_status"
                ]
                for item
                in results
            ).items()
        )
    )


def _source_counts(
    results,
) -> dict:
    return dict(
        sorted(
            Counter(
                item[
                    "source"
                ]
                for item
                in results
            ).items()
        )
    )


def _http_counts(
    results,
) -> dict:
    return dict(
        sorted(
            Counter(
                str(
                    item[
                        "http_status"
                    ]
                )
                for item
                in results
            ).items()
        )
    )


def _reason_counts(
    results,
) -> dict:
    return dict(
        sorted(
            Counter(
                item[
                    "classification_reason"
                ]
                for item
                in results
            ).items()
        )
    )


def artifact_oracle_sha256(
    results,
) -> str:
    payload = [
        {
            "number":
                item[
                    "number"
                ],

            "source":
                item[
                    "source"
                ],

            "dvd_id":
                item[
                    "dvd_id"
                ],

            "http_status":
                item[
                    "http_status"
                ],

            "status":
                item[
                    "classification_status"
                ],

            "reason":
                item[
                    "classification_reason"
                ],

            "request_attempts":
                item[
                    "request_attempts"
                ],

            "redirects_followed":
                item[
                    "redirects_followed"
                ],

            "media_requests":
                item[
                    "media_requests"
                ],
        }
        for item
        in results
    ]

    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        ).encode(
            "utf-8"
        )
    ).hexdigest()


def _safe_collector_result(
    *,
    number: int,
    expected_source: str,
    expected_dvd_id: str,
    value: Any,
) -> dict:
    if not isinstance(
        value,
        dict,
    ):
        raise RuntimeError(
            "collector result "
            "must be an object"
        )

    source = _text(
        value.get(
            "source"
        )
    )

    dvd_id = canonical_dvd_id(
        value.get(
            "dvd_id"
        )
    )

    if source != expected_source:
        raise RuntimeError(
            "collector source mismatch"
        )

    if dvd_id != expected_dvd_id:
        raise RuntimeError(
            "collector dvd_id mismatch"
        )

    if source not in AVAILABILITY_SOURCES:
        raise RuntimeError(
            "collector source invalid"
        )

    page_url = _text(
        value.get(
            "page_url"
        )
    )

    if page_url != canonical_page_url(
        source,
        dvd_id,
    ):
        raise RuntimeError(
            "collector page URL "
            "is not canonical"
        )

    if value.get(
        "route"
    ) != "fixed-vpn":
        raise RuntimeError(
            "collector escaped "
            "fixed-vpn route"
        )

    if value.get(
        "request_attempts"
    ) != 1:
        raise RuntimeError(
            "collector request "
            "accounting changed"
        )

    if value.get(
        "redirects_followed"
    ) != 0:
        raise RuntimeError(
            "collector followed redirect"
        )

    if value.get(
        "media_requests"
    ) != 0:
        raise RuntimeError(
            "collector crossed "
            "media boundary"
        )

    classification = value.get(
        "classification"
    )

    if not isinstance(
        classification,
        dict,
    ):
        raise RuntimeError(
            "collector classification missing"
        )

    status = _text(
        classification.get(
            "status"
        )
    )

    if status not in AVAILABILITY_STATUSES:
        raise RuntimeError(
            "collector availability "
            "status invalid"
        )

    reason = _text(
        classification.get(
            "reason"
        )
    )

    if not reason:
        raise RuntimeError(
            "collector classification "
            "reason missing"
        )

    return {
        "number":
            number,

        "source":
            source,

        "dvd_id":
            dvd_id,

        "page_url":
            page_url,

        "route":
            "fixed-vpn",

        "request_attempts":
            1,

        "redirects_followed":
            0,

        "media_requests":
            0,

        "http_status":
            value.get(
                "http_status"
            ),

        "content_type":
            value.get(
                "content_type"
            ),

        "effective_url":
            value.get(
                "effective_url"
            ),

        "location":
            value.get(
                "location"
            ),

        "error":
            value.get(
                "error"
            ),

        "body_bytes":
            value.get(
                "body_bytes"
            ),

        "classification_status":
            status,

        "classification_reason":
            reason,
    }


def collect_batch_artifact(
    connection: sqlite3.Connection,
    *,
    now: Any,
    observed_at: Any = None,
    max_requests: int = DEFAULT_MAX_REQUESTS,
    inter_request_delay_seconds: Any = (
        DEFAULT_INTER_REQUEST_DELAY_SECONDS
    ),
    stop_on_unknown: bool = True,
    collector=collect_availability_page,
    sleeper=time.sleep,
) -> dict:
    if type(
        stop_on_unknown
    ) is not bool:
        raise ValueError(
            "stop_on_unknown "
            "must be bool"
        )

    delay = _validated_delay(
        inter_request_delay_seconds
    )

    plan_now = _format_timestamp(
        _parse_timestamp(
            now,
            field="now",
        )
    )

    if observed_at is None:
        observed = datetime.now(
            timezone.utc
        ).replace(
            microsecond=0
        )

    else:
        observed = _parse_timestamp(
            observed_at,
            field="observed_at",
        )

    observed_text = (
        _format_timestamp(
            observed
        )
    )

    plan = build_due_request_plan(
        connection,
        now=plan_now,
        max_requests=max_requests,
    )

    selected_plan = [
        {
            "number":
                number,

            "source":
                item[
                    "source"
                ],

            "dvd_id":
                item[
                    "dvd_id"
                ],
        }
        for number, item
        in enumerate(
            plan[
                "selected"
            ],
            start=1,
        )
    ]

    results = []
    aborted_on_unknown = False

    for number, item in enumerate(
        plan[
            "selected"
        ],
        start=1,
    ):
        if (
            number > 1
            and delay > 0
        ):
            sleeper(
                delay
            )

        value = collector(
            source=item[
                "source"
            ],
            dvd_id=item[
                "dvd_id"
            ],
        )

        safe = _safe_collector_result(
            number=number,
            expected_source=item[
                "source"
            ],
            expected_dvd_id=item[
                "dvd_id"
            ],
            value=value,
        )

        results.append(
            safe
        )

        if (
            stop_on_unknown
            and safe[
                "classification_status"
            ] == STATUS_UNKNOWN
        ):
            aborted_on_unknown = True
            break

    request_attempts = sum(
        item[
            "request_attempts"
        ]
        for item
        in results
    )

    redirect_count = sum(
        item[
            "redirects_followed"
        ]
        for item
        in results
    )

    media_count = sum(
        item[
            "media_requests"
        ]
        for item
        in results
    )

    request_error_count = sum(
        1
        for item
        in results
        if item[
            "error"
        ]
        is not None
    )

    redirect_location_count = sum(
        1
        for item
        in results
        if item[
            "location"
        ]
        is not None
    )

    artifact = {
        "purpose":
            ARTIFACT_PURPOSE,

        "observed_at":
            observed_text,

        "plan_now":
            plan_now,

        "universe_titles":
            plan[
                "universe"
            ][
                "total"
            ],

        "possible_source_checks":
            plan[
                "possible_checks"
            ],

        "due_before_batch":
            plan[
                "due_count"
            ],

        "fresh_before_batch":
            plan[
                "fresh_count"
            ],

        "planned_count":
            plan[
                "selected_count"
            ],

        "completed_count":
            len(
                results
            ),

        "remaining_after_plan":
            plan[
                "remaining_after_batch"
            ],

        "stop_on_unknown":
            stop_on_unknown,

        "aborted_on_unknown":
            aborted_on_unknown,

        "inter_request_delay_seconds":
            delay,

        "route":
            "fixed-vpn",

        "request_attempts":
            request_attempts,

        "redirects_followed":
            redirect_count,

        "media_requests":
            media_count,

        "rapidapi_requests":
            0,

        "real_db_writes":
            0,

        "status_counts":
            _status_counts(
                results
            ),

        "source_counts":
            _source_counts(
                results
            ),

        "http_status_counts":
            _http_counts(
                results
            ),

        "reason_counts":
            _reason_counts(
                results
            ),

        "request_error_count":
            request_error_count,

        "redirect_location_count":
            redirect_location_count,

        "selected_plan":
            selected_plan,

        "results":
            results,
    }

    artifact[
        "oracle_sha256"
    ] = artifact_oracle_sha256(
        results
    )

    validate_batch_artifact(
        artifact
    )

    return artifact


def validate_batch_artifact(
    artifact: Any,
) -> dict:
    if not isinstance(
        artifact,
        dict,
    ):
        raise ValueError(
            "batch artifact "
            "must be an object"
        )

    if artifact.get(
        "purpose"
    ) != ARTIFACT_PURPOSE:
        raise ValueError(
            "batch artifact "
            "purpose mismatch"
        )

    observed_text = (
        _format_timestamp(
            _parse_timestamp(
                artifact.get(
                    "observed_at"
                ),
                field="observed_at",
            )
        )
    )

    plan_now = (
        _format_timestamp(
            _parse_timestamp(
                artifact.get(
                    "plan_now"
                ),
                field="plan_now",
            )
        )
    )

    planned = artifact.get(
        "planned_count"
    )

    completed = artifact.get(
        "completed_count"
    )

    if (
        type(planned) is not int
        or planned < 0
        or planned > 200
    ):
        raise ValueError(
            "artifact planned_count invalid"
        )

    if (
        type(completed) is not int
        or completed < 0
        or completed > planned
    ):
        raise ValueError(
            "artifact completed_count invalid"
        )

    stop_on_unknown = artifact.get(
        "stop_on_unknown"
    )

    aborted = artifact.get(
        "aborted_on_unknown"
    )

    if type(
        stop_on_unknown
    ) is not bool:
        raise ValueError(
            "artifact stop_on_unknown invalid"
        )

    if type(
        aborted
    ) is not bool:
        raise ValueError(
            "artifact aborted_on_unknown invalid"
        )

    if artifact.get(
        "route"
    ) != "fixed-vpn":
        raise ValueError(
            "artifact route invalid"
        )

    if artifact.get(
        "rapidapi_requests"
    ) != 0:
        raise ValueError(
            "artifact RapidAPI "
            "boundary changed"
        )

    if artifact.get(
        "real_db_writes"
    ) != 0:
        raise ValueError(
            "collection artifact "
            "must be read-only"
        )

    selected_plan = artifact.get(
        "selected_plan"
    )

    results = artifact.get(
        "results"
    )

    if (
        not isinstance(
            selected_plan,
            list,
        )
        or len(
            selected_plan
        ) != planned
    ):
        raise ValueError(
            "artifact selected plan invalid"
        )

    if (
        not isinstance(
            results,
            list,
        )
        or len(
            results
        ) != completed
    ):
        raise ValueError(
            "artifact result count invalid"
        )

    selected_keys = []
    seen_plan = set()

    for number, item in enumerate(
        selected_plan,
        start=1,
    ):
        if not isinstance(
            item,
            dict,
        ):
            raise ValueError(
                "artifact selected plan "
                "item invalid"
            )

        if item.get(
            "number"
        ) != number:
            raise ValueError(
                "artifact selected plan "
                "sequence invalid"
            )

        source = _text(
            item.get(
                "source"
            )
        )

        dvd_id = canonical_dvd_id(
            item.get(
                "dvd_id"
            )
        )

        if source not in AVAILABILITY_SOURCES:
            raise ValueError(
                "artifact selected "
                "source invalid"
            )

        key = (
            dvd_id,
            source,
        )

        if key in seen_plan:
            raise ValueError(
                "artifact selected "
                "plan duplicate"
            )

        seen_plan.add(
            key
        )

        selected_keys.append(
            key
        )

    seen_results = set()
    unknown_indexes = []

    for number, item in enumerate(
        results,
        start=1,
    ):
        if not isinstance(
            item,
            dict,
        ):
            raise ValueError(
                "artifact result item invalid"
            )

        if item.get(
            "number"
        ) != number:
            raise ValueError(
                "artifact result "
                "sequence invalid"
            )

        source = _text(
            item.get(
                "source"
            )
        )

        dvd_id = canonical_dvd_id(
            item.get(
                "dvd_id"
            )
        )

        key = (
            dvd_id,
            source,
        )

        if key != selected_keys[
            number - 1
        ]:
            raise ValueError(
                "artifact result does not "
                "match selected-plan prefix"
            )

        if key in seen_results:
            raise ValueError(
                "artifact result duplicate"
            )

        seen_results.add(
            key
        )

        if item.get(
            "route"
        ) != "fixed-vpn":
            raise ValueError(
                "artifact result route invalid"
            )

        if item.get(
            "request_attempts"
        ) != 1:
            raise ValueError(
                "artifact result "
                "request count invalid"
            )

        if item.get(
            "redirects_followed"
        ) != 0:
            raise ValueError(
                "artifact result "
                "redirect invalid"
            )

        if item.get(
            "media_requests"
        ) != 0:
            raise ValueError(
                "artifact result "
                "media boundary invalid"
            )

        if item.get(
            "page_url"
        ) != canonical_page_url(
            source,
            dvd_id,
        ):
            raise ValueError(
                "artifact result "
                "page URL invalid"
            )

        status = _text(
            item.get(
                "classification_status"
            )
        )

        if status not in AVAILABILITY_STATUSES:
            raise ValueError(
                "artifact result "
                "status invalid"
            )

        reason = _text(
            item.get(
                "classification_reason"
            )
        )

        if not reason:
            raise ValueError(
                "artifact result "
                "reason missing"
            )

        if status == STATUS_UNKNOWN:
            unknown_indexes.append(
                number
            )

    if stop_on_unknown:
        if unknown_indexes:
            if unknown_indexes != [
                completed,
            ]:
                raise ValueError(
                    "UNKNOWN must be final "
                    "completed result"
                )

            if not aborted:
                raise ValueError(
                    "UNKNOWN artifact must "
                    "mark circuit breaker"
                )

        elif aborted:
            raise ValueError(
                "artifact claims UNKNOWN "
                "abort without UNKNOWN"
            )

    elif aborted:
        raise ValueError(
            "artifact cannot abort "
            "when stop_on_unknown=False"
        )

    if artifact.get(
        "request_attempts"
    ) != completed:
        raise ValueError(
            "artifact request accounting invalid"
        )

    if artifact.get(
        "redirects_followed"
    ) != 0:
        raise ValueError(
            "artifact redirect "
            "accounting invalid"
        )

    if artifact.get(
        "media_requests"
    ) != 0:
        raise ValueError(
            "artifact media "
            "accounting invalid"
        )

    if artifact.get(
        "status_counts"
    ) != _status_counts(
        results
    ):
        raise ValueError(
            "artifact status counts changed"
        )

    if artifact.get(
        "source_counts"
    ) != _source_counts(
        results
    ):
        raise ValueError(
            "artifact source counts changed"
        )

    if artifact.get(
        "http_status_counts"
    ) != _http_counts(
        results
    ):
        raise ValueError(
            "artifact HTTP counts changed"
        )

    if artifact.get(
        "reason_counts"
    ) != _reason_counts(
        results
    ):
        raise ValueError(
            "artifact reason counts changed"
        )

    request_errors = sum(
        1
        for item
        in results
        if item.get(
            "error"
        )
        is not None
    )

    redirect_locations = sum(
        1
        for item
        in results
        if item.get(
            "location"
        )
        is not None
    )

    if artifact.get(
        "request_error_count"
    ) != request_errors:
        raise ValueError(
            "artifact request-error "
            "count changed"
        )

    if artifact.get(
        "redirect_location_count"
    ) != redirect_locations:
        raise ValueError(
            "artifact redirect-location "
            "count changed"
        )

    computed_oracle = (
        artifact_oracle_sha256(
            results
        )
    )

    if artifact.get(
        "oracle_sha256"
    ) != computed_oracle:
        raise ValueError(
            "artifact oracle changed"
        )

    normalized = dict(
        artifact
    )

    normalized[
        "observed_at"
    ] = observed_text

    normalized[
        "plan_now"
    ] = plan_now

    return normalized


def replay_batch_artifact(
    db_path: Any,
    artifact: Any,
) -> dict:
    value = validate_batch_artifact(
        artifact
    )

    path = Path(
        db_path
    )

    if not path.is_file():
        raise ValueError(
            "availability DB missing"
        )

    checked = _parse_timestamp(
        value[
            "observed_at"
        ],
        field="observed_at",
    )

    checked_text = _format_timestamp(
        checked
    )

    results = value[
        "results"
    ]

    #
    # Preflight every row before the first
    # write. This makes stale/mismatched
    # artifacts fail closed before mutation.
    #
    connection = sqlite3.connect(
        "file:"
        + str(path)
        + "?mode=ro",
        uri=True,
    )

    connection.row_factory = sqlite3.Row

    actions = []

    try:
        for item in results:
            row = connection.execute(
                """
                SELECT
                    status,
                    page_url,
                    last_checked_at,
                    fail_count
                FROM availability
                WHERE dvd_id = ?
                  AND source = ?
                """,
                (
                    item[
                        "dvd_id"
                    ],
                    item[
                        "source"
                    ],
                ),
            ).fetchone()

            if row is None:
                actions.append(
                    "apply"
                )
                continue

            existing_checked = (
                _parse_timestamp(
                    row[
                        "last_checked_at"
                    ],
                    field=
                        "stored last_checked_at",
                )
            )

            if existing_checked > checked:
                raise RuntimeError(
                    "stale availability artifact"
                )

            if existing_checked == checked:
                if (
                    row[
                        "status"
                    ]
                    != item[
                        "classification_status"
                    ]
                    or row[
                        "page_url"
                    ]
                    != item[
                        "page_url"
                    ]
                ):
                    raise RuntimeError(
                        "same-timestamp "
                        "availability mismatch"
                    )

                actions.append(
                    "already-applied"
                )
                continue

            actions.append(
                "apply"
            )

    finally:
        connection.close()

    applied = 0
    already_applied = 0

    for item, action in zip(
        results,
        actions,
    ):
        if action == "already-applied":
            already_applied += 1
            continue

        connection = sqlite3.connect(
            path
        )

        connection.row_factory = sqlite3.Row

        try:
            persist_availability_result(
                connection,
                {
                    "source":
                        item[
                            "source"
                        ],

                    "dvd_id":
                        item[
                            "dvd_id"
                        ],

                    "page_url":
                        item[
                            "page_url"
                        ],

                    "status":
                        item[
                            "classification_status"
                        ],
                },
                checked_at=
                    checked_text,
            )

        finally:
            connection.close()

        applied += 1

    #
    # Exact post-readback also makes a
    # partially completed prior replay safe
    # to resume without re-applying UNKNOWN.
    #
    connection = sqlite3.connect(
        "file:"
        + str(path)
        + "?mode=ro",
        uri=True,
    )

    connection.row_factory = sqlite3.Row

    try:
        for item in results:
            row = connection.execute(
                """
                SELECT
                    status,
                    page_url,
                    last_checked_at,
                    fail_count
                FROM availability
                WHERE dvd_id = ?
                  AND source = ?
                """,
                (
                    item[
                        "dvd_id"
                    ],
                    item[
                        "source"
                    ],
                ),
            ).fetchone()

            if row is None:
                raise RuntimeError(
                    "availability replay "
                    "readback missing"
                )

            if row[
                "status"
            ] != item[
                "classification_status"
            ]:
                raise RuntimeError(
                    "availability replay "
                    "status mismatch"
                )

            if row[
                "page_url"
            ] != item[
                "page_url"
            ]:
                raise RuntimeError(
                    "availability replay "
                    "page URL mismatch"
                )

            if row[
                "last_checked_at"
            ] != checked_text:
                raise RuntimeError(
                    "availability replay "
                    "checked time mismatch"
                )

            fail_count = row[
                "fail_count"
            ]

            if item[
                "classification_status"
            ] == STATUS_UNKNOWN:
                if (
                    type(fail_count) is not int
                    or fail_count < 1
                ):
                    raise RuntimeError(
                        "UNKNOWN replay "
                        "fail_count invalid"
                    )

            elif fail_count != 0:
                raise RuntimeError(
                    "successful replay "
                    "fail_count invalid"
                )

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

    finally:
        connection.close()

    if integrity != "ok":
        raise RuntimeError(
            "availability DB integrity failed"
        )

    return {
        "completed_count":
            len(
                results
            ),

        "applied_count":
            applied,

        "already_applied_count":
            already_applied,

        "observed_at":
            checked_text,

        "integrity":
            integrity,
    }
