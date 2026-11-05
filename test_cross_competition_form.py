import unittest
import json
import tempfile
from pathlib import Path
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
    def test_cup_league_and_uefa_results_are_sorted_together(self):
        """A national cup match can be among the five most recent games."""
        league_games=[event("100","2026-11-01T18:00:00Z"),
                      event("101","2026-10-26T18:00:00Z")]
        cup_games=[event("200","2026-11-03T18:00:00Z"),
                   event("201","2026-10-31T18:00:00Z"),
                   event("202","2026-10-25T18:00:00Z"),
                   event("203","2026-11-06T18:00:00Z")]
        cup_games.append({"id":"204","date":"2026-11-02T18:00:00Z",
                          "status":{"type":{"state":"pre"}},
                          "competitions":[]})
        def fetch(url):
            if "/esp.1/teams?" in url or "/esp.copa_del_rey/teams?" in url:
                return {"sports":[{"leagues":[{"teams":[{"team":{
                    "id":"86","displayName":"Real Madrid"}}]}]}]}
            if "/esp.1/teams/86/schedule?" in url:
                return {"team":{"displayName":"Real Madrid"},"events":league_games}
            if "/esp.copa_del_rey/teams/86/schedule?" in url:
                return {"team":{"displayName":"Real Madrid"},"events":cup_games}
            if "/summary?" in url:return {"header":{"id":"valid"}}
            return {}
        original={"event_id":"old","date":"2026-10-30T18:00:00Z",
                  "name":"Real Madrid at Opponent","statistics":{"available":True}}
        data={"fixtures":[{"fixture_id":"f","league":"uefa.champions",
                           "home":"Real Madrid","away":"Opponent",
                           "start_utc":"2026-11-04T18:00:00Z"}],
              "target_matches_per_team":5,
              "leagues":{"uefa.champions":{"teams":{"Real Madrid":{
                  "found":1,"complete":False,"matches":[original]}}}}}
        result=augment(data,request=fetch,now=NOW)
        form=result["leagues"]["uefa.champions"]["teams"]["Real Madrid"]
        self.assertTrue(form["complete"])
        self.assertEqual([m["event_id"] for m in form["matches"]],
                         ["200","100","201","old","101"])
        self.assertIn("esp.copa_del_rey",form["competitions_used"])
        self.assertIn("esp.1",form["competitions_used"])
        self.assertIn("uefa.champions",form["competitions_used"])
        self.assertEqual(len({m["event_id"] for m in form["matches"]}),5)

    def test_missing_uefa_scoreboard_does_not_prevent_domestic_results(self):
        def fetch(url):
            if "/eng.1/teams?" in url:
                return {"sports":[{"leagues":[{"teams":[{"team":{
                    "id":"14","displayName":"Crystal Palace"}}]}]}]}
            if "/eng.1/teams/14/schedule?" in url:
                return {"team":{"displayName":"Crystal Palace"},
                        "events":[event(str(i),f"2026-11-{i:02d}T18:00:00Z",
                                        home="Crystal Palace") for i in (1,2,3)]}
            if "/summary?" in url:return {}
            return {}
        data={"fixtures":[{"fixture_id":"f","league":"uefa.europa",
                           "home":"Crystal Palace","away":"Opponent",
                           "start_utc":"2026-11-04T18:00:00Z"}],
              "target_matches_per_team":5,
              "leagues":{"uefa.europa":{"teams":{"Crystal Palace":{
                  "found":0,"complete":False,"matches":[]}}}}}
        form=augment(data,request=fetch,now=NOW)["leagues"]["uefa.europa"]["teams"]["Crystal Palace"]
        self.assertEqual(form["found"],3)
        self.assertFalse(form["complete"])
        self.assertEqual(form["competitions_used"],["eng.1"])

    def test_json_output_is_valid_document(self):
        # Regression: do not write escaped '\\n' after JSON document.
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"history.json"
            payload={"leagues":{},"fixtures":[]}
            path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            self.assertEqual(json.loads(path.read_text()),payload)

if __name__=="__main__":unittest.main()
