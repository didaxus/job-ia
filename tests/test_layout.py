"""Offline checks for fresh-clone deployment."""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]

class LayoutTests(unittest.TestCase):
    def test_build_files(self):
        for p in ["Dockerfile.worker","Dockerfile.dashboard","app/jobpilot.py",
                  "config/filters.yaml","config/companies.yaml","config/aggregators.yaml",
                  "config/employers.yaml","private/facts.example.yaml",
                  "private/profile.example.yaml"]:
            with self.subTest(path=p):
                self.assertTrue((ROOT/p).is_file())
    def test_compose_defaults(self):
        cfg=yaml.safe_load((ROOT/"compose.yaml").read_text())
        self.assertNotIn("env_file",cfg["services"]["pipeline"])
        self.assertEqual(cfg["services"]["pipeline"]["environment"]["AUTO_EMAIL"],"${AUTO_EMAIL:-false}")
        self.assertEqual(cfg["services"]["dashboard"]["ports"],["127.0.0.1:13030:3000"])
        self.assertIn("postgres", cfg["services"])
        self.assertEqual(cfg["services"]["postgres"]["image"], "postgres:16-alpine")
        self.assertIn("jobpilot_postgres", cfg["volumes"])
        self.assertIn("service_healthy", str(cfg["services"]["dashboard"]["depends_on"]))
        for service in cfg["services"].values():
            if "build" not in service:
                continue
            build=service["build"]
            self.assertTrue((ROOT/build["context"]/build["dockerfile"]).is_file())
    def test_worker_copy_sources(self):
        d=(ROOT/"Dockerfile.worker").read_text()
        self.assertIn("COPY app/",d)
        self.assertIn("COPY config/",d)
    def test_postgres_private_and_cv_persistence(self):
        cfg=yaml.safe_load((ROOT/"compose.yaml").read_text())
        db=cfg["services"]["postgres"]
        self.assertNotIn("ports", db)
        self.assertNotIn("coolify", db.get("networks", []))
        self.assertIn("JOBPILOT_DB_PASSWORD", str(db["environment"]))
        dashboard=cfg["services"]["dashboard"]
        self.assertNotIn("CF_ACCESS_AUD", dashboard["environment"])
        self.assertIn("CODEX_HOME", cfg["services"]["pipeline"]["environment"])
        self.assertNotIn("CODEX_HOME", dashboard["environment"])
        self.assertIn("JOBPILOT_PRIVATE_DIR", dashboard["environment"])
    def test_secret_rules(self):
        ignore=(ROOT/".gitignore").read_text()
        self.assertIn("private/*.yaml",ignore)
        self.assertFalse((ROOT/".env").exists())

if __name__=="__main__":
    unittest.main()
