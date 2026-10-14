#!/usr/bin/env python3
"""Offline smoke checks for workstream routing and fail-closed governance."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from check_project_governance import validate


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _contract(version: str = "1.0.0", status: str = "APPROVED") -> str:
    return (
        "# Contract\n\n"
        f"CONTRACT_VERSION: {version}\n"
        f"PROJECT_CONTRACT_STATUS: {status}\n"
    )


def _active(
    name: str,
    task_id: str,
    status: str,
    version: str = "1.0.0",
    requires: str | None = None,
) -> str:
    requires = requires or name
    return f"""# {name} active work

WORKSTREAM: {name}
TASK_ID: {task_id}
STATUS: {status}
CONTRACT_VERSION: {version}
REQUIRES_WORKSTREAMS: {requires}

## OBJECTIVE
Complete the authorized task for {name}.

## APPROVED_SCOPE
- Change only the requested {name} files.

## PROHIBITED_SCOPE
- Do not change unrelated workstreams.

## ACCEPTANCE_CRITERIA
- Required checks pass.

## EVIDENCE
- Workstream source and task ID are recorded.

## NEXT_DECISION
The user reviews the result.
"""


def _router(extra: str = "") -> str:
    return f"""# Workstream routing

ROUTER_VERSION: 1.0.0
COMMON_CONTRACT_VERSION: 1.0.0

## WORKSTREAM: governance
STATUS: INACTIVE
TASK_ID: NONE
CONTRACT_PATH: docs/governance/PROJECT_CONTRACT.md
ACTIVE_WORK_PATH: docs/governance/governance/ACTIVE_WORK.md
AREA_HINTS:
- Governance.

## WORKSTREAM: stage11
STATUS: INACTIVE
TASK_ID: NONE
CONTRACT_PATH: docs/governance/stage11/PROJECT_CONTRACT.md
ACTIVE_WORK_PATH: docs/governance/stage11/ACTIVE_WORK.md
AREA_HINTS:
- Stage11 subtitle work.
{extra}
"""


def _setup(root: Path) -> None:
    subprocess.run(["git", "-C", str(root), "init", "--quiet"], check=True)
    _write(root, "AGENTS.md", "# Shared instructions\n")
    _write(root, "docs/governance/PROJECT_CONTRACT.md", _contract(status="APPROVED"))
    _write(root, "docs/governance/ACTIVE_WORK.md", _router())
    _write(root, "docs/governance/CHATGPT_STARTUP.md", "# Startup\n")
    _write(root, "docs/governance/governance/ACTIVE_WORK.md", _active("governance", "NONE", "INACTIVE"))
    _write(root, "docs/governance/stage11/PROJECT_CONTRACT.md", _contract(status="APPROVED"))
    _write(
        root,
        "docs/governance/stage11/ACTIVE_WORK.md",
        _active("stage11", "NONE", "INACTIVE"),
    )


def _run_case(
    name: str,
    workstreams: list[str] | None,
    task_id: str | None,
    expected_error: str | None,
    *,
    all_workstreams: bool = False,
    mutate=None,
) -> None:
    with tempfile.TemporaryDirectory(prefix="governance-case-") as temporary:
        root = Path(temporary)
        _setup(root)
        if mutate:
            mutate(root)
        errors = validate(
            root,
            workstreams,
            task_id,
            all_workstreams=all_workstreams,
        )
        if expected_error is None and errors:
            raise AssertionError(f"{name}: expected PASS, got {errors}")
        if expected_error is not None and not any(expected_error in item for item in errors):
            raise AssertionError(f"{name}: expected {expected_error!r}, got {errors}")


def _replace_file(root: Path, relative: str, old: str, new: str) -> None:
    path = root / relative
    content = path.read_text(encoding="utf-8")
    if old not in content:
        raise AssertionError(f"fixture text not found in {relative}: {old!r}")
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


def _version_mismatch(root: Path) -> None:
    _replace_file(
        root,
        "docs/governance/governance/ACTIVE_WORK.md",
        "CONTRACT_VERSION: 1.0.0",
        "CONTRACT_VERSION: 9.9.9",
    )


def _router_common_version_mismatch(root: Path) -> None:
    _replace_file(
        root,
        "docs/governance/ACTIVE_WORK.md",
        "COMMON_CONTRACT_VERSION: 1.0.0",
        "COMMON_CONTRACT_VERSION: 9.9.9",
    )


def _remove_common_contract(root: Path) -> None:
    (root / "docs/governance/PROJECT_CONTRACT.md").unlink()


def _remove_stage11_contract(root: Path) -> None:
    (root / "docs/governance/stage11/PROJECT_CONTRACT.md").unlink()


def _remove_acceptance(root: Path) -> None:
    _replace_file(
        root,
        "docs/governance/governance/ACTIVE_WORK.md",
        "## ACCEPTANCE_CRITERIA\n- Required checks pass.\n\n",
        "",
    )


def _duplicate_task(root: Path) -> None:
    _replace_file(
        root,
        "docs/governance/governance/ACTIVE_WORK.md",
        "TASK_ID: NONE",
        "TASK_ID: NONE\nTASK_ID: P2-N",
    )


def _invalid_common_contract_status(root: Path) -> None:
    _replace_file(
        root,
        "docs/governance/PROJECT_CONTRACT.md",
        "PROJECT_CONTRACT_STATUS: APPROVED",
        "PROJECT_CONTRACT_STATUS: DRAFT",
    )


def _activate_governance(root: Path) -> None:
    _replace_file(
        root,
        "docs/governance/ACTIVE_WORK.md",
        "## WORKSTREAM: governance\nSTATUS: INACTIVE\nTASK_ID: NONE",
        "## WORKSTREAM: governance\nSTATUS: IN_PROGRESS\nTASK_ID: GOV-001",
    )
    _replace_file(
        root,
        "docs/governance/governance/ACTIVE_WORK.md",
        "TASK_ID: NONE\nSTATUS: INACTIVE",
        "TASK_ID: GOV-001\nSTATUS: IN_PROGRESS",
    )


def _activate_stage11(root: Path) -> None:
    _replace_file(
        root,
        "docs/governance/ACTIVE_WORK.md",
        "## WORKSTREAM: stage11\nSTATUS: INACTIVE\nTASK_ID: NONE",
        "## WORKSTREAM: stage11\nSTATUS: IN_PROGRESS\nTASK_ID: S11-001",
    )
    _replace_file(
        root,
        "docs/governance/stage11/ACTIVE_WORK.md",
        "TASK_ID: NONE\nSTATUS: INACTIVE",
        "TASK_ID: S11-001\nSTATUS: IN_PROGRESS",
    )


def _stage11_maps_to_common_only(root: Path) -> None:
    _activate_stage11(root)
    _replace_file(
        root,
        "docs/governance/ACTIVE_WORK.md",
        "CONTRACT_PATH: docs/governance/stage11/PROJECT_CONTRACT.md",
        "CONTRACT_PATH: docs/governance/PROJECT_CONTRACT.md",
    )


def _add_workstream(
    root: Path,
    name: str,
    task_id: str,
    requires: str,
    *,
    contract_version: str = "1.0.0",
) -> None:
    contract_path = f"docs/governance/{name}/PROJECT_CONTRACT.md"
    active_path = f"docs/governance/{name}/ACTIVE_WORK.md"
    _write(root, contract_path, _contract(contract_version, "APPROVED"))
    _write(root, active_path, _active(name, task_id, "IN_PROGRESS", requires=requires))
    route = f"""
## WORKSTREAM: {name}
STATUS: IN_PROGRESS
TASK_ID: {task_id}
CONTRACT_PATH: {contract_path}
ACTIVE_WORK_PATH: {active_path}
AREA_HINTS:
- Synthetic smoke-test workstream.
"""
    path = root / "docs/governance/ACTIVE_WORK.md"
    path.write_text(path.read_text(encoding="utf-8") + route, encoding="utf-8")


def _approve_common(root: Path) -> None:
    document = (root / "docs/governance/PROJECT_CONTRACT.md").read_text(encoding="utf-8")
    if "PROJECT_CONTRACT_STATUS: APPROVED" not in document:
        raise AssertionError("common contract fixture must be approved")


def _add_discovery(root: Path) -> None:
    _approve_common(root)
    _add_workstream(root, "discovery", "DISC-001", "discovery")


def _add_shared_workstreams(root: Path) -> None:
    _approve_common(root)
    related = "shared_a,shared_b"
    _add_workstream(root, "shared_a", "SHARED-001", related)
    _add_workstream(root, "shared_b", "SHARED-001", related)


def _break_second_shared_contract(root: Path) -> None:
    _replace_file(
        root,
        "docs/governance/shared_b/PROJECT_CONTRACT.md",
        "CONTRACT_VERSION: 1.0.0",
        "CONTRACT_VERSION: 2.0.0",
    )


def _nested_root_case() -> None:
    with tempfile.TemporaryDirectory(prefix="governance-root-case-") as temporary:
        root = Path(temporary)
        subprocess.run(["git", "-C", str(root), "init", "--quiet"], check=True)
        nested = root / "nested"
        nested.mkdir()
        errors = validate(nested, ["governance"], "GOV-001")
        expected = "is not Git top-level"
        if not any(expected in item for item in errors):
            raise AssertionError(f"nested non-root directory: expected {expected!r}, got {errors}")


def main() -> int:
    cases = (
        ("valid GOV-001 in an explicitly active fixture", ["governance"], "GOV-001", None, False, _activate_governance),
        ("all-workstreams structural check", None, None, None, True, None),
        ("completed GOV-001 cannot run from the final inactive registry", ["governance"], "GOV-001", "not runnable: STATUS=INACTIVE", False, None),
        ("nonexistent task ID", ["governance"], "GOV-999", "does not match governance active task", False, None),
        ("unauthorized P2 task ID", ["governance"], "P2-N", "does not match governance active task", False, None),
        ("contract version mismatch", ["governance"], "GOV-001", "does not match its contract", False, lambda root: (_activate_governance(root), _version_mismatch(root))),
        ("router common contract version mismatch", ["governance"], "GOV-001", "COMMON_CONTRACT_VERSION does not match common contract", False, lambda root: (_activate_governance(root), _router_common_version_mismatch(root))),
        ("missing common contract", ["governance"], "GOV-001", "docs/governance/PROJECT_CONTRACT.md", False, _remove_common_contract),
        ("missing acceptance criteria", ["governance"], "GOV-001", "ACCEPTANCE_CRITERIA", False, _remove_acceptance),
        ("multiple active task IDs", ["governance"], "GOV-001", "exactly one non-empty TASK_ID", False, _duplicate_task),
        ("invalid contract status", ["governance"], "GOV-001", "PROJECT_CONTRACT_STATUS must be", False, _invalid_common_contract_status),
        ("approved Stage11 contract without an active task is blocked", ["stage11"], "S11-001", "not runnable: STATUS=INACTIVE", False, None),
        ("Stage11 contract is required", None, None, "docs/governance/stage11/PROJECT_CONTRACT.md", True, _remove_stage11_contract),
        ("Stage11 task has its own approved contract", ["stage11"], "S11-001", None, False, _activate_stage11),
        ("Stage11 cannot use only common contract", ["stage11"], "S11-001", "stage11 must use its required contract", False, _stage11_maps_to_common_only),
        ("unrelated registered work passes while Stage11 is inactive", ["discovery"], "DISC-001", None, False, _add_discovery),
        ("unregistered workstream fails closed", ["discovery"], "DISC-001", "workstream is not registered", False, None),
        ("shared task requires every related workstream", ["shared_a"], "SHARED-001", "also requires selected workstreams: shared_b", False, _add_shared_workstreams),
        ("shared task checks every selected contract", ["shared_a", "shared_b"], "SHARED-001", "does not match its contract", False, lambda root: (_add_shared_workstreams(root), _break_second_shared_contract(root))),
        ("all shared contracts and active IDs pass", ["shared_a", "shared_b"], "SHARED-001", None, False, _add_shared_workstreams),
    )
    for name, workstreams, task_id, expected_error, all_workstreams, mutate in cases:
        _run_case(
            name,
            workstreams,
            task_id,
            expected_error,
            all_workstreams=all_workstreams,
            mutate=mutate,
        )
        print(f"PASS: {name}")
    _nested_root_case()
    print("PASS: nested non-root directory")
    print(f"Governance smoke: {len(cases) + 1} checks PASS, 0 FAIL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
