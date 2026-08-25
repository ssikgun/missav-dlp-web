from dataclasses import dataclass
from pathlib import Path
import re
from typing import Optional


@dataclass(frozen=True)
class DvdIdMatch:
    dvd_id: str
    method: str


# Teddy-controlled filenames and the current library both put the
# authoritative DVD ID at the beginning of the filename.
#
# Examples:
#   SONE-978 title.mp4
#   [snos-334] title.mp4
#   [ebwh-350-uncensored-leak] EBWH-350 title.mp4
#   FC2-PPV-4592689 title.mp4
#
# Deliberately DO NOT scan arbitrary title prose for candidates.
# That would turn text such as "Kcup 173cm" into a false KCUP-173 ID.

LEADING_FC2_RE = re.compile(
    r"^\s*\[?\s*FC2[\s_-]*PPV[\s_-]*(\d{4,9})(?!\d)",
    re.I,
)

LEADING_STANDARD_RE = re.compile(
    r"^\s*\[?\s*"
    r"([A-Z0-9]{2,12})[-_]"
    r"(\d{2,8})([A-Z]{0,3})"
    r"(?=\]|\s|[._-]|$)",
    re.I,
)

LEADING_COMPACT_RE = re.compile(
    r"^\s*\[?\s*"
    r"([A-Z]{2,12})"
    r"(\d{2,6})([A-Z]{0,3})"
    r"(?=\]|\s|[._-]|$)",
    re.I,
)

NOISE_PREFIXES = {
    "HD",
    "FHD",
    "UHD",
    "MP",
    "FPS",
}


def _normalize_prefix(prefix: str) -> Optional[str]:
    value = prefix.upper().strip("-_ ")

    if not value:
        return None

    if value in NOISE_PREFIXES:
        return None

    if not any(ch.isalpha() for ch in value):
        return None

    return value


def parse_dvd_id(filename: str) -> Optional[DvdIdMatch]:
    stem = Path(filename).stem

    match = LEADING_FC2_RE.search(stem)
    if match:
        return DvdIdMatch(
            dvd_id=f"FC2-PPV-{match.group(1)}",
            method="fc2-leading",
        )

    match = LEADING_STANDARD_RE.search(stem)
    if match:
        prefix = _normalize_prefix(match.group(1))
        if prefix:
            return DvdIdMatch(
                dvd_id=(
                    f"{prefix}-"
                    f"{match.group(2)}"
                    f"{match.group(3).upper()}"
                ),
                method="standard-leading",
            )

    match = LEADING_COMPACT_RE.search(stem)
    if match:
        prefix = _normalize_prefix(match.group(1))
        if prefix:
            return DvdIdMatch(
                dvd_id=(
                    f"{prefix}-"
                    f"{match.group(2)}"
                    f"{match.group(3).upper()}"
                ),
                method="compact-leading",
            )

    return None
