from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from types import SimpleNamespace

import teddy_discovery_completion_metadata_docker as docker
from teddy_discovery_completion_metadata import (
    recover_held_metadata,
)
from teddy_discovery_completion import (
    plan_remote_downloads,
)
from teddy_discovery_completion_runner import (
    CONFIRMATION,
    run_once,
)
from teddy_discovery_db import (
    connect,
    initialize,
)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def new_db(root: Path) -> Path:
    path = root / "discovery.sqlite3"
    connection = connect(path)
    initialize(connection)
    connection.close()
    return path


def item(dvd_id: str) -> dict:
    return {
        "name": "missav/" + dvd_id + ".mp4",
        "size": 123,
        "modified": 1000,
    }


def found(dvd_id: str) -> dict:
    return {
        "dvd_id": dvd_id,
        "status": "FOUND",
        "route": "javdatabase-movie",
        "request_count": 1,
        "item": {
            "dvd_id": dvd_id,
            "title": dvd_id + " title",
            "release_date": "2026-08-01",
            "studio": "Test Studio",
            "idols": [],
            "genres": [],
            "source_url": "https://example.invalid/" + dvd_id.lower(),
            "cover_url": "https://example.invalid/" + dvd_id.lower() + ".jpg",
        },
    }


def not_found(dvd_id: str) -> dict:
    return {
        "dvd_id": dvd_id,
        "status": "NOT_FOUND",
        "route": None,
        "request_count": 1,
        "item": None,
    }


def plan_for(db_path: Path, dvd_id: str):
    return plan_remote_downloads(
        [item(dvd_id)],
        db_path=db_path,
    )[0]


class FakeDockerRunner:
    def __init__(
        self,
        *,
        image_id=docker.EXPECTED_IMAGE_ID,
        revision=docker.EXPECTED_OCI_REVISION,
        image_returncode=0,
        network_returncode=0,
        run_returncode=0,
        run_payload=None,
        run_stdout=None,
        timeout=False,
        events=None,
    ):
        self.image_id = image_id
        self.revision = revision
        self.image_returncode = image_returncode
        self.network_returncode = network_returncode
        self.run_returncode = run_returncode
        self.run_payload = run_payload
        self.run_stdout = run_stdout
        self.timeout = timeout
        self.calls = []
        self.events = events

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), dict(kwargs)))

        if self.events is not None:
            self.events.append(argv[1])

        require(isinstance(argv, list), "Docker command was not argv list")
        require(kwargs.get("shell") is not True, "shell=True was used")

        if argv[1:3] == ["image", "inspect"]:
            return SimpleNamespace(
                returncode=self.image_returncode,
                stdout=json.dumps([
                    {
                        "Id": self.image_id,
                        "Config": {
                            "Labels": {
                                "org.opencontainers.image.revision": self.revision,
                            },
                        },
                    },
                ]),
                stderr="image error" if self.image_returncode else "",
            )

        if argv[1:3] == ["network", "inspect"]:
            return SimpleNamespace(
                returncode=self.network_returncode,
                stdout=json.dumps([
                    {"Name": docker.DOCKER_NETWORK},
                ]) if self.network_returncode == 0 else "",
                stderr="network error" if self.network_returncode else "",
            )

        require(argv[1] == "run", "unexpected Docker command")

        if self.timeout:
            raise subprocess.TimeoutExpired(
                argv,
                kwargs["timeout"],
            )

        stdout = self.run_stdout
        if stdout is None:
            stdout = json.dumps(self.run_payload)

        return SimpleNamespace(
            returncode=self.run_returncode,
            stdout=stdout,
            stderr="container diagnostic",
        )


def expect_failure(function, message):
    try:
        function()
    except docker.DockerMetadataCollectorError:
        return
    raise AssertionError(message)


def docker_collector(runner):
    return lambda dvd_id: docker.collect_metadata_candidate_docker(
        dvd_id,
        runner=runner,
    )


# 1. FOUND validates the JSON envelope, identity, and fixed runtime contract.
runner = FakeDockerRunner(
    run_payload=found("JUR-750"),
)
result = docker.collect_metadata_candidate_docker(
    "JUR-750",
    runner=runner,
)
require(result["status"] == "FOUND", "Docker FOUND was not decoded")
require(result["dvd_id"] == "JUR-750", "Docker FOUND DVD-ID mismatch")
run_call = next(
    argv
    for argv, kwargs in runner.calls
    if argv[1] == "run"
)
require(run_call[:4] == [docker.DOCKER_BINARY, "run", "--rm", "--network"], "run contract mismatch")
require(
    run_call[4:6] == [docker.DOCKER_NETWORK, "--pull"],
    "Docker network contract mismatch",
)
require(
    run_call[6:8] == ["never", "--env"],
    "--pull never was not enforced",
)
require(
    run_call[8] == "GLUETUN_PROXY_URL=http://gluetun:8888",
    "Gluetun proxy boundary missing",
)
require(
    run_call[9:11] == ["--entrypoint", "python"],
    "container Python entrypoint missing",
)
require(
    run_call[11] == docker.METADATA_IMAGE,
    "immutable metadata image missing",
)
require(run_call[-1] == "JUR-750", "DVD-ID was not a separate argv value")
require(
    not any(
        token in {"-v", "--volume", "--mount", "--volumes-from"}
        or "/var/run/docker.sock" in token
        or "discovery.sqlite3" in token
        or "NAS" in token
        or "missav-pwa-subtitle-stage11" in token
        for token in run_call
    ),
    "collector Docker command exposed a forbidden mount",
)
require(
    runner.calls[-1][1]["timeout"] == docker.DOCKER_TIMEOUT_SECONDS,
    "Docker collection timeout was not bounded",
)


# FOUND recovery uses the existing held adapter and is consumed only by the
# next planner cycle.
with tempfile.TemporaryDirectory(prefix="teddy-stage9-docker-") as temp:
    root = Path(temp)
    db_path = new_db(root)
    runner = FakeDockerRunner(run_payload=found("JUR-751"))
    result = run_once(
        items=[item("JUR-751")],
        db_path=db_path,
        ssh=object(),
        mutator=object(),
        writer_lock_path=root / "writer.lock",
        operation_lock_path=root / "operation.lock",
        apply=True,
        confirm=CONFIRMATION,
        metadata_collector=docker_collector(runner),
        metadata_state_path=root / "retry.sqlite3",
    )
    require(result["eligible"] == 0, "Docker recovery moved in same cycle")
    require(result["metadata_recovery"]["recovered"] == 1, "Docker FOUND recovery failed")

    connection = connect(db_path)
    row = connection.execute(
        "SELECT title, metadata_source, cover_url FROM titles WHERE dvd_id = 'JUR-751'"
    ).fetchone()
    connection.close()
    require(row["title"] == "JUR-751 title", "Docker recovery title missing")
    require(row["metadata_source"] == "javdatabase-movie", "Docker route missing")
    require(row["cover_url"], "Docker recovery cover URL missing")
    require(
        plan_for(db_path, "JUR-751").planned_operation
        == "PLAN_STAGE9_SSH_MOVE",
        "Docker recovery was not eligible on next plan",
    )


# 2. NOT_FOUND follows the existing durable backoff path without a move.
with tempfile.TemporaryDirectory(prefix="teddy-stage9-docker-") as temp:
    root = Path(temp)
    db_path = new_db(root)
    state_path = root / "retry.sqlite3"
    runner = FakeDockerRunner(run_payload=not_found("MSFH-048"))
    plan = plan_for(db_path, "MSFH-048")
    base = datetime.fromisoformat("2026-09-03T00:00:00+00:00")
    first = recover_held_metadata(
        [plan],
        db_path=db_path,
        writer_lock_path=root / "writer.lock",
        state_path=state_path,
        now=base,
        collector=docker_collector(runner),
    )
    require(first["not_found"] == 1, "Docker NOT_FOUND did not remain held")
    require(first["failed"] == 0, "Docker NOT_FOUND became a crash")
    run_count = len([call for call, _ in runner.calls if call[1] == "run"])
    second = recover_held_metadata(
        [plan],
        db_path=db_path,
        writer_lock_path=root / "writer.lock",
        state_path=state_path,
        now=base + timedelta(minutes=1),
        collector=docker_collector(runner),
    )
    require(second["backoff_skipped"] == 1, "Docker NOT_FOUND backoff was not honored")
    require(
        len([call for call, _ in runner.calls if call[1] == "run"]) == run_count,
        "Docker NOT_FOUND retried during backoff",
    )
    connection = connect(db_path)
    require(
        connection.execute("SELECT COUNT(*) FROM titles").fetchone()[0] == 0,
        "Docker NOT_FOUND wrote metadata",
    )
    connection.close()


# 3-5. Image provenance and Docker network guards prevent container execution.
for kwargs, message in [
    ({"image_returncode": 1}, "absent Docker image was not fail closed"),
    ({"image_id": "sha256:wrong"}, "image provenance mismatch was not fail closed"),
    ({"revision": "wrong"}, "OCI revision mismatch was not fail closed"),
    ({"network_returncode": 1}, "missing Docker network was not fail closed"),
]:
    runner = FakeDockerRunner(run_payload=found("GUARD-001"), **kwargs)
    expect_failure(
        lambda: docker.collect_metadata_candidate_docker(
            "GUARD-001",
            runner=runner,
        ),
        message,
    )
    require(
        not any(argv[1] == "run" for argv, _ in runner.calls),
        "guard failure still executed collection",
    )


# 6-9. Container failures, timeout, malformed stdout, and identity mismatch
# all become adapter failures for the existing FAILED retry path.
failure_runners = [
    FakeDockerRunner(
        run_payload=found("FAIL-001"),
        run_returncode=1,
    ),
    FakeDockerRunner(
        run_payload=found("FAIL-002"),
        timeout=True,
    ),
    FakeDockerRunner(
        run_stdout="traceback mixed into stdout",
    ),
    FakeDockerRunner(
        run_payload={
            **found("FAIL-004"),
            "dvd_id": "OTHER-004",
        },
    ),
]
for index, failure_runner in enumerate(failure_runners, start=1):
    expect_failure(
        lambda failure_runner=failure_runner: docker.collect_metadata_candidate_docker(
            "FAIL-00" + str(index),
            runner=failure_runner,
        ),
        "Docker failure did not fail closed",
    )

with tempfile.TemporaryDirectory(prefix="teddy-stage9-docker-") as temp:
    root = Path(temp)
    db_path = new_db(root)
    failure_runner = FakeDockerRunner(
        run_payload=found("FAIL-005"),
        run_returncode=1,
    )
    result = recover_held_metadata(
        [plan_for(db_path, "FAIL-005")],
        db_path=db_path,
        writer_lock_path=root / "writer.lock",
        state_path=root / "retry.sqlite3",
        collector=docker_collector(failure_runner),
    )
    require(result["failed"] == 1, "Docker RC failure did not enter FAILED recovery")
    require(result["recovered"] == 0, "Docker RC failure recovered metadata")


# 13. Existing eligible completion is called before any Docker collection.
with tempfile.TemporaryDirectory(prefix="teddy-stage9-docker-") as temp:
    root = Path(temp)
    db_path = new_db(root)
    connection = connect(db_path)
    connection.execute(
        """
        INSERT INTO titles(
            dvd_id, title, metadata_source,
            first_seen_at, last_seen_at
        ) VALUES ('READY-003', 'Ready', 'smoke', ?, ?)
        """,
        ("2026-09-03", "2026-09-03"),
    )
    connection.commit()
    connection.close()

    events = []
    runner = FakeDockerRunner(
        run_payload=found("ORDER-002"),
        events=events,
    )

    def processor(plan, **kwargs):
        events.append("processor:" + plan.dvd_id)

    result = run_once(
        items=[item("READY-003"), item("ORDER-002")],
        db_path=db_path,
        ssh=object(),
        mutator=object(),
        writer_lock_path=root / "writer.lock",
        operation_lock_path=root / "operation.lock",
        apply=True,
        confirm=CONFIRMATION,
        processor=processor,
        metadata_collector=docker_collector(runner),
        metadata_state_path=root / "retry.sqlite3",
    )
    require(result["applied"] == 1, "ready completion was not applied")
    require(
        events[0] == "processor:READY-003",
        "Docker recovery ran before ready completion",
    )
    require(events[1:] == ["image", "network", "run"], "Docker order was unexpected")


# 14. Dry-run performs neither Docker inspection/collection nor retry DB setup.
with tempfile.TemporaryDirectory(prefix="teddy-stage9-docker-") as temp:
    root = Path(temp)
    db_path = new_db(root)
    state_path = root / "dry-run-retry.sqlite3"
    runner = FakeDockerRunner(run_payload=found("DRY-001"))
    collector_calls = []

    def dry_collector(dvd_id):
        collector_calls.append(dvd_id)
        return docker.collect_metadata_candidate_docker(
            dvd_id,
            runner=runner,
        )

    result = run_once(
        items=[item("DRY-001")],
        db_path=db_path,
        ssh=object(),
        mutator=object(),
        writer_lock_path=root / "writer.lock",
        operation_lock_path=root / "operation.lock",
        apply=False,
        metadata_collector=dry_collector,
        metadata_state_path=state_path,
    )
    require(result["metadata_recovery"]["skipped"] == "DRY_RUN", "dry-run recovery was not skipped")
    require(collector_calls == [], "dry-run invoked collector")
    require(runner.calls == [], "dry-run invoked Docker inspect/run")
    require(not state_path.exists(), "dry-run created retry DB")


print("STAGE9_DOCKER_METADATA_COLLECTOR_SMOKE=PASS")
