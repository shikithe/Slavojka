"""Source-safe regressions: TOP10 research != A/B approval, last-five real."""
import unittest
from datetime import datetime, timezone

from lista.scout_six_markets import detailed_ai_handoff, league_goal_reference
from lista.scout_history import (
    parsed_event, scoreboard_team_ids, team_form, get_team_schedule,
    verified_cross_competition_form,
)

NOW=datetime(2026,11,24,12,0,tzinfo=timezone.utc)

def example(i, eligible=False):
    return {
        "fixture_id": f"espn:football:uefa.champions:{i}",
        "match": f"Home{i} - Away{i}", "datetime": "2026-11-24T20:00:00Z",
        "strongest_market": "3+", "strongest_pct": 75.0,
        "second_market": "GG", "second_pct": 69.0, "third_pct": 55.0,
        "recommended_market": "3+", "recommended_pct":75.0,
        "recommended_adjusted_pct":67.0,"recommended_score":40-i/20,
        "recommended_ev_pct":4.5,"data_quality_index_pct":42,
        "strongest_odds":1.65,"recommended_odds":1.65,
        "candidate_A":eligible,"candidate_B":False,
        "history_evidence_complete":eligible,
        "confidence":"normal" if eligible else "low_data",
        "probability_pct":{"1":43,"X":25,"2":32,"3+":75,"GG":69,"NG":31},
        "estimated_goals":{"home":2.1,"away":1.1},
        "evidence":{"home_last_matches":5 if eligible else 3,
                    "away_last_matches":5 if eligible else 3},
    }

def event(event_id, home, away, home_id,away_id,date,gs1=1,gs2=0,completed=True):
    return {"id":str(event_id),"date":date,
            "status":{"type":{"completed":completed}},
            "season":{"displayName":"2026-27 English Premier League"},
            "competitions":[{"competitors":[
                {"homeAway":"home","team":{"id":str(home_id),"displayName":home},"score":str(gs1)},
                {"homeAway":"away","team":{"id":str(away_id),"displayName":away},"score":str(gs2)}
            ]}]}

class TopTenAndRealForm(unittest.TestCase):
    def test_ten_comes_from_13_even_if_only_two_are_ticket_eligible(self):
        rows=[example(i,i in (2,3)) for i in range(13)]
        d=detailed_ai_handoff(rows,NOW)
        self.assertEqual(d["count"],10)
        self.assertEqual([x["fixture_id"] for x in d["candidates"]],
                         [x["fixture_id"] for x in rows[:10]])
        self.assertEqual(sum(x["eligible_for_A"] for x in d["candidates"]),2)
        self.assertEqual(sum(x["research_only"] for x in d["candidates"]),8)
        self.assertFalse(d["candidates"][0]["eligible_for_A"])
        self.assertTrue(d["candidates"][0]["research_only"])

    def test_not_padded_when_only_three_games_have_genuine_odds(self):
        rows=[example(i) for i in range(4)]
        rows[2]["recommended_odds"]=None
        d=detailed_ai_handoff(rows,NOW)
        self.assertEqual(d["count"],3)
        self.assertNotIn(rows[2]["fixture_id"],[r["fixture_id"] for r in d["candidates"]])

    def test_no_game_after_kickoff_is_added_to_research(self):
        rows=[example(i) for i in range(13)]
        rows[0]["datetime"]="2026-11-24T10:00:00Z"
        d=detailed_ai_handoff(rows,NOW)
        self.assertEqual(d["count"],10)
        self.assertNotIn(rows[0]["fixture_id"],[x["fixture_id"] for x in d["candidates"]])

    def test_espen_event_team_ids_reject_reversed_and_reserve(self):
        fixture=event("401915295","Arsenal","Borussia Dortmund",359,124,
                      "2026-11-24T20:00Z",completed=False)
        members=scoreboard_team_ids(fixture)
        self.assertEqual(members["home"]["id"],"359")
        self.assertEqual(members["away"]["id"],"124")
        with self.assertRaises(ValueError):
            get_team_schedule("../../../other",2026)

    def test_genuine_all_competition_scores_fill_five_by_verified_team_id(self):
        dates=["2026-11-21T17:30Z","2026-11-18T19:00Z",
               "2026-11-14T15:00Z","2026-11-08T16:00Z",
               "2026-11-04T20:00Z","2026-10-20T20:00Z"]
        events=[]
        for i,dt in enumerate(dates):
            events.append(parsed_event(event(f"4{i}","Arsenal",f"Opponent{i}",359,1000+i,dt,2,1),
                                       "all",NOW.date()))
        events.append(parsed_event(event("400","Arsenal U21","Opponent",9999,3000,
                                       "2026-11-23T12:00Z",4,0),"all",NOW.date()))
        result=team_form("Arsenal",events,"359")
        self.assertEqual(result["found"],5)
        self.assertEqual(result["matches"][0]["date"],dates[0])
        self.assertTrue(all(x["home_team_id"]=="359" for x in result["matches"]))
        self.assertEqual(result["goals_for"],10)
        self.assertTrue(result["complete"])

    def test_league_average_excludes_cross_competition_form(self):
        league=parsed_event(event("1","A","B",10,11,"2026-11-15T12:00Z"),"uefa.champions",NOW.date())
        domestic=parsed_event(event("2","A","C",10,12,"2026-11-18T12:00Z",7,0),"all",NOW.date())
        record=team_form("A",[domestic,league],"10")
        h,a,n=league_goal_reference({"league":"uefa.champions","teams":{"A":record}})
        self.assertEqual(n,1)
        self.assertLess(h,2.15)

    def test_future_and_unconfirmed_scores_excluded(self):
        completed=parsed_event(event("1","Arsenal","B",359,20,"2026-11-17T20:00Z"),"all",NOW.date())
        unplayed=parsed_event(event("2","Arsenal","C",359,30,"2026-11-24T20:00Z",completed=False),
                              "all",NOW.date())
        self.assertIsNotNone(completed)
        self.assertIsNone(unplayed)

if __name__=="__main__":
    unittest.main()
