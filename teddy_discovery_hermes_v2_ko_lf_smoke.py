"""Offline regression for LF only in the Hermes v2 Korean output field."""

from dataclasses import replace
import json
import unittest

from teddy_discovery_hermes_v2 import (
    HermesV2CueInput, HermesV2CueOutput, HermesV2Request,
    HermesV2ValidationError, _validate_text, parse_hermes_v2_result,
)


class KoreanOutputLFSmoke(unittest.TestCase):
    def setUp(self):
        self.cue = HermesV2CueInput("generic-cue", "source", None, None, (), ())
        self.output = HermesV2CueOutput(self.cue.cue_id, None, "첫 화자\n둘째 화자")

    def test_ko_internal_lf_preserved(self):
        self.assertEqual(self.output.ko, "첫 화자\n둘째 화자")

    def test_ko_lf_wire_parse_preserved(self):
        payload = json.dumps({"cues": [{
            "cue_id": self.output.cue_id, "repaired_ja": None, "ko": self.output.ko,
        }]}, ensure_ascii=False).encode()
        parsed = parse_hermes_v2_result(payload, HermesV2Request((self.cue,)))
        self.assertEqual(parsed.cues, (self.output,))

    def test_ko_other_controls_rejected(self):
        # Also test combinations with LF so its exception cannot hide another control.
        for control in ("\t", "\r", "\x00", "\x7f", "\x01", "\x85"):
            for text in ("앞" + control + "뒤", "앞\n중간" + control + "뒤"):
                with self.subTest(control=repr(control), text=repr(text)), \
                     self.assertRaises(HermesV2ValidationError):
                    replace(self.output, ko=text)

    def test_repaired_ja_lf_rejected(self):
        with self.assertRaises(HermesV2ValidationError):
            replace(self.output, repaired_ja="前\n後")

    def test_input_text_lf_rejected(self):
        for field in ("external_ja", "stt_ja", "en"):
            with self.subTest(field=field), self.assertRaises(HermesV2ValidationError):
                replace(self.cue, **{field: "before\nafter"})

    def test_context_lf_rejected(self):
        for field in ("before_context", "after_context"):
            with self.subTest(field=field), self.assertRaises(HermesV2ValidationError):
                replace(self.cue, **{field: ("before\nafter",)})

    def test_input_and_output_cue_id_lf_rejected(self):
        for cue in (self.cue, self.output):
            with self.subTest(type=type(cue).__name__), self.assertRaises(HermesV2ValidationError):
                replace(cue, cue_id="generic\ncue")

    def test_text_validator_remains_strict_by_default(self):
        with self.assertRaises(HermesV2ValidationError):
            _validate_text("첫 화자\n둘째 화자", field_name="ko", allow_none=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
