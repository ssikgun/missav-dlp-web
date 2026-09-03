"""Isolated regression matrix for the separate Stage10 apply service.

All databases and filesystem views in this file are temporary synthetic
fixtures.  The apply entrypoint is exercised through its injectable local
apply boundary; no production path or service manager is touched.
"""

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import os
import sqlite3
import stat
import tempfile

import teddy_discovery_import as import_mod
import teddy_discovery_jav_reconcile as reconcile_mod
import teddy_discovery_jav_reconcile_apply as apply_mod
from teddy_discovery_db import connect, initialize
from teddy_discovery_organizer import canonical_destination
from teddy_discovery_organizer_apply import (
    ExclusiveLockBusy,
    exclusive_lock,
)
from teddy_discovery_operation_lock import operation_lock
from teddy_ownership import is_owned


ROOT = apply_mod.CANONICAL_LIBRARY_ROOT
STORAGE_ROOT = "jav"
BASELINE_IDS = ("AAA-001", "BBB-002")
SEMANTIC_FIELDS = (
    "holding_id",
    "storage_root",
    "relative_path",
    "dvd_id",
    "parse_status",
    "parse_method",
    "parse_candidates_json",
    "size_bytes",
    "mtime_ns",
    "discovered_by",
    "present",
    "first_seen_at",
)


def require(value, message):
    if not value:
        raise RuntimeError(message)


class FakeStat:
    def __init__(self, mode, size=0, mtime_ns=0):
        self.st_mode = mode
        self.st_size = size
        self.st_mtime_ns = mtime_ns


class FakeEntry:
    def __init__(self, name, value):
        self.name = name
        self.value = value

    def is_symlink(self):
        return stat.S_ISLNK(self.value.st_mode)

    def is_dir(self, follow_symlinks=False):
        return stat.S_ISDIR(self.value.st_mode)

    def stat(self, follow_symlinks=False):
        return self.value


def _join(parent, name):
    return name if parent in ("", ".") else parent + "/" + name


def _entry(tree, parent, name):
    for value in tree.setdefault(parent, []):
        if value.name == name:
            return value

    value = FakeEntry(
        name,
        FakeStat(stat.S_IFDIR | 0o755),
    )
    tree[parent].append(value)
    tree.setdefault(_join(parent, name), [])
    return value


def _ensure_parent(tree, relative):
    parts = Path(relative).as_posix().split("/")
    parent = "."
    for part in parts[:-1]:
        _entry(tree, parent, part)
        parent = _join(parent, part)
    return parent, parts[-1]


def empty_tree():
    return {".": []}


def add_file(tree, relative, size, mtime_ns, mode=None):
    parent, name = _ensure_parent(tree, relative)
    tree.setdefault(parent, []).append(
        FakeEntry(
            name,
            FakeStat(
                mode or stat.S_IFREG | 0o644,
                size,
                mtime_ns,
            ),
        )
    )


def add_directory(tree, relative):
    parent = "."
    for part in Path(relative).as_posix().split("/"):
        _entry(tree, parent, part)
        parent = _join(parent, part)


def record_for(dvd_id, size=1, mtime_ns=1):
    relative = canonical_destination(
        dvd_id,
        ".mp4",
    ).as_posix()
    return {
        "relative_path": relative,
        "dvd_id": dvd_id,
        "size_bytes": size,
        "mtime_ns": mtime_ns,
    }


def tree_for_records(records):
    tree = empty_tree()
    for record in records:
        add_file(
            tree,
            record["relative_path"],
            record["size_bytes"],
            record["mtime_ns"],
        )
    for entries in tree.values():
        entries.sort(key=lambda item: item.name)
    return tree


class SequenceFilesystem:
    def __init__(self, snapshots):
        self.snapshots = snapshots
        self.scan_index = -1
        self.calls = []

    def lstat(self, relative_path):
        self.calls.append(relative_path)
        if relative_path == ".":
            self.scan_index += 1
        return FakeStat(stat.S_IFDIR | 0o755)

    def listdir(self, relative_path):
        self.calls.append(relative_path)
        index = min(
            max(self.scan_index, 0),
            len(self.snapshots) - 1,
        )
        return list(self.snapshots[index].get(relative_path, ()))


class FakeSSH:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def create_db(path):
    db = connect(path)
    initialize(db)
    db.close()


def seed_holding(path, record, present=1):
    with sqlite3.connect(path) as db:
        db.execute(
            """
            INSERT INTO holdings(
                storage_root, relative_path, dvd_id,
                parse_status, parse_method,
                parse_candidates_json, size_bytes, mtime_ns,
                discovered_by, present, first_seen_at, last_seen_at,
                last_seen_run_id
            ) VALUES (
                'jav', ?, ?, 'MATCHED', 'smoke', ?, ?, ?,
                'smoke', ?, 'first', 'last', NULL
            )
            """,
            (
                record["relative_path"],
                record["dvd_id"],
                json.dumps([record["dvd_id"]]),
                record["size_bytes"],
                record["mtime_ns"],
                present,
            ),
        )


def baseline_records():
    return tuple(
        record_for(
            dvd_id,
            size=index + 1,
            mtime_ns=(index + 1) * 100,
        )
        for index, dvd_id in enumerate(BASELINE_IDS)
    )


def baseline_db(path, *, absent=()):
    create_db(path)
    absent = set(absent)
    for record in baseline_records():
        seed_holding(
            path,
            record,
            present=int(record["dvd_id"] not in absent),
        )


def rows(path):
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in db.execute(
                """
                SELECT holding_id, storage_root, relative_path, dvd_id,
                       parse_status, parse_method,
                       parse_candidates_json, size_bytes, mtime_ns,
                       discovered_by, present, first_seen_at,
                       last_seen_at, last_seen_run_id
                FROM holdings ORDER BY holding_id
                """
            )
        ]


def semantic_hash(path):
    payload = [
        [
            row[field]
            for field in SEMANTIC_FIELDS
        ]
        for row in rows(path)
    ]
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()


def counts(path):
    with sqlite3.connect(path) as db:
        row = db.execute(
            """
            SELECT COUNT(*),
                   SUM(CASE WHEN present = 1 THEN 1 ELSE 0 END)
            FROM holdings WHERE storage_root = 'jav'
            """
        ).fetchone()
    return int(row[0]), int(row[1] or 0)


def run_count(path):
    with sqlite3.connect(path) as db:
        return db.execute(
            "SELECT COUNT(*) FROM inventory_runs"
        ).fetchone()[0]


def environment(db_path):
    return {
        "TEDDY_DISCOVERY_DB": str(db_path),
        "TEDDY_FINAL_LIBRARY_ROOT": ROOT,
        "TEDDY_FINAL_SSH_HOST": "fake-nas",
        "TEDDY_FINAL_SSH_USER": "tester",
        "TEDDY_FINAL_SSH_KEY": "/fake/key",
        "TEDDY_FINAL_SSH_KNOWN_HOSTS": "/fake/known_hosts",
    }


def local_run(db_path, filesystem, base, **kwargs):
    output = []

    def local_apply(path, ssh, **apply_kwargs):
        apply_kwargs.pop("library_root", None)
        return reconcile_mod.apply_reconciliation(
            path,
            ROOT,
            filesystem=filesystem,
            **apply_kwargs,
        )

    result = apply_mod.run_apply(
        environ=environment(db_path),
        operation_lock_path=base / "operation.lock",
        writer_lock_path=base / "writer.lock",
        writer_timeout=kwargs.pop("writer_timeout", 0.15),
        ssh_factory=FakeSSH,
        apply_fn=local_apply,
        output=output.append,
        **kwargs,
    )
    return result, output


def output_value(output, key):
    prefix = key + "="
    for value in output:
        if value.startswith(prefix):
            return value[len(prefix):]
    return None


def require_output(output, key, value):
    require(
        output_value(output, key) == str(value),
        "unexpected output %s: %s" % (key, output),
    )


def no_mutation(path, before_hash, before_counts, before_runs):
    require(semantic_hash(path) == before_hash, "hold mutated holdings")
    require(counts(path) == before_counts, "hold changed counts")
    require(run_count(path) == before_runs, "hold wrote inventory audit")


def test_a_noop(base):
    path = base / "a.sqlite3"
    baseline_db(path)
    before = (semantic_hash(path), counts(path), run_count(path))
    result, output = local_run(
        path,
        SequenceFilesystem([tree_for_records(baseline_records())] * 2),
        base,
    )
    require(result == "PASS", "A did not PASS")
    require_output(output, "ACTION", "NOOP")
    require_output(output, "APPLY", 0)
    require((semantic_hash(path), counts(path), run_count(path)) == before,
            "A was not a no-op")


def test_b_insert(base):
    path = base / "b.sqlite3"
    baseline_db(path)
    new = record_for("B4-001", size=9, mtime_ns=900)
    result, output = local_run(
        path,
        SequenceFilesystem([
            tree_for_records([*baseline_records(), new])
        ] * 2),
        base,
    )
    require(result == "PASS", "B did not PASS")
    require_output(output, "ACTION", "APPLIED")
    require_output(output, "APPLY", 1)
    require_output(output, "INSERTED", 1)
    with sqlite3.connect(path) as db:
        row = db.execute(
            "SELECT storage_root, relative_path, dvd_id, parse_status, present "
            "FROM holdings WHERE relative_path = ?",
            (new["relative_path"],),
        ).fetchone()
    require(tuple(row) == (
        "jav", new["relative_path"], "B4-001", "MATCHED", 1,
    ), "B row semantics changed")
    require(is_owned("B4-001", db_path=path), "B ownership failed")


def test_c_absent(base):
    path = base / "c.sqlite3"
    baseline_db(path)
    selected = baseline_records()[0]
    before = semantic_hash(path)
    result, output = local_run(
        path,
        SequenceFilesystem([
            tree_for_records(baseline_records()[1:])
        ] * 2),
        base,
    )
    require(result == "PASS", "C did not PASS")
    require_output(output, "ABSENT_MARKED", 1)
    with sqlite3.connect(path) as db:
        present = db.execute(
            "SELECT present FROM holdings WHERE relative_path = ?",
            (selected["relative_path"],),
        ).fetchone()[0]
    require(present == 0, "C did not mark absent")
    require(not is_owned(selected["dvd_id"], db_path=path),
            "C absent row remained owned")
    require(semantic_hash(path) != before, "C did not change target row")


def test_d_revive(base):
    path = base / "d.sqlite3"
    selected = baseline_records()[0]
    baseline_db(path, absent=(selected["dvd_id"],))
    before_id = rows(path)[0]["holding_id"]
    result, output = local_run(
        path,
        SequenceFilesystem([tree_for_records(baseline_records())] * 2),
        base,
    )
    require(result == "PASS", "D did not PASS")
    require_output(output, "REVIVED", 1)
    after = rows(path)
    require(len(after) == 2, "D created a duplicate row")
    require(after[0]["holding_id"] == before_id and after[0]["present"] == 1,
            "D did not revive identity")
    require(is_owned(selected["dvd_id"], db_path=path), "D ownership failed")


def test_e_metadata(base):
    path = base / "e.sqlite3"
    baseline_db(path)
    selected = baseline_records()[0]
    changed = dict(selected, size_bytes=77, mtime_ns=7700)
    before = rows(path)[0]
    result, output = local_run(
        path,
        SequenceFilesystem([
            tree_for_records([changed, baseline_records()[1]])
        ] * 2),
        base,
    )
    require(result == "PASS", "E did not PASS")
    require_output(output, "METADATA_UPDATED", 1)
    after = rows(path)[0]
    require(after["holding_id"] == before["holding_id"],
            "E changed identity")
    require((after["size_bytes"], after["mtime_ns"]) == (77, 7700),
            "E did not update size/mtime")


def test_f_repairable_combination(base):
    path = base / "f.sqlite3"
    baseline_db(path)
    new = record_for("F4-001", size=6, mtime_ns=600)
    changed = dict(baseline_records()[0], size_bytes=8, mtime_ns=800)
    result, output = local_run(
        path,
        SequenceFilesystem([
            tree_for_records([changed, baseline_records()[1], new])
        ] * 2),
        base,
    )
    require(result == "PASS", "F did not PASS")
    require_output(output, "ACTION", "APPLIED")
    require_output(output, "INSERTED", 1)
    require_output(output, "METADATA_UPDATED", 1)


def unsafe_case(base, name, tree, expected):
    path = base / (name + ".sqlite3")
    baseline_db(path)
    before = (semantic_hash(path), counts(path), run_count(path))
    report = reconcile_mod.reconcile(
        path,
        ROOT,
        filesystem=SequenceFilesystem([tree]),
    )
    require(
        expected in {
            finding.category
            for finding in report.findings
        },
        name + " finding was not observed",
    )
    result, output = local_run(
        path,
        SequenceFilesystem([tree, tree]),
        base,
    )
    require(result == "HOLD", name + " did not HOLD")
    require_output(output, "APPLY", 0)
    no_mutation(path, *before)


def test_g_h_i_unsafe(base):
    malformed = tree_for_records(baseline_records())
    add_file(malformed, "BAD/BAD-001/not-a-dvd-id.mp4", 1, 1)
    unsafe_case(base, "g-malformed", malformed, "UNMATCHED_DVD_ID")

    duplicate = tree_for_records(baseline_records())
    add_file(duplicate, "DUP/DUP-001/DUP-001.mkv", 2, 2)
    add_file(duplicate, "DUP/DUP-001/DUP-001.mp4", 1, 1)
    unsafe_case(base, "h-duplicate", duplicate, "DUPLICATE_PHYSICAL_MEDIA")

    unsafe = tree_for_records(baseline_records())
    add_file(
        unsafe,
        "SYM/SYM-001/SYM-001-link.mp4",
        0,
        0,
        mode=stat.S_IFLNK | 0o777,
    )
    add_directory(unsafe, "UNX/UNX-001/nested")
    unsafe_case(base, "i-symlink-unexpected", unsafe, "SYMLINK")
    report = reconcile_mod.reconcile(
        base / "i-symlink-unexpected.sqlite3",
        ROOT,
        filesystem=SequenceFilesystem([unsafe]),
    )
    categories = {
        finding.category
        for finding in report.findings
    }
    require(
        "SYMLINK" in categories
        and "UNEXPECTED_LAYOUT" in categories,
        "I did not observe both symlink and unexpected layout",
    )


def test_j_stability(base):
    path = base / "j.sqlite3"
    baseline_db(path)
    before = (semantic_hash(path), counts(path), run_count(path))
    added = [*baseline_records(), record_for("J4-001")]
    result, output = local_run(
        path,
        SequenceFilesystem([
            tree_for_records(baseline_records()),
            tree_for_records(added),
        ]),
        base,
    )
    require(result == "HOLD", "J did not HOLD")
    require_output(output, "REASON", "STABILITY_CHANGED")
    require_output(output, "APPLY", 0)
    no_mutation(path, *before)


def test_k_operation_busy(base):
    path = base / "k.sqlite3"
    baseline_db(path)
    before = (semantic_hash(path), counts(path), run_count(path))
    operation_path = base / "operation.lock"
    with operation_lock(operation_path):
        result, output = local_run(
            path,
            SequenceFilesystem([tree_for_records(baseline_records())] * 2),
            base,
        )
    require(result == "SKIP", "K was not SKIP")
    require_output(output, "REASON", "OPERATION_LOCK_BUSY")
    no_mutation(path, *before)


def test_l_writer_busy(base):
    path = base / "l.sqlite3"
    baseline_db(path)
    new = record_for("L4-001")
    before = (semantic_hash(path), counts(path), run_count(path))
    writer_path = base / "writer.lock"
    with exclusive_lock(writer_path):
        result, output = local_run(
            path,
            SequenceFilesystem([
                tree_for_records([*baseline_records(), new])
            ] * 2),
            base,
            writer_timeout=0.05,
        )
    require(result == "SKIP", "L was not SKIP")
    require_output(output, "REASON", "WRITER_LOCK_BUSY")
    no_mutation(path, *before)


class FaultConnection:
    def __init__(self, connection, fail_on_holding_insert):
        self.connection = connection
        self.fail_on_holding_insert = fail_on_holding_insert
        self.insert_count = 0

    def execute(self, sql, parameters=()):
        normalized = " ".join(str(sql).upper().split())
        if "INSERT INTO HOLDINGS" in normalized:
            self.insert_count += 1
            if self.insert_count == self.fail_on_holding_insert:
                raise RuntimeError("synthetic mid-transaction fault")
        return self.connection.execute(sql, parameters)

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        return self.connection.__exit__(exc_type, exc, traceback)

    def __getattr__(self, name):
        return getattr(self.connection, name)


def test_m_transaction_rollback(base):
    path = base / "m.sqlite3"
    baseline_db(path)
    new = record_for("M4-001")
    before = (semantic_hash(path), counts(path), run_count(path))
    original_connect = import_mod.connect

    def fault_connect(db_path):
        return FaultConnection(
            connect(db_path),
            fail_on_holding_insert=1,
        )

    import_mod.connect = fault_connect
    try:
        result, output = local_run(
            path,
            SequenceFilesystem([
                tree_for_records([*baseline_records(), new])
            ] * 2),
            base,
        )
    finally:
        import_mod.connect = original_connect
    require(result == "FAIL", "M did not FAIL")
    require_output(output, "APPLY", 0)
    require(semantic_hash(path) == before[0], "M partial holdings mutation")
    require(counts(path) == before[1], "M changed holding counts")
    require(run_count(path) == before[2] + 1, "M did not audit failed run")
    with sqlite3.connect(path) as db:
        status = db.execute(
            "SELECT status FROM inventory_runs ORDER BY run_id DESC LIMIT 1"
        ).fetchone()[0]
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
    require(status == "FAILED", "M run status was not FAILED")
    require(integrity == "ok", "M integrity_check failed")


def test_n_unknown_category(base):
    path = base / "n.sqlite3"
    baseline_db(path)
    before = (semantic_hash(path), counts(path), run_count(path))
    report = SimpleNamespace(
        root=ROOT,
        db_available=True,
        root_available=True,
        mount_available=None,
        scan_complete=True,
        apply_eligible=True,
        canonical_present_files=(
            {"relative_path": "AAA/AAA-001/AAA-001.mp4"},
        ),
        findings=(
            reconcile_mod.Finding(
                category="FUTURE_UNKNOWN_FINDING",
                relative_path=".",
                dvd_id=None,
                detail="synthetic unknown category",
                blocking=False,
            ),
        ),
    )

    def unknown_apply(*args, **kwargs):
        decision = kwargs["policy_fn"](report)
        require(decision.action == "HOLD", "N unknown category was allowed")
        raise reconcile_mod.ReconciliationUnsafe(report)

    output = []
    result = apply_mod.run_apply(
        environ=environment(path),
        operation_lock_path=base / "operation.lock",
        writer_lock_path=base / "writer.lock",
        ssh_factory=FakeSSH,
        apply_fn=unknown_apply,
        output=output.append,
    )
    require(result == "HOLD", "N did not HOLD")
    require_output(output, "APPLY", 0)
    no_mutation(path, *before)


def test_policy_taxonomy():
    require(
        apply_mod.REPAIRABLE_FINDINGS == {
            "FILESYSTEM_PRESENT_DB_MISSING",
            "DB_PRESENT_FILESYSTEM_MISSING",
            "ABSENT_HOLDING_REAPPEARED",
            "SIZE_MISMATCH",
            "MTIME_MISMATCH",
        },
        "repair allowlist changed",
    )
    require(
        {
            "UNMATCHED_DVD_ID",
            "AMBIGUOUS_DVD_ID",
            "DUPLICATE_PHYSICAL_MEDIA",
            "UNEXPECTED_LAYOUT",
            "SYMLINK",
            "DVD_ID_MISMATCH",
            "DB_STATUS_MISMATCH",
            "DB_DUPLICATE_PRESENT",
            "EMPTY_ROOT_WITH_PRESENT_HOLDINGS",
            "EMPTY_SCAN_WITH_PRESENT_HOLDINGS",
            "STABILITY_CHANGED",
            "DB_STATE_CHANGED_AFTER_PREFLIGHT",
            "AUTO_APPLY_POLICY_HOLD",
        } <= apply_mod.BLOCKING_UNSAFE_FINDINGS,
        "known unsafe taxonomy changed",
    )


def test_artifacts():
    report_source = Path(
        "teddy_discovery_jav_reconcile_report.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "apply_reconciliation",
        "remote-apply",
        "import_inventory",
    ):
        require(forbidden not in report_source,
                "report-only module gained " + forbidden)
    service = Path(
        "deploy/systemd/teddy-discovery-jav-reconcile-apply.service"
    ).read_text(encoding="utf-8")
    wrapper = Path(
        "deploy/systemd/teddy-discovery-jav-reconcile-apply"
    ).read_text(encoding="utf-8")
    require("Type=oneshot" in service, "apply service is not oneshot")
    require("EnvironmentFile=-/etc/default/teddy-discovery" in service,
            "apply service lost environment file")
    require("TEDDY_FINAL_LIBRARY_ROOT=" + ROOT in service,
            "apply service root is not exact")
    require("Restart=" not in service, "apply service has Restart")
    require("teddy_discovery_jav_reconcile_apply.py" in wrapper,
            "apply wrapper target missing")
    require(not Path(
        "deploy/systemd/teddy-discovery-jav-reconcile-apply.timer"
    ).exists(), "apply timer was created")


def main():
    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-reconcile-apply-smoke-"
    ) as temp:
        base = Path(temp)
        test_policy_taxonomy()
        test_a_noop(base)
        print("APPLY_A_NO_DRIFT=PASS")
        test_b_insert(base)
        print("APPLY_B_INSERT=PASS")
        test_c_absent(base)
        print("APPLY_C_ABSENT=PASS")
        test_d_revive(base)
        print("APPLY_D_REVIVE=PASS")
        test_e_metadata(base)
        print("APPLY_E_METADATA=PASS")
        test_f_repairable_combination(base)
        print("APPLY_F_COMBINATION=PASS")
        test_g_h_i_unsafe(base)
        print("APPLY_GHI_UNSAFE=PASS")
        test_j_stability(base)
        print("APPLY_J_STABILITY=PASS")
        test_k_operation_busy(base)
        print("APPLY_K_OPERATION_BUSY=PASS")
        test_l_writer_busy(base)
        print("APPLY_L_WRITER_BUSY=PASS")
        test_m_transaction_rollback(base)
        print("APPLY_M_ROLLBACK=PASS")
        test_n_unknown_category(base)
        print("APPLY_N_UNKNOWN=PASS")
        test_artifacts()
    print("STAGE10_B4_SEPARATE_APPLY_SMOKE=PASS")


if __name__ == "__main__":
    main()
