#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile


HERE = Path(
    __file__
).resolve().parent

MODULE_PATH = (
    HERE
    / "patch_selkies_resolution.py"
)


spec = importlib.util.spec_from_file_location(
    "patch_selkies_resolution",
    MODULE_PATH,
)

if (
    spec is None
    or spec.loader is None
):
    raise RuntimeError(
        "module import failed"
    )

module = importlib.util.module_from_spec(
    spec
)

spec.loader.exec_module(
    module
)


parts = []


for (
    _label,
    old,
    _new,
    expected_count,
) in module.REPLACEMENTS:
    for _ in range(
        expected_count
    ):
        parts.append(
            old
        )


fixture = (
    "/* synthetic selkies fixture */"
    + "|".join(
        parts
    )
)


assert fixture.count(
    "4080"
) == 17


patched = module.patch_bytes(
    fixture.encode(
        "utf-8"
    ),
    verify_original_sha=False,
)


patched_text = patched.decode(
    "utf-8"
)


assert "4080" not in patched_text

assert patched_text.count(
    "3840"
) == 10

assert patched_text.count(
    "2160"
) == 11

assert (
    len(patched)
    == len(
        fixture.encode(
            "utf-8"
        )
    ) + 36
)

print(
    "SYNTHETIC_PATCH_EXACT=PASS"
)


try:
    module.patch_bytes(
        b"not-the-pinned-base",
        verify_original_sha=True,
    )
except RuntimeError:
    print(
        "WRONG_SHA_FAIL_CLOSED=PASS"
    )
else:
    raise RuntimeError(
        "wrong SHA was accepted"
    )


with tempfile.TemporaryDirectory() as td:
    web_root = Path(
        td
    )

    (
        web_root
        / "src"
    ).mkdir()

    (
        web_root
        / "assets"
    ).mkdir()

    (
        web_root
        / "src"
        / "selkies-core.js"
    ).write_text(
        fixture,
        encoding="utf-8",
    )

    (
        web_root
        / "assets"
        / "selkies-core-test.js"
    ).write_text(
        fixture,
        encoding="utf-8",
    )

    targets = (
        module.discover_targets(
            web_root
        )
    )

    assert len(
        targets
    ) == 2

    print(
        "TARGET_DISCOVERY_EXACT=PASS"
    )


print(
    "SELKIES_RESOLUTION_PATCH_SMOKE=PASS"
)
