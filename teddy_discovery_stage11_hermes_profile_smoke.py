"""Small offline checks for the Stage11 Hermes profile boundary."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from teddy_discovery_stage11_hermes_profile import (
    HermesExecutionSettings,
    HermesProfileSettingsError,
    REMOTE_PROFILE_SETTINGS_PROBE,
    STAGE11_HERMES_PROFILE,
    STAGE11_HERMES_TIMEOUT_ENV,
    STAGE11_HERMES_TIMEOUT_ENV_NAMES,
    legacy_receipt_matches,
    settings_from_probe,
    timeout_environment,
    validate_settings_evidence,
)


def _fixture_settings(provider, model, reasoning):
    return HermesExecutionSettings(
        profile_name=STAGE11_HERMES_PROFILE,
        provider=provider,
        model=model,
        reasoning_effort=reasoning,
        hermes_version="synthetic-1.2.3",
        config_sha256="a" * 64,
        timeout_env_supported=STAGE11_HERMES_TIMEOUT_ENV_NAMES,
    )


def _remote_probe(source: Path, config: Path):
    return subprocess.run(
        [sys.executable, "-S", "-c", REMOTE_PROFILE_SETTINGS_PROBE,
         str(config), str(source), STAGE11_HERMES_PROFILE,
         *STAGE11_HERMES_TIMEOUT_ENV_NAMES],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=10,
        check=False,
    )


def main():
    compile(REMOTE_PROFILE_SETTINGS_PROBE, "<remote-hermes-profile-probe>", "exec")
    base = {"HERMES_HOME": "/unrelated/profile", "EXISTING": "kept"}
    applied = timeout_environment(base)
    assert base == {"HERMES_HOME": "/unrelated/profile", "EXISTING": "kept"}
    assert applied["HERMES_HOME"] == "/unrelated/profile"
    assert {name: applied[name] for name in STAGE11_HERMES_TIMEOUT_ENV_NAMES} == dict(
        STAGE11_HERMES_TIMEOUT_ENV
    )

    settings = _fixture_settings("synthetic-provider", "synthetic-model", "high")
    assert validate_settings_evidence(settings.evidence()) == settings.evidence()
    receipt = {
        "provider": settings.provider,
        "model": settings.model,
        "reasoning": settings.reasoning_effort,
    }
    assert legacy_receipt_matches(receipt, settings)
    assert not legacy_receipt_matches({**receipt, "model": "different-model"}, settings)

    malformed = dict(settings.evidence())
    malformed["timeout_environment"] = {"HERMES_API_CALL_STALE_TIMEOUT": "90"}
    try:
        validate_settings_evidence(malformed)
    except HermesProfileSettingsError:
        pass
    else:
        raise AssertionError("changed timeout policy evidence was accepted")

    with tempfile.TemporaryDirectory(prefix="stage11-hermes-profile-smoke-") as temporary:
        root = Path(temporary)
        source = root / "source"
        profile = root / "profiles" / STAGE11_HERMES_PROFILE
        for directory in (source / "hermes_cli", source / "agent", profile):
            directory.mkdir(parents=True, mode=0o700)
        (source / "hermes_cli" / "__init__.py").write_text("", encoding="utf-8")
        (source / "hermes_cli" / "profiles.py").write_text(
            "def get_active_profile_name(): return 'subtitle-translator'\n",
            encoding="utf-8",
        )
        (source / "hermes_cli" / "config.py").write_text(
            "def read_user_config_raw(config_path=None):\n"
            "    return {'model': {'provider': 'synthetic-provider', "
            "'default': 'synthetic-model'}, 'agent': {'reasoning_effort': 'high'}}\n",
            encoding="utf-8",
        )
        (source / "run_agent.py").write_text(
            f"import os\nAPI_STALE = os.getenv({STAGE11_HERMES_TIMEOUT_ENV_NAMES[0]!r})\n",
            encoding="utf-8",
        )
        helpers = source / "agent" / "chat_completion_helpers.py"
        helper_calls = "\n".join(
            f"VALUE_{index} = _env_float({name!r}, 1)"
            for index, name in enumerate(STAGE11_HERMES_TIMEOUT_ENV_NAMES[1:])
        )
        helpers.write_text(
            "def _env_float(name, default): return default\n"
            + helper_calls + "\n",
            encoding="utf-8",
        )
        dist = source / "hermes_agent-1.2.3.dist-info"
        dist.mkdir(mode=0o700)
        (dist / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: hermes-agent\nVersion: 1.2.3\n\n",
            encoding="utf-8",
        )
        (dist / "top_level.txt").write_text("hermes_cli\nagent\n", encoding="utf-8")
        config = profile / "config.yaml"
        config.write_text("synthetic private config fixture\n", encoding="utf-8")
        before = (config.stat().st_ino, config.stat().st_size,
                  config.stat().st_mtime_ns, hashlib.sha256(config.read_bytes()).hexdigest())
        result = _remote_probe(source, config)
        assert result.returncode == 0, "synthetic Hermes runtime probe failed"
        parsed = settings_from_probe(result.stdout)
        assert (parsed.profile_name, parsed.provider, parsed.model,
                parsed.reasoning_effort, parsed.hermes_version,
                parsed.config_sha256) == (
                    STAGE11_HERMES_PROFILE, "synthetic-provider",
                    "synthetic-model", "high", "1.2.3",
                    hashlib.sha256(config.read_bytes()).hexdigest())
        after = (config.stat().st_ino, config.stat().st_size,
                 config.stat().st_mtime_ns, hashlib.sha256(config.read_bytes()).hexdigest())
        assert after == before, "profile probe changed its config file"

        missing_source = root / "missing-timeout-source"
        import shutil
        shutil.copytree(source, missing_source)
        helper_copy = missing_source / "agent" / "chat_completion_helpers.py"
        helper_copy.write_text(
            helper_copy.read_text(encoding="utf-8").replace(
                f"_env_float({STAGE11_HERMES_TIMEOUT_ENV_NAMES[1]!r}, 1)",
                "_env_float('OTHER', 1)",
            ) + "\n# " + STAGE11_HERMES_TIMEOUT_ENV_NAMES[1] + "\n"
            + repr(STAGE11_HERMES_TIMEOUT_ENV_NAMES[1]) + "\n",
            encoding="utf-8",
        )
        unsupported = _remote_probe(missing_source, config)
        assert unsupported.returncode != 0, "unsupported timeout env was not rejected"

    print("STAGE11_HERMES_PROFILE_SMOKE_PASS=8")


if __name__ == "__main__":
    main()
