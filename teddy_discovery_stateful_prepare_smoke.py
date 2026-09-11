"""Offline smoke for Stage11 stateful nonlexical preparation."""

from teddy_discovery_hermes_v2 import HermesV2CueInput
from teddy_discovery_stateful_prepare import (
    StatefulPrepareValidationError,
    prepare_stateful_package,
)
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
    stateful_session_id_for_package,
)


def cue(cue_id, text):
    return HermesV2CueInput(
        cue_id=cue_id,
        external_ja=None,
        stt_ja=text,
        en=None,
        before_context=(),
        after_context=(),
    )


def main():
    source = StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="TEST-001",
        generation_key="generation-old",
        claim_token=7,
        cues=(
            cue("asr-0001", "普通の文です"),
            cue("asr-0002", "ああああ"),
            cue("asr-0003", "次の文です"),
        ),
    )

    prepared = prepare_stateful_package(
        source,
        generation_key="generation-filtered",
    )

    assert tuple(
        item.cue_id
        for item in prepared.package.cues
    ) == (
        "asr-0001",
        "asr-0003",
    )

    assert prepared.omitted_cue_ids == (
        "asr-0002",
    )

    assert prepared.package.claim_token == source.claim_token
    assert prepared.package.dvd_id == source.dvd_id

    assert (
        stateful_session_id_for_package(prepared.package)
        != stateful_session_id_for_package(source)
    )

    try:
        prepare_stateful_package(
            source,
            generation_key=source.generation_key,
        )
    except StatefulPrepareValidationError:
        pass
    else:
        raise AssertionError(
            "unchanged generation_key was accepted"
        )

    print("STATEFUL_PREPARE_SMOKE_PASS")


if __name__ == "__main__":
    main()
