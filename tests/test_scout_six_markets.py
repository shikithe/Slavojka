import unittest
from datetime import datetime, timezone, timedelta

from lista.scout_six_markets import (
    MARKETS, analyze, six_probs, ranking, suggestions, evaluate_fixture
)

NOW = datetime(2026, 11, 21, 10, 30, tzinfo=timezone.utc)

def form(team, side):
    matches = []
    for i in range(5):
        matches.append({"event_id":f"{team}.{i}", "date":f"2026-11-{10-i:02d}T12:00Z",
                        "home_goals":2,"away_goals":1, "side":side,
                        "goals_for":2, "goals_against":1})
    return {"found":5, "matches":matches}

def row(i, day="2026-11-21", with_odds=True):
    id = f"espn:football:eng.1:{i}"
    return {"fixture_id":id, "datetime":day+"T20:00:00Z",
            "match":f"Home{i} - Away{i}",
            "home_odds":1.7 if with_odds else None,
            "draw_odds":3.0 if with_odds else None,
            "away_odds":4.5 if with_odds else None,
            "over25_odds":1.7 if with_odds else None,
            "btts_yes_odds":1.85 if with_odds else None,
            "btts_no_odds":1.9 if with_odds else None}

def fixture(i):
    return {"fixture_id":f"espn:football:eng.1:{i}",
            "league":"eng.1","home":f"Home{i}","away":f"Away{i}",
            "start_utc":"2026-11-21T20:00:00Z"}

class ScoutSixTests(unittest.TestCase):
    def test_complete_and_consistent_probabilities(self):
        for home,away in ((.4,2.5),(1.6,1.2),(3.4,.5)):
            p = six_probs(home,away)
            self.assertEqual(set(p), set(MARKETS))
            self.assertAlmostEqual(p["1"]+p["X"]+p["2"],100.0,places=2)
            self.assertAlmostEqual(p["GG"]+p["NG"],100.0,places=2)
            self.assertTrue(all(0<=x<=100 for x in p.values()))
        self.assertGreater(six_probs(3.1,.5)["1"],70)

    def test_covers_all_100_fixtures_six_per_match(self):
        fixtures=[fixture(i) for i in range(100)]
        feed={"date":"2026-11-21","football_candidates":fixtures}
        active={"date":"2026-11-21","fixtures":[row(i) for i in range(100)]}
        history={"date":"2026-11-21","fixtures":fixtures,
                 "leagues":{"eng.1":{"teams":{name:form(name,side)
                 for i in range(100) for name,side in ((f"Home{i}","home"),(f"Away{i}","away"))}}}}
        result=analyze(feed,active,history,NOW)
        self.assertEqual(result["total_espn_fixtures"],100)
        self.assertEqual(result["total_market_probabilities"],600)
        self.assertEqual(len(result["ranked_fixtures"]),100)
        self.assertTrue(all(len(r["probability_pct"])==6 for r in result["ranked_fixtures"]))
        self.assertTrue(all(r["strongest_pct"]==max(r["probability_pct"].values()) for r in result["ranked_fixtures"]))
        self.assertFalse(result["publication_allowed"])

    def test_best_market_only_no_fallback(self):
        history={"leagues":{"eng.1":{"teams":{
                 "Home0":form("Home0","home"),"Away0":form("Away0","away")}}}}
        r=evaluate_fixture(row(0),history,NOW)
        self.assertEqual(r["strongest_pct"],max(r["probability_pct"].values()))
        chosen=r["strongest_market"]
        missing=row(0);missing[{"1":"home_odds","X":"draw_odds","2":"away_odds",
                               "3+":"over25_odds","GG":"btts_yes_odds","NG":"btts_no_odds"}[chosen]]=None
        r2=evaluate_fixture(missing,history,NOW)
        self.assertEqual(r2["strongest_market"],chosen)
        self.assertFalse(r2["candidate_A"])

    def test_tie_uses_second_highest(self):
        lower={"fixture_id":"a","strongest_pct":72.0,"second_pct":56.0,"third_pct":48.0}
        higher={"fixture_id":"b","strongest_pct":72.0,"second_pct":61.0,"third_pct":41.0}
        self.assertEqual(sorted([lower,higher],key=ranking)[0]["fixture_id"],"b")

    def test_a_b_no_overlap_and_3plus_only_for_b(self):
        arr=[]
        for i,(p,prob,second,odd) in enumerate([
            ("1",78,60,1.40),("2",76,57,1.52),("3+",74,58,1.60),
            ("3+",73,52,1.55),("GG",70,69,1.62),("3+",68,61,1.75),
        ]):
            arr.append({"fixture_id":str(i),"match":f"Match {i}",
                        "datetime":"2026-11-21T20:00:00Z",
                        "strongest_market":p,"strongest_pct":prob,
                        "second_pct":second,"third_pct":30.0,
                        "strongest_odds":odd,"candidate_A":True,"candidate_B":p=="3+"})
        ans=suggestions(sorted(arr,key=ranking))
        self.assertTrue(ans["A"],ans["reason"])
        self.assertTrue(ans["B"],ans["reason"])
        aa,bb=ans["A"]["matches"],ans["B"]["matches"]
        self.assertTrue(all(x["pick"]=="3+" for x in bb))
        self.assertTrue(set(x["fixture_id"] for x in aa).isdisjoint(x["fixture_id"] for x in bb))
        for ticket in (ans["A"],ans["B"]):
            self.assertTrue(2<=ticket["combined_odds"]<=3)
            self.assertFalse(ticket["ready_for_publication"])

if __name__ == "__main__":
    unittest.main()
