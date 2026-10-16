"""Integration tests: enable with JOBPILOT_TEST_POSTGRES=1 against disposable PG."""
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

@unittest.skipUnless(os.environ.get("JOBPILOT_TEST_POSTGRES") == "1",
                     "requires disposable PostgreSQL test service")
class PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import profile_worker as worker
        cls.worker = worker
        worker.initialize()
        with worker.pg_connect() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM search_profiles ORDER BY id").fetchall()]
            assert ids == ["assistant", "professional"], ids

    def test_codex_device_login_is_ephemeral(self):
        import codex_device_login as auth
        worker = self.worker
        with worker.pg_connect() as db:
            db.execute("DELETE FROM codex_device_logins")
            request = db.execute("""
                INSERT INTO codex_device_logins DEFAULT VALUES RETURNING id
            """).fetchone()[0]
            db.commit()
        self.assertEqual(auth.request_login(worker.pg_connect), request)
        auth.update_request(worker.pg_connect, request, "awaiting_user",
                            code="ABCD-1234")
        with worker.pg_connect() as db:
            value = db.execute("""
                SELECT state,user_code,verification_url FROM codex_device_logins
                WHERE id=%s
            """, (request,)).fetchone()
            self.assertEqual(value, ("awaiting_user", "ABCD-1234",
                                     "https://auth.openai.com/codex/device"))
        auth.update_request(worker.pg_connect, request, "connected")
        worker.write_heartbeat()
        with worker.pg_connect() as db:
            state = db.execute("""
                SELECT state,user_code,verification_url FROM codex_device_logins
                WHERE id=%s
            """, (request,)).fetchone()
            self.assertEqual(state, ("connected", None, None))
            heartbeat = db.execute("""
                SELECT state FROM worker_heartbeat WHERE worker_id='pipeline'
            """).fetchone()
            self.assertEqual(heartbeat, ("active",))
            db.execute("DELETE FROM codex_device_logins WHERE id=%s", (request,))
            db.commit()

    def test_idempotent_legacy_import_and_single_history(self):
        worker = self.worker
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "legacy.sqlite3"
            db = sqlite3.connect(path)
            db.executescript("""
                CREATE TABLE job_details
                    (url TEXT PRIMARY KEY,company TEXT,title TEXT,
                     location TEXT,description TEXT,source TEXT,
                     posted_at TEXT,passed_filters INTEGER);
                CREATE TABLE user_status (url TEXT PRIMARY KEY,my_status TEXT,notes TEXT);
            """)
            url = "https://job-boards.greenhouse.io/gitlab/jobs/987654321"
            db.execute("INSERT INTO job_details VALUES (?,?,?,?,?,?,?,?)",
                       (url, "GitLab", "Instructional Designer", "Remote Latin America",
                        "Training resources", "greenhouse", "2026-10-15", 0))
            db.execute("INSERT INTO user_status VALUES (?,?,?)",
                       (url, "applied", "Imported from old board; receipt not verified"))
            db.commit()
            db.close()
            old = worker.SOURCE_DB
            worker.SOURCE_DB = path
            verified = ([{"name":"GitLab","slug":"gitlab","ats":"greenhouse"}],
                        {"gitlab":{"987654321"}})
            try:
                with patch.object(worker, "official_boards", return_value=verified):
                    self.assertEqual(worker.sync_once(), 1)
                    self.assertEqual(worker.sync_once(), 1)
                    with worker.pg_connect() as conn:
                        self.assertEqual(conn.execute("SELECT count(*) FROM jobs WHERE url=%s", (url,)).fetchone()[0], 1)
                        decisions = conn.execute(
                            "SELECT profile_id,decision FROM profile_matches WHERE job_url=%s ORDER BY profile_id",
                            (url,)).fetchall()
                        self.assertEqual(len(decisions), 2)
                        self.assertEqual(decisions[0][0], "assistant")
                        self.assertEqual(decisions[0][1], "TITLE_NOT_RELEVANT")
                        self.assertEqual(decisions[1][0], "professional")
                        self.assertEqual(decisions[1][1], "AWAITING_VERIFIED_EVIDENCE")
                        history = conn.execute(
                            "SELECT status,origin FROM application_history WHERE job_url=%s", (url,)
                        ).fetchone()
                        self.assertEqual(history, ("applied_reported", "legacy_sqlite_unverified"))
                        conn.execute(
                            "UPDATE application_history SET status='interview' WHERE job_url=%s", (url,)
                        )
                        conn.commit()
                    worker.sync_once()
                    with worker.pg_connect() as conn:
                        self.assertEqual(conn.execute(
                            "SELECT status FROM application_history WHERE job_url=%s",
                            (url,)).fetchone()[0], "interview")
            finally:
                worker.SOURCE_DB = old
                with worker.pg_connect() as conn:
                    conn.execute("DELETE FROM jobs WHERE url=%s", (url,))
                    conn.commit()

if __name__ == "__main__":
    unittest.main()
