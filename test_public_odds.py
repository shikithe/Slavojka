"""Offline safety tests for public odds matching and quote parsing."""
import unittest
from kvoter.public_odds import row_offer,choose,similarity,read_date

class PublicOddsTests(unittest.TestCase):
    def setUp(self):
        self.fixture={"fixture_id":"es:123","league":"eng.1","home":"Manchester United FC",
                      "away":"Liverpool","start_utc":"2026-11-21T15:00:00Z"}
        self.row={"Div":"E0","Date":"21/11/2026","Time":"15:00","HomeTeam":"Man United",
                  "AwayTeam":"Liverpool","B365H":"2.1","B365D":"3.2","B365A":"3.5",
                  "B365>2.5":"1.78"}
    def test_parse_markets_no_2plus(self):
        row=dict(self.row,HomeTeam="Manchester United")
        p=row_offer(row,"public-csv","2026-11-20T10:00:00Z")
        self.assertIn("1X2",p["markets"])
        self.assertIn("3+",p["markets"])
        self.assertNotIn("2+",p["markets"])
    def test_auto_typographic_alias(self):
        row=dict(self.row,HomeTeam="Man Utd")
        offer=row_offer(row,"public-csv","2026-11-20T10:00:00Z")
        self.assertEqual(len(choose([self.fixture],[offer])),1)
    def test_no_swapped_teams(self):
        row=dict(self.row,HomeTeam="Liverpool",AwayTeam="Manchester United")
        offer=row_offer(row,"public-csv","2026-11-20T10:00:00Z")
        self.assertEqual(choose([self.fixture],[offer]),{})
    def test_no_cross_league(self):
        row=dict(self.row,Div="D1",HomeTeam="Manchester United")
        offer=row_offer(row,"public-csv","2026-11-20T10:00:00Z")
        self.assertEqual(choose([self.fixture],[offer]),{})
    def test_no_premature_matches(self):
        row=dict(self.row,Date="29/11/2026",HomeTeam="Manchester United")
        offer=row_offer(row,"public-csv","2026-11-20T10:00:00Z")
        self.assertEqual(choose([self.fixture],[offer]),{})
    def test_no_ambiguous_provider(self):
        row=dict(self.row,HomeTeam="Manchester United")
        offer=row_offer(row,"public-csv","2026-11-20T10:00:00Z")
        self.assertEqual(choose([self.fixture],[offer,dict(offer,event_id="duplicate")]),{})
if __name__=="__main__":unittest.main()
