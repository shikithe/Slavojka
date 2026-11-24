import unittest
from lista.tipster_feedback_cycle import complete

class FeedbackCycleTests(unittest.TestCase):
    def basic(self, missing):
        return {"date":"2026-11-23","status":"ai_review_required" if missing else "ready_for_scout",
                "feedback":"ODDS_MISSING_AI_REVIEW" if missing else "ODDS_COMPLETE_SCOUT_6OF6",
                "espn_total":3,"with_at_least_one_quote":3-missing,"without_quote":missing,
                "missing_fixtures":[{"fixture_id":"espn:missing"}]*missing}

    def test_all_matched_goes_directly_to_final(self):
        result=complete(self.basic(0), False)
        self.assertEqual(result["feedback"],"ODDS_READY")
        self.assertEqual(result["skipped_unmatched"],0)
        self.assertFalse(result["retry_attempted"])
        self.assertEqual(result["coverage_status"],"complete")
        self.assertFalse(result["sensor_action_required"])

    def test_partial_after_retry_still_ready(self):
        result=complete(self.basic(1), True)
        self.assertEqual(result["feedback"],"ODDS_READY")
        self.assertEqual(result["matched_with_quotes"],2)
        self.assertEqual(result["skipped_unmatched"],1)
        self.assertEqual(result["coverage_status"],"partial")
        self.assertEqual(result["coverage_feedback"],"ODDS_PARTIAL_READY")
        self.assertTrue(result["sensor_action_required"])
        self.assertEqual(len(result["sensor_missing_fixtures"]),1)

    def test_partial_without_retry_is_not_final(self):
        with self.assertRaises(ValueError):
            complete(self.basic(1), False)

    def test_invalid_totals_rejected(self):
        fb=self.basic(1)
        fb["espn_total"]=5
        with self.assertRaises(ValueError):
            complete(fb,True)

if __name__=="__main__":
    unittest.main()
