import unittest
from lista.scout_feedback import inspect, canonical_hash

TODAY="2026-11-22"
def source():
    feed={"date":TODAY,"generated_at_utc":"2026-11-22T08:45:00Z",
          "football_candidates":[{"fixture_id":"e1","home":"A","away":"B","start_utc":"2026-11-22T17:00:00Z"}]}
    active={"date":TODAY,"fixtures":[{"fixture_id":"e1","home_odds":1.8}]}
    history={"date":TODAY,"fixtures":[{"fixture_id":"e1"}]}
    row={"fixture_id":"e1","candidate_A":True,"recommended_market":"3+",
         "probability_pct":{"1":40,"X":20,"2":40,"3+":60,"GG":50,"NG":50}}
    candidate={"fixture_id":"e1","rank":1,"recommended_market":"3+"}
    scout={"date":TODAY,"source_feed_generated_at_utc":feed["generated_at_utc"],
           "source_active_sha256":canonical_hash(active),"source_history_sha256":canonical_hash(history),
           "ranked_fixtures":[row],"all_fixtures_evaluated":1,"total_market_probabilities":6,
           "detailed_ai_handoff":{"count":1,"candidates":[candidate]},
           "detailed_ai_top_ten_fixture_ids":["e1"]}
    return feed,active,history,scout

class ScoutFeedbackTests(unittest.TestCase):
    def test_complete_then_top10_ready(self):
        done,top=inspect(*source(),TODAY)
        self.assertEqual(done["feedback"],"SCOUT_6OF6_COMPLETE")
        self.assertEqual(top["feedback"],"TOP10_READY")
        self.assertEqual(top["fixture_ids"],["e1"])
        self.assertFalse(top["publication_allowed"])
    def test_stale_odds_or_history_refused(self):
        f,a,h,s=source()
        a["fixtures"][0]["home_odds"]=2.0
        with self.assertRaises(ValueError):inspect(f,a,h,s,TODAY)
    def test_missing_market_refused(self):
        f,a,h,s=source();del s["ranked_fixtures"][0]["probability_pct"]["NG"]
        with self.assertRaises(ValueError):inspect(f,a,h,s,TODAY)
    def test_wrong_candidate_refused(self):
        f,a,h,s=source();s["detailed_ai_handoff"]["candidates"][0]["fixture_id"]="wrong"
        s["detailed_ai_top_ten_fixture_ids"]=["wrong"]
        with self.assertRaises(ValueError):inspect(f,a,h,s,TODAY)
    def test_zero_top10_not_falsely_ready(self):
        f,a,h,s=source()
        s["detailed_ai_handoff"]={"count":0,"candidates":[]}
        s["detailed_ai_top_ten_fixture_ids"]=[]
        self.assertEqual(inspect(f,a,h,s,TODAY)[1]["feedback"],"TOP10_UNAVAILABLE")
if __name__=="__main__":
    unittest.main()
