import unittest
from urllib.parse import urlparse,parse_qs
from kvoter.the_odds_api import collect,parse_bookmaker,LEAGUES

class OddsApiEuropeTests(unittest.TestCase):
    def test_uefa_competitions_are_requested(self):
        self.assertEqual(LEAGUES["uefa.europa"],"soccer_uefa_europa_league")
        self.assertEqual(LEAGUES["uefa.europa.conf"],"soccer_uefa_europa_conference_league")
        seen=[]
        def fake(url):
            seen.append(url)
            return []
        base={"fixtures":[
            {"league":"uefa.europa","start_utc":"2026-11-05T17:45:00Z"},
            {"league":"uefa.europa.conf","start_utc":"2026-11-05T20:00:00Z"}]}
        offers,raw,coverage,errors=collect(base,"placeholder",fetch=fake)
        self.assertFalse(errors)
        self.assertEqual(set(coverage),{"uefa.europa","uefa.europa.conf"})
        self.assertEqual(len(seen),2)
        self.assertTrue(any("/soccer_uefa_europa_league/odds?" in x for x in seen))
        self.assertTrue(any("/soccer_uefa_europa_conference_league/odds?" in x for x in seen))
        for url in seen:
            params=parse_qs(urlparse(url).query)
            self.assertEqual(params["markets"],["h2h,totals"])
    def test_goal_totals_and_btts_mapping(self):
        event={"id":"e","home_team":"Home FC","away_team":"Away FC",
               "commence_time":"2026-11-05T17:45:00Z"}
        book={"key":"sample","markets":[
             {"key":"totals","last_update":"2026-11-05T09:00:00Z",
              "outcomes":[{"name":"Over","point":1.5,"price":1.3},
                          {"name":"Over","point":2.5,"price":1.9}]},
             {"key":"btts","outcomes":[{"name":"Yes","price":1.74},
                                       {"name":"No","price":2.01}]},
             {"key":"h2h","outcomes":[{"name":"Home FC","price":2.2},
                                     {"name":"Draw","price":3.3},
                                     {"name":"Away FC","price":3.4}]}]}
        result=parse_bookmaker(event,book,"uefa.europa")
        self.assertEqual(result["markets"]["2+"]["over"],1.3)
        self.assertEqual(result["markets"]["3+"]["over"],1.9)
        self.assertEqual(result["markets"]["BTTS"]["yes"],1.74)
        self.assertEqual(result["markets"]["1X2"]["home"],2.2)

if __name__=="__main__":
    unittest.main()
