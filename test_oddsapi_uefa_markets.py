import unittest
from urllib.parse import urlparse,parse_qs
from datetime import datetime,timezone
from kvoter.the_odds_api import collect,parse_bookmaker,LEAGUES,recover_recent_cached_offers

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
    def test_cached_verified_quotes_survive_transient_europa_api_error(self):
        now=datetime(2026,11,5,10,40,tzinfo=timezone.utc)
        history={"fixtures":[{"league":"uefa.europa","start_utc":"2026-11-05T17:45:00Z"},
                             {"league":"uefa.europa.conf","start_utc":"2026-11-05T20:00:00Z"}]}
        old=[{"event_id":"e11","league":"uefa.europa","bookmaker":"old-book",
              "home":"Milan","away":"Ferencváros","start_utc":"2026-11-05T17:45:00Z",
              "updated_at_utc":"2026-11-05T09:59:19Z","markets":{"3+":{"over":1.92}}},
             {"event_id":"e12","league":"uefa.europa.conf","bookmaker":"old-book",
              "home":"Team A","away":"Team B","start_utc":"2026-11-05T20:00:00Z",
              "updated_at_utc":"2026-11-05T09:59:19Z","markets":{"1X2":{"home":1.55}}}]
        recovered,counts=recover_recent_cached_offers(history,old,
                     [{"league":"uefa.europa","error":"HTTP 429"}],now=now)
        self.assertEqual(counts,{"uefa.europa":1})
        self.assertEqual(len(recovered),1)
        self.assertEqual(recovered[0]["event_id"],"e11")

    def test_stale_and_wrong_kickoff_cache_rejected(self):
        now=datetime(2026,11,5,10,40,tzinfo=timezone.utc)
        history={"fixtures":[{"league":"uefa.europa",
                               "start_utc":"2026-11-05T17:45:00Z"}]}
        old=[{"event_id":"yesterday","league":"uefa.europa","bookmaker":"book",
              "start_utc":"2026-11-05T17:45:00Z",
              "updated_at_utc":"2026-11-04T10:40:00Z",
              "markets":{"3+":{"over":2.0}}},
             {"event_id":"wrong-match","league":"uefa.europa","bookmaker":"book",
              "start_utc":"2026-11-05T22:15:00Z",
              "updated_at_utc":"2026-11-05T09:59:19Z",
              "markets":{"1X2":{"home":2.0}}}]
        recovered,counts=recover_recent_cached_offers(history,old,
                     [{"league":"uefa.europa","error":"HTTP 503"}],now=now)
        self.assertEqual(recovered,[])
        self.assertEqual(counts,{"uefa.europa":0})

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
