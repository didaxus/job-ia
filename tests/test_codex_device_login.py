"""Codex device authorization bridge tests: synthetic output only, no account."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import codex_device_login as login


class DeviceLoginTests(unittest.TestCase):
    def test_official_device_code_and_ansi_colors(self):
        lines = [
            "\n",
            "1. Open this link in your browser and sign in to your account\n",
            "https://auth.openai.com/codex/device\n",
            "2. Enter this one-time code (expires in 15 minutes)\n",
            "\x1b[94mABCD-1234\x1b[0m\n",
        ]
        self.assertEqual(login.parse_device_output(lines), "ABCD-1234")

    def test_does_not_accept_random_text_prior_to_prompt(self):
        self.assertIsNone(login.parse_device_output([
            "ABCD-1234\n",
            "https://evil.example/test\n",
        ]))
        self.assertIsNone(login.parse_device_output([
            "2. Enter this one-time code (expires in 15 minutes)\n",
            "sk-live-THIS-IS-NOT-A-DEVICE-CODE\n",
        ]))

    def test_explicit_code_pattern(self):
        self.assertTrue(login.CODES.fullmatch("ABCD-1234"))
        self.assertFalse(login.CODES.fullmatch("../../auth.json"))
        self.assertFalse(login.CODES.fullmatch("https://evil.test"))

    def test_only_codex_cli_runs_in_isolated_worker(self):
        worker = (ROOT / "app/codex_device_login.py").read_text()
        self.assertIn('["login", "--device-auth"]', worker.replace("CODEX_BIN, ", ""))
        self.assertIn("env=safe_environment()", worker)
        self.assertIn("subprocess.DEVNULL", worker)
        self.assertNotIn("OPENAI_API_KEY", worker)
        self.assertNotIn("CF_ACCESS_AUD", worker)
        self.assertNotIn("auth.json", (ROOT / "db/schema.sql").read_text())
        compose = (ROOT / "compose.yaml").read_text()
        self.assertIn("Dockerfile.migrate", compose)
        self.assertIn("service_completed_successfully", compose)
        dashboard = compose.split("  dashboard:", 1)[1]
        self.assertNotIn("/opt/jobpilot-codex-home", dashboard)

    def test_device_user_code_not_an_oauth_token(self):
        api = (ROOT / "web-overrides/app/api/ai/connect/route.ts").read_text()
        self.assertIn("user_code", api)
        self.assertIn("expires_at", api)
        self.assertIn("rejectCrossOrigin", api)
        self.assertNotIn("refresh_token", api)
        self.assertNotIn("access_token", api)
        self.assertIn("CODEX_HOME", (ROOT / "app/profile_worker.py").read_text() +
                      (ROOT / "compose.yaml").read_text())


if __name__ == "__main__":
    unittest.main()
