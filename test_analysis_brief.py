import unittest
from agent.analysis_brief import compress
from agent.five_matches import verified_scores

class TestAnalysisBrief(unittest.TestCase):
    def test_preserves_verified_match_dates_and_missing_scores(self):
        source={
            "date":"2026-11-07",
            "generated_at_utc":"2026-11-07T08:45:00Z",
            "fixtures":[{"fixture_id":"espn:football:eng.1:xyz","league":"eng.1","home":"Leeds United","away":"Tottenham Hotspur","start_utc":"2026-11-07T12:30:00Z"}],
            "leagues":{"eng.1":{"teams":{
                "Leeds United":{"found":1,"complete":False,"matches":[{"event_id":"a","date":"2026-11-01T15:00:00Z","name":"Leeds United vs Liverpool","competition":"eng.1","statistics":{"available":True}}]},
                "Tottenham Hotspur":{"found":1,"complete":False,"matches":[{"event_id":"b","date":"2026-10-30T15:00:00Z","name":"Tottenham Hotspur vs Everton","scores":{"home":"1","away":"0"}}]}
            }}},
            "head_to_head":{},
            "form_scope":"Last five finished matches across available ESPN club competitions",
        }
        d=compress(source)
        self.assertFalse(d["publication_allowed"])
        self.assertEqual(d["fixture_count"],1)
        h=d["fixtures"][0]["home_form"]["last_five_matches"][0]
        a=d["fixtures"][0]["away_form"]["last_five_matches"][0]
        self.assertEqual(h["date"],"2026-11-01T15:00:00Z")
        self.assertIsNone(h["scores"])
        self.assertEqual(a["scores"],{"home":"1","away":"0"})
        self.assertFalse(d["fixtures"][0]["home_form"]["complete"])
        self.assertFalse(d["fixtures"][0]["away_form"]["complete"])

    def test_score_capture_requires_completed_event_and_both_sides(self):
        event = {
            "status": {"type": {"state": "post"}},
            "competitions": [{"competitors": [
                {"homeAway":"home","score":"3"},
                {"homeAway":"away","score":"1"}
            ]}]
        }
        self.assertEqual(verified_scores(event), {"home":"3","away":"1"})
        event["status"]["type"]["state"] = "pre"
        self.assertIsNone(verified_scores(event))
        event["status"]["type"]["state"] = "post"
        event["competitions"][0]["competitors"][1].pop("score")
        self.assertIsNone(verified_scores(event))

if __name__=="__main__":
    unittest.main()
