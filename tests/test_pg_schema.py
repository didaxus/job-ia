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

    def test_codex_cli_account_isolated_from_dashboard(self):
        worker = (ROOT / "Dockerfile.worker").read_text()
        compose = (ROOT / "compose.yaml").read_text()
        self.assertIn("@openai/codex@0.162.1", worker)
        self.assertIn("CODEX_HOME: /opt/jobpilot-codex-home", compose)
        self.assertIn("JOBPILOT_CODEX_HOST_DIR", compose)
        self.assertNotIn("OPENAI_API_KEY", compose)
        self.assertNotIn("ANTHROPIC_API_KEY", compose)
        self.assertNotIn("CF_ACCESS_TEAM_DOMAIN", compose)
        self.assertNotIn("CF_ACCESS_AUD", compose)
        self.assertFalse((ROOT / "web-overrides/proxy.ts").exists())
        self.assertIn("ai_provider", (ROOT / "db/schema.sql").read_text())
        self.assertIn("ai_inferences jsonb", (ROOT / "db/schema.sql").read_text())
        self.assertIn("ai_runtime_status", (ROOT / "db/schema.sql").read_text())

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
