"""Offline smoke tests for the stateful Stage11 translator boundary."""

from dataclasses import FrozenInstanceError, MISSING, fields
import json
import os
from pathlib import Path
import stat
import tempfile

from teddy_discovery_hermes_v2 import (
    HermesV2CueInput,
    HermesV2CueOutput,
    MAX_HERMES_V2_REQUEST_CUES,
)
from teddy_discovery_stateful_translator import (
    MAX_STATEFUL_TRANSLATOR_CUES,
    STATEFUL_TRANSLATOR_EXECUTABLE,
    STATEFUL_TRANSLATOR_INPUT_FILENAME,
    STATEFUL_TRANSLATOR_MAX_PACKAGE_BYTES,
    STATEFUL_TRANSLATOR_MAX_RESULT_BYTES,
    STATEFUL_TRANSLATOR_MODEL,
    STATEFUL_TRANSLATOR_PASS_SESSION_ID_FLAG,
    STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE,
    STATEFUL_TRANSLATOR_PROFILE,
    STATEFUL_TRANSLATOR_PROVIDER,
    STATEFUL_TRANSLATOR_QUERY,
    STATEFUL_TRANSLATOR_REASONING,
    STATEFUL_TRANSLATOR_RESULT_FILENAME,
    STATEFUL_TRANSLATOR_SESSION_SOURCE,
    STATEFUL_TRANSLATOR_TASK_DIRECTORY_MODE,
    StatefulSubtitlePackage,
    StatefulSubtitleResult,
    StatefulTranslatorLimitError,
    StatefulTranslatorSessionError,
    StatefulTranslatorStagingError,
    StatefulTranslatorValidationError,
    build_stateful_translator_command,
    create_stateful_staging_directory,
    derive_stateful_session_id,
    parse_stateful_package,
    parse_stateful_result,
    premint_stateful_session,
    read_stateful_result,
    resolve_stateful_staging_path,
    serialize_stateful_package,
    serialize_stateful_result,
    stateful_session_id_for_package,
    stateful_staging_paths,
    validate_stateful_result,
    write_stateful_input,
)


def require(condition: bool, marker: str):
    if not condition:
        raise AssertionError(marker)


def expect_raises(exception_type, callback, marker: str):
    try:
        callback()
    except exception_type:
        return
    except Exception as error:
        raise AssertionError(
            marker + ": wrong exception " + type(error).__name__
        ) from error
    raise AssertionError(marker)


def cue(index: int) -> HermesV2CueInput:
    return HermesV2CueInput(
        cue_id=f"cue-{index:04d}",
        external_ja=f"authorized-ja-{index}",
        stt_ja=None,
        en=None,
        before_context=(),
        after_context=(),
    )


def package(count: int = 3, *, claim_token: int = 7) -> StatefulSubtitlePackage:
    return StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="DVD-EXAMPLE",
        generation_key="generation-001",
        claim_token=claim_token,
        cues=tuple(cue(index) for index in range(count)),
    )


def result_for(
    source_package: StatefulSubtitlePackage,
    *,
    session_id: str | None = None,
    outputs: tuple[HermesV2CueOutput, ...] | None = None,
) -> StatefulSubtitleResult:
    session_id = session_id or stateful_session_id_for_package(source_package)
    outputs = outputs or tuple(
        HermesV2CueOutput(
            cue_id=item.cue_id,
            repaired_ja=None,
            ko=f"한국어-{item.cue_id}",
        )
        for item in source_package.cues
    )
    return StatefulSubtitleResult(
        schema_version=source_package.schema_version,
        dvd_id=source_package.dvd_id,
        generation_key=source_package.generation_key,
        claim_token=source_package.claim_token,
        session_id=session_id,
        cues=outputs,
    )


def write_private_file(path: Path, payload: bytes):
    file_descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE,
    )
    try:
        os.fchmod(file_descriptor, STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE)
        os.write(file_descriptor, payload)
        os.fsync(file_descriptor)
    finally:
        os.close(file_descriptor)


def result_payload(
    source_package: StatefulSubtitlePackage,
    *,
    dvd_id: str | None = None,
    generation_key: str | None = None,
    claim_token: int | None = None,
    session_id: str | None = None,
    outputs: list[dict[str, object]] | None = None,
) -> bytes:
    result = result_for(source_package, session_id=session_id)
    return json.dumps(
        {
            "schema_version": result.schema_version,
            "dvd_id": dvd_id if dvd_id is not None else result.dvd_id,
            "generation_key": (
                generation_key
                if generation_key is not None
                else result.generation_key
            ),
            "claim_token": (
                claim_token if claim_token is not None else result.claim_token
            ),
            "session_id": result.session_id,
            "cues": (
                outputs
                if outputs is not None
                else [
                    {
                        "cue_id": item.cue_id,
                        "repaired_ja": item.repaired_ja,
                        "ko": item.ko,
                    }
                    for item in result.cues
                ]
            ),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


class FakeSessionDB:
    def __init__(self, returned_id: str | None = None):
        self.returned_id = returned_id
        self.calls: list[dict[str, str]] = []

    def create_session(self, *, session_id: str, source: str) -> str:
        self.calls.append({"session_id": session_id, "source": source})
        return self.returned_id if self.returned_id is not None else session_id


def main():
    small_package = package()
    require(
        tuple(field.name for field in fields(StatefulSubtitlePackage))
        == (
            "schema_version",
            "dvd_id",
            "generation_key",
            "claim_token",
            "cues",
        )
        and tuple(field.name for field in fields(StatefulSubtitleResult))
        == (
            "schema_version",
            "dvd_id",
            "generation_key",
            "claim_token",
            "session_id",
            "cues",
        ),
        "EXACT_STATEFUL_ENVELOPE_FIELDS",
    )
    for contract_type in (StatefulSubtitlePackage, StatefulSubtitleResult):
        require(
            getattr(contract_type.__dataclass_params__, "frozen", False),
            contract_type.__name__ + "_FROZEN",
        )
        for field in fields(contract_type):
            require(
                field.default is MISSING and field.default_factory is MISSING,
                contract_type.__name__ + "_NO_HIDDEN_DEFAULT_" + field.name,
            )

    serialized_package = serialize_stateful_package(small_package)
    parsed_package = parse_stateful_package(serialized_package)
    require(
        parsed_package == small_package
        and serialized_package == serialize_stateful_package(small_package)
        and len(serialized_package) <= STATEFUL_TRANSLATOR_MAX_PACKAGE_BYTES
        and MAX_HERMES_V2_REQUEST_CUES == 512,
        "VALID_PACKAGE_DETERMINISTIC_SERIALIZATION_OLD_LIMIT_UNCHANGED",
    )
    expect_raises(
        FrozenInstanceError,
        lambda: setattr(small_package, "dvd_id", "changed"),
        "PACKAGE_IMMUTABLE",
    )

    package_661 = package(661)
    package_661_wire = serialize_stateful_package(package_661)
    require(
        len(package_661.cues) == 661
        and parse_stateful_package(package_661_wire) == package_661,
        "STATEFUL_661_PACKAGE_ACCEPTED",
    )
    package_max = package(MAX_STATEFUL_TRANSLATOR_CUES)
    require(
        len(parse_stateful_package(serialize_stateful_package(package_max)).cues)
        == MAX_STATEFUL_TRANSLATOR_CUES,
        "STATEFUL_MAX_CUE_BOUND_ACCEPTED",
    )
    expect_raises(
        StatefulTranslatorLimitError,
        lambda: package(MAX_STATEFUL_TRANSLATOR_CUES + 1),
        "STATEFUL_OVER_MAX_CUES_REJECTED",
    )
    for invalid_package in (
        lambda: StatefulSubtitlePackage(
            1, "", "generation-001", 1, (cue(1),)
        ),
        lambda: StatefulSubtitlePackage(
            1, "DVD-EXAMPLE", "", 1, (cue(1),)
        ),
        lambda: StatefulSubtitlePackage(
            1, "DVD-EXAMPLE", "generation-001", True, (cue(1),)
        ),
        lambda: StatefulSubtitlePackage(
            1, "DVD-EXAMPLE", "generation-001", -1, (cue(1),)
        ),
    ):
        expect_raises(
            StatefulTranslatorValidationError,
            invalid_package,
            "MALFORMED_IDENTITY_REJECTED",
        )
    expect_raises(
        StatefulTranslatorValidationError,
        lambda: StatefulSubtitlePackage(
            1,
            "DVD-EXAMPLE",
            "generation-001",
            1,
            (cue(1), cue(1)),
        ),
        "DUPLICATE_INPUT_CUE_ID_REJECTED",
    )
    expect_raises(
        StatefulTranslatorLimitError,
        lambda: parse_stateful_package(
            b" " * (STATEFUL_TRANSLATOR_MAX_PACKAGE_BYTES + 1)
        ),
        "OVERSIZED_PACKAGE_WIRE_REJECTED",
    )

    session_id = derive_stateful_session_id(
        small_package.dvd_id,
        small_package.generation_key,
        small_package.claim_token,
    )
    require(
        session_id == derive_stateful_session_id(
            small_package.dvd_id,
            small_package.generation_key,
            small_package.claim_token,
        )
        and session_id == stateful_session_id_for_package(small_package)
        and session_id != derive_stateful_session_id(
            small_package.dvd_id,
            small_package.generation_key,
            small_package.claim_token + 1,
        )
        and session_id != derive_stateful_session_id(
            small_package.dvd_id,
            "generation-002",
            small_package.claim_token,
        )
        and len(session_id) == 36,
        "DETERMINISTIC_SESSION_ID_IDENTITY_CONTRACT",
    )
    require(
        "authorized-ja" not in session_id
        and "한국어" not in session_id,
        "SESSION_ID_HAS_NO_DIALOGUE",
    )

    fake_db = FakeSessionDB()
    require(
        premint_stateful_session(fake_db, small_package) == session_id
        and fake_db.calls == [
            {
                "session_id": session_id,
                "source": STATEFUL_TRANSLATOR_SESSION_SOURCE,
            }
        ],
        "SESSION_PREMINT_NATIVE_API_SUCCESS",
    )
    mismatch_db = FakeSessionDB(returned_id=derive_stateful_session_id(
        small_package.dvd_id,
        small_package.generation_key,
        small_package.claim_token + 1,
    ))
    expect_raises(
        StatefulTranslatorSessionError,
        lambda: premint_stateful_session(mismatch_db, small_package),
        "SESSION_PREMINT_RETURNED_ID_MISMATCH_REJECTED",
    )

    command = build_stateful_translator_command(session_id)
    command_text = " ".join(command)
    chat_index = command.index("chat")
    pass_session_id_index = command.index(
        STATEFUL_TRANSLATOR_PASS_SESSION_ID_FLAG
    )
    resume_index = command.index("--resume")
    query_index = command.index("-q")
    require(
        command[:3]
        == [STATEFUL_TRANSLATOR_EXECUTABLE, "--profile", STATEFUL_TRANSLATOR_PROFILE]
        and "chat" in command
        and "-Q" in command
        and command.count(STATEFUL_TRANSLATOR_PASS_SESSION_ID_FLAG) == 1
        and chat_index < pass_session_id_index < resume_index < query_index
        and "--resume" in command
        and session_id in command
        and "--provider" in command
        and STATEFUL_TRANSLATOR_PROVIDER in command
        and "--model" in command
        and STATEFUL_TRANSLATOR_MODEL in command
        and "--reasoning" in command
        and STATEFUL_TRANSLATOR_REASONING in command
        and "-q" in command
        and command[-1] == STATEFUL_TRANSLATOR_QUERY
        and "-z" not in command
        and "retry" not in command_text.lower()
        and "fallback" not in command_text.lower()
        and "external-ja" not in command_text
        and "authorized-ja" not in command_text
        and "한국어" not in command_text,
        "EXACT_STATEFUL_COMMAND_WITHOUT_DIALOGUE_OR_ONESHOT",
    )
    for required_phrase, marker in (
        (STATEFUL_TRANSLATOR_INPUT_FILENAME, "QUERY_INPUT_FILENAME"),
        (STATEFUL_TRANSLATOR_RESULT_FILENAME, "QUERY_RESULT_FILENAME"),
        (
            "schema_version, dvd_id, generation_key, claim_token",
            "QUERY_INPUT_IDENTITY_FIELDS",
        ),
        (
            "current Hermes session ID is supplied by Hermes in the system prompt",
            "QUERY_SESSION_SOURCE",
        ),
        (
            "--pass-session-id is active",
            "QUERY_PASS_SESSION_ID_SEMANTICS",
        ),
        (
            "copy that exact value into result field session_id",
            "QUERY_RESULT_SESSION_ID",
        ),
        (
            "Top-level fields must be exactly: schema_version, dvd_id, "
            "generation_key, claim_token, session_id, cues",
            "QUERY_EXACT_RESULT_FIELDS",
        ),
        (
            "Every cue object must contain exactly: cue_id, repaired_ja, ko",
            "QUERY_EXACT_CUE_FIELDS",
        ),
    ):
        require(required_phrase in STATEFUL_TRANSLATOR_QUERY, marker)
    require(
        "authorized-ja" not in STATEFUL_TRANSLATOR_QUERY
        and "한국어" not in STATEFUL_TRANSLATOR_QUERY,
        "QUERY_HAS_NO_DIALOGUE",
    )
    stateful_source = Path(__file__).with_name(
        "teddy_discovery_stateful_translator.py"
    ).read_text(encoding="utf-8")
    for forbidden, marker in (
        ("hermes_state", "NO_NATIVE_RUNTIME_IMPORT"),
        ("sqlite3", "NO_DIRECT_SQLITE"),
        ("subprocess", "NO_PROCESS_INVOCATION"),
        ("socket", "NO_NETWORK_SOCKET"),
        ("requests", "NO_HTTP_CLIENT"),
        ("urllib", "NO_NETWORK_LIBRARY"),
        ("-z", "NO_ONESHOT_FLAG_IN_SOURCE"),
    ):
        require(forbidden not in stateful_source, marker)

    result = result_for(small_package)
    serialized_result = serialize_stateful_result(result)
    require(
        validate_stateful_result(
            parse_stateful_result(serialized_result, small_package),
            small_package,
        )
        == result
        and serialized_result == serialize_stateful_result(result)
        and len(serialized_result) <= STATEFUL_TRANSLATOR_MAX_RESULT_BYTES
        and all(
            forbidden not in serialized_result.decode("utf-8").lower()
            for forbidden in ("timestamp", "start_ms", "end_ms")
        ),
        "VALID_RESULT_DETERMINISTIC_NO_TIMESTAMP_AUTHORITY",
    )
    expect_raises(
        StatefulTranslatorLimitError,
        lambda: parse_stateful_result(
            b" " * (STATEFUL_TRANSLATOR_MAX_RESULT_BYTES + 1),
            small_package,
        ),
        "OVERSIZED_RESULT_WIRE_REJECTED",
    )
    expect_raises(
        StatefulTranslatorValidationError,
        lambda: parse_stateful_result(b"not json", small_package),
        "MALFORMED_RESULT_REJECTED",
    )
    expected_result_wire = json.loads(serialized_result.decode("utf-8"))
    expect_raises(
        StatefulTranslatorValidationError,
        lambda: parse_stateful_result(
            result_payload(small_package, dvd_id="DVD-OTHER"),
            small_package,
        ),
        "WRONG_DVD_ID_REJECTED",
    )
    expect_raises(
        StatefulTranslatorValidationError,
        lambda: parse_stateful_result(
            result_payload(small_package, generation_key="generation-002"),
            small_package,
        ),
        "WRONG_GENERATION_REJECTED",
    )
    expect_raises(
        StatefulTranslatorValidationError,
        lambda: parse_stateful_result(
            result_payload(small_package, claim_token=8),
            small_package,
        ),
        "WRONG_CLAIM_REJECTED",
    )
    expect_raises(
        StatefulTranslatorValidationError,
        lambda: parse_stateful_result(
            result_payload(
                small_package,
                session_id=derive_stateful_session_id(
                    small_package.dvd_id,
                    small_package.generation_key,
                    small_package.claim_token + 1,
                ),
            ),
            small_package,
        ),
        "WRONG_SESSION_REJECTED",
    )
    missing = list(expected_result_wire["cues"][:-1])
    expect_raises(
        StatefulTranslatorValidationError,
        lambda: parse_stateful_result(
            result_payload(small_package, outputs=missing),
            small_package,
        ),
        "MISSING_OUTPUT_CUE_REJECTED",
    )
    reordered = list(reversed(expected_result_wire["cues"]))
    expect_raises(
        StatefulTranslatorValidationError,
        lambda: parse_stateful_result(
            result_payload(small_package, outputs=reordered),
            small_package,
        ),
        "REORDERED_OUTPUT_CUE_REJECTED",
    )
    duplicate = list(expected_result_wire["cues"])
    duplicate[1] = dict(duplicate[0])
    expect_raises(
        StatefulTranslatorValidationError,
        lambda: parse_stateful_result(
            result_payload(small_package, outputs=duplicate),
            small_package,
        ),
        "DUPLICATE_OUTPUT_CUE_REJECTED",
    )
    extra = list(expected_result_wire["cues"])
    extra.append({"cue_id": "cue-extra", "repaired_ja": None, "ko": "ko"})
    expect_raises(
        StatefulTranslatorValidationError,
        lambda: parse_stateful_result(
            result_payload(small_package, outputs=extra),
            small_package,
        ),
        "EXTRA_OUTPUT_CUE_REJECTED",
    )
    expect_raises(
        StatefulTranslatorValidationError,
        lambda: parse_stateful_result(
            b'{"schema_version":1,"schema_version":1,"dvd_id":"DVD-EXAMPLE",'
            b'"generation_key":"generation-001","claim_token":7,"session_id":"'
            + session_id.encode("ascii")
            + b'","cues":[]}',
            small_package,
        ),
        "DUPLICATE_JSON_KEY_REJECTED",
    )
    package_result_661 = result_for(package_661)
    require(
        len(
            parse_stateful_result(
                serialize_stateful_result(package_result_661),
                package_661,
            ).cues
        )
        == 661,
        "STATEFUL_661_COMPLETE_RESULT_ACCEPTED",
    )

    with tempfile.TemporaryDirectory(prefix="stage11-stateful-smoke-") as root:
        task_directory = create_stateful_staging_directory(root, session_id)
        directory_mode = stat.S_IMODE(os.stat(task_directory).st_mode)
        require(
            directory_mode == STATEFUL_TRANSLATOR_TASK_DIRECTORY_MODE,
            "STAGING_DIRECTORY_MODE_0700",
        )
        input_path = write_stateful_input(task_directory, small_package)
        input_mode = stat.S_IMODE(os.stat(input_path).st_mode)
        require(
            input_path.name == STATEFUL_TRANSLATOR_INPUT_FILENAME
            and input_mode == STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE,
            "PRIVATE_INPUT_MODE_0600",
        )
        paths = stateful_staging_paths(task_directory)
        require(
            paths.result_path.name == STATEFUL_TRANSLATOR_RESULT_FILENAME,
            "FIXED_RESULT_FILENAME",
        )
        expect_raises(
            StatefulTranslatorStagingError,
            lambda: resolve_stateful_staging_path(task_directory, "../escape"),
            "TRAVERSAL_REJECTED",
        )
        expect_raises(
            StatefulTranslatorStagingError,
            lambda: read_stateful_result(
                task_directory,
                small_package,
                process_finished=False,
            ),
            "PARTIAL_RESULT_NOT_CONSUMED",
        )
        write_private_file(paths.result_path, serialized_result)
        require(
            stat.S_IMODE(os.stat(paths.result_path).st_mode)
            == STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE
            and read_stateful_result(
                task_directory,
                small_package,
                process_finished=True,
            )
            == result,
            "PRIVATE_COMPLETE_RESULT_CONSUMED_AFTER_PROCESS",
        )
        paths.result_path.unlink()
        os.symlink(paths.input_path, paths.result_path)
        expect_raises(
            StatefulTranslatorStagingError,
            lambda: read_stateful_result(
                task_directory,
                small_package,
                process_finished=True,
            ),
            "SYMLINK_RESULT_REJECTED",
        )

    policy = Path(__file__).with_name(
        "teddy_discovery_stateful_translator_policy.txt"
    ).read_text(encoding="utf-8").lower()
    for required_phrase, marker in (
        ("one title is one persistent semantic subtitle-translation task", "POLICY_TITLE_TASK"),
        ("authorized japanese evidence", "POLICY_AUTHORIZED_JA"),
        ("natural korean", "POLICY_KOREAN"),
        ("external korean subtitles are prohibited", "POLICY_NO_EXTERNAL_KO"),
        ("cue ids are immutable", "POLICY_IMMUTABLE_IDS"),
        ("do not create, change, or infer timestamps", "POLICY_NO_TIMESTAMPS"),
        ("partial result is not publishable", "POLICY_NO_PARTIAL_PUBLICATION"),
    ):
        require(required_phrase in policy, marker)
    for forbidden, marker in (
        ("homeboy", "POLICY_NO_HOMEBOY"),
        ("planner", "POLICY_NO_PLANNER"),
        ("kanban", "POLICY_NO_KANBAN"),
        ("slack", "POLICY_NO_MESSAGING"),
    ):
        require(forbidden not in policy, marker)

    print("STATEFUL_TRANSLATOR_SMOKE_PASS")


if __name__ == "__main__":
    main()
