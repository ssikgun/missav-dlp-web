#!/usr/bin/env python3

from __future__ import annotations

from flask import Flask

import teddy_selkies_control_api as api


TOKEN_CALLS = 0


def unavailable_token():
    global TOKEN_CALLS

    TOKEN_CALLS += 1

    raise FileNotFoundError(
        "intentional smoke token absence"
    )


class Core:
    pass


core = Core()
core.app = Flask(
    "selkies-control-runtime-smoke"
)


first = api.install(
    core,
    token_loader=unavailable_token,
    opener=object(),
)

assert first == {
    "enabled":
        True,

    "installed":
        True,

    "reason":
        "configured",
}

assert TOKEN_CALLS == 0

print(
    "SELKIES_RUNTIME_LAZY_TOKEN_INSTALL=PASS"
)


rules = {
    (
        rule.rule,
        frozenset(
            rule.methods
        ),
    )
    for rule
    in core.app.url_map.iter_rules()
    if rule.rule.startswith(
        "/api/system/selkies/"
    )
}

expected_status = (
    "/api/system/selkies/"
    "<role>/status"
)

expected_restart = (
    "/api/system/selkies/"
    "<role>/restart"
)

status_matches = [
    methods
    for path, methods
    in rules
    if path == expected_status
]

restart_matches = [
    methods
    for path, methods
    in rules
    if path == expected_restart
]

assert len(
    status_matches
) == 1

assert len(
    restart_matches
) == 1

assert "GET" in status_matches[0]
assert "POST" not in status_matches[0]

assert "POST" in restart_matches[0]
assert "GET" not in restart_matches[0]

print(
    "SELKIES_RUNTIME_ROUTE_REGISTRATION=PASS"
)


second = api.install(
    core,
    token_loader=(
        lambda: (
            (_ for _ in ())
            .throw(
                AssertionError(
                    "second install must "
                    "not replace blueprint"
                )
            )
        )
    ),
    opener=object(),
)

assert second == {
    "enabled":
        True,

    "installed":
        False,

    "reason":
        "already-installed",
}

assert (
    list(
        core.app.blueprints
    ).count(
        api.BLUEPRINT_NAME
    )
    == 1
)

print(
    "SELKIES_RUNTIME_IDEMPOTENT_INSTALL=PASS"
)


client = core.app.test_client()

response = client.get(
    "/api/system/selkies/"
    "desktop/status"
)

assert response.status_code == 503

assert response.get_json() == {
    "status":
        "error",

    "message":
        (
            "Selkies control "
            "unavailable"
        ),
}

assert TOKEN_CALLS == 1

print(
    "SELKIES_RUNTIME_MISSING_TOKEN_FAIL_CLOSED=PASS"
)


before_calls = TOKEN_CALLS

response = client.get(
    "/api/system/selkies/"
    "unknown/status"
)

assert response.status_code == 404
assert TOKEN_CALLS == before_calls

print(
    "SELKIES_RUNTIME_UNKNOWN_ROLE_NO_TOKEN_READ=PASS"
)


broken = Core()

try:
    api.install(
        broken
    )

except ValueError as exc:
    assert (
        "core.app"
        in str(exc)
    )

else:
    raise AssertionError(
        "missing core.app must fail"
    )

print(
    "SELKIES_RUNTIME_MISSING_APP_FAIL_CLOSED=PASS"
)


assert set(
    api.TARGETS
) == {
    "desktop",
    "mobile",
}

print(
    "SELKIES_RUNTIME_FIXED_TARGET_SET=PASS"
)


print(
    "TEDDY_SELKIES_CONTROL_RUNTIME_SMOKE=PASS"
)
