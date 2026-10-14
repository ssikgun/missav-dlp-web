#!/usr/bin/env python3
"""Fail-closed workstream-aware checks for Downloader governance documents."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


COMMON_DOCUMENTS = (
    Path("AGENTS.md"),
    Path("docs/governance/PROJECT_CONTRACT.md"),
    Path("docs/governance/ACTIVE_WORK.md"),
    Path("docs/governance/CHATGPT_STARTUP.md"),
)
CONTRACT_STATUSES = {"DRAFT_PENDING_USER_APPROVAL", "APPROVED"}
ROUTE_STATUSES = {
    "IN_PROGRESS",
    "READY_FOR_USER_REVIEW",
    "BLOCKED",
    "PAUSED_FOR_GOVERNANCE",
    "INACTIVE",
}
RUNNABLE_STATUSES = {"IN_PROGRESS", "READY_FOR_USER_REVIEW"}
VERSION_RE = re.compile(r"\A[0-9]+\.[0-9]+\.[0-9]+\Z")
TASK_ID_RE = re.compile(r"\A[A-Z][A-Z0-9]*-[A-Z0-9]+\Z")
WORKSTREAM_RE = re.compile(r"\A[a-z][a-z0-9_-]*\Z")
EXPECTED_WORKSTREAM_PATHS = {
    "governance": (
        Path("docs/governance/PROJECT_CONTRACT.md"),
        Path("docs/governance/governance/ACTIVE_WORK.md"),
    ),
    "stage11": (
        Path("docs/governance/stage11/PROJECT_CONTRACT.md"),
        Path("docs/governance/stage11/ACTIVE_WORK.md"),
    ),
}


def _field_values(document: str, name: str) -> list[str]:
    return re.compile(rf"(?m)^{re.escape(name)}:\s*(.*?)\s*$").findall(document)


def _single_field(document: str, name: str, label: str, errors: list[str]) -> str | None:
    values = _field_values(document, name)
    if len(values) != 1 or not values[0]:
        errors.append(f"{label} must contain exactly one non-empty {name} field")
        return None
    return values[0]


def _section_body(document: str, heading: str) -> str | None:
    pattern = re.compile(
        rf"(?ms)^## {re.escape(heading)}\s*\n(.*?)(?=^## (?!#)|\Z)"
    )
    match = pattern.search(document)
    return match.group(1).strip() if match else None


def _check_active_sections(document: str, label: str, errors: list[str]) -> None:
    for heading, require_bullet in (
        ("OBJECTIVE", False),
        ("APPROVED_SCOPE", True),
        ("PROHIBITED_SCOPE", True),
        ("ACCEPTANCE_CRITERIA", True),
        ("EVIDENCE", True),
        ("NEXT_DECISION", False),
    ):
        body = _section_body(document, heading)
        if not body or not body.strip(" \t\r\n-*"):
            errors.append(f"{label} section {heading} is missing or empty")
        elif require_bullet and not any(
            line.lstrip().startswith("- ") for line in body.splitlines()
        ):
            errors.append(f"{label} section {heading} must contain at least one bullet")


def _git_root(path: Path) -> tuple[Path | None, str | None]:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return None, f"could not run git to verify repository root: {exc}"
    if result.returncode != 0:
        detail = result.stderr.strip() or "not a Git repository"
        return None, f"repository root verification failed: {detail}"
    return Path(result.stdout.strip()).resolve(), None


def _safe_repo_path(root: Path, raw: str, label: str, errors: list[str]) -> Path | None:
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        errors.append(f"{label} must be a repository-relative path without '..': {raw}")
        return None
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        errors.append(f"{label} resolves outside the repository: {raw}")
        return None
    return path


def _read_text(path: Path, label: str, errors: list[str]) -> str | None:
    if not path.is_file():
        errors.append(f"required governance document is missing: {label}")
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"cannot read {label}: {exc}")
        return None
    if not content.strip():
        errors.append(f"required governance document is empty: {label}")
        return None
    return content


def _contract_metadata(
    root: Path, relative: Path, label: str, errors: list[str]
) -> tuple[str | None, str | None]:
    document = _read_text(root / relative, relative.as_posix(), errors)
    if document is None:
        return None, None
    version = _single_field(document, "CONTRACT_VERSION", label, errors)
    status = _single_field(document, "PROJECT_CONTRACT_STATUS", label, errors)
    if version and not VERSION_RE.fullmatch(version):
        errors.append(f"{label} CONTRACT_VERSION must use MAJOR.MINOR.PATCH")
    if status and status not in CONTRACT_STATUSES:
        errors.append(
            f"{label} PROJECT_CONTRACT_STATUS must be "
            "DRAFT_PENDING_USER_APPROVAL or APPROVED"
        )
    return version, status


def _registry_sections(router: str, errors: list[str]) -> dict[str, str]:
    matches = list(
        re.finditer(r"(?m)^## WORKSTREAM:\s*([a-z][a-z0-9_-]*)\s*$", router)
    )
    if not matches:
        errors.append("ACTIVE_WORK.md has no registered WORKSTREAM sections")
        return {}
    registry: dict[str, str] = {}
    for index, match in enumerate(matches):
        name = match.group(1)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(router)
        if name in registry:
            errors.append(f"ACTIVE_WORK.md has duplicate workstream registration: {name}")
        else:
            registry[name] = router[match.end() : end]
    return registry


def _csv_names(value: str, label: str, errors: list[str]) -> set[str]:
    names = [item.strip() for item in value.split(",") if item.strip()]
    if not names or len(names) != len(set(names)):
        errors.append(f"{label} must contain a non-empty, duplicate-free comma-separated list")
        return set()
    invalid = [name for name in names if not WORKSTREAM_RE.fullmatch(name)]
    if invalid:
        errors.append(f"{label} contains an invalid workstream name: {invalid[0]}")
        return set()
    return set(names)


def _validate_workstream(
    root: Path,
    name: str,
    route_block: str,
    registry_names: set[str],
    errors: list[str],
) -> dict[str, str | set[str] | None]:
    label = f"workstream {name}"
    fields: dict[str, str | None] = {}
    for key in ("STATUS", "TASK_ID", "CONTRACT_PATH", "ACTIVE_WORK_PATH"):
        fields[key] = _single_field(route_block, key, f"ACTIVE_WORK.md {label}", errors)

    raw_contract = fields["CONTRACT_PATH"]
    raw_active = fields["ACTIVE_WORK_PATH"]
    contract_rel = (
        _safe_repo_path(root, raw_contract, f"{label} CONTRACT_PATH", errors)
        if raw_contract
        else None
    )
    active_rel = (
        _safe_repo_path(root, raw_active, f"{label} ACTIVE_WORK_PATH", errors)
        if raw_active
        else None
    )
    if contract_rel:
        contract_rel = contract_rel.relative_to(root)
    if active_rel:
        active_rel = active_rel.relative_to(root)

    expected_paths = EXPECTED_WORKSTREAM_PATHS.get(name)
    if expected_paths and contract_rel and contract_rel != expected_paths[0]:
        errors.append(
            f"{label} must use its required contract {expected_paths[0].as_posix()}"
        )
    if expected_paths and active_rel and active_rel != expected_paths[1]:
        errors.append(
            f"{label} must use its required active-work file {expected_paths[1].as_posix()}"
        )
    if name not in EXPECTED_WORKSTREAM_PATHS and contract_rel == Path(
        "docs/governance/PROJECT_CONTRACT.md"
    ):
        errors.append(f"{label} requires a workstream-specific contract")

    route_status = fields["STATUS"]
    route_task_id = fields["TASK_ID"]
    if route_status and route_status not in ROUTE_STATUSES:
        errors.append(f"ACTIVE_WORK.md {label} has an invalid STATUS: {route_status}")
    if route_task_id and route_task_id != "NONE" and not TASK_ID_RE.fullmatch(route_task_id):
        errors.append(f"ACTIVE_WORK.md {label} has an invalid TASK_ID: {route_task_id}")
    if route_status in RUNNABLE_STATUSES and route_task_id == "NONE":
        errors.append(f"ACTIVE_WORK.md {label} is runnable but has no TASK_ID")
    if route_status in {"PAUSED_FOR_GOVERNANCE", "INACTIVE"} and route_task_id not in {
        "NONE",
        None,
    }:
        errors.append(f"ACTIVE_WORK.md {label} must use TASK_ID NONE while paused/inactive")

    contract_version: str | None = None
    contract_status: str | None = None
    active_version: str | None = None
    active_status: str | None = None
    active_task_id: str | None = None
    required_workstreams: set[str] = set()
    if contract_rel:
        contract_version, contract_status = _contract_metadata(
            root, contract_rel, f"{label} contract", errors
        )
    if active_rel:
        active_doc = _read_text(root / active_rel, active_rel.as_posix(), errors)
        if active_doc is not None:
            active_name = _single_field(active_doc, "WORKSTREAM", active_rel.as_posix(), errors)
            active_ids = _field_values(active_doc, "TASK_ID")
            if len(active_ids) != 1 or not active_ids[0]:
                errors.append(f"{active_rel.as_posix()} must contain exactly one non-empty TASK_ID")
            else:
                active_task_id = active_ids[0]
                if active_task_id != "NONE" and not TASK_ID_RE.fullmatch(active_task_id):
                    errors.append(f"{active_rel.as_posix()} has an invalid TASK_ID")
            active_status = _single_field(active_doc, "STATUS", active_rel.as_posix(), errors)
            active_version = _single_field(
                active_doc, "CONTRACT_VERSION", active_rel.as_posix(), errors
            )
            requires = _single_field(
                active_doc, "REQUIRES_WORKSTREAMS", active_rel.as_posix(), errors
            )
            if active_name and active_name != name:
                errors.append(
                    f"{active_rel.as_posix()} WORKSTREAM {active_name} does not match {name}"
                )
            if active_status and active_status not in ROUTE_STATUSES:
                errors.append(f"{active_rel.as_posix()} has an invalid STATUS: {active_status}")
            if requires:
                required_workstreams = _csv_names(
                    requires, f"{active_rel.as_posix()} REQUIRES_WORKSTREAMS", errors
                )
                if name not in required_workstreams:
                    errors.append(
                        f"{active_rel.as_posix()} REQUIRES_WORKSTREAMS must include {name}"
                    )
                missing_registrations = required_workstreams - registry_names
                if missing_registrations:
                    errors.append(
                        f"{active_rel.as_posix()} requires unregistered workstreams: "
                        + ", ".join(sorted(missing_registrations))
                    )
            _check_active_sections(active_doc, active_rel.as_posix(), errors)

    if route_status and active_status and route_status != active_status:
        errors.append(f"{label} route STATUS does not match its active-work file")
    if route_task_id and active_task_id and route_task_id != active_task_id:
        errors.append(f"{label} route TASK_ID does not match its active-work file")
    if active_version and not VERSION_RE.fullmatch(active_version):
        errors.append(f"{label} ACTIVE_WORK CONTRACT_VERSION must use MAJOR.MINOR.PATCH")
    if contract_version and active_version and contract_version != active_version:
        errors.append(f"{label} active-work CONTRACT_VERSION does not match its contract")

    return {
        "status": route_status,
        "task_id": route_task_id,
        "contract_status": contract_status,
        "required_workstreams": required_workstreams,
    }


def validate(
    repo_root: Path,
    workstreams: list[str] | None = None,
    requested_task_id: str | None = None,
    *,
    all_workstreams: bool = False,
) -> list[str]:
    """Return structural or authorization errors for selected workstreams."""

    errors: list[str] = []
    root = repo_root.resolve()
    actual_root, git_error = _git_root(root)
    if git_error:
        errors.append(git_error)
    elif actual_root != root:
        errors.append(f"provided repository root {root} is not Git top-level {actual_root}")

    common_text: dict[Path, str] = {}
    for relative in COMMON_DOCUMENTS:
        content = _read_text(root / relative, relative.as_posix(), errors)
        if content is not None:
            common_text[relative] = content

    common_contract = common_text.get(Path("docs/governance/PROJECT_CONTRACT.md"), "")
    common_version = _single_field(
        common_contract, "CONTRACT_VERSION", "PROJECT_CONTRACT.md", errors
    )
    common_status = _single_field(
        common_contract, "PROJECT_CONTRACT_STATUS", "PROJECT_CONTRACT.md", errors
    )
    if common_version and not VERSION_RE.fullmatch(common_version):
        errors.append("PROJECT_CONTRACT.md CONTRACT_VERSION must use MAJOR.MINOR.PATCH")
    if common_status and common_status not in CONTRACT_STATUSES:
        errors.append(
            "PROJECT_CONTRACT.md PROJECT_CONTRACT_STATUS must be "
            "DRAFT_PENDING_USER_APPROVAL or APPROVED"
        )

    router = common_text.get(Path("docs/governance/ACTIVE_WORK.md"), "")
    router_version = _single_field(router, "ROUTER_VERSION", "ACTIVE_WORK.md", errors)
    router_common_version = _single_field(
        router, "COMMON_CONTRACT_VERSION", "ACTIVE_WORK.md", errors
    )
    if router_version and not VERSION_RE.fullmatch(router_version):
        errors.append("ACTIVE_WORK.md ROUTER_VERSION must use MAJOR.MINOR.PATCH")
    if router_common_version and not VERSION_RE.fullmatch(router_common_version):
        errors.append("ACTIVE_WORK.md COMMON_CONTRACT_VERSION must use MAJOR.MINOR.PATCH")
    if common_version and router_common_version and common_version != router_common_version:
        errors.append("ACTIVE_WORK.md COMMON_CONTRACT_VERSION does not match common contract")

    registry = _registry_sections(router, errors)
    registry_names = set(registry)
    if all_workstreams:
        if workstreams:
            errors.append("--all-workstreams cannot be combined with --workstream")
        if requested_task_id:
            errors.append("--all-workstreams is structural only and cannot take --task-id")
        selected_names = list(registry)
    else:
        selected_names = workstreams or []
        if not selected_names:
            errors.append("select at least one --workstream or use --all-workstreams")
        if len(selected_names) != len(set(selected_names)):
            errors.append("--workstream selections must be unique")
        if requested_task_id is None:
            errors.append("--task-id is required when selecting workstream task authorization")
        elif not TASK_ID_RE.fullmatch(requested_task_id):
            errors.append("requested --task-id has invalid format")

    selected: dict[str, dict[str, str | set[str] | None]] = {}
    for name in selected_names:
        if not WORKSTREAM_RE.fullmatch(name):
            errors.append(f"invalid workstream name: {name}")
            continue
        route_block = registry.get(name)
        if route_block is None:
            errors.append(f"workstream is not registered: {name}")
            continue
        selected[name] = _validate_workstream(
            root, name, route_block, registry_names, errors
        )

    if not all_workstreams and requested_task_id and TASK_ID_RE.fullmatch(requested_task_id):
        selected_names_set = set(selected)
        for name, result in selected.items():
            status = result["status"]
            task_id = result["task_id"]
            if status not in RUNNABLE_STATUSES:
                errors.append(f"selected workstream {name} is not runnable: STATUS={status}")
            if task_id != requested_task_id:
                errors.append(
                    f"requested task {requested_task_id} does not match {name} active task {task_id}"
                )
            if name != "governance" and result["contract_status"] != "APPROVED":
                errors.append(f"selected workstream {name} contract is not APPROVED")
            if name != "governance" and common_status != "APPROVED":
                errors.append("common project contract is not APPROVED for non-governance work")
            required = result["required_workstreams"]
            if isinstance(required, set) and not required.issubset(selected_names_set):
                missing = sorted(required - selected_names_set)
                errors.append(
                    f"workstream {name} also requires selected workstreams: "
                    + ", ".join(missing)
                )
        selected_task_ids = {
            result["task_id"] for result in selected.values() if result["task_id"]
        }
        if len(selected_task_ids) > 1:
            errors.append("all selected workstreams must authorize the same TASK_ID")
    elif all_workstreams:
        for name, result in selected.items():
            required = result["required_workstreams"]
            if isinstance(required, set) and not required.issubset(registry_names):
                missing = sorted(required - registry_names)
                errors.append(
                    f"workstream {name} requires unregistered workstreams: "
                    + ", ".join(missing)
                )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument(
        "--workstream",
        action="append",
        dest="workstreams",
        help="registered workstream to authorize; repeat for shared work",
    )
    selector.add_argument(
        "--all-workstreams",
        action="store_true",
        help="check all registered files/metadata structurally; grants no task authorization",
    )
    parser.add_argument(
        "--task-id",
        help="require the requested task to match every selected workstream",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="repository root to verify (defaults to this script's repository)",
    )
    args = parser.parse_args(argv)
    default_root = Path(__file__).resolve().parent.parent
    root = (args.repo_root or default_root).resolve()

    errors = validate(
        root,
        args.workstreams,
        args.task_id,
        all_workstreams=args.all_workstreams,
    )
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1

    if args.all_workstreams:
        router = (root / "docs/governance/ACTIVE_WORK.md").read_text(encoding="utf-8")
        registry_names = _registry_sections(router, [])
        print(
            "PASS: structural governance check only; no task authorization; workstreams="
            + ",".join(registry_names)
        )
    else:
        print(
            f"PASS: repo={root} workstreams={','.join(args.workstreams)} task={args.task_id}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
