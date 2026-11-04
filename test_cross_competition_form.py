import unittest
from datetime import datetime,timezone
from agent.cross_competition_form import augment

NOW=datetime(2026,11,4,12,0,tzinfo=timezone.utc)
def event(event_id,day,home="Real Madrid",away="Opponent"):
    return {"id":str(event_id),"date":day,"name":home+" at "+away,
            "status":{"type":{"state":"post"}},
            "competitions":[{"competitors":[{"team":{"id":"86","displayName":home}},
                                             {"team":{"id":"777","displayName":away}}]}]}
class CrossCompetitionTests(unittest.TestCase):
    def test_uefa_team_gets_last_five_from_domestic_and_europe(self):
        original=event("10","2026-10-29T19:00:00Z")
        games=[event(str(i),f"2026-11-{i:02d}T19:00:00Z") for i in (1,2,3)]
        games += [event("20","2026-10-30T19:00:00Z"),
                  event("21","2026-10-27T19:00:00Z"),
                  event("22","2026-11-06T19:00:00Z")] # future, must skip
        queries=[]
        def get(url):
            queries.append(url)
            if "uefa.champions/scoreboard?" in url:return {"events":[event("99","2026-11-04T19:00:00Z")]}
            if "/esp.1/teams?" in url:return {"sports":[{"leagues":[{"teams":[{"team":{"id":"86","displayName":"Real Madrid"}}]}]}]}
            if "/esp.1/teams/86/schedule?" in url:return {"team":{"displayName":"Real Madrid"},"events":games}
            if "/esp.1/summary?" in url:return {"header":{"id":"valid"}}
            return {}
        data={"fixtures":[{"fixture_id":"fixture1","league":"uefa.champions",
                           "home":"Real Madrid","away":"Opponent",
                           "start_utc":"2026-11-04T19:00:00Z"}],
              "target_matches_per_team":5,
              "leagues":{"uefa.champions":{"teams":{"Real Madrid":{"found":1,"complete":False,
                   "matches":[{"event_id":"10","date":original["date"],"name":original["name"],
                               "statistics":{"available":True}}]}}}}}
        out=augment(data,request=get,now=NOW)
        entry=out["leagues"]["uefa.champions"]["teams"]["Real Madrid"]
        self.assertEqual(entry["found"],5)
        self.assertTrue(entry["complete"])
        self.assertEqual(len({x["event_id"] for x in entry["matches"]}),5)
        self.assertEqual(entry["matches"][0]["event_id"],"3")
        self.assertTrue(all(x["date"]<NOW.isoformat().replace("+00:00","Z") for x in entry["matches"]))
        self.assertEqual(set(entry["competitions_used"]),{"esp.1","uefa.champions"})
if __name__=="__main__":unittest.main()
