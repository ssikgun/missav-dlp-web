#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


EXPECTED_ORIGINAL_SHA = (
    "b9750025167d8f37edd07e4d6f1242e6"
    "b106a50134e18f7ddc1ae9dd1961dcbf"
)

EXPECTED_PATCHED_SHA = (
    "9d5dfcddb62a13d40eda7ba9c103e00f"
    "f96c3d89d998fa5203d0f011fffc78b5"
)

EXPECTED_ORIGINAL_SIZE = 276845
EXPECTED_PATCHED_SIZE = 276881
EXPECTED_4080_COUNT = 17


REPLACEMENTS = (
    (
        "resolution-send",
        (
            "n>4080&&(n=4080),"
            "r>4080&&(r=4080)"
        ),
        (
            "n>3840&&(n=3840),"
            "r>2160&&(r=2160)"
        ),
        2,
    ),
    (
        "webrtc-resize-handler",
        (
            "g[0]*e>4080&&"
            "(g[0]=Math.floor(4080/e)),"
            "g[1]*e>4080&&"
            "(g[1]=Math.floor(4080/e))"
        ),
        (
            "g[0]*e>3840&&"
            "(g[0]=Math.floor(3840/e)),"
            "g[1]*e>2160&&"
            "(g[1]=Math.floor(2160/e))"
        ),
        1,
    ),
    (
        "websocket-initial-client-size",
        (
            "i>4080&&(i=4080),"
            "a>4080&&(a=4080),"
            "e.initialClientWidth=i,"
            "e.initialClientHeight=a"
        ),
        (
            "i>3840&&(i=3840),"
            "a>2160&&(a=2160),"
            "e.initialClientWidth=i,"
            "e.initialClientHeight=a"
        ),
        1,
    ),
    (
        "websocket-resize-handler",
        (
            "i=H?1:window.devicePixelRatio||1,"
            "a=4080;"
            "if(n*i>a&&"
            "(n=Math.floor(a/i),n=$(n)),"
            "r*i>a&&"
            "(r=Math.floor(a/i),r=$(r)),"
        ),
        (
            "i=H?1:window.devicePixelRatio||1,"
            "a=3840;"
            "if(n*i>a&&"
            "(n=Math.floor(a/i),n=$(n)),"
            "r*i>2160&&"
            "(r=Math.floor(2160/i),r=$(r)),"
        ),
        1,
    ),
    (
        "websocket-initial-settings",
        (
            "t.is_manual_resolution_mode=!1,"
            "t.initialClientWidth=$(r.width*n),"
            "t.initialClientHeight=$(r.height*n)"
        ),
        (
            "t.is_manual_resolution_mode=!1,"
            "t.initialClientWidth=Math.min(3840,$(r.width*n)),"
            "t.initialClientHeight=Math.min(2160,$(r.height*n))"
        ),
        1,
    ),
)


def sha256_bytes(
    data: bytes,
) -> str:
    return hashlib.sha256(
        data
    ).hexdigest()


def patch_bytes(
    raw: bytes,
    *,
    verify_original_sha: bool = True,
) -> bytes:
    if verify_original_sha:
        actual_sha = sha256_bytes(
            raw
        )

        if (
            actual_sha
            != EXPECTED_ORIGINAL_SHA
        ):
            raise RuntimeError(
                "unexpected Selkies core SHA: "
                + actual_sha
            )

        if (
            len(raw)
            != EXPECTED_ORIGINAL_SIZE
        ):
            raise RuntimeError(
                "unexpected Selkies core size: "
                + str(
                    len(raw)
                )
            )

    text = raw.decode(
        "utf-8"
    )

    original_count = text.count(
        "4080"
    )

    if (
        original_count
        != EXPECTED_4080_COUNT
    ):
        raise RuntimeError(
            "unexpected 4080 count: "
            + str(
                original_count
            )
        )

    expected_size_delta = 0

    for (
        label,
        old,
        new,
        expected_count,
    ) in REPLACEMENTS:
        actual_count = text.count(
            old
        )

        if (
            actual_count
            != expected_count
        ):
            raise RuntimeError(
                label
                + " occurrence mismatch: "
                + str(
                    actual_count
                )
            )

        expected_size_delta += (
            len(
                new.encode(
                    "utf-8"
                )
            )
            - len(
                old.encode(
                    "utf-8"
                )
            )
        ) * expected_count

        text = text.replace(
            old,
            new,
        )

    if expected_size_delta != 36:
        raise RuntimeError(
            "unexpected size delta: "
            + str(
                expected_size_delta
            )
        )

    if "4080" in text:
        raise RuntimeError(
            "unpatched 4080 tokens remain: "
            + str(
                text.count(
                    "4080"
                )
            )
        )

    patched = text.encode(
        "utf-8"
    )

    if (
        len(patched)
        != len(raw) + 36
    ):
        raise RuntimeError(
            "patched size delta mismatch"
        )

    if verify_original_sha:
        if (
            len(patched)
            != EXPECTED_PATCHED_SIZE
        ):
            raise RuntimeError(
                "unexpected patched size: "
                + str(
                    len(patched)
                )
            )

        patched_sha = sha256_bytes(
            patched
        )

        if (
            patched_sha
            != EXPECTED_PATCHED_SHA
        ):
            raise RuntimeError(
                "unexpected patched SHA: "
                + patched_sha
            )

    return patched


def discover_targets(
    web_root: Path,
) -> list[Path]:
    source = (
        web_root
        / "src"
        / "selkies-core.js"
    )

    assets = sorted(
        (
            web_root
            / "assets"
        ).glob(
            "selkies-core-*.js"
        )
    )

    if len(assets) != 1:
        raise RuntimeError(
            "expected exactly one "
            "selkies-core asset, got "
            + str(
                len(assets)
            )
        )

    targets = [
        source,
        assets[0],
    ]

    for target in targets:
        if not target.is_file():
            raise RuntimeError(
                "missing Selkies core: "
                + str(
                    target
                )
            )

    return targets


def patch_web_root(
    web_root: Path,
) -> list[Path]:
    targets = discover_targets(
        web_root
    )

    originals = {}

    for target in targets:
        raw = target.read_bytes()

        if (
            sha256_bytes(
                raw
            )
            != EXPECTED_ORIGINAL_SHA
        ):
            raise RuntimeError(
                "input SHA mismatch: "
                + str(
                    target
                )
            )

        originals[
            target
        ] = raw

    patched_outputs = {}

    for target, raw in originals.items():
        patched_outputs[
            target
        ] = patch_bytes(
            raw,
            verify_original_sha=True,
        )

    for target, patched in (
        patched_outputs.items()
    ):
        target.write_bytes(
            patched
        )

    for target in targets:
        result = target.read_bytes()

        if (
            sha256_bytes(
                result
            )
            != EXPECTED_PATCHED_SHA
        ):
            raise RuntimeError(
                "post-write SHA mismatch: "
                + str(
                    target
                )
            )

    return targets


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--web-root",
        default=(
            "/usr/local/lib/python3.14/"
            "dist-packages/selkies/"
            "selkies_web"
        ),
    )

    return parser.parse_args()


def main():
    args = parse_args()

    targets = patch_web_root(
        Path(
            args.web_root
        )
    )

    for target in targets:
        print(
            "PATCHED="
            + str(
                target
            )
        )

    print(
        "SELKIES_RESOLUTION_PATCH=PASS"
    )


if __name__ == "__main__":
    main()
