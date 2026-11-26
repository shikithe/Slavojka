import unittest
from datetime import datetime, timezone
from lista.scout_feedback import inspect
from lista.scout_six_markets import analyze
from test_scout_six_markets import inputs, HTML, NOW, DAY

class FairXGFeedbackTests(unittest.TestCase):
    def test_source_checked_and_partial_coverage_honest(self):
        f,a=inputs()
        s=analyze(f,a,NOW,lambda url:HTML)
        done,top=inspect(f,a,{},s,DAY)
        self.assertEqual(done["feedback"],"FAIRXG_LIST_READY")
        self.assertEqual(done["status"],"partial")
        self.assertEqual(top["count"],1)
        self.assertFalse(top["publication_allowed"])
        a["fixtures"][0]["over25_odds"]=2.0
        with self.assertRaises(ValueError):inspect(f,a,{},s,DAY)
    def test_removed_poisson_not_accepted(self):
        f,a=inputs()
        with self.assertRaises(ValueError):inspect(f,a,{},{"date":DAY,"model":"Poisson"},DAY)
if __name__=="__main__":
    unittest.main()
