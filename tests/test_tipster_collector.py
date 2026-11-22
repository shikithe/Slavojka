import unittest
from datetime import date
from bs4 import BeautifulSoup

from kvoter.tipster_collector import parse_daily, assign_links, parse_markets, verified_match_page

DAY = date(2026, 11, 21)
DAILY = """<html><body><h1>Matches for Saturday, 21 November, 2026</h1>
<a href="/match/manchester-city-fulham-premier-league-england-955986">12:30 Manchester City - Fulham 1.40 5.41 7.33</a>
<a href="/match/other">12:30 Fulham - Manchester City 7.33 5.41 1.40</a>
</body></html>"""
MATCH = """<html><head><title>Manchester City - Fulham, 21 November 2026, Premier League, England | TipsterArea.com</title></head>
<body><h2>Leading Bookmakers Odds</h2>
<table>
<tr><th>Standard 1X2</th><th>1</th><th>X</th><th>2</th></tr>
<tr><td><img alt="1xbet"></td><td>1.42</td><td>5.53</td><td>7.60</td></tr>
<tr><th>Over/Under</th><th>Goals</th><th>Under</th><th>Over</th></tr>
<tr><td><img alt="1xbet"></td><td>1.5</td><td>5.94</td><td>1.11</td></tr>
<tr><td><img alt="1xbet"></td><td>2.5</td><td>2.87</td><td>1.42</td></tr>
<tr><td><img alt="1xbet"></td><td>3.5</td><td>1.84</td><td>2.13</td></tr>
<tr><th>BTS</th><th>Yes</th><th>No</th></tr>
<tr><td><img alt="1xbet"></td><td>&nbsp;</td><td>1.60</td><td>2.22</td></tr>
</table>
<h2>Manchester City - Last Matches</h2><table><tr><td>Some historical odds</td><td>3.50</td><td>1.80</td></tr></table>
</body></html>"""

class TipsterCollectorTests(unittest.TestCase):
    def test_date_and_pair_mapping(self):
        matches = parse_daily(BeautifulSoup(DAILY, "html.parser"), DAY)
        self.assertEqual(len(matches), 2)
        fixture = dict(fixture_id="espn:test", home="Manchester City", away="Fulham")
        links = assign_links([fixture], matches)
        self.assertIn("espn:test", links)
        self.assertEqual(links["espn:test"]["home"], "Manchester City")

    def test_verified_espn_tipster_aliases_20261122(self):
        pairs = [
            (("Erzurum BB", "Goztepe"), ("Erzurumspor", "Goztepe")),
            (("FC Twente", "Willem II"), ("Twente", "Willem II Tilburg")),
            (("Waasland-Beveren", "KAA Gent"), ("SK Beveren", "KAA Gent")),
            (("Hull City", "Brighton & Hove Albion"), ("Hull City", "Brighton")),
            (("Lorient", "Stade Rennais"), ("Lorient", "Rennais")),
            (("Werder Bremen", "Hamburg SV"), ("Werder Bremen", "Hamburger")),
            (("Anderlecht", "OH Leuven"), ("Anderlecht", "Oud-Heverlee Leuven")),
            (("Athletico-PR", "Remo"), ("Atletico PR", "Remo PA")),
            (("Atalanta", "Internazionale"), ("Atalanta", "Inter")),
            (("Fluminense", "Mirassol"), ("Fluminense RJ", "Mirassol SP")),
            (("Red Bull Bragantino", "Vasco da Gama"), ("Bragantino SP", "Vasco Da Gama RJ")),
            (("Chicago Fire FC", "Charlotte FC"), ("Chicago Fire", "Charlotte FC")),
            (("Instituto (Córdoba)", "Huracán"), ("Instituto AC Cordoba", "Huracan Buenos Aires")),
        ]
        for i, (espn, tipster) in enumerate(pairs):
            with self.subTest(espn=espn):
                fixture = dict(fixture_id=f"espn:alias:{i}", home=espn[0], away=espn[1])
                candidate = dict(home=tipster[0], away=tipster[1], url=f"https://tipsterarea.com/match/test-{i}")
                matched = assign_links([fixture], [candidate])
                self.assertIn(fixture["fixture_id"], matched)
                swapped = dict(candidate, home=tipster[1], away=tipster[0])
                self.assertNotIn(fixture["fixture_id"], assign_links([fixture], [swapped]))

    def test_bookmakers_market_columns(self):
        prices, books = parse_markets(BeautifulSoup(MATCH, "html.parser"))
        self.assertEqual(prices["1X2"], {"home": 1.42, "draw": 5.53, "away": 7.6})
        self.assertEqual(prices["3+"], {"over": 1.42})
        self.assertEqual(prices["BTTS"], {"yes": 1.6, "no": 2.22})
        self.assertEqual(books["3+"]["over"], "1xbet")

    def test_team_and_date_validation(self):
        fixture = dict(home="Manchester City", away="Fulham")
        daily = dict(home="Manchester City", away="Fulham")
        soup = BeautifulSoup(MATCH, "html.parser")
        self.assertTrue(verified_match_page(soup, daily, fixture, DAY))
        self.assertFalse(verified_match_page(soup, daily, dict(home="Fulham",away="Manchester City"), DAY))
        self.assertFalse(verified_match_page(soup, daily, fixture, date(2026, 11, 22)))
if __name__ == "__main__":
    unittest.main()
