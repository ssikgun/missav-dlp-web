"""Offline smoke for the shared fresh review-session contract.

The fake database exposes the native SessionDB method shape; no SQLite or
Hermes process is opened here.  The native temporary-DB probe is run
separately against Hermes' own venv and schema.
"""

from pathlib import Path
from types import SimpleNamespace
import tempfile
import uuid

import teddy_discovery_stateful_quality_review as review
import teddy_discovery_stateful_quality_review_runner as runner
from teddy_discovery_stateful_hybrid import prepare_stateful_hybrid
from teddy_discovery_stateful_hybrid_smoke import semantic_result
from teddy_discovery_subtitle_v2_pipeline_smoke import accepted_hybrid_route
from teddy_discovery_subtitle_source_quality import classify_source_document
from teddy_discovery_quality_review_session import (
    QUALITY_REVIEW_SESSION_SOURCE,
    QualityReviewSessionError,
    ensure_fresh_review_execution_session,
    new_review_execution_session_id,
)


class FakeNativeSessionDB:
    """Minimal native SessionDB-shaped test double."""

    def __init__(self):
        self.rows = {}
        self.messages = {}
        self.create_calls = []
        self.get_calls = []

    def get_session(self, session_id):
        self.get_calls.append(session_id)
        return self.rows.get(session_id)

    def create_session(self, *, session_id, source, profile_name):
        self.create_calls.append(
            (session_id, source, profile_name)
        )
        self.rows.setdefault(
            session_id,
            {
                "id": session_id,
                "source": source,
                "profile_name": profile_name,
                "parent_session_id": None,
            },
        )
        return session_id

    def get_messages(self, session_id, *, include_inactive=False):
        del include_inactive
        return list(self.messages.get(session_id, ()))


def _assert_raises(callback):
    try:
        callback()
    except QualityReviewSessionError:
        return
    raise AssertionError("expected fail-closed session error")


def _hybrid_fixture():
    preparation = prepare_stateful_hybrid(
        accepted_hybrid_route(), generation_key="fresh-session-smoke", claim_token=7
    )
    package = preparation.package
    first_pass = semantic_result(package)
    request = review.build_review_request(
        preparation=preparation,
        package=package,
        result=first_pass,
        source_quality=classify_source_document(
            preparation.route_decision.alignment_application.bundle.external_ja_document
        ),
    )
    return (
        request,
        review.serialize_review_request(request),
        {
            "preparation": preparation,
            "package": package,
            "result": first_pass,
            "source_quality": classify_source_document(
                preparation.route_decision.alignment_application.bundle.external_ja_document
            ),
        },
    )


def main():
    passed = failed = 0

    def check(name, callback):
        nonlocal passed, failed
        try:
            callback()
        except Exception as error:
            failed += 1
            print(f"FAIL {name}: {type(error).__name__}: {error}")
        else:
            passed += 1
            print("PASS " + name)

    session_id = new_review_execution_session_id()
    check(
        "uuid.uuid4 canonical generation",
        lambda: str(uuid.UUID(session_id)) == session_id,
    )
    db = FakeNativeSessionDB()
    created = ensure_fresh_review_execution_session(
        db,
        session_id,
        expected_profile_name="subtitle-translator",
    )
    check(
        "native-shaped exact-ID creation",
        lambda: (
            created.review_execution_session_id == session_id
            and db.create_calls == [
                (session_id, QUALITY_REVIEW_SESSION_SOURCE, "subtitle-translator")
            ]
        ),
    )
    check(
        "empty history and ownership read-back",
        lambda: (
            db.rows[session_id]["id"] == session_id
            and db.rows[session_id]["profile_name"] == "subtitle-translator"
            and db.get_messages(session_id, include_inactive=True) == []
        ),
    )
    create_count = len(db.create_calls)
    _assert_raises(
        lambda: ensure_fresh_review_execution_session(
            db,
            session_id,
            expected_profile_name="subtitle-translator",
        )
    )
    check(
        "duplicate existing ID fails closed",
        lambda: len(db.create_calls) == create_count,
    )
    malformed_db = FakeNativeSessionDB()
    _assert_raises(
        lambda: ensure_fresh_review_execution_session(
            malformed_db,
            session_id.upper(),
            expected_profile_name="subtitle-translator",
        )
    )
    check(
        "malformed canonical ID fails closed",
        lambda: malformed_db.create_calls == [] and malformed_db.get_calls == [],
    )
    nonempty_db = FakeNativeSessionDB()
    nonempty_db.messages[session_id] = [{"role": "user", "content": "old"}]
    _assert_raises(
        lambda: ensure_fresh_review_execution_session(
            nonempty_db,
            session_id,
            expected_profile_name="subtitle-translator",
        )
    )
    check("non-empty fresh row fails closed", lambda: True)
    helper_source = Path(__file__).with_name(
        "teddy_discovery_quality_review_session.py"
    ).read_text(encoding="utf-8")
    check(
        "helper has no raw SQL schema writes",
        lambda: "INSERT INTO" not in helper_source
        and "UPDATE sessions" not in helper_source
        and "sqlite3" not in helper_source,
    )

    request, payload, originals = _hybrid_fixture()
    execution_id = new_review_execution_session_id()
    hybrid_db = FakeNativeSessionDB()
    result = review.QualityReviewResult(
        request.schema_version,
        review.review_request_sha256(request),
        tuple(
            review.QualityReviewResultCue(
                cue.cue_id,
                "KEEP",
                "DIALOGUE",
                "synthetic fresh-session smoke evidence",
                None,
                None,
            )
            for cue in request.cues
        ),
    )
    result_payload = review.serialize_review_result(result, request)
    with tempfile.TemporaryDirectory(prefix="quality-fresh-session-smoke-") as temporary:
        task = Path(temporary)
        task.chmod(0o700)
        launch_observed = {}

        def launch(command, *, cwd, timeout):
            del cwd, timeout
            launch_observed["session_id"] = command[command.index("--resume") + 1]
            target = task / runner.QUALITY_REVIEW_RESULT_FILENAME
            target.write_bytes(result_payload)
            target.chmod(0o600)
            return SimpleNamespace(returncode=0)

        reviewed = runner.run_quality_review(
            task,
            payload,
            review_execution_session_id=execution_id,
            fresh_review_session=True,
            fresh_session_db=hybrid_db,
            expected_profile_name="subtitle-translator",
            launcher=launch,
            **originals,
        )
    check(
        "Hybrid fresh create then resume same exact ID",
        lambda: (
            launch_observed["session_id"] == execution_id
            and hybrid_db.create_calls[0][0] == execution_id
            and reviewed.review_execution_session_id == execution_id
            and reviewed.source_translation_session_id
            == request.source_translation_session_id
            and reviewed.source_translation_session_id != execution_id
        ),
    )

    if failed:
        raise SystemExit(f"QUALITY_REVIEW_SESSION_SMOKE_FAIL={failed}/{passed + failed}")
    print(f"QUALITY_REVIEW_SESSION_SMOKE_PASS={passed}")


if __name__ == "__main__":
    main()
