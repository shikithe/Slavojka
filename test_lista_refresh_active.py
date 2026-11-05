"""Regression tests: reprice a published ListaSix offer from the latest Kvoter match file."""
import json
import tempfile
import unittest
from pathlib import Path
from lista.publish import publish

class ActiveListRefreshTests(unittest.TestCase):
    def test_refresh_replaces_old_odds_and_both_public_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            shared=root/"shared"
            docs=root/"docs"
            shared.mkdir()
            docs.mkdir()
            feed=shared/"collector-feed.json"
            matches=shared/"matched_fixtures.json"
            fixture={"fixture_id":"espn:football:uefa.europa:event42",
                     "home":"Home FC","away":"Away FC","sport":"football",
                     "league":"uefa.europa","status":"pre",
                     "start_utc":"2026-11-05T19:00:00Z"}
            feed.write_text(json.dumps({"date":"2026-11-05","football_candidates":[fixture]}))
            def matched(over):
                return {"fixtures":[{**fixture,"odds_offers":[
                    {"bookmaker":"verified","markets":{"1X2":{"home":2.2},
                                                       "2+":{"over":1.33},
                                                       "3+":{"over":over},
                                                       "BTTS":{"yes":1.75}}}]}]}
            matches.write_text(json.dumps(matched(1.88)))
            self.assertEqual(publish(feed,matches,None,shared,docs),1)
            first=json.loads((shared/"active-list.json").read_text())
            self.assertEqual(first["fixtures"][0]["over25_odds"],1.88)
            matches.write_text(json.dumps(matched(2.07)))
            self.assertEqual(publish(feed,matches,None,shared,docs),1)
            current=json.loads((shared/"active-list.json").read_text())
            public=json.loads((docs/"active-list.json").read_text())
            self.assertEqual(current,public)
            self.assertEqual(current["fixtures"][0]["over25_odds"],2.07)
            self.assertEqual(current["fixtures"][0]["over15_odds"],1.33)
            self.assertEqual(current["fixtures"][0]["btts_yes_odds"],1.75)
            self.assertEqual(len(current["fixtures"]),1)
            self.assertIn("2.07",(docs/"kvoter-ponuda.txt").read_text())
            self.assertEqual((docs/"kvoter-ponuda.txt").read_text(),
                             (shared/"kvoter-ponuda.txt").read_text())

    def test_absent_fixture_does_not_survive_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            shared=root/"shared"
            docs=root/"docs"
            shared.mkdir()
            docs.mkdir()
            (docs/"active-list.json").write_text('{"date":"2026-11-04","fixtures":[{"fixture_id":"old"}]}')
            feed=shared/"collector-feed.json"
            feed.write_text(json.dumps({"date":"2026-11-05","football_candidates":[
                {"fixture_id":"new","sport":"football","status":"pre","start_utc":"2026-11-05T20:00:00Z"}]}))
            matched=shared/"matched_fixtures.json"
            matched.write_text(json.dumps({"fixtures":[
                {"fixture_id":"new","home":"A","away":"B","start_utc":"2026-11-05T20:00:00Z",
                 "odds_offers":[{"bookmaker":"verified","markets":{"3+":{"over":1.8}}}]},
                {"fixture_id":"old","home":"Old","away":"Old","start_utc":"2026-11-04T20:00:00Z",
                 "odds_offers":[{"bookmaker":"verified","markets":{"3+":{"over":2.1}}}]}]}))
            self.assertEqual(publish(feed,matched,None,shared,docs),1)
            result=json.loads((docs/"active-list.json").read_text())
            self.assertEqual([x["fixture_id"] for x in result["fixtures"]],["new"])

if __name__=="__main__":
    unittest.main()
