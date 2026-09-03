from __future__ import annotations

import json
import subprocess
from typing import Any, Callable

from teddy_discovery_ids import parse_dvd_id


DOCKER_BINARY = "/usr/bin/docker"
DOCKER_NETWORK = "missav-dlp-web_default"
GLUETUN_PROXY_URL = "http://gluetun:8888"
METADATA_IMAGE = (
    "ghcr.io/ssikgun/missav-dlp-web@sha256:"
    "3f5ff6ffa7930d56992209ad643b7ea1a7e5b9c3d6088dca3b939d13583371b4"
)
EXPECTED_IMAGE_ID = (
    "sha256:3f5ff6ffa7930d56992209ad643b7ea1a7e5b9c3d6088dca3b939d13583371b4"
)
EXPECTED_OCI_REVISION = (
    "64be674a0641419465b2130eca0c2dfcbc650a39"
)

# collect_metadata_candidate() permits two 45-second HTTP attempts when its
# fallback is used.  Allow that bounded work plus Docker startup/inspection,
# while still preventing a permanently blocked Stage9 oneshot.
DOCKER_INSPECT_TIMEOUT_SECONDS = 10
DOCKER_TIMEOUT_SECONDS = 120

CONTAINER_CODE = r'''
import json
import sys

from teddy_discovery_refresh import collect_metadata_candidate


dvd_id = sys.argv[1]
try:
    result = collect_metadata_candidate(dvd_id)
    output = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
except Exception as error:
    print(json.dumps({
        "status": "ERROR",
        "error_type": type(error).__name__,
        "error": str(error),
    }, ensure_ascii=False, separators=(",", ":")))
    raise SystemExit(1)

print(output)
'''.strip()


class DockerMetadataCollectorError(RuntimeError):
    """The isolated metadata collection contract failed closed."""


def _stdout_json(
    completed,
    *,
    description: str,
) -> Any:
    stdout = getattr(completed, "stdout", "")

    try:
        return json.loads(stdout)
    except (TypeError, json.JSONDecodeError) as error:
        raise DockerMetadataCollectorError(
            f"{description} did not return JSON"
        ) from error


def _run(
    runner: Callable[..., Any],
    argv: list[str],
    *,
    timeout: int,
):
    try:
        return runner(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise DockerMetadataCollectorError(
            "Docker metadata collection timed out"
        ) from error
    except OSError as error:
        raise DockerMetadataCollectorError(
            "Docker metadata collection could not start"
        ) from error


def _inspect_image(
    runner: Callable[..., Any],
) -> None:
    completed = _run(
        runner,
        [
            DOCKER_BINARY,
            "image",
            "inspect",
            METADATA_IMAGE,
        ],
        timeout=DOCKER_INSPECT_TIMEOUT_SECONDS,
    )

    if completed.returncode != 0:
        raise DockerMetadataCollectorError(
            "metadata image is absent or cannot be inspected"
        )

    payload = _stdout_json(
        completed,
        description="Docker image inspect",
    )

    if (
        not isinstance(payload, list)
        or len(payload) != 1
        or not isinstance(payload[0], dict)
    ):
        raise DockerMetadataCollectorError(
            "Docker image inspect returned an invalid object"
        )

    image = payload[0]
    image_id = image.get("Id")
    config = image.get("Config")
    labels = (
        config.get("Labels")
        if isinstance(config, dict)
        else None
    )

    if image_id != EXPECTED_IMAGE_ID:
        raise DockerMetadataCollectorError(
            "metadata image ID provenance mismatch"
        )

    if (
        not isinstance(labels, dict)
        or labels.get("org.opencontainers.image.revision")
        != EXPECTED_OCI_REVISION
    ):
        raise DockerMetadataCollectorError(
            "metadata image OCI revision provenance mismatch"
        )


def _inspect_network(
    runner: Callable[..., Any],
) -> None:
    completed = _run(
        runner,
        [
            DOCKER_BINARY,
            "network",
            "inspect",
            DOCKER_NETWORK,
        ],
        timeout=DOCKER_INSPECT_TIMEOUT_SECONDS,
    )

    if completed.returncode != 0:
        raise DockerMetadataCollectorError(
            "metadata Docker network is absent or cannot be inspected"
        )

    payload = _stdout_json(
        completed,
        description="Docker network inspect",
    )

    if not isinstance(payload, list) or not any(
        isinstance(network, dict)
        and network.get("Name") == DOCKER_NETWORK
        for network in payload
    ):
        raise DockerMetadataCollectorError(
            "Docker network inspect returned no expected network"
        )


def _requested_canonical_dvd_id(
    dvd_id: str,
) -> str:
    parsed = parse_dvd_id(str(dvd_id))

    if parsed is None or parsed.dvd_id != str(dvd_id):
        raise DockerMetadataCollectorError(
            "metadata collection requires a canonical DVD-ID"
        )

    return parsed.dvd_id


def _validate_result(
    result: Any,
    *,
    requested_dvd_id: str,
) -> dict:
    if not isinstance(result, dict):
        raise DockerMetadataCollectorError(
            "metadata collector result is not a JSON object"
        )

    returned_dvd_id = result.get("dvd_id")
    parsed = parse_dvd_id(str(returned_dvd_id or ""))

    if (
        parsed is None
        or parsed.dvd_id != requested_dvd_id
    ):
        raise DockerMetadataCollectorError(
            "metadata collector returned a different DVD-ID"
        )

    status = result.get("status")

    if status not in {"FOUND", "NOT_FOUND"}:
        raise DockerMetadataCollectorError(
            "metadata collector returned an invalid status"
        )

    if status == "FOUND":
        if (
            not isinstance(result.get("route"), str)
            or not result["route"].strip()
            or not isinstance(result.get("item"), dict)
        ):
            raise DockerMetadataCollectorError(
                "FOUND metadata result is missing route or item"
            )

    return result


def collect_metadata_candidate_docker(
    dvd_id: str,
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> dict:
    """Collect metadata in the immutable production runtime only.

    The host performs only local Docker contract/provenance checks and
    validates the returned envelope.  No database, NAS, socket, or worktree
    volume is made available to the container.
    """
    requested_dvd_id = _requested_canonical_dvd_id(dvd_id)

    _inspect_image(runner)
    _inspect_network(runner)

    completed = _run(
        runner,
        [
            DOCKER_BINARY,
            "run",
            "--rm",
            "--network",
            DOCKER_NETWORK,
            "--pull",
            "never",
            "--env",
            f"GLUETUN_PROXY_URL={GLUETUN_PROXY_URL}",
            "--entrypoint",
            "python",
            METADATA_IMAGE,
            "-c",
            CONTAINER_CODE,
            requested_dvd_id,
        ],
        timeout=DOCKER_TIMEOUT_SECONDS,
    )

    result = _stdout_json(
        completed,
        description="metadata Docker container",
    )

    if completed.returncode != 0:
        raise DockerMetadataCollectorError(
            "metadata Docker container failed"
        )

    return _validate_result(
        result,
        requested_dvd_id=requested_dvd_id,
    )
