from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from teddy_discovery_availability import (
    SOURCE_123AV,
    SOURCE_MISSAV,
    STATUS_FOUND,
    STATUS_NOT_FOUND,
    STATUS_UNKNOWN,
    canonical_dvd_id,
    canonical_page_url,
    classify_page_response,
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def canonical_url_smoke():
    require(
        canonical_dvd_id(
            "jur-821"
        )
        == "JUR-821",
        "lowercase canonical ID changed",
    )

    require(
        canonical_page_url(
            SOURCE_MISSAV,
            "SDNM-560",
        )
        == (
            "https://missav.ws/"
            "ko/sdnm-560"
        ),
        "MissAV canonical URL changed",
    )

    require(
        canonical_page_url(
            SOURCE_123AV,
            "JUR-821",
        )
        == (
            "https://123av.com/"
            "ko/v/jur-821"
        ),
        "123AV canonical URL changed",
    )

    for invalid in (
        "",
        "JUR-821 extra title",
        "movie-JUR-821",
        "https://missav.ws/ko/jur-821",
    ):
        try:
            canonical_dvd_id(
                invalid
            )

        except ValueError:
            pass

        else:
            raise RuntimeError(
                "non-canonical DVD ID "
                "must fail closed: "
                + repr(
                    invalid
                )
            )

    try:
        canonical_page_url(
            "other",
            "JUR-821",
        )

    except ValueError:
        pass

    else:
        raise RuntimeError(
            "unknown source must fail closed"
        )

    print(
        "AVAILABILITY_CANONICAL_URL_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_CANONICAL_ID_FAIL_CLOSED_SMOKE=PASS"
    )


def forensic_oracle_smoke(
    forensic_path: Path,
):
    value = json.loads(
        forensic_path.read_text(
            encoding="utf-8"
        )
    )

    require(
        value[
            "request_attempts"
        ]
        == 4,
        "forensic request count changed",
    )

    require(
        value[
            "redirects_followed"
        ]
        == 0,
        "forensic redirect count changed",
    )

    require(
        value[
            "media_requests"
        ]
        == 0,
        "forensic media boundary changed",
    )

    records = value[
        "records"
    ]

    require(
        len(records) == 4,
        "forensic record count changed",
    )

    expected = [
        (
            SOURCE_MISSAV,
            "SDNM-560",
            STATUS_FOUND,
        ),
        (
            SOURCE_MISSAV,
            "ZZZZ-999999",
            STATUS_NOT_FOUND,
        ),
        (
            SOURCE_123AV,
            "JUR-821",
            STATUS_FOUND,
        ),
        (
            SOURCE_123AV,
            "ZZZZ-999999",
            STATUS_NOT_FOUND,
        ),
    ]

    observed = []

    for record, oracle in zip(
        records,
        expected,
    ):
        (
            expected_source,
            expected_dvd_id,
            expected_status,
        ) = oracle

        result = classify_page_response(
            source=record[
                "source"
            ],
            dvd_id=record[
                "dvd_id"
            ],
            requested_url=record[
                "requested_url"
            ],
            http_status=record[
                "status"
            ],
            content_type=record[
                "content_type"
            ],
            effective_url=record[
                "effective_url"
            ],
            location=record[
                "location"
            ],
            error=record[
                "error"
            ],
            body=record[
                "body"
            ],
        )

        require(
            result[
                "source"
            ]
            == expected_source,
            "forensic source changed",
        )

        require(
            result[
                "dvd_id"
            ]
            == expected_dvd_id,
            "forensic DVD ID changed",
        )

        require(
            result[
                "status"
            ]
            == expected_status,
            (
                "forensic classification "
                "changed: "
                + repr(
                    result
                )
            ),
        )

        observed.append({
            "source":
                result[
                    "source"
                ],

            "dvd_id":
                result[
                    "dvd_id"
                ],

            "page_url":
                result[
                    "page_url"
                ],

            "status":
                result[
                    "status"
                ],

            "reason":
                result[
                    "reason"
                ],

            "http_status":
                result[
                    "http_status"
                ],
        })

    #
    # Real MissAV 404 page contains the
    # requested synthetic ID in its body.
    #
    # This proves arbitrary body ID hits
    # cannot be a FOUND discriminator.
    #
    missav_missing = (
        records[1]
    )

    require(
        missav_missing[
            "shape"
        ][
            "dvd_id_dashed_hits"
        ]
        > 0,
        "MissAV 404 echo oracle changed",
    )

    digest = hashlib.sha256(
        json.dumps(
            observed,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode(
            "utf-8"
        )
    ).hexdigest()

    print(
        "AVAILABILITY_REAL_ORACLE_SHA256="
        + digest
    )

    print(
        "AVAILABILITY_REAL_4_PAGE_ORACLE_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_BODY_HITS_NOT_CLASSIFIER_SMOKE=PASS"
    )


def unknown_fail_closed_smoke():
    url = canonical_page_url(
        SOURCE_MISSAV,
        "JUR-821",
    )

    cases = [
        {
            "name":
                "request-error",

            "http_status":
                None,

            "content_type":
                None,

            "effective_url":
                None,

            "error":
                "TimeoutError: synthetic",
        },
        {
            "name":
                "redirect",

            "http_status":
                302,

            "content_type":
                "text/html",

            "effective_url":
                url,

            "location":
                "https://example.invalid/",
        },
        {
            "name":
                "403",

            "http_status":
                403,

            "content_type":
                "text/html",

            "effective_url":
                url,
        },
        {
            "name":
                "429",

            "http_status":
                429,

            "content_type":
                "text/html",

            "effective_url":
                url,
        },
        {
            "name":
                "500",

            "http_status":
                500,

            "content_type":
                "text/html",

            "effective_url":
                url,
        },
        {
            "name":
                "non-html",

            "http_status":
                200,

            "content_type":
                "application/json",

            "effective_url":
                url,

            "body":
                '{"dvd":"JUR-821"}',
        },
        {
            "name":
                "wrong-identity",

            "http_status":
                200,

            "content_type":
                "text/html",

            "effective_url":
                url,

            "body":
                (
                    "<html>"
                    "<title>OTHER-001</title>"
                    "<h1>OTHER-001</h1>"
                    "</html>"
                ),
        },
        {
            "name":
                "effective-url-mismatch",

            "http_status":
                200,

            "content_type":
                "text/html",

            "effective_url":
                (
                    "https://missav.ws/"
                    "ko/other-001"
                ),

            "body":
                (
                    "<html>"
                    "<title>JUR-821</title>"
                    "</html>"
                ),
        },
        {
            "name":
                "404-non-html",

            "http_status":
                404,

            "content_type":
                "application/json",

            "effective_url":
                url,

            "body":
                "{}",
        },
    ]

    for case in cases:
        result = classify_page_response(
            source=SOURCE_MISSAV,
            dvd_id="JUR-821",
            requested_url=url,
            http_status=case.get(
                "http_status"
            ),
            content_type=case.get(
                "content_type"
            ),
            effective_url=case.get(
                "effective_url"
            ),
            location=case.get(
                "location"
            ),
            error=case.get(
                "error"
            ),
            body=case.get(
                "body"
            ),
        )

        require(
            result[
                "status"
            ]
            == STATUS_UNKNOWN,
            (
                "UNKNOWN boundary changed "
                "for "
                + case[
                    "name"
                ]
                + ": "
                + repr(
                    result
                )
            ),
        )

    print(
        "AVAILABILITY_UNKNOWN_FAIL_CLOSED_SMOKE=PASS"
    )


def identity_or_smoke():
    missav_url = canonical_page_url(
        SOURCE_MISSAV,
        "JUR-821",
    )

    title_only = classify_page_response(
        source=SOURCE_MISSAV,
        dvd_id="JUR-821",
        requested_url=missav_url,
        http_status=200,
        content_type="text/html",
        effective_url=missav_url,
        body=(
            "<html>"
            "<title>JUR-821 example</title>"
            "<h1>Something else</h1>"
            "</html>"
        ),
    )

    require(
        title_only[
            "status"
        ]
        == STATUS_FOUND,
        "title-only identity changed",
    )

    av123_url = canonical_page_url(
        SOURCE_123AV,
        "JUR-821",
    )

    h1_only = classify_page_response(
        source=SOURCE_123AV,
        dvd_id="JUR-821",
        requested_url=av123_url,
        http_status=200,
        content_type="text/html",
        effective_url=av123_url,
        body=(
            "<html>"
            "<title>Something else</title>"
            "<h1>JUR-821 example</h1>"
            "</html>"
        ),
    )

    require(
        h1_only[
            "status"
        ]
        == STATUS_FOUND,
        "H1-only identity changed",
    )

    print(
        "AVAILABILITY_TITLE_OR_H1_IDENTITY_SMOKE=PASS"
    )


def request_escape_smoke():
    try:
        classify_page_response(
            source=SOURCE_MISSAV,
            dvd_id="JUR-821",
            requested_url=(
                "https://missav.ws/"
                "ko/not-jur-821"
            ),
            http_status=404,
            content_type="text/html",
            effective_url=(
                "https://missav.ws/"
                "ko/not-jur-821"
            ),
            body="<html></html>",
        )

    except ValueError:
        pass

    else:
        raise RuntimeError(
            "non-canonical request URL "
            "must fail closed"
        )

    print(
        "AVAILABILITY_REQUEST_ESCAPE_FAIL_CLOSED_SMOKE=PASS"
    )


def main():
    if len(
        sys.argv
    ) != 2:
        raise RuntimeError(
            "usage: "
            "teddy_discovery_availability_smoke.py "
            "<availability-forensic>"
        )

    forensic_path = Path(
        sys.argv[1]
    )

    canonical_url_smoke()

    forensic_oracle_smoke(
        forensic_path
    )

    unknown_fail_closed_smoke()

    identity_or_smoke()

    request_escape_smoke()

    print(
        "TEDDY_AVAILABILITY_CORE_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
