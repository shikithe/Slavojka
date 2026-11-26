"""Source-safe regressions: TOP10 research != A/B approval, last-five real."""
import unittest
from datetime import datetime, timezone

from lista.scout_history import (
    parsed_event, scoreboard_team_ids, team_form, get_team_schedule,
    verified_cross_competition_form,
)

NOW=datetime(2026,11,24,12,0,tzinfo=timezone.utc)

def event(event_id, home, away, home_id,away_id,date,gs1=1,gs2=0,completed=True):
    return {"id":str(event_id),"date":date,
            "status":{"type":{"completed":completed}},
            "season":{"displayName":"2026-27 English Premier League"},
            "competitions":[{"competitors":[
                {"homeAway":"home","team":{"id":str(home_id),"displayName":home},"score":str(gs1)},
                {"homeAway":"away","team":{"id":str(away_id),"displayName":away},"score":str(gs2)}
            ]}]}

class TopTenAndRealForm(unittest.TestCase):
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

    def test_real_espn_team_schedule_completion_is_inside_competition(self):
        e=event("401879232","Newcastle United","Arsenal",361,359,
                "2026-11-21T17:30Z",2,2)
        e["competitions"][0]["status"]=e.pop("status")
        parsed=parsed_event(e,"all",NOW.date())
        self.assertEqual(parsed["home_goals"],2)
        self.assertEqual(parsed["away_goals"],2)
        self.assertEqual(parsed["away_team_id"],"359")

    def test_future_and_unconfirmed_scores_excluded(self):
        completed=parsed_event(event("1","Arsenal","B",359,20,"2026-11-17T20:00Z"),"all",NOW.date())
        unplayed=parsed_event(event("2","Arsenal","C",359,30,"2026-11-24T20:00Z",completed=False),
                              "all",NOW.date())
        self.assertIsNotNone(completed)
        self.assertIsNone(unplayed)

if __name__=="__main__":
    unittest.main()
