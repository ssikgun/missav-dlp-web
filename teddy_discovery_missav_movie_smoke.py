from __future__ import annotations

from teddy_discovery_missav_movie import (
    parse_missav_movie_envelope,
)


def _genre_anchor(
    value: str,
) -> str:
    return (
        '<a class="text-nord13 font-medium" '
        f'href="/dm1/en/genres/{value}">'
        f'{value}</a>'
    )


def fixture(
    *,
    dvd_id: str = "GANA-3432",
    release: str = "2026-08-24",
    maker: str = "ナンパTV",
    maker_label: str | None = None,
    actor: str | None = (
        "Maina, 21 Years Old, "
        "Works Part-Time At A Ramen Shop."
    ),
    actor_link: str | None = None,
    actor_label: str | None = None,
    genres: tuple[str, ...] = (
        "Big Breasts",
        "Hit On Girls",
        "Ordinary Person",
        "Exclusive",
        "G Cup",
    ),
    genre_label: str | None = None,
) -> str:
    if maker_label is None:
        maker_label = maker

    if actor_link is None:
        actor_link = actor

    if actor_label is None:
        actor_label = actor

    expected_genres = ", ".join(
        genres
    )

    if genre_label is None:
        genre_label = expected_genres

    actor_meta = (
        ""
        if actor is None
        else (
            '<meta property="og:video:actor" '
            f'content="{actor}">'
        )
    )

    actor_detail = ""

    if actor_link is not None:
        actor_detail = (
            '<div class="text-secondary">'
            '<span>Actress:</span> '
            '<a class="text-nord13 font-medium" '
            'href="/en/actresses/'
            f'{actor_link}">'
            f'{actor_label}</a>'
            '</div>'
        )

    normal_genre_links = ", ".join(
        _genre_anchor(
            genre
        )
        for genre in genres
    )

    if genre_label == expected_genres:
        genre_detail = (
            '<div class="text-secondary">'
            '<span>Genre:</span> '
            f'{normal_genre_links}'
            '</div>'
        )

    else:
        genre_detail = (
            '<div class="text-secondary">'
            '<span>Genre:</span> '
            f'{genre_label}'
            '</div>'
            '<div class="text-secondary">'
            + " ".join(
                _genre_anchor(
                    genre
                )
                for genre in genres
            )
            + '</div>'
        )

    maker_anchor = (
        '<a class="text-nord13 font-medium" '
        f'href="/en/makers/{maker}">'
        f'{maker}</a>'
    )

    if maker_label == maker:
        maker_detail = (
            '<div class="text-secondary">'
            '<span>Maker:</span> '
            f'{maker_anchor}'
            '</div>'
        )

    else:
        maker_detail = (
            '<div class="text-secondary">'
            '<span>Maker:</span> '
            f'{maker_label}'
            '</div>'
            '<div class="text-secondary">'
            f'{maker_anchor}'
            '</div>'
        )

    return f"""
    <html>
      <head>
        <meta
          property="og:title"
          content="{dvd_id} English fixture title">

        <meta
          property="og:video:release_date"
          content="{release}">

        {actor_meta}

        <meta
          property="og:video:tag"
          content="200GANA">

        <meta
          property="og:video:tag"
          content="GANA">
      </head>

      <body>

        <!-- Global navigation decoys -->
        <div class="relative xl:hidden">

          <a
            class="block px-4 py-2"
            href="/en/actresses/ranking">
            Actress Ranking
          </a>

          <a
            class="block px-4 py-2"
            href="/en/genres/VR">
            VR
          </a>

        </div>

        <!-- Actual detail block -->
        <div class="space-y-2">

          <div class="text-secondary">
            <span>Release date:</span>
            {release}
          </div>

          {actor_detail}

          {genre_detail}

          {maker_detail}

        </div>

      </body>
    </html>
    """


def envelope(
    body: str,
    *,
    dvd_id: str = "GANA-3432",
    locale: str = "en",
) -> dict[str, object]:
    url = (
        "https://missav.ws/"
        + locale
        + "/"
        + dvd_id.lower()
    )

    return {
        "status":
            200,

        "requested_url":
            url,

        "final_url":
            url,

        "body":
            body,
    }


def expect_failure(
    label: str,
    *,
    body: str,
    dvd_id: str = "GANA-3432",
    locale: str = "en",
) -> None:
    try:
        parse_missav_movie_envelope(
            envelope(
                body,
                dvd_id=dvd_id,
                locale=locale,
            ),
            expected_dvd_id=
                dvd_id,
        )

    except ValueError:
        print(
            label
            + "=PASS"
        )
        return

    raise AssertionError(
        label
        + " did not fail closed"
    )


#
# 1. Normal English contract.
#
item = parse_missav_movie_envelope(
    envelope(
        fixture()
    ),
    expected_dvd_id=
        "GANA-3432",
)

assert item["dvd_id"] == "GANA-3432"
assert item["release_date"] == "2026-08-24"
assert item["studio"] == "ナンパTV"

assert item["idols"] == [
    "Maina, 21 Years Old, "
    "Works Part-Time At A Ramen Shop."
]

assert item["genres"] == [
    "Big Breasts",
    "Hit On Girls",
    "Ordinary Person",
    "Exclusive",
    "G Cup",
]

assert "VR" not in item["genres"]
assert (
    "Actress Ranking"
    not in item["idols"]
)

assert item["brand_tags"] == [
    "200GANA",
    "GANA",
]

assert (
    item["source_url"]
    == "https://missav.ws/en/gana-3432"
)

print(
    "MISSAV_EN_FULL_CONTRACT_SMOKE=PASS"
)

print(
    "MISSAV_EN_MENU_DECOY_SMOKE=PASS"
)

print(
    "MISSAV_EN_BRAND_TAG_NOT_GENRE_SMOKE=PASS"
)

print(
    "MISSAV_EN_JAPANESE_MAKER_ALLOWED_SMOKE=PASS"
)


#
# 2. Actor-less work.
#
actorless = parse_missav_movie_envelope(
    envelope(
        fixture(
            dvd_id="IMJO-011",
            release="2026-08-22",
            maker="イマドキ性事情",
            actor=None,
            actor_link=None,
            actor_label=None,
            genres=(
                "Slim",
                "Selfie",
                "4K",
            ),
        ),
        dvd_id="IMJO-011",
    ),
    expected_dvd_id=
        "IMJO-011",
)

assert actorless["idols"] == []

print(
    "MISSAV_EN_ACTORLESS_SMOKE=PASS"
)


#
# 3. Korean locale must never be accepted
# for fallback metadata.
#
expect_failure(
    "MISSAV_EN_KO_LOCALE_REJECTED_SMOKE",
    body=fixture(),
    locale="ko",
)


#
# 4. Localized Korean actor must fail.
#
expect_failure(
    "MISSAV_EN_HANGUL_ACTOR_REJECTED_SMOKE",
    body=fixture(
        actor="한국 배우",
        actor_link="한국 배우",
        actor_label="한국 배우",
    ),
)


#
# 5. Localized Korean genre must fail.
#
expect_failure(
    "MISSAV_EN_HANGUL_GENRE_REJECTED_SMOKE",
    body=fixture(
        genres=(
            "Big Breasts",
            "아마추어",
        ),
    ),
)


#
# 6. Maker contract mismatch.
#
expect_failure(
    "MISSAV_EN_MAKER_MISMATCH_SMOKE",
    body=fixture(
        maker_label=
            "WRONG MAKER"
    ),
)


#
# 7. Actor meta/detail mismatch.
#
expect_failure(
    "MISSAV_EN_ACTOR_MISMATCH_SMOKE",
    body=fixture(
        actor=
            "Actor A",

        actor_link=
            "Actor B",

        actor_label=
            "Actor B",
    ),
)


#
# 8. Genre label/detail mismatch.
#
expect_failure(
    "MISSAV_EN_GENRE_MISMATCH_SMOKE",
    body=fixture(
        genres=(
            "Genre A",
            "Genre B",
        ),
        genre_label=
            "Genre A, Genre C",
    ),
)


#
# 9. Identity mismatch.
#
expect_failure(
    "MISSAV_EN_IDENTITY_MISMATCH_SMOKE",
    body=fixture(
        dvd_id=
            "WRONG-999"
    ),
)


#
# 10. Redirect mismatch.
#
redirected = envelope(
    fixture()
)

redirected[
    "final_url"
] = (
    "https://missav.ws/en/imjo-011"
)

try:
    parse_missav_movie_envelope(
        redirected,
        expected_dvd_id=
            "GANA-3432",
    )

except ValueError:
    print(
        "MISSAV_EN_REDIRECT_FORBIDDEN_SMOKE=PASS"
    )

else:
    raise AssertionError(
        "redirect mismatch did not fail closed"
    )


print(
    "DISCOVERY_MISSAV_ENGLISH_MOVIE_SMOKE=PASS"
)
