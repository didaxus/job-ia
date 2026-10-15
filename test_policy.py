"""Offline tests: python -m unittest discover -s tests -v"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("jobpilot", Path(__file__).resolve().parents[1] / "app" / "jobpilot.py")
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)

COMPANY = {"name": "GitLab", "slug": "gitlab", "ats": "greenhouse", "company_domain": "gitlab.com"}
URL = "https://job-boards.greenhouse.io/gitlab/jobs/123456"


class PolicyTests(unittest.TestCase):
    def test_exact_official_attribution(self):
        self.assertEqual(pilot.official_greenhouse_id(URL, COMPANY), "123456")
        self.assertIsNone(pilot.official_greenhouse_id("https://job-boards.greenhouse.io/fake/jobs/123456", COMPANY))
        self.assertIsNone(pilot.official_greenhouse_id("https://job-boards.greenhouse.io.evil.com/gitlab/jobs/123456", COMPANY))
        self.assertIsNone(pilot.official_greenhouse_id("http://job-boards.greenhouse.io/gitlab/jobs/123456", COMPANY))

    def test_colombian_eligibility(self):
        self.assertEqual(pilot.geographic_eligibility("Remote, Latin America", ""), "ELIGIBLE_LOCATION_SIGNAL")
        self.assertEqual(pilot.geographic_eligibility("Hybrid Bogota", ""), "ELIGIBLE_LOCATION_SIGNAL")
        self.assertEqual(pilot.geographic_eligibility("Remote", ""), "LOCATION_UNCLEAR")
        self.assertEqual(pilot.geographic_eligibility("Bogota", ""), "LOCATION_UNCLEAR")
        self.assertEqual(pilot.geographic_eligibility("Remote US", ""), "RESTRICTED_OTHER_COUNTRY")
        self.assertEqual(pilot.geographic_eligibility("Worldwide Remote", "Must reside in the United States"), "RESTRICTED_OTHER_COUNTRY")
        self.assertEqual(pilot.geographic_eligibility("Remote Latin America (Mexico only)", ""), "RESTRICTED_OTHER_COUNTRY")

    def test_scam_flags(self):
        self.assertTrue(pilot.suspicious_application_terms("Candidates need to pay an application fee"))
        self.assertFalse(pilot.suspicious_application_terms("Free application to design instructional courses"))

    def test_truthful_resume_derives_bullets_from_facts(self):
        facts = {"identity": {"name": "Test Candidate", "email": "person@domain.test", "location": "Bogota"},
                 "summary": "Verified summary", "skills": ["Articulate Rise"],
                 "experience": [{"title": "Designer", "company": "ABC", "dates": "2021-2024", "highlights": ["Built three learning modules", "Created training storyboards"]}],
                 "education": ["Degree in Education"]}
        resume, cover = pilot.markdown_docs(facts, {"company": "GitLab", "title": "Instructional Designer", "description": "training storyboards"})
        self.assertTrue(resume.startswith("# Test Candidate"))
        self.assertIn("Created training storyboards", resume)
        self.assertIn("Created training storyboards", cover)
        self.assertNotIn("increased learning by 50%", resume)

    def test_no_default_automatic_email(self):
        job = {"url": URL, "title": "Instructional Designer"}
        self.assertEqual(pilot.send_approved_email(job, COMPANY, (Path("/tmp/missing.pdf"), Path("/tmp/missing2.pdf")), {"identity": {"name": "Test"}}, []), "QUEUED_FOR_VERIFIED_BROWSER_ADAPTER")

    def test_verified_registry_is_not_enough_without_live_posting(self):
        job = {"company": "GitLab", "title": "Instructional Designer", "url": URL, "source": "greenhouse",
               "description": "remote learning design", "location": "Remote, Latin America", "match_score": 91}
        employers = {"gitlab": COMPANY}
        self.assertEqual(pilot.evaluate_job(job, employers, {"gitlab": set()}, 80)[0], "POSTING_NOT_LIVE")
        self.assertEqual(pilot.evaluate_job(job, employers, {"gitlab": {"123456"}}, 80)[0], "READY_TO_PREPARE")
        self.assertEqual(pilot.evaluate_job({**job, "source": "remotive"}, employers, {"gitlab": {"123456"}}, 80)[0], "NEEDS_OFFICIAL_ATS_RECONCILIATION")


if __name__ == "__main__":
    unittest.main()
