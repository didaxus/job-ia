"""Offline dual-profile policy tests: no network, no user CV required."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from profile_worker import topic_relevance, classify

PRO = {
    "roles": ["Instructional Designer", "Learning Experience Designer"],
    "summary": "Verified learning experience",
    "evidence": "Created teaching resources",
    "mode": "both",
}
ASSIST = {
    "roles": ["Virtual Assistant", "Administrative Assistant"],
    "summary": "Verified organizational experience",
    "evidence": "Document management",
    "mode": "both",
}
def job(title, location="Remote - Latin America", description="Training projects"):
    return {"title": title, "location": location, "description": description}

class DualProfileTests(unittest.TestCase):
    def test_profiles_do_not_inherit_others_matches(self):
        self.assertGreater(topic_relevance("Instructional Designer", PRO["roles"]), 0)
        self.assertEqual(topic_relevance("Instructional Designer", ASSIST["roles"]), 0)
        self.assertGreater(topic_relevance("Virtual Assistant", ASSIST["roles"]), 0)
        self.assertEqual(topic_relevance("Virtual Assistant", PRO["roles"]), 0)

    def test_exclude_pure_sales_even_if_assistant(self):
        self.assertEqual(topic_relevance("Sales Virtual Assistant", ASSIST["roles"]), 0)

    def test_unverified_company_never_becomes_ready(self):
        self.assertEqual(classify(job("Virtual Assistant"), ASSIST, "UNVERIFIED")[1],
                         "EMPLOYER_REVIEW_REQUIRED")

    def test_no_implicit_colombia_eligibility(self):
        self.assertEqual(classify(job("Virtual Assistant", "Remote US"), ASSIST,
                                  "VERIFIED")[1], "RESTRICTED_LOCATION")
        self.assertEqual(classify(job("Virtual Assistant", "Remote"), ASSIST,
                                  "VERIFIED")[1], "LOCATION_UNVERIFIED")

    def test_mode_restrictions(self):
        remote_only = {**ASSIST, "mode": "remote"}
        hybrid_only = {**ASSIST, "mode": "hybrid"}
        self.assertEqual(classify(job("Virtual Assistant", "Hybrid Bogota"), remote_only,
                                  "VERIFIED")[1], "MODE_MISMATCH")
        self.assertEqual(classify(job("Virtual Assistant"), hybrid_only,
                                  "VERIFIED")[1], "MODE_MISMATCH")

    def test_factual_evidence_required_before_fit_score(self):
        missing = {**PRO, "evidence": ""}
        result = classify(job("Instructional Designer"), missing, "VERIFIED")
        self.assertEqual(result[1], "AWAITING_VERIFIED_EVIDENCE")
        self.assertEqual(classify(job("Instructional Designer"), PRO,
                                  "VERIFIED")[1], "READY_FOR_FIT_REVIEW")

if __name__ == "__main__":
    unittest.main()
