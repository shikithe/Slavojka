import unittest
from datetime import date
from bs4 import BeautifulSoup

from kvoter.tipster_collector import parse_daily, assign_links, assign_links_secondary, secondary_key, parse_markets, verified_match_page, recover_verified_page_links

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

    def test_missing_index_link_recovers_only_verified_exact_fixture(self):
        fixture = dict(fixture_id="espn:chicago", home="Chicago Fire FC",
                       away="Charlotte FC", start_utc="2026-11-22T23:30:00Z")
        links = {}
        days = {}
        recover_verified_page_links([fixture], links, days)
        self.assertEqual(links["espn:chicago"]["url"],
                         "https://tipsterarea.com/match/chicago-fire-charlotte-fc-playoff-usa-956702")
        other = dict(fixture, fixture_id="espn:wrong", away="Columbus Crew")
        recover_verified_page_links([other], links, days)
        self.assertNotIn("espn:wrong", links)

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
    def test_secondary_recovers_nine_champions_league_fixtures(self):
        day=date(2026,11,24)
        fixtures=[
          ("Bodo/Glimt","LASK Linz","Bodo Glimt (Nor)","LASK Linz (Aut)"),
          ("Galatasaray","Aston Villa","Galatasaray (Tur)","Aston Villa (Eng)"),
          ("Arsenal","Borussia Dortmund","Arsenal (Eng)","Borussia Dortmund (Ger)"),
          ("Como","AEK Athens","Como (Ita)","AEK Athens (Gre)"),
          ("Feyenoord Rotterdam","FC Porto","Feyenoord (Ned)","Porto (Por)"),
          ("Manchester City","Napoli","Manchester City (Eng)","Napoli (Ita)"),
          ("RB Leipzig","Lens","RB Leipzig (Ger)","Lens (Fra)"),
          ("Real Madrid","PSV Eindhoven","Real Madrid (Esp)","PSV Eindhoven (Ned)"),
          ("Slovan Bratislava","Real Betis","Slovan Bratislava (Svk)","Real Betis (Esp)")
        ]
        html='<h1>Matches for Tuesday, 24 November, 2026</h1>'
        feed=[]
        for i,(home,away,source_home,source_away) in enumerate(fixtures):
            clock="17:45" if i<2 else "20:00"
            html+=f'<a href="/match/ucl-{i}">{clock} {source_home} - {source_away} 2.10 3.20 3.60</a>'
            feed.append({"fixture_id":f"espn:football:uefa.champions:{i}",
                         "home":home,"away":away,"league":"uefa.champions"})
        matches=parse_daily(BeautifulSoup(html,"html.parser"),day)
        self.assertEqual(len(matches),9)
        self.assertLess(len(assign_links(feed,matches)),9)
        mapped=assign_links_secondary(feed,matches)
        self.assertEqual(len(mapped),9)
        for i in range(9):
            self.assertTrue(mapped[feed[i]["fixture_id"]]["url"].endswith(f"/ucl-{i}"))
        # Same-day URL must still validate the exact teams and competition.
        first=feed[0];candidate=mapped[first["fixture_id"]]
        page=BeautifulSoup(
          "<title>Bodo Glimt - LASK Linz, 24 November 2026, Champions League Group | TipsterArea.com</title>",
          "html.parser")
        self.assertTrue(verified_match_page(page,candidate,first,day,secondary=True))
        self.assertFalse(verified_match_page(page,candidate,first,date(2026,11,25),secondary=True))
        self.assertFalse(verified_match_page(
           BeautifulSoup("<title>Bodo Glimt - LASK Linz, 24 November 2026, Europa League | TipsterArea.com</title>","html.parser"),
           candidate,first,day,secondary=True))

    def test_secondary_rejects_swapped_unknown_and_ambiguous_names(self):
        fixture={"fixture_id":"espn:fixture", "home":"Arsenal","away":"Borussia Dortmund"}
        correct={"home":"Arsenal (Eng)","away":"Borussia Dortmund (Ger)","url":"https://tipsterarea.com/match/real"}
        reversed_match=dict(correct,home=correct["away"],away=correct["home"])
        self.assertEqual(assign_links_secondary([fixture],[reversed_match]),{})
        self.assertEqual(len(assign_links_secondary([fixture],[correct])),1)
        self.assertEqual(assign_links_secondary([fixture],[correct,dict(correct,url="https://tipsterarea.com/match/duplicate")]),{})
        self.assertNotEqual(secondary_key("Arsenal (U19)"),secondary_key("Arsenal"))
        self.assertEqual(secondary_key("FC Porto"),secondary_key("Porto (Por)"))
        self.assertEqual(secondary_key("Bodo/Glimt"),secondary_key("Bodo Glimt (Nor)"))

    def test_tertiary_aliases_and_strict_identity(self):
        from kvoter.tipster_collector import assign_links_tertiary, verified_tertiary_page
        from kvoter.team_matcher import same_team
        day = date(2026, 11, 26)
        pairs = [
            ("Kairat Almaty", "Mjällby AIF", "Kairat Almaty (Kaz)", "Mjallby (Swe)"),
            ("Besiktas", "Hapoel Be'er", "Besiktas (Tur)", "Hapoel Beer Sheva (Isr)"),
            ("Olympiacos", "AC Milan", "Olympiacos Piraeus (Gre)", "Milan (Ita)"),
            ("RB Salzburg", "Ararat-Armenia", "Red Bull Salzburg (Aut)", "Ararat-Armenia (Arm)"),
            ("Union St.-Gilloise", "Lech Poznan", "Union Saint-Gilloise (Bel)", "Lech Poznan (Pol)"),
            ("Brighton & Hove Albion", "CSU Craiova", "Brighton (Eng)", "Universitatea Craiova (Rou)"),
            ("Egnatia", "Lincoln Red Imps", "Egnatia Rrogozhine (Alb)", "Lincoln Red Imps (Gib)"),
            ("Iberia 1999", "Getafe", "Iberia 1999 Tbilisi (Geo)", "Getafe (Esp)"),
            ("SK Brann", "AGF", "Brann Bergen (Nor)", "AGF Aarhus (Den)"),
            ("Ferencvaros", "NK Celje", "Ferencvarosi (Hun)", "NK Celje (Svn)"),
            ("TSG Hoffenheim", "SK Sturm Graz", "Hoffenheim (Ger)", "Sturm Graz (Aut)"),
            ("FC Nordsjælland", "Panathinaikos", "FC Nordsjaelland (Den)", "Panathinaikos (Gre)"),
            ("Inter D'Escaldes", "F.C. København", "Inter Club d'Escaldes (And)", "FC Copenhagen (Den)"),
            ("KAA Gent", "Red Star Belgrade", "KAA Gent (Bel)", "Crvena zvezda Belgrade (Srb)"),
            ("São Paulo", "Remo", "Sao Paulo SP", "Remo PA"),
        ]
        for i, (home, away, sh, sa) in enumerate(pairs):
            with self.subTest(home=home):
                league, slug, title = ("bra.1", "serie-a-brazil", "Serie A, Brazil") if i == 14 else ("uefa.europa", "europa-league-group-stage", "Europa League Group") if i in (1,2,3,4,9,10) else ("uefa.europa.conf", "europa-conference-league-group-stage", "Europa Conference League Group")
                clock = "23:00" if i == 14 else "15:30" if i == 0 else "17:45" if i < 9 else "20:00"
                f = dict(fixture_id=str(i), home=home, away=away, league=league, start_utc=f"2026-11-26T{clock}:00Z")
                m = dict(home=sh, away=sa, url=f"https://tipsterarea.com/match/test-{slug}-{i}", clock=clock)
                self.assertIn(str(i), assign_links_tertiary([f], [m], day))
                self.assertFalse(assign_links_tertiary([f], [dict(m, clock="12:00")], day))
                self.assertFalse(assign_links_tertiary([f], [dict(m, home=sa, away=sh)], day))
                self.assertFalse(assign_links_tertiary([f], [dict(m, url=m["url"]+"-duplicate"), m], day))
                page = BeautifulSoup(f"<title>{sh} - {sa}, 26 November 2026, {title} | TipsterArea.com</title>", "html.parser")
                self.assertTrue(verified_tertiary_page(page, m, f, day))
                self.assertFalse(verified_tertiary_page(page, m, f, date(2026, 11, 27)))
                self.assertFalse(verified_tertiary_page(page, m, dict(f, league="eng.1"), day))
        self.assertFalse(same_team("Arsenal", "Arsenal U19"))
        self.assertFalse(same_team("AC Milan", "Inter Milan"))
        self.assertFalse(same_team("CSU Craiova", "FC U Craiova 1948"))

if __name__ == "__main__":
    unittest.main()
