from teddy_discovery_ids import (
    parse_dvd_id,
)
from teddy_discovery_javinfo import (
    normalize_query_response,
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def parser_suffix_smoke():
    cases = {
        "SNOS-334":
            "SNOS-334",

        "snos334":
            "SNOS-334",

        "NAAC-088":
            "NAAC-088",

        "NAAC-088B":
            "NAAC-088B",

        "NAAC088B":
            "NAAC-088B",

        "MBDD-2194B":
            "MBDD-2194B",

        "MBDD-2194BTK":
            "MBDD-2194BTK",

        "MBDD-2194TK":
            "MBDD-2194TK",

        "START-601EC":
            "START-601EC",

        "FC2-PPV-4555371":
            "FC2-PPV-4555371",

        (
            "[ebwh-350-uncensored-leak] "
            "EBWH-350 Kcup 173cm.mp4"
        ):
            "EBWH-350",
    }

    for raw, expected in cases.items():
        parsed = parse_dvd_id(
            raw
        )

        actual = (
            parsed.dvd_id
            if parsed
            else None
        )

        require(
            actual == expected,
            (
                f"parser mismatch: "
                f"{raw!r} -> {actual!r}, "
                f"expected {expected!r}"
            ),
        )

    print(
        "PARSER_SUFFIX_SMOKE=PASS"
    )


def query_normalizer_smoke():
    payload = {
        "q": None,
        "source": "fanza",
        "count": 3,
        "results": [
            {
                "id":
                    "naac088",

                "dvdId":
                    "NAAC-088",

                "title":
                    None,

                "cover":
                    "https://example.invalid/a.jpg",

                "releaseDate":
                    "2026-10-28",

                "extra": {
                    "titleJa":
                        "Example A",

                    "maker":
                        "Maker A",

                    "categories": [
                        "Featured Actress"
                    ],

                    "actresses": [
                        {
                            "name":
                                "Actress A",

                            "image":
                                "https://example.invalid/a-actress.jpg",
                        }
                    ],

                    "actors": [],

                    "directors": [
                        "Director A"
                    ],

                    "authors": [],
                },
            },
            {
                "id":
                    "naac088b",

                "dvdId":
                    "NAAC-088B",

                "title":
                    None,

                "cover":
                    "https://example.invalid/b.jpg",

                "releaseDate":
                    "2026-10-28",

                "extra": {
                    "titleJa":
                        "Example B",

                    "maker":
                        "Maker B",

                    "categories": [
                        "Idol Video"
                    ],

                    "actresses": [],
                    "actors": [],
                    "directors": [],
                    "authors": [],
                },
            },
            {
                "id":
                    "mbdd2194btk",

                "dvdId":
                    "MBDD-2194BTK",

                "title":
                    None,

                "cover":
                    "https://example.invalid/c.jpg",

                "releaseDate":
                    "2026-10-01",

                "extra": {
                    "titleJa":
                        "Example C",

                    "maker":
                        "Maker C",

                    "categories": [],

                    "actresses": [],
                    "actors": [],

                    "directors": [
                        {
                            "name":
                                "Director C"
                        }
                    ],

                    "authors": [],
                },
            },
        ],
    }

    items = normalize_query_response(
        payload
    )

    ids = [
        item["dvd_id"]
        for item in items
    ]

    require(
        ids == [
            "NAAC-088",
            "NAAC-088B",
            "MBDD-2194BTK",
        ],
        (
            "query IDs changed: "
            + repr(ids)
        ),
    )

    require(
        len(set(ids)) == 3,
        "suffix variants collapsed",
    )

    require(
        items[0]["title"]
        == "Example A",
        "titleJa fallback failed",
    )

    require(
        items[0]["maker"]
        == "Maker A",
        "maker mapping failed",
    )

    require(
        (
            "Actress A",
            "actress",
        )
        in items[0]["people"],
        "actress mapping failed",
    )

    require(
        (
            "Director A",
            "director",
        )
        in items[0]["people"],
        "string director mapping failed",
    )

    require(
        (
            "Director C",
            "director",
        )
        in items[2]["people"],
        "object director mapping failed",
    )

    require(
        items[0]["genres"]
        == [
            "Featured Actress"
        ],
        "category mapping failed",
    )

    print(
        "QUERY_NORMALIZER_SMOKE=PASS"
    )


def main():
    parser_suffix_smoke()
    query_normalizer_smoke()

    print(
        "DISCOVERY_QUERY_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
