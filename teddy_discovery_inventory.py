from collections import Counter, defaultdict
from pathlib import Path
import sys

from teddy_discovery_ids import parse_dvd_id


VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".m4v",
    ".ts",
    ".webm",
}


def inventory(root: Path):
    files = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and "@eaDir" not in path.parts
        and path.suffix.lower() in VIDEO_EXTENSIONS
    ]

    matched = []
    unmatched = []
    methods = Counter()
    by_id = defaultdict(list)

    for path in files:
        relative = str(path.relative_to(root))
        result = parse_dvd_id(path.name)

        if result is None:
            unmatched.append(relative)
            continue

        matched.append((result.dvd_id, result.method, relative))
        methods[result.method] += 1
        by_id[result.dvd_id].append(relative)

    duplicates = {
        dvd_id: paths
        for dvd_id, paths in by_id.items()
        if len(paths) > 1
    }

    print(f"ROOT={root}")
    print(f"VIDEO_FILES={len(files)}")
    print(f"MATCHED={len(matched)}")
    print(f"UNMATCHED={len(unmatched)}")
    print(f"UNIQUE_DVD_IDS={len(by_id)}")
    print(f"DUPLICATE_DVD_IDS={len(duplicates)}")

    if files:
        print(f"MATCH_RATE={len(matched) / len(files) * 100:.2f}%")

    print(f"METHODS={dict(methods)}")

    if unmatched:
        print()
        print("===== UNMATCHED =====")
        for relative in unmatched[:100]:
            print(relative)

    if duplicates:
        print()
        print("===== DUPLICATES =====")
        for dvd_id, paths in sorted(duplicates.items()):
            print(f"{dvd_id} ({len(paths)})")
            for path in paths[:10]:
                print(f"    {path}")


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: python3 teddy_discovery_inventory.py ROOT"
        )

    inventory(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
