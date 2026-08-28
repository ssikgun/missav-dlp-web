from pathlib import Path
import tempfile

import teddy_discovery_db as discovery_db

from teddy_discovery_variant_classifier import (
    extract_owned_uncensored_missav_variants,
    has_uncensored_token,
    is_owned_uncensored_missav_url,
    preferred_owned_uncensored_missav_variant,
)

from teddy_discovery_variants import (
    persist_title_variant,
    read_title_variants,
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def token_smoke():
    require(
        has_uncensored_token(
            "sw-893-uncensored-leak"
        ),
        "owned uncensored token missed",
    )

    require(
        has_uncensored_token(
            "SW-893_UNCENSORED"
        ),
        "underscore uncensored "
        "token missed",
    )

    require(
        not has_uncensored_token(
            "sw-893-uncensoredleak"
        ),
        "joined uncensored token "
        "must not match",
    )

    require(
        not has_uncensored_token(
            "sw-893-leak"
        ),
        "leak alone must not match",
    )

    print(
        "VARIANT_UNCENSORED_TOKEN_SMOKE=PASS"
    )


def ownership_smoke():
    require(
        is_owned_uncensored_missav_url(
            dvd_id="SW-893",
            page_url=(
                "https://missav123.com/"
                "ko/"
                "sw-893-uncensored-leak"
            ),
        ),
        "owned variant rejected",
    )

    require(
        is_owned_uncensored_missav_url(
            dvd_id="SW-893",
            page_url=(
                "https://missav.ws/"
                "ko/"
                "sw-893-uncensored-leak"
            ),
        ),
        "MissAV-family mirror "
        "variant rejected",
    )

    require(
        not is_owned_uncensored_missav_url(
            dvd_id="SW-893",
            page_url=(
                "https://missav123.com/"
                "ko/"
                "adn-785-uncensored-leak"
            ),
        ),
        "other-title variant "
        "must be rejected",
    )

    require(
        not is_owned_uncensored_missav_url(
            dvd_id="SW-893",
            page_url=(
                "https://missav123.com/"
                "ko/"
                "sw-893-leak"
            ),
        ),
        "leak-only link "
        "must be rejected",
    )

    require(
        not is_owned_uncensored_missav_url(
            dvd_id="SW-893",
            page_url=(
                "https://missav123.com/"
                "ko/"
                "sw-893-uncensoredleak"
            ),
        ),
        "non-separated uncensored "
        "must be rejected",
    )

    require(
        not is_owned_uncensored_missav_url(
            dvd_id="SW-893",
            page_url=(
                "https://example.com/"
                "ko/"
                "sw-893-uncensored-leak"
            ),
        ),
        "off-family URL "
        "must be rejected",
    )

    require(
        not is_owned_uncensored_missav_url(
            dvd_id="SW-893",
            page_url=(
                "https://missav123.com/"
                "ko/"
                "xsw-893-uncensored-leak"
            ),
        ),
        "embedded DVD-ID prefix "
        "must be rejected",
    )

    print(
        "VARIANT_OWNERSHIP_SMOKE=PASS"
    )


def html_extraction_smoke():
    html = """
    <html>
      <body>

        <p>
          uncensored
        </p>

        <a href="/ko/sw-893-leak">
          leak only
        </a>

        <a href="/ko/adn-785-uncensored-leak">
          wrong title
        </a>

        <a href="/ko/sw-893-uncensoredleak">
          joined token
        </a>

        <a href="https://example.com/ko/sw-893-uncensored-leak">
          wrong family
        </a>

        <a href="javascript:void(0)">
          invalid
        </a>

        <a href="https://missav.ws/ko/sw-893-uncensored-leak">
          owned mirror
        </a>

        <a href="https://missav123.com/ko/sw-893-uncensored-leak#player">
          owned preferred
        </a>

        <a href="/ko/sw-893-uncensored-leak">
          duplicate preferred
        </a>

      </body>
    </html>
    """

    rows = (
        extract_owned_uncensored_missav_variants(
            html,
            dvd_id="SW-893",
            page_url=(
                "https://missav123.com/"
                "ko/sw-893"
            ),
        )
    )

    require(
        len(
            rows
        )
        == 2,
        "owned variant count mismatch",
    )

    require(
        rows[0][
            "page_url"
        ]
        == (
            "https://missav123.com/"
            "ko/"
            "sw-893-uncensored-leak"
        ),
        "missav123 must be preferred",
    )

    require(
        rows[0][
            "dvd_id"
        ]
        == "SW-893",
        "canonical DVD ID mismatch",
    )

    require(
        rows[0][
            "variant_kind"
        ]
        == "uncensored",
        "variant kind mismatch",
    )

    require(
        rows[0][
            "confirmed"
        ]
        == 1,
        "confirmed flag mismatch",
    )

    preferred = (
        preferred_owned_uncensored_missav_variant(
            html,
            dvd_id="SW-893",
            page_url=(
                "https://missav123.com/"
                "ko/sw-893"
            ),
        )
    )

    require(
        preferred
        == rows[0],
        "preferred variant mismatch",
    )

    print(
        "VARIANT_HTML_EXTRACTION_SMOKE=PASS"
    )

    print(
        "VARIANT_MISSAV123_PREFERENCE_SMOKE=PASS"
    )


def text_only_noise_smoke():
    html = """
    <html>
      <body>

        <div>
          SW-893 uncensored
        </div>

        <div>
          sw-893-uncensored-leak
        </div>

        <a href="/ko/sw-893">
          standard
        </a>

        <a href="/ko/adn-785-uncensored-leak">
          other title
        </a>

      </body>
    </html>
    """

    rows = (
        extract_owned_uncensored_missav_variants(
            html,
            dvd_id="SW-893",
            page_url=(
                "https://missav123.com/"
                "ko/sw-893"
            ),
        )
    )

    require(
        rows == [],
        "generic text must not "
        "create variant",
    )

    print(
        "VARIANT_GENERIC_TEXT_IGNORED_SMOKE=PASS"
    )


def invalid_context_smoke():
    try:
        extract_owned_uncensored_missav_variants(
            """
            <a href="/ko/sw-893-uncensored-leak">
              candidate
            </a>
            """,
            dvd_id="SW-893",
            page_url=(
                "https://example.com/"
                "ko/sw-893"
            ),
        )

    except ValueError:
        pass

    else:
        raise RuntimeError(
            "off-family context "
            "must fail closed"
        )

    try:
        extract_owned_uncensored_missav_variants(
            """
            <a href="/ko/sw-893-uncensored-leak">
              candidate
            </a>
            """,
            dvd_id="SW-893",
            page_url=(
                "https://missav123.com/"
                "ko/adn-785"
            ),
        )

    except ValueError:
        pass

    else:
        raise RuntimeError(
            "wrong-title context "
            "must fail closed"
        )

    print(
        "VARIANT_CONTEXT_FAIL_CLOSED_SMOKE=PASS"
    )


def storage_compatibility_smoke():
    html = """
    <html>
      <body>

        <a href="/ko/sw-893-uncensored-leak">
          owned
        </a>

      </body>
    </html>
    """

    preferred = (
        preferred_owned_uncensored_missav_variant(
            html,
            dvd_id="SW-893",
            page_url=(
                "https://missav123.com/"
                "ko/sw-893"
            ),
        )
    )

    require(
        preferred is not None,
        "storage candidate missing",
    )

    with tempfile.TemporaryDirectory(
        prefix="teddy-variant-classifier-"
    ) as temp:

        db_path = (
            Path(temp)
            / "classifier.sqlite3"
        )

        connection = (
            discovery_db.connect(
                db_path
            )
        )

        try:
            discovery_db.initialize(
                connection
            )

            connection.execute(
                """
                INSERT INTO titles(
                    dvd_id,
                    title,
                    first_seen_at,
                    last_seen_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    "SW-893",
                    "SW-893 title",
                    (
                        "2026-08-28"
                        "T00:00:00+00:00"
                    ),
                    (
                        "2026-08-28"
                        "T00:00:00+00:00"
                    ),
                ),
            )

            connection.commit()

            stored = (
                persist_title_variant(
                    connection,
                    preferred,
                    observed_at=(
                        "2026-08-28"
                        "T01:00:00+00:00"
                    ),
                    checked_at=(
                        "2026-08-28"
                        "T01:01:00+00:00"
                    ),
                )
            )

            require(
                stored[
                    "dvd_id"
                ]
                == "SW-893",
                "stored DVD ID mismatch",
            )

            require(
                stored[
                    "variant_kind"
                ]
                == "uncensored",
                "stored kind mismatch",
            )

            require(
                stored[
                    "page_url"
                ]
                == (
                    "https://missav123.com/"
                    "ko/"
                    "sw-893-uncensored-leak"
                ),
                "stored URL mismatch",
            )

            rows = (
                read_title_variants(
                    connection,
                    dvd_id="SW-893",
                    confirmed_only=True,
                )
            )

            require(
                len(
                    rows
                )
                == 1,
                "stored variant "
                "readback mismatch",
            )

        finally:
            connection.close()

    print(
        "VARIANT_CLASSIFIER_STORAGE_COMPATIBILITY_SMOKE=PASS"
    )


def main():
    token_smoke()
    ownership_smoke()
    html_extraction_smoke()
    text_only_noise_smoke()
    invalid_context_smoke()
    storage_compatibility_smoke()

    print(
        "TEDDY_DISCOVERY_VARIANT_CLASSIFIER_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
