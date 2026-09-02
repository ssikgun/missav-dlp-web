import hashlib
import sqlite3
import tempfile
from pathlib import Path

import teddy_duplicates
import teddy_ownership


def require(value, message):
    if not value:
        raise RuntimeError(message)


class Core:
    def __init__(self):
        self.tasks = {}
        self.jsonify = lambda payload: Response(payload)


class Response:
    def __init__(self, payload):
        self.payload = payload

    def get_json(self):
        return self.payload


def create_db(path):
    db = sqlite3.connect(path)
    db.execute(
        """
        CREATE TABLE holdings (
            dvd_id TEXT,
            parse_status TEXT NOT NULL,
            present INTEGER NOT NULL
        )
        """
    )
    db.executemany(
        "INSERT INTO holdings VALUES (?, ?, ?)",
        [
            ("ABC-123", "MATCHED", 1),
            ("ABSENT-1", "MATCHED", 0),
            ("ROUGH-2", "AMBIGUOUS", 1),
        ],
    )
    db.commit()
    db.close()


def body(result):
    response, status = result
    return status, response.get_json()


def main():
    with tempfile.TemporaryDirectory(prefix="teddy-ownership-") as temp:
        db_path = Path(temp) / "holdings.sqlite3"
        create_db(db_path)
        before = hashlib.sha256(db_path.read_bytes()).hexdigest()

        require(teddy_ownership.is_owned("ABC-123", db_path), "canonical owned row missed")
        require(not teddy_ownership.is_owned("ABSENT-1", db_path), "present=0 row counted as owned")
        require(not teddy_ownership.is_owned("ROUGH-2", db_path), "non-MATCHED row counted as owned")
        require(
            teddy_ownership.dvd_id_from_supported_url("https://missav.ws/ko/abc-123") == "ABC-123"
            and teddy_ownership.dvd_id_from_supported_url("https://123av.com/ko/v/abc-123") == "ABC-123"
            and teddy_ownership.dvd_id_from_supported_url("https://missav.ws.evil.example/ko/abc-123") is None,
            "supported URL boundary changed",
        )

        core = Core()
        created = []

        def creator():
            created.append("enqueue")
            return Response({"status": "success"}), 200

        def run(url):
            return body(teddy_duplicates.guarded_enqueue(core, url, creator))

        original = teddy_duplicates.teddy_ownership.is_owned

        def owned_with_test_db(dvd_id, db_path=None):
            return original(dvd_id, db_path=db_path or str(globals_db_path))

        globals_db_path = db_path
        teddy_duplicates.teddy_ownership.is_owned = owned_with_test_db
        try:
            created.clear()
            status, payload = run("https://missav.ws/ko/abc-123")
            require((status, payload["status"], created) == (409, "owned", []), "owned MissAV escaped")

            status, payload = run("https://123av.com/ko/v/abc-123")
            require((status, payload["status"], created) == (409, "owned", []), "owned 123AV escaped")

            status, payload = body(
                teddy_duplicates.guarded_enqueue_by_key(
                    core,
                    "ABC-123",
                    lambda task: task.get("dvd_id"),
                    creator,
                    ownership_dvd_id="ABC-123",
                    ownership_db_path=db_path,
                )
            )
            require((status, payload["status"], created) == (409, "owned", []), "owned Discovery DVD ID escaped")

            status, payload = run("https://missav.ws/ko/new-456")
            require(status == 200 and created == ["enqueue"], "unowned supported URL did not enqueue")

            created.clear()
            core.tasks = {"active": {"url": "https://missav.ws/ko/new-456", "status": "대기 중"}}
            status, payload = run("https://missav.live/en/new-456")
            require((status, payload["status"], created) == (409, "duplicate", []), "active duplicate escaped")

            core.tasks = {"active": {"url": "https://missav.live/en/abc-123", "status": "대기 중"}}
            status, payload = run("https://missav.ws/ko/abc-123")
            require((status, payload["status"], created) == (409, "owned", []), "owned must take priority over duplicate")

            for url in (
                "https://example.com/video/abc-123",
                "https://missav.ws.evil.example/ko/abc-123",
                "not a URL",
            ):
                core.tasks = {}
                created.clear()
                status, _ = run(url)
                require(status == 200 and created == ["enqueue"], "unsupported/malformed URL regressed: " + url)

            teddy_duplicates.teddy_ownership.is_owned = original
            core.tasks = {}
            created.clear()
            missing_path = Path(temp) / "missing.sqlite3"

            def unavailable(dvd_id, db_path=None):
                return original(dvd_id, db_path=missing_path)

            teddy_duplicates.teddy_ownership.is_owned = unavailable
            status, payload = run("https://missav.ws/ko/abc-123")
            require((status, payload["status"], created) == (503, "ownership_unavailable", []), "DB error did not fail closed")
        finally:
            teddy_duplicates.teddy_ownership.is_owned = original

        after = hashlib.sha256(db_path.read_bytes()).hexdigest()
        require(before == after, "ownership checks wrote the DB")
        print("TEDDY_OWNERSHIP_POLICY_SMOKE=PASS")
        print("TEDDY_OWNERSHIP_DB_WRITE_COUNT=0")


if __name__ == "__main__":
    main()
