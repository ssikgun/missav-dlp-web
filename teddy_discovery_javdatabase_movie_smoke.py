from __future__ import annotations

import teddy_discovery_javdatabase_movie as movie


TARGET = "SDNM-560"

URL = (
    "https://www.javdatabase.com/"
    "movies/sdnm-560/"
)


def require(
    condition,
    message,
):
    if not condition:
        raise AssertionError(
            message
        )


def synthetic_html(
    *,
    dvd_id=TARGET,
    duplicate_release=False,
    studio_host=
        "www.javdatabase.com",
):
    duplicate = ""

    if duplicate_release:
        duplicate = """
        <p class="mb-1">
          <b>Release Date: </b>
          2026-08-26
        </p>
        """

    return f"""
    <!doctype html>
    <html>
      <body>

        <!--
          Real movie pages also expose a
          DVD-matched full cover outside the
          metadata thumbnailContainer.
          This must NOT become the parser's
          metadata cover candidate.
        -->
        <div id="poster-container">
          <img
            src="https://www.javdatabase.com/covers/full/1s/1sdnm00560pl.webp"
            alt="SDNM-560 JAV Movie Cover"
          >
        </div>

        <!-- Global navigation noise -->
        <nav>
          <a
            href="https://www.javdatabase.com/idols/"
          >
            All Idols
          </a>

          <a
            href="https://www.javdatabase.com/top-jav-studios/"
          >
            Studios
          </a>

          <a
            href="https://www.javdatabase.com/genres/vr/"
          >
            VR NAV
          </a>
        </nav>

        <!-- Unrelated dates -->
        <div>
          2026-07-28
          2026-08-27
        </div>

        <div class="row">
          <div id="thumbnailContainer">
            <img
              src="https://www.javdatabase.com/covers/thumb/1s/1sdnm00560ps.webp"
              alt="SDNM-560 test cover"
            >
          </div>

          <div class="col-md-10">
            <p class="mb-1">
              <b>Title: </b>
              Test Direct Movie
            </p>

            <p class="mb-1">
              <b>JAV Series: </b>
            </p>

            <p class="mb-1">
              <b>DVD ID: </b>
              {dvd_id}
            </p>

            <p class="mb-1">
              <b>Content ID: </b>
              1sdnm00560
            </p>

            <p class="mb-1">
              <b>Release Date: </b>
              2026-08-25
            </p>

            {duplicate}

            <p class="mb-1">
              <b>Runtime: </b>
              141 min.
            </p>

            <p class="mb-1">
              <b>Studio: </b>
              <span>
                <a
                  href="https://{studio_host}/studios/sod-create/"
                  rel="tag"
                >
                  SOD Create
                </a>
              </span>
            </p>

            <p class="mb-1">
              <b>Director: </b>
            </p>

            <p class="mb-1">
              <b>Genre(s): </b>

              <span>
                <a
                  href="https://www.javdatabase.com/genres/4k/"
                >
                  4K
                </a>
              </span>

              <span>
                <a
                  href="https://www.javdatabase.com/genres/creampie/"
                >
                  Creampie
                </a>
              </span>
            </p>

            <p class="mb-1">
              <b>Idol(s)/Actress(es): </b>

              <span>
                <a
                  href="https://www.javdatabase.com/idols/yuka-arisawama/"
                >
                  Yuka Arisawama
                </a>
              </span>
            </p>
          </div>
        </div>

      </body>
    </html>
    """


def success_smoke():
    item = (
        movie
        .parse_javdatabase_movie_html(
            synthetic_html(),
            URL,
            expected_dvd_id=
                TARGET,
        )
    )

    require(
        item["source"]
        == "javdatabase-movie",
        "source changed",
    )

    require(
        item["dvd_id"]
        == TARGET,
        "DVD ID changed",
    )

    require(
        item["title"]
        == "Test Direct Movie",
        "title changed",
    )

    require(
        item["release_date"]
        == "2026-08-25",
        "release date changed",
    )

    require(
        item["studio"]
        == "SOD Create",
        "studio changed",
    )

    require(
        item["genres"]
        == [
            "4K",
            "Creampie",
        ],
        "genres changed",
    )

    require(
        item["idols"]
        == [
            "Yuka Arisawama",
        ],
        "idols changed",
    )

    require(
        item["cover_url"]
        == (
            "https://www.javdatabase.com/"
            "covers/thumb/1s/"
            "1sdnm00560ps.webp"
        ),
        "cover changed",
    )

    print(
        "DIRECT_MOVIE_SUCCESS_SMOKE=PASS"
    )


def navigation_noise_smoke():
    item = (
        movie
        .parse_javdatabase_movie_html(
            synthetic_html(),
            URL,
            expected_dvd_id=
                TARGET,
        )
    )

    require(
        "All Idols"
        not in item["idols"],
        "navigation idol leaked",
    )

    require(
        "VR NAV"
        not in item["genres"],
        "navigation genre leaked",
    )

    print(
        "DIRECT_MOVIE_NAVIGATION_BOUNDARY_SMOKE=PASS"
    )


def dvd_mismatch_smoke():
    try:
        movie.parse_javdatabase_movie_html(
            synthetic_html(
                dvd_id="ABC-123",
            ),
            URL,
            expected_dvd_id=
                TARGET,
        )

    except ValueError:
        print(
            "DIRECT_MOVIE_DVD_MISMATCH_FAIL_CLOSED=PASS"
        )
        return

    raise AssertionError(
        "DVD mismatch did not fail"
    )


def duplicate_release_smoke():
    try:
        movie.parse_javdatabase_movie_html(
            synthetic_html(
                duplicate_release=True,
            ),
            URL,
            expected_dvd_id=
                TARGET,
        )

    except ValueError:
        print(
            "DIRECT_MOVIE_DUPLICATE_RELEASE_FAIL_CLOSED=PASS"
        )
        return

    raise AssertionError(
        "duplicate release did not fail"
    )


def offhost_studio_smoke():
    try:
        movie.parse_javdatabase_movie_html(
            synthetic_html(
                studio_host=
                    "example.com",
            ),
            URL,
            expected_dvd_id=
                TARGET,
        )

    except ValueError:
        print(
            "DIRECT_MOVIE_OFFHOST_STUDIO_FAIL_CLOSED=PASS"
        )
        return

    raise AssertionError(
        "off-host studio did not fail"
    )


def envelope_smoke():
    item = (
        movie
        .parse_javdatabase_movie_envelope(
            {
                "status": 200,
                "requested_url":
                    URL,
                "final_url":
                    URL,
                "body":
                    synthetic_html(),
            },
            expected_dvd_id=
                TARGET,
        )
    )

    require(
        item["dvd_id"]
        == TARGET,
        "envelope DVD changed",
    )

    try:
        (
            movie
            .parse_javdatabase_movie_envelope(
                {
                    "status": 404,
                    "final_url":
                        URL,
                    "body":
                        "",
                },
                expected_dvd_id=
                    TARGET,
            )
        )

    except ValueError:
        print(
            "DIRECT_MOVIE_ENVELOPE_STATUS_FAIL_CLOSED=PASS"
        )

    else:
        raise AssertionError(
            "non-200 envelope did not fail"
        )


def main():
    success_smoke()
    navigation_noise_smoke()
    dvd_mismatch_smoke()
    duplicate_release_smoke()
    offhost_studio_smoke()
    envelope_smoke()

    print(
        "JAVDATABASE_DIRECT_MOVIE_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
