import unittest
from datetime import datetime, timezone
from lista.scout_six_markets import analyze, parse_list, select_match, feedback

NOW=datetime(2026,11,26,10,0,tzinfo=timezone.utc)
DAY="2026-11-26"
HTML='<a href="/sport/football/match/olympiakos-vs-milan"><span>11-26</span><span>Olympiakos</span><span>Milan</span><span>Europa League</span><span>35%</span><span>2.86</span><span>27%</span><span>3.69</span><span>38%</span><span>2.63</span><span>44%</span><span>xG 2.5</span><span>50%</span><span>2.01</span></a>'
def inputs():
    fixtures=[{"fixture_id":"espn:football:uefa.europa:1","league":"uefa.europa","home":"Olympiacos","away":"AC Milan","start_utc":"2026-11-26T17:45:00Z"},
              {"fixture_id":"espn:football:uefa.europa:2","league":"uefa.europa","home":"Unknown","away":"Other","start_utc":"2026-11-26T17:45:00Z"}]
    feed={"date":DAY,"generated_at_utc":"2026-11-26T08:45:00Z","football_candidates":fixtures}
    active={"date":DAY,"fixtures":[{"fixture_id":f["fixture_id"],"match":f["home"]+" - "+f["away"],"datetime":f["start_utc"],
             "home_odds":2.88,"draw_odds":3.46,"away_odds":2.53,"over25_odds":1.88,"btts_yes_odds":1.63,"btts_no_odds":2.17} for f in fixtures]}
    return feed,active

class FairXGTests(unittest.TestCase):
    def test_exact_published_percentages_and_odds(self):
        f,a=inputs()
        report=analyze(f,a,NOW,lambda url:HTML)
        r=report["ranked_fixtures"][0]
        self.assertEqual(r["probability_pct"],{"1":35.0,"X":27.0,"2":38.0,"3+":44.0,"GG":50.0,"NG":50.0})
        self.assertEqual(r["odds"]["3+"],1.88)
        self.assertAlmostEqual(r["market_value"]["3+"]["ev_pct"],-17.28)
        self.assertEqual(report["coverage"]["matched"],1)
        self.assertEqual(report["coverage"]["unmatched"],1)
        self.assertEqual(report["total_market_probabilities"],6)
        self.assertEqual(feedback(report)[1]["feedback"],"TOP10_READY")
        self.assertEqual(feedback(report)[1]["count"],1)
        self.assertFalse(report["publication_allowed"])
    def test_reversed_wrong_date_wrong_competition(self):
        f,_=inputs()
        rows=parse_list(HTML,"Europa League")
        fixture=dict(f["football_candidates"][0],home="AC Milan",away="Olympiacos")
        self.assertIsNone(select_match(fixture,rows)[0])
        fixture=dict(f["football_candidates"][0],start_utc="2026-11-27T17:45:00Z")
        self.assertIsNone(select_match(fixture,rows)[0])
        self.assertEqual(parse_list(HTML,"Conference League"),[])
    def test_no_guess_when_source_unavailable(self):
        f,a=inputs()
        report=analyze(f,a,NOW,lambda url:"<html>Unavailable</html>")
        self.assertEqual(report["ranked_fixtures"],[])
        self.assertEqual(report["coverage"]["unmatched"],2)
        self.assertEqual(feedback(report)[1]["feedback"],"TOP10_UNAVAILABLE")
    def test_stale_feed_and_identity_mismatch(self):
        f,a=inputs()
        a["date"]="2026-11-25"
        with self.assertRaises(ValueError):analyze(f,a,NOW,lambda url:HTML)
        f,a=inputs()
        a["fixtures"][0]["match"]="Wrong - Teams"
        with self.assertRaises(ValueError):analyze(f,a,NOW,lambda url:HTML)
    def test_incomplete_or_inequality_is_not_exact_probability(self):
        self.assertEqual(parse_list(HTML.replace("44%","&lt;1%"),"Europa League"),[])
        self.assertEqual(parse_list(HTML.replace("50%",""),"Europa League"),[])
    def test_rounded_one_x_two_allowed(self):
        self.assertEqual(len(parse_list(HTML.replace("35%","36%"),"Europa League")),1)
    def test_future_only_top10(self):
        f,a=inputs()
        later=datetime(2026,11,26,17,30,tzinfo=timezone.utc)
        self.assertEqual(analyze(f,a,later,lambda url:HTML)["detailed_ai_handoff"]["count"],0)
    def test_no_old_math_fallback(self):
        f,a=inputs()
        report=analyze(f,a,NOW,lambda url:HTML)
        self.assertEqual(report["model"],"FairXG")
        self.assertEqual(report["unmatched"][0]["fixture_id"],f["football_candidates"][1]["fixture_id"])


    def test_four_verified_fairxg_aliases(self):
        cases=[
            ("Kairat Almaty","Mjällby AIF","Kairat Almaty","Mjallby","kairat-almaty-vs-mjallby","Conference League"),
            ("Crystal Palace","Real Sociedad","Crystal Palace","Sociedad","crystal-palace-vs-sociedad","Europa League"),
            ("Sunderland","Jagiellonia Bialystok","Sunderland","Jagiellonia","sunderland-vs-jagiellonia","Europa League"),
            ("FC Nordsjælland","Panathinaikos","Nordsjaelland","Panathinaikos","nordsjaelland-vs-panathinaikos","Conference League"),
        ]
        for home,away,shown_h,shown_a,slug,league in cases:
            with self.subTest(home=home,away=away):
                html=f'<a href="/sport/football/match/{slug}">11-26 {shown_h} {shown_a} {league} 40% 2.50 25% 4.00 35% 2.86 54%xG 2.8 58%1.72</a>'
                rows=parse_list(html,league)
                f={"home":home,"away":away,"start_utc":"2026-11-26T20:00:00Z"}
                match,reason=select_match(f,rows)
                self.assertIsNone(reason)
                self.assertEqual(match["probability_pct"]["3+"],54)
                self.assertIsNone(select_match(dict(f,home=away,away=home),rows)[0])

if __name__=="__main__":
    unittest.main()
