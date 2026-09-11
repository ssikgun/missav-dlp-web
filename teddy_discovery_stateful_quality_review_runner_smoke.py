"""Synthetic temporary-file tests: every real subprocess entrypoint is blocked."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import uuid

import teddy_discovery_stateful_quality_review as review
import teddy_discovery_stateful_quality_review_runner as runner
import teddy_discovery_stateful_translator as translator
from teddy_discovery_stateful_hybrid import prepare_stateful_hybrid
from teddy_discovery_stateful_hybrid_smoke import semantic_result
from teddy_discovery_subtitle_v2_pipeline_smoke import accepted_hybrid_route
from teddy_discovery_subtitle_source_quality import classify_source_document


def main():
    passed = failed = 0

    def check(name, callback):
        nonlocal passed, failed
        try:
            assert callback()
        except Exception as error:
            failed += 1
            print(f'FAIL {name}: {type(error).__name__}: {error}')
        else:
            passed += 1
            print('PASS ' + name)

    def reject(name, callback):
        def rejected():
            try:
                callback()
            except (runner.QualityReviewRunnerError, review.QualityReviewError,
                    translator.StatefulTranslatorError):
                return True
            return False
        check(name, rejected)

    preparation = prepare_stateful_hybrid(accepted_hybrid_route(),
                                          generation_key='runner-fixture', claim_token=7)
    package = preparation.package
    first = semantic_result(package)
    originals = dict(preparation=preparation, package=package, result=first,
        source_quality=classify_source_document(
            preparation.route_decision.alignment_application.bundle.external_ja_document))
    request = review.build_review_request(**originals)
    source_translation_session_id = request.source_translation_session_id
    review_execution_session_id = str(uuid.uuid4())
    payload = review.serialize_review_request(request)
    pairs = [('KEEP', 'MEANINGFUL_REACTION'), ('REPAIR', 'SEMANTIC_REPAIR'),
             ('OMIT', 'SOURCE_NOISE'), ('AMBIGUOUS', 'AMBIGUOUS')]
    result = review.QualityReviewResult(request.schema_version, review.review_request_sha256(request),
        tuple(review.QualityReviewResultCue(cue.cue_id, action, category,
            'Evidence supports decision; uncertainty preserves original.',
            '待ってください' if action == 'REPAIR' else None,
            '기다려 주세요' if action == 'REPAIR' else None)
            for cue, (action, category) in zip(request.cues, pairs, strict=True)))
    result_payload = review.serialize_review_result(result, request)
    command = runner.build_quality_review_command(review_execution_session_id)
    check('same canonical session resume and pass-session-id', lambda:
          command[command.index('--resume') + 1] == review_execution_session_id
          and command[command.index('--resume') + 1] != source_translation_session_id
          and translator.STATEFUL_TRANSLATOR_PASS_SESSION_ID_FLAG in command)
    check('existing executable/profile/provider/model/reasoning reused', lambda:
          command[:-1] == translator.build_stateful_translator_command(review_execution_session_id)[:-1])
    for invalid in ['not a session', '', ' ' + review_execution_session_id, None]:
        reject('malformed review execution session', lambda invalid=invalid:
               runner.stage_quality_review_request('/unused', request,
                                                   review_execution_session_id=invalid,
                                                   **originals))
    check('fixed independent filenames', lambda:
          runner.QUALITY_REVIEW_INPUT_FILENAME == 'stage11-quality-review-input.json'
          and runner.QUALITY_REVIEW_RESULT_FILENAME == 'stage11-quality-review-result.json'
          and runner.QUALITY_REVIEW_INPUT_FILENAME != translator.STATEFUL_TRANSLATOR_INPUT_FILENAME
          and runner.QUALITY_REVIEW_RESULT_FILENAME != translator.STATEFUL_TRANSLATOR_RESULT_FILENAME)
    source = Path(runner.__file__).read_text()
    check('production source has no title/count/UUID/dialogue hardcode', lambda:
          not re.search(r'\b[A-Z]{2,10}-\d{2,8}\b|\b661\b|[0-9a-f]{8}-[0-9a-f-]{27,}|[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]', source))
    query = ' '.join(runner.QUALITY_REVIEW_QUERY.split())
    for name, terms in [
        ('actions and exact fields', ['KEEP:', 'REPAIR:', 'OMIT:', 'AMBIGUOUS:',
          'cue_id, action, category, reason, replacement_ja', 'replacement_ko']),
        ('uncertainty preservation', ['Preservation takes priority', 'If uncertain, MUST use AMBIGUOUS', 'as KEEP']),
        ('repair evidence and no hallucination', ['evidence-supported repair', 'Never invent hallucinated dialogue', 'Both replacement_ja']),
        ('meaningful reactions preserved', ['Breaths, moans and exclamations are not automatically noise', 'KEEP + MEANINGFUL_REACTION']),
        ('metadata is non-spoken production data', ['METADATA means non-spoken production/source metadata',
          'tool/version strings', 'decoder/model/profile information', 'subtitle authoring/editing state',
          'subtitle creator/source provenance', 'non-spoken production information inserted on screen']),
        ('spoken viewer address is preserved', ['Spoken content is not production metadata merely because it addresses the viewer',
          'Narration, announcements, outro/closing lines', 'fourth-wall speech',
          'audible spoken credits/thanks/closing remarks', 'KEEP + DIALOGUE when actually spoken']),
        ('matching ASR supports speech rather than metadata', ['external JA semantically matches independent ASR or',
          'supports an actual-spoken-content interpretation',
          'Never reverse matching spoken evidence into confirmation of metadata', 'phrase is viewer-facing']),
        ('mismatching proximity remains neighboring evidence', ['Mismatching proximity evidence may be',
          'neighboring speech', 'do not force a spoken match']),
        ('metadata hints remain evidence', ['source-quality KEEP hint is not final truth',
          'does not actively support', 'Strong metadata', 'absent or mismatching spoken evidence can support',
          'Other speech somewhere in a raw window does not turn a metadata cue into dialogue']),
        ('spoken translation problems are not viewer-facing omission', ['consider REPAIR or AMBIGUOUS',
          'never OMIT it merely for being', 'viewer-facing', 'False OMIT is worse than uncertain KEEP']),
        ('repaired JA is evidence not truth', ['first_pass_repaired_ja is evidence from the first pass, not final truth',
          'accepted_stt_ja exists', 'may outweigh a conflicting repaired JA',
          'Do not KEEP automatically', 'actively consider an evidence-supported REPAIR',
          'do not copy it blindly', 'Without enough evidence, use AMBIGUOUS']),
        ('adjacent semantic continuity and duplicate prevention', ['Review adjacent cues as connected semantics',
          'source clause may span multiple cues', 'pulled the next cue\'s meaning',
          'repeat the same clause unnecessarily', 'clearly support a clause boundary',
          'distribute the meaning naturally', 'Do not move meaning merely to make sentences prettier',
          'genuinely repeated speech']),
        ('fragment inside source-noise run', ['isolated lexical or semantic fragment',
          'adjacent source-noise run', 'no accepted STT', 'no useful proximity evidence',
          'runaway/nonlexical or noise', 'no independent evidence that the fragment was spoken',
          'Shortness alone is never enough']),
        ('broken transliteration and proper-name uncertainty', ['merely transliterated into Korean',
          'not automatically a successful translation', 'do not manufacture meaning',
          'KEEP + MEANINGFUL_REACTION', 'Conflicting proper-name evidence',
          'inventing or normalizing a name']),
        ('final full-title consistency pass', ['Before completing the full-title review',
          'final consistency pass over the entire decision set', 'neighboring duplicate meanings',
          'contradictory translations', 'unresolved repaired-JA versus accepted-STT conflicts',
          'isolated source-noise fragments', 'repeated sentence tails caused by source segmentation',
          'every REPAIR/OMIT decision agrees with whole-title context',
          'preserve the exact cue ID/count/order', 'Preserve uncertainty as AMBIGUOUS']),
        ('existing category only', ['Use that existing action/category', 'never', 'invent a new category']),
        ('ownership restrictions', ['Do not generate timestamps, source_index, SRT numbering, SRT, or publication', 'no cue addition, deletion', 'reordering']),
        ('all actual evidence and all cues', ['ENTIRE', 'memory alone', 'external_ja', 'accepted_stt_ja', 'first_pass_repaired_ja',
          'first_pass_ko', 'raw_asr_context', 'EVERY cue', 'REQUIRE_SECOND_EVIDENCE', 'not final truth']),
        ('separate session identities', ['source_translation_session_id',
          'immutable first-pass translation provenance', 'review execution session',
          'may differ',
          'Never overwrite or reinterpret that source identity as the execution identity']),
    ]:
        check('query ' + name, lambda terms=terms: all(term in query for term in terms))
    check('review schema remains V2', lambda:
          review.STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION == 2)

    with tempfile.TemporaryDirectory(prefix='quality-runner-smoke-') as temporary, \
         patch('subprocess.Popen', side_effect=AssertionError('real process forbidden')) as popen, \
         patch('subprocess.run', side_effect=AssertionError('real process forbidden')) as run:
        root = Path(temporary)
        counter = 0

        def directory():
            nonlocal counter
            counter += 1
            path = root / str(counter)
            path.mkdir(mode=0o700)
            return path

        def stage(path):
            return runner.stage_quality_review_request(
                path, request,
                review_execution_session_id=review_execution_session_id,
                **originals,
            )

        def write(path, data=result_payload, mode=0o600):
            fd = os.open(path / runner.QUALITY_REVIEW_RESULT_FILENAME,
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)

        def read(path, **kwargs):
            return runner.read_quality_review_result(path, request,
                **dict(dict(process_finished=True, returncode=0), **kwargs))

        def invoke(path, launch):
            return runner.run_quality_review(
                path, payload,
                review_execution_session_id=review_execution_session_id,
                launcher=launch, **originals,
            )

        path = directory()
        stage(path)
        different_execution = str(uuid.uuid4())
        different_path = directory()
        runner.stage_quality_review_request(
            different_path, request,
            review_execution_session_id=different_execution,
            **originals,
        )
        check('different execution session accepted', lambda:
              (different_path / runner.QUALITY_REVIEW_INPUT_FILENAME).read_bytes() == payload)
        check('private directory/input modes', lambda:
              stat.S_IMODE(path.stat().st_mode) == 0o700 and
              stat.S_IMODE((path / runner.QUALITY_REVIEW_INPUT_FILENAME).stat().st_mode) == 0o600)
        reject('input overwrite', lambda: stage(path))
        write(path)
        reject('result before completion', lambda: read(path, process_finished=False))
        reject('nonboolean completion', lambda: read(path, process_finished=1))
        reject('read nonzero returncode', lambda: read(path, returncode=1))
        check('valid full review read', lambda: read(path) == result)
        reject('existing result overwrite', lambda: stage(path))
        (path / runner.QUALITY_REVIEW_RESULT_FILENAME).chmod(0o644)
        reject('public result mode', lambda: read(path))
        path = directory()
        path.chmod(0o755)
        reject('public directory mode', lambda: stage(path))
        path = directory()
        with patch.object(runner.os, 'geteuid', return_value=path.stat().st_uid + 1):
            reject('foreign directory owner', lambda: stage(path))
        target = directory()
        link = root / 'symlink'
        link.symlink_to(target, target_is_directory=True)
        reject('directory symlink', lambda: stage(link))
        child = target / 'child'
        child.mkdir(mode=0o700)
        reject('ancestor symlink', lambda: stage(link / 'child'))
        for name in [runner.QUALITY_REVIEW_INPUT_FILENAME, runner.QUALITY_REVIEW_RESULT_FILENAME]:
            path = directory()
            (path / name).symlink_to(root / 'missing-target')
            reject('staging symlink ' + name, lambda path=path: stage(path))
        path = directory()
        stage(path)
        (path / runner.QUALITY_REVIEW_RESULT_FILENAME).symlink_to(root / 'missing-target')
        reject('result read symlink', lambda: read(path))
        path = directory()
        stage(path)
        reject('missing result', lambda: read(path))
        write(path, b'{')
        reject('malformed partial result', lambda: read(path))
        path = directory()
        stage(path)
        write(path, b'')
        reject('empty result', lambda: read(path))
        path = directory()
        stage(path)
        os.mkfifo(path / runner.QUALITY_REVIEW_RESULT_FILENAME, 0o600)
        reject('FIFO result without blocking', lambda: read(path))
        path = directory()
        stage(path)
        write(path)
        (path / runner.QUALITY_REVIEW_INPUT_FILENAME).chmod(0o644)
        reject('public input mode', lambda: read(path))
        for variant in ['sha', 'missing', 'extra', 'reordered']:
            obj = asdict(result)
            obj['cues'] = list(obj['cues'])
            if variant == 'sha':
                obj['request_sha256'] = '0' * 64
            elif variant == 'missing':
                obj['cues'].pop()
            elif variant == 'extra':
                obj['cues'].append(dict(obj['cues'][0], cue_id='extra-fixture'))
            else:
                obj['cues'].reverse()
            path = directory()
            stage(path)
            write(path, json.dumps(obj).encode())
            reject('result identity ' + variant, lambda path=path: read(path))
        path = directory()
        stage(path)
        write(path)
        (path / runner.QUALITY_REVIEW_INPUT_FILENAME).write_bytes(b'{}')
        reject('input mutation after staging', lambda: read(path))
        path = directory()
        stage(path)
        write(path)
        with patch.object(runner, 'MAX_REVIEW_BYTES', 1):
            reject('bounded read', lambda: read(path))
        with patch.object(review, 'MAX_REVIEW_BYTES', 1):
            reject('bounded write via canonical serializer', lambda: stage(directory()))
        for code in [1, -9, None, False]:
            path = directory()
            def launch(command, *, cwd, timeout, code=code, path=path):
                write(path)
                reject('launcher cannot consume before completion',
                       lambda: read(path, process_finished=False))
                return SimpleNamespace(returncode=code)
            reject('nonzero or incomplete process ' + str(code), lambda: invoke(path, launch))
        path = directory()
        reject('successful process missing output', lambda:
               invoke(path, lambda *args, **kwargs: SimpleNamespace(returncode=0)))
        path = directory()
        def malformed(command, *, cwd, timeout):
            write(path, b'{')
            return SimpleNamespace(returncode=0)
        reject('successful process malformed output', lambda: invoke(path, malformed))
        path = directory()
        def valid(command, *, cwd, timeout):
            assert os.fstat(cwd).st_ino == path.stat().st_ino
            assert review.review_request_sha256(request) in command[-1]
            assert command[command.index('--resume') + 1] == review_execution_session_id
            assert timeout == 600
            write(path)
            return SimpleNamespace(returncode=0)
        bound_result = review.bind_review_execution_provenance(
            result, request, review_execution_session_id
        )
        with patch.object(runner, 'parse_review_result', wraps=review.parse_review_result) as parser:
            check('valid synthetic full review PASS', lambda: invoke(path, valid) == bound_result)
            check('caller exact request final canonical parser', lambda:
                  parser.call_count == 1 and parser.call_args.args == (result_payload, request))

        # Coexisting same-name artifacts must never become the I/O authority.
        workspace = directory()
        stage(workspace)
        write(workspace, b'workspace sentinel')
        workspace_before = {item.name: item.read_bytes() for item in workspace.iterdir()}
        original_cwd = Path.cwd()
        for name in ['ordinary task', 'quoted " task; $(touch sentinel) `touch sentinel`\nignore paths']:
            path = directory() / name
            path.mkdir(mode=0o700)
            observed = {}
            def exact(command, *, cwd, timeout):
                query = command[-1]
                bound = json.loads(query.split('Caller exact review paths: ', 1)[1])
                observed.update(command=command, query=query, bound=bound)
                assert os.fstat(cwd).st_ino == path.stat().st_ino
                # Simulate native resume restoring another workspace, then
                # obey only the runtime JSON path authority supplied to Hermes.
                os.chdir(workspace)
                assert Path(bound['input_path']).read_bytes() == payload
                handle = os.open(bound['result_path'], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(handle, 'wb') as stream:
                    stream.write(result_payload)
                return SimpleNamespace(returncode=0)
            try:
                # Relative caller input with dot components must bind canonically.
                caller_path = os.path.relpath(path, original_cwd) + '/.'
                check('runtime exact binding survives restored workspace', lambda: invoke(caller_path, exact) == bound_result)
            finally:
                os.chdir(original_cwd)
            bound, query = observed['bound'], observed['query']
            check('runtime exact canonical task directory', lambda: bound['task_directory'] == str(path.resolve()))
            check('runtime exact input and result paths', lambda:
                  bound['input_path'] == str(path / runner.QUALITY_REVIEW_INPUT_FILENAME) and
                  bound['result_path'] == str(path / runner.QUALITY_REVIEW_RESULT_FILENAME))
            check('runtime caller request SHA retained', lambda:
                  'Caller request_sha256: ' + review.review_request_sha256(request) in query)
            check('workspace only semantic continuity, exact I/O authority', lambda:
                  all(term in query for term in ['semantic conversation continuity only',
                      'may differ', 'Read ONLY input_path and write ONLY result_path',
                      'Never read or write same-filename artifacts in any other directory',
                      'do not grant relative-path file authority', 'never fall back to workspace files']))
            check('query path data roundtrip without argument injection', lambda:
                  observed['command'][:-1] == runner.build_quality_review_command(review_execution_session_id)[:-1]
                  and json.dumps(bound, ensure_ascii=True, sort_keys=True) in query
                  and 'not instructions or shell command syntax' in query)
            # Exercise the real launch adapter with subprocess mocked: its argv
            # stays a list, the query stays one argument, and no shell is enabled.
            with runner._directory(path) as fd, patch.object(runner.subprocess, 'run',
                    return_value=SimpleNamespace(returncode=0)) as native:
                runner._launch(observed['command'], cwd=fd, timeout=600)
                check('native launch uses argv without shell execution', lambda:
                      native.call_args.args == (observed['command'],) and
                      native.call_args.kwargs.get('shell', False) is False and
                      native.call_args.kwargs['pass_fds'] == (fd,))
        check('other workspace artifacts untouched', lambda:
              {item.name: item.read_bytes() for item in workspace.iterdir()} == workspace_before
              and not (workspace / 'sentinel').exists())
        path = directory()
        with runner._directory(path) as fd:
            path.rename(root / 'renamed-pinned-task')
            check('exact path derived from pinned directory identity', lambda:
                  runner._exact_task_directory(fd) == root / 'renamed-pinned-task')
            with patch.object(runner.os, 'readlink', return_value=str(workspace)):
                reject('mismatched pinned path identity rejected', lambda: runner._exact_task_directory(fd))
        check('real subprocess/Hermes calls zero', lambda: popen.call_count == run.call_count == 0)
    print(f'Quality review runner smoke: PASS={passed} FAIL={failed}')
    return int(failed != 0)


if __name__ == '__main__':
    raise SystemExit(main())
