"""Stage11-only Hermes profile resolution and timeout policy.

The remote probe uses Hermes' own read-only ``read_user_config_raw`` parser
against the dedicated profile.  It never calls ``load_config`` or a mutating
configuration command.  Model values are copied into each Stage11 invocation
and recorded with the profile-config digest; other Hermes profiles and
processes do not inherit the timeout overrides.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Mapping


STAGE11_HERMES_PROFILE = "subtitle-translator"
STAGE11_HERMES_PROFILE_DIR = (
    "/home/teddy/.hermes/profiles/subtitle-translator"
)
STAGE11_HERMES_CONFIG_PATH = STAGE11_HERMES_PROFILE_DIR + "/config.yaml"
STAGE11_HERMES_TIMEOUT_ENV: Mapping[str, str] = {
    "HERMES_API_CALL_STALE_TIMEOUT": "480",
    "HERMES_CODEX_TTFB_TIMEOUT_SECONDS": "300",
    "HERMES_CODEX_TTFB_MAX_SECONDS": "300",
    "HERMES_CODEX_EVENT_STALE_TIMEOUT_SECONDS": "300",
}
STAGE11_HERMES_TIMEOUT_ENV_NAMES = tuple(STAGE11_HERMES_TIMEOUT_ENV)
_SAFE_VALUE = re.compile(r"^[^\x00-\x20\x7f]{1,256}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class HermesProfileSettingsError(ValueError):
    """Profile settings or installed Hermes timeout support is unverified."""


def _value(value: object, label: str) -> str:
    if type(value) is not str or not _SAFE_VALUE.fullmatch(value):
        raise HermesProfileSettingsError(label + " is missing or invalid")
    return value


@dataclass(frozen=True)
class HermesExecutionSettings:
    profile_name: str
    provider: str
    model: str
    reasoning_effort: str
    hermes_version: str
    config_sha256: str
    timeout_env_supported: tuple[str, ...]

    def __post_init__(self) -> None:
        _value(self.profile_name, "profile name")
        _value(self.provider, "provider")
        _value(self.model, "model")
        _value(self.reasoning_effort, "reasoning effort")
        _value(self.hermes_version, "Hermes version")
        if type(self.config_sha256) is not str or not _SHA256.fullmatch(
            self.config_sha256
        ):
            raise HermesProfileSettingsError("profile config identity is invalid")
        if (type(self.timeout_env_supported) is not tuple
                or self.timeout_env_supported != STAGE11_HERMES_TIMEOUT_ENV_NAMES):
            raise HermesProfileSettingsError(
                "installed Hermes timeout environment support is incomplete"
            )

    def invocation_values(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
        }

    def evidence(self) -> dict[str, object]:
        values = self.invocation_values()
        return {
            "profile_name": self.profile_name,
            "hermes_version": self.hermes_version,
            "profile_config_sha256": self.config_sha256,
            "profile_values": values,
            "invocation_values": dict(values),
            "timeout_environment": dict(STAGE11_HERMES_TIMEOUT_ENV),
            "timeout_environment_supported": list(self.timeout_env_supported),
        }


def settings_from_probe(payload: bytes) -> HermesExecutionSettings:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise HermesProfileSettingsError("Hermes profile probe output is invalid") from error
    if type(value) is not dict or set(value) != {
        "profile_name", "provider", "model", "reasoning_effort",
        "hermes_version", "config_sha256", "timeout_env_supported",
    }:
        raise HermesProfileSettingsError("Hermes profile probe fields are invalid")
    names = value["timeout_env_supported"]
    if type(names) is not list or any(type(item) is not str for item in names):
        raise HermesProfileSettingsError("Hermes timeout support report is invalid")
    return HermesExecutionSettings(
        profile_name=value["profile_name"],
        provider=value["provider"],
        model=value["model"],
        reasoning_effort=value["reasoning_effort"],
        hermes_version=value["hermes_version"],
        config_sha256=value["config_sha256"],
        timeout_env_supported=tuple(names),
    )


def validate_settings_evidence(value: object) -> dict[str, object]:
    """Validate safe persisted settings evidence, including legacy absence."""
    if type(value) is not dict:
        raise HermesProfileSettingsError("Hermes execution evidence is invalid")
    required = {
        "profile_name", "hermes_version", "profile_config_sha256",
        "profile_values", "invocation_values", "timeout_environment",
        "timeout_environment_supported",
    }
    if set(value) != required:
        raise HermesProfileSettingsError("Hermes execution evidence fields differ")
    _value(value["profile_name"], "profile name")
    _value(value["hermes_version"], "Hermes version")
    if type(value["profile_config_sha256"]) is not str or not _SHA256.fullmatch(
        value["profile_config_sha256"]
    ):
        raise HermesProfileSettingsError("Hermes config digest is invalid")
    for key in ("profile_values", "invocation_values"):
        fields = value[key]
        if type(fields) is not dict or set(fields) != {
            "provider", "model", "reasoning_effort"
        }:
            raise HermesProfileSettingsError("Hermes model values are invalid")
        for field in ("provider", "model", "reasoning_effort"):
            _value(fields[field], field)
    if value["profile_values"] != value["invocation_values"]:
        raise HermesProfileSettingsError(
            "Hermes invocation differs from the resolved profile"
        )
    if value["timeout_environment"] != dict(STAGE11_HERMES_TIMEOUT_ENV):
        raise HermesProfileSettingsError("Hermes timeout policy differs")
    if value["timeout_environment_supported"] != list(
        STAGE11_HERMES_TIMEOUT_ENV_NAMES
    ):
        raise HermesProfileSettingsError("Hermes timeout support is unverified")
    return value


def legacy_receipt_matches(receipt: object, settings: HermesExecutionSettings) -> bool:
    """Check old per-attempt receipts without requiring new evidence fields."""
    if type(receipt) is not dict:
        return False
    expected = settings.invocation_values()
    legacy = {
        "provider": receipt.get("provider"),
        "model": receipt.get("model"),
        "reasoning_effort": receipt.get("reasoning"),
    }
    if legacy != expected:
        return False
    evidence = receipt.get("hermes_execution_settings")
    return evidence is None or validate_settings_evidence(evidence) == settings.evidence()


# Executed on the Hermes host with its pinned venv/source.  Only the three
# approved settings, package version, file digest, and timeout-source support
# are returned.  Config bytes and all unrelated config fields stay private.
REMOTE_PROFILE_SETTINGS_PROBE = r'''
import ast, hashlib, importlib.metadata, importlib.util, inspect, json, os, stat, sys
from pathlib import Path
config_path, source_root, expected_profile, *timeout_names = sys.argv[1:]
config_path = Path(config_path)
source_root = Path(source_root)
try:
    info_before = os.lstat(config_path)
    if not stat.S_ISREG(info_before.st_mode) or stat.S_ISLNK(info_before.st_mode):
        raise SystemExit(20)
    config_bytes = config_path.read_bytes()
    sys.path.insert(0, str(source_root))
    os.environ['HERMES_HOME'] = str(config_path.parent)
    from hermes_cli.profiles import get_active_profile_name
    from hermes_cli.config import read_user_config_raw
    if get_active_profile_name() != expected_profile:
        raise SystemExit(21)
    reader_signature = inspect.signature(read_user_config_raw)
    reader_parameters = tuple(reader_signature.parameters.values())
    if (len(reader_parameters) == 1
            and reader_parameters[0].name in {'path', 'config_path'}):
        raw = read_user_config_raw(config_path)
    elif not reader_parameters:
        raw = read_user_config_raw()
    else:
        raise SystemExit(22)
    if type(raw) is not dict:
        raise SystemExit(22)
    model_cfg = raw.get('model')
    if type(model_cfg) is not dict:
        raise SystemExit(23)
    model = model_cfg.get('default') or model_cfg.get('model')
    provider = model_cfg.get('provider')
    agent_cfg = raw.get('agent')
    if type(agent_cfg) is not dict:
        raise SystemExit(24)
    reasoning = agent_cfg.get('reasoning_effort')
    values = (provider, model, reasoning)
    if any(type(item) is not str or not item or item != item.strip()
           or any(ord(ch) < 32 or ord(ch) == 127 for ch in item)
           or len(item) > 256 for item in values):
        raise SystemExit(25)
    after = os.lstat(config_path)
    if ((info_before.st_dev, info_before.st_ino, info_before.st_size,
         info_before.st_mtime_ns, info_before.st_ctime_ns)
        != (after.st_dev, after.st_ino, after.st_size,
            after.st_mtime_ns, after.st_ctime_ns)):
        raise SystemExit(26)
    distribution_names = importlib.metadata.packages_distributions().get('hermes_cli', [])
    versions = sorted({importlib.metadata.version(name) for name in distribution_names})
    if len(versions) != 1:
        raise SystemExit(27)
    package_roots = []
    for package in ('hermes_cli', 'agent'):
        spec = importlib.util.find_spec(package)
        if spec is None or not spec.submodule_search_locations:
            raise SystemExit(28)
        package_roots.extend(Path(item) for item in spec.submodule_search_locations)
    if (source_root / 'agent').resolve() not in {
            root.resolve() for root in package_roots}:
        raise SystemExit(28)
    max_source_bytes = 2 * 1024 * 1024

    def read_source_tree(path):
        info = os.lstat(path)
        if (stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode)
                or info.st_size > max_source_bytes):
            raise SystemExit(28)
        source_bytes = path.read_bytes()
        if len(source_bytes) != info.st_size:
            raise SystemExit(28)
        return ast.parse(source_bytes.decode('utf-8'))

    # Hermes 0.20 reads the API stale-call setting in run_agent.py via
    # os.getenv(), outside the agent package tree. Inspect that exact file.
    run_agent_tree = read_source_tree(source_root / 'run_agent.py')
    api_stale_name = timeout_names[0]
    api_stale_read = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == 'getenv'
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == 'os'
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and type(node.args[0].value) is str
        and node.args[0].value == api_stale_name
        for node in ast.walk(run_agent_tree)
    )

    # The remaining Hermes 0.20 timeout settings are read by _env_float()
    # in the installed agent helper. Do not accept comments or bare strings.
    helper_path = source_root / 'agent' / 'chat_completion_helpers.py'
    helper_tree = read_source_tree(helper_path)
    helper_reads = {
        node.args[0].value
        for node in ast.walk(helper_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == '_env_float'
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and type(node.args[0].value) is str
    }
    supported = {api_stale_name} if api_stale_read else set()
    supported.update(set(timeout_names[1:]) & helper_reads)
    if supported != set(timeout_names):
        raise SystemExit(29)
    print(json.dumps({
        'profile_name': expected_profile,
        'provider': provider,
        'model': model,
        'reasoning_effort': reasoning,
        'hermes_version': versions[0],
        'config_sha256': hashlib.sha256(config_bytes).hexdigest(),
        'timeout_env_supported': list(timeout_names),
    }, sort_keys=True, separators=(',', ':')))
except SystemExit:
    raise
except BaseException:
    raise SystemExit(30)
'''


def timeout_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Copy an environment and apply the Stage11-only request timeout values."""
    result = dict(base or {})
    result.update(STAGE11_HERMES_TIMEOUT_ENV)
    return result


__all__ = [
    "HermesExecutionSettings", "HermesProfileSettingsError",
    "REMOTE_PROFILE_SETTINGS_PROBE", "STAGE11_HERMES_CONFIG_PATH",
    "STAGE11_HERMES_PROFILE", "STAGE11_HERMES_PROFILE_DIR",
    "STAGE11_HERMES_TIMEOUT_ENV",
    "STAGE11_HERMES_TIMEOUT_ENV_NAMES", "legacy_receipt_matches",
    "settings_from_probe", "timeout_environment", "validate_settings_evidence",
]
