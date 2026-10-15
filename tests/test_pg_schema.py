"""Offline PostgreSQL contract checks; live database checks run separately."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class PostgresContractTests(unittest.TestCase):
    def test_separate_profiles_one_global_job_application(self):
        sql = (ROOT / "db/schema.sql").read_text(encoding="utf-8")
        self.assertIn("id IN ('professional', 'assistant')", sql)
        self.assertIn("PRIMARY KEY (job_url, profile_id)", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS application_history", sql)
        self.assertIn("job_url text PRIMARY KEY REFERENCES jobs(url)", sql)
        self.assertIn("ON CONFLICT (id) DO NOTHING", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS source_fetches", sql)

    def test_dashboard_write_endpoints_fail_closed_without_auth(self):
        auth = (ROOT / "web-overrides/proxy.ts").read_text()
        self.assertIn("createRemoteJWKSet", auth)
        self.assertIn("jwtVerify", auth)
        self.assertIn("algorithms: [\"RS256\"]", auth)
        self.assertIn("CF_ACCESS_AUD", auth)
        self.assertIn("status: 503", auth)
        self.assertIn("status: 401", auth)
        self.assertNotIn("CF_ACCESS_DEV_BYPASS", auth)

    def test_original_sqlite_not_deleted_or_replaced(self):
        worker = (ROOT / "app/profile_worker.py").read_text()
        self.assertIn("mode=ro", worker)
        self.assertIn("ON CONFLICT (job_url) DO NOTHING", worker)
        self.assertIn("4 requests/24h", worker)

    def test_upload_is_private_and_limited(self):
        source = (ROOT / "web-overrides/app/api/cv/route.ts").read_text()
        self.assertIn("5 * 1024 * 1024", source)
        self.assertIn("%PDF-", source)
        self.assertIn("createHash", source)
        self.assertIn("knownProfile", source)

if __name__ == "__main__":
    unittest.main()
