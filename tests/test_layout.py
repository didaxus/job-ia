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
        for service in cfg["services"].values():
            build=service["build"]
            self.assertTrue((ROOT/build["context"]/build["dockerfile"]).is_file())
    def test_worker_copy_sources(self):
        d=(ROOT/"Dockerfile.worker").read_text()
        self.assertIn("COPY app/",d)
        self.assertIn("COPY config/",d)
    def test_secret_rules(self):
        ignore=(ROOT/".gitignore").read_text()
        self.assertIn("private/*.yaml",ignore)
        self.assertFalse((ROOT/".env").exists())

if __name__=="__main__":
    unittest.main()
