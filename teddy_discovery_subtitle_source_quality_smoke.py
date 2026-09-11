"""Synthetic offline quality-boundary checks; no model or artifact I/O."""
import ast
from dataclasses import FrozenInstanceError
from pathlib import Path
import re
from unittest.mock import patch

import teddy_discovery_subtitle_source_quality as quality
from teddy_discovery_stateful_parts import has_runaway_repetition
from teddy_discovery_subtitle_text import SubtitleCue, parse_subtitle_bytes


def indexed(texts, *, gap=0, duration=100, indexes=None):
    return tuple(quality.SourceQualityCue(i if indexes is None else indexes[i],
                 SubtitleCue(i * (duration + gap), i * (duration + gap) + duration, text))
                 for i, text in enumerate(texts))


def decisions(texts, **kwargs):
    return quality.classify_source_quality(indexed(texts, **kwargs))


def all_action(texts, action, **kwargs):
    return all(d.action == action for d in decisions(texts, **kwargs))


def raises(kind, callback):
    try:
        callback()
    except kind:
        return True
    return False


def main():
    passed = failed = 0

    def check(name, callback):
        nonlocal passed, failed
        try:
            assert callback()
        except Exception as error:
            failed += 1
            print(f"FAIL {name}: {type(error).__name__}: {error}")
        else:
            passed += 1
            print(f"PASS {name}")

    for word in ('作成', '制作', '製作'):
        check('Japanese authoring structure ' + word, lambda word=word: all_action(['字幕 | ' + word, word + '：字幕'], quality.OMIT_METADATA))
    check('ASCII generic tool/version', lambda: all_action(['ExampleTool | v2.4', 'Utility / 3.12.1'], quality.OMIT_METADATA))
    check('normal Japanese dialogue', lambda: all_action(['今日はどこへ行きますか。', '字幕を読んでください。'], quality.KEEP))
    check('ordinary ASCII dialogue', lambda: all_action(['Hello / goodbye', 'We will meet tomorrow.'], quality.KEEP))
    check('version alone', lambda: all_action(['2.4.1', '2.4 | 3.0'], quality.KEEP))
    check('separator alone', lambda: all_action(['|', '/'], quality.KEEP))
    check('missing separator', lambda: all_action(['ExampleTool v2.4'], quality.KEEP))
    check('non ASCII version text', lambda: all_action(['道具 | 2.4'], quality.KEEP))
    check('distant authoring words', lambda: all_action(['字幕' + 'の' * (quality.AUTHORING_MAX_CONTEXT_CHARS + 1) + '作成'], quality.KEEP))
    check('authoring sentence boundary', lambda: all_action(['字幕。作成', '字幕\n制作'], quality.KEEP))

    diverse = ['あ', 'き', 'す', 'ね', 'ほ', 'む', 'や', 'ろ']
    check('long dense diverse kana', lambda: all_action(diverse, quality.REQUIRE_SECOND_EVIDENCE))
    check('repeated identical reaction', lambda: all_action(['んー?'] * 8, quality.KEEP))
    check('below minimum run', lambda: all_action(diverse[:quality.FRAGMENT_MIN_RUN - 1], quality.KEEP))
    check('long sparse run', lambda: all_action(diverse, quality.KEEP, gap=101))
    check('isolated kana', lambda: all_action(['き'], quality.KEEP))
    check('meaningful short cue', lambda: all_action(['はい', '待って'], quality.KEEP))
    check('density equality', lambda: all_action(diverse, quality.REQUIRE_SECOND_EVIDENCE, gap=100))
    check('diversity equality', lambda: all_action(diverse[:6] + diverse[:2], quality.REQUIRE_SECOND_EVIDENCE))
    check('below diversity threshold', lambda: all_action(diverse[:5] + diverse[:3], quality.KEEP))
    check('normalization reduces diversity', lambda: all_action(['あ', 'ア', 'ｱ', 'き', 'キ', 'ｷ'], quality.KEEP))
    check('punctuated two-kana run', lambda: all_action(['「あき」', 'すね!', 'ほむ?', 'やろ。', 'けさ', 'とに'], quality.REQUIRE_SECOND_EVIDENCE))
    check('lexical cue breaks run', lambda: all_action(diverse[:4] + ['ここで待ってください'] + diverse[4:], quality.KEEP))
    check('index gap breaks run', lambda: all_action(diverse, quality.KEEP, indexes=[0, 1, 2, 3, 5, 6, 7, 8]))

    suspect = decisions(diverse)[0]
    metadata = decisions(['字幕：作成'])[0]
    keep = decisions(['ここで待ってください'])[0]
    check('normal second STT', lambda: quality.resolve_second_evidence(suspect, '少し待ってください').action == quality.KEEP_WITH_SECOND_EVIDENCE)
    check('missing second STT', lambda: quality.resolve_second_evidence(suspect, None).action == quality.OMIT_FRAGMENT_UNSUPPORTED)
    check('runaway second STT', lambda: quality.resolve_second_evidence(suspect, 'あ' * 64).action == quality.OMIT_FRAGMENT_UNSUPPORTED)
    check('metadata remains omitted', lambda: quality.resolve_second_evidence(metadata, '少し待ってください').action == quality.OMIT_METADATA)
    check('keep without STT', lambda: quality.resolve_second_evidence(keep, None).action == quality.KEEP)
    check('canonical detector identity', lambda: quality.has_runaway_repetition is has_runaway_repetition)

    def detector_called():
        with patch.object(quality, 'has_runaway_repetition', wraps=has_runaway_repetition) as detector:
            quality.resolve_second_evidence(suspect, 'あ' * 64)
            detector.assert_called_once_with('あ' * 64)
        return True

    check('canonical detector invoked', detector_called)
    class StringSubclass(str):
        pass
    for invalid in [1, False, b'text', '', ' \n', '\x00', '\ud800', StringSubclass('text'), 'a' * (quality.MAX_CUE_TEXT_CHARS + 1)]:
        check('invalid second STT fails closed', lambda invalid=invalid: raises(quality.SourceQualityError, lambda: quality.resolve_second_evidence(suspect, invalid)))

    texts = ['ここで待ってください'] * 10
    texts[3] = '字幕：制作'
    texts[7] = 'ExampleTool | 1.2'
    results = decisions(texts)
    check('all original indexes retained', lambda: [d.source_index for d in results] == list(range(10)))
    check('omitted subset without reindex', lambda: [d.source_index for d in results if d.action == quality.KEEP] == [0, 1, 2, 4, 5, 6, 8, 9])
    check('explicit subset retains indexes', lambda: [d.source_index for d in decisions(['はい', 'はい'], indexes=[4, 9])] == [4, 9])
    check('original text identity', lambda: all(d.source_text is text for d, text in zip(results, texts)))
    outcome = quality.resolve_second_evidence(suspect, '少し待ってください')
    check('outcome retains source identity', lambda: outcome.source_decision is suspect and outcome.source_index == suspect.source_index and outcome.source_text is suspect.source_text)
    check('immutable decision', lambda: raises(FrozenInstanceError, lambda: setattr(keep, 'source_index', 2)))
    check('immutable outcome', lambda: raises(FrozenInstanceError, lambda: setattr(outcome, 'action', quality.KEEP)))
    check('immutable input', lambda: raises(FrozenInstanceError, lambda: setattr(indexed(['はい'])[0], 'source_index', 2)))
    check('immutable collection', lambda: type(results) is tuple)
    document = parse_subtitle_bytes(b'1\n00:00:00,000 --> 00:00:01,000\nHello\n', 'srt')
    check('original document adapter', lambda: quality.classify_source_document(document)[0].source_index == 0)
    check('empty subset', lambda: quality.classify_source_quality(()) == ())
    for invalid in [None, [], (None,)]:
        check('invalid input collection', lambda invalid=invalid: raises(quality.SourceQualityError, lambda: quality.classify_source_quality(invalid)))
    for index in [-1, True, '0', quality.MAX_SUBTITLE_CUES]:
        check('invalid source index', lambda index=index: raises(quality.SourceQualityError, lambda: quality.SourceQualityCue(index, SubtitleCue(0, 100, 'はい'))))
    check('duplicate index', lambda: raises(quality.SourceQualityError, lambda: decisions(['はい', 'はい'], indexes=[2, 2])))
    check('unordered index', lambda: raises(quality.SourceQualityError, lambda: decisions(['はい', 'はい'], indexes=[2, 1])))
    check('unordered timing', lambda: raises(quality.SourceQualityError, lambda: quality.classify_source_quality((quality.SourceQualityCue(0, SubtitleCue(100, 200, 'はい')), quality.SourceQualityCue(1, SubtitleCue(0, 100, 'はい'))))))
    check('invalid decision', lambda: raises(quality.SourceQualityError, lambda: quality.SourceQualityDecision(0, 'UNKNOWN', 'no_quality_objection', 'はい')))
    check('invalid decision reason', lambda: raises(quality.SourceQualityError, lambda: quality.SourceQualityDecision(0, quality.KEEP, 'dense_diverse_kana_run', 'はい')))
    check('invalid helper decision', lambda: raises(quality.SourceQualityError, lambda: quality.resolve_second_evidence(None, None)))
    check('detached outcome', lambda: raises(quality.SourceQualityError, lambda: quality.SecondEvidenceOutcome(metadata, quality.KEEP, 'source_keep')))
    check('invalid document', lambda: raises(quality.SourceQualityError, lambda: quality.classify_source_document(None)))

    source = Path(quality.__file__).read_text()
    tree = ast.parse(source)
    literals = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    check('no DVD-ID or numeric SubtitleCat path', lambda: not re.search(r'(?i)\b[A-Z]{2,10}-\d{2,8}\b|/subs/\d+', source))
    check('no cue number exceptions', lambda: not any(isinstance(node, ast.Compare) and any(isinstance(part, ast.Attribute) and part.attr == 'source_index' for part in ast.walk(node)) and any(isinstance(part, ast.Constant) and type(part.value) is int and part.value > 1 for part in ast.walk(node)) for node in ast.walk(tree)))
    # All Japanese production literals are structural tokens/kana ranges and
    # punctuation, never observed dialogue phrases or exact title exceptions.
    japanese_literals = [value for value in literals if re.search(r'[\u3040-\u30ff\u3400-\u9fff]', value)]
    allowed = {'字幕', '(?:作成|制作|製作)|(?:作成|制作|製作)',
               'ァ', 'ヶ', 'ぁ', 'ゖ', 'ー'}
    check('Japanese literal structural allowlist', lambda: set(japanese_literals) <= allowed)
    print(f'Subtitle source quality smoke: PASS={passed} FAIL={failed}')
    return int(failed != 0)


if __name__ == '__main__':
    raise SystemExit(main())
