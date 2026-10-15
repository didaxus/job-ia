"""Contract tests for ChatGPT-authenticated Codex CLI (no account needed in CI)."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import codex_provider as provider

PROFILE = {
    "summary": "Producción de recursos de aprendizaje",
    "evidence": "Creé y actualicé cursos utilizando Moodle y herramientas de autor.",
    "skills": ["Moodle", "Diseño de contenidos"],
    "roles": ["Instructional Designer"],
}
JOB = {
    "title": "Instructional Designer",
    "company": "Employer",
    "location": "Remote LATAM",
    "description": "Experience using learning management systems (LMS) required.",
}
RESULT = {
    "match_score": 77,
    "recommendation": "consider",
    "genuine_gaps": "No se demuestra administración avanzada.",
    "transferable_strengths": "Uso de Moodle respaldado por experiencia.",
    "risk_factors": "Validar disponibilidad para Colombia.",
    "skill_inferences": [{
        "required_skill": "LMS",
        "relation": "inferred",
        "evidence_text": "Moodle",
        "rationale": "Moodle es un LMS; esto respalda su uso, no su administración.",
    }],
}

class CodexCliTests(unittest.TestCase):
    def test_explicitly_chatgpt_not_api_key(self):
        with patch.object(provider.subprocess, "run", return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Logged in using ChatGPT", stderr="")):
            self.assertEqual(provider.login_status(), "connected")
        with patch.object(provider.subprocess, "run", return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Logged in using an API key", stderr="")):
            self.assertEqual(provider.login_status(), "wrong_auth_method")

    def test_no_service_secrets_in_codex_environment(self):
        with patch.dict(os.environ, {"PGPASSWORD": "private-db-password",
             "SMTP_PASSWORD":"private-smtp-password","OPENAI_API_KEY":"unused",
             "ANTHROPIC_API_KEY":"unused", "CODEX_API_KEY":"unused"}):
            clean = provider.safe_environment()
        for key in ("PGPASSWORD","SMTP_PASSWORD","OPENAI_API_KEY",
                    "ANTHROPIC_API_KEY","CODEX_API_KEY"):
            self.assertNotIn(key, clean)
        self.assertEqual(clean["CODEX_HOME"], provider.CODEX_HOME)

    def test_inference_based_on_literal_moodle_is_accepted(self):
        validated = provider.validate_evaluation(RESULT, PROFILE)
        self.assertEqual(validated["skill_inferences"][0]["relation"], "inferred")
        self.assertEqual(validated["match_score"], 77)

    def test_unsupported_claims_cannot_invent_evidence(self):
        tampered = json.loads(json.dumps(RESULT))
        tampered["skill_inferences"][0]["evidence_text"] = "Certified LMS system administrator"
        with self.assertRaises(provider.CodexEvaluationError):
            provider.validate_evaluation(tampered, PROFILE)

    def test_fake_exec_uses_read_only_ephemeral_schema(self):
        def fake_run(argv, **kwargs):
            self.assertEqual(argv[:2], ["codex", "exec"])
            self.assertIn("--sandbox", argv)
            self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
            self.assertIn("--ephemeral", argv)
            self.assertIn("--output-schema", argv)
            self.assertNotIn("OPENAI_API_KEY", kwargs["env"])
            self.assertNotIn("PGPASSWORD", kwargs["env"])
            self.assertIn("Moodle", kwargs["input"])
            self.assertIn("UNTRUSTED DATA", kwargs["input"])
            Path(argv[argv.index("--output-last-message") + 1]).write_text(
                json.dumps(RESULT), encoding="utf-8")
            return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")
        with patch.object(provider, "login_status", return_value="connected"), \
             patch.object(provider.subprocess, "run", side_effect=fake_run), \
             patch.object(provider, "SCHEMA", ROOT / "config/codex_fit_schema.json"), \
             patch.object(provider, "CODEX_BIN", "codex"):
            evaluation = provider.evaluate(PROFILE, JOB)
        self.assertEqual(evaluation["match_score"], 77)

    def test_quota_error_is_classified_without_leaking_details(self):
        self.assertEqual(provider._safe_error("Rate limit reached by user"), "quota_exhausted")
        self.assertEqual(provider._safe_error("401 Unauthorized"), "login_required")
        self.assertEqual(provider._safe_error("Password abc..."), "codex_run_failed")

    def test_schema_is_valid_json(self):
        doc = json.loads((ROOT / "config/codex_fit_schema.json").read_text())
        self.assertIn("skill_inferences", doc["required"])
        self.assertFalse(doc["additionalProperties"])

if __name__ == "__main__":
    unittest.main()
