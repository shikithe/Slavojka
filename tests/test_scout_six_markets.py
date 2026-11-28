import unittest
from datetime import datetime, timezone
from lista.scout_six_markets import analyze, parse_list, select_match, select_match_second_pass, feedback

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


    def test_second_pass_recovers_six_verified_nov27_aliases_and_mls(self):
        # These are genuine source display names and league codes, not guesses.
        from datetime import timezone
        matches = [
            ("tur.1","T1","Süper Lig","Caykur Rizespor","Kasimpasa",
             "rizespor-vs-kasimpasa","Rizespor","Kasimpasa","11-27","2026-11-27T17:00:00Z","50% 24% 26% 53% 56%"),
            ("bel.1","B1","Belgian Pro League","OH Leuven","KV Kortrijk",
             "oud-heverlee-leuven-vs-kortrijk","Oud-Heverlee Leuven","Kortrijk","11-27","2026-11-27T19:45:00Z","52% 24% 24% 49% 51%"),
            ("esp.1","SP1","La Liga","Levante","Racing Santander",
             "levante-vs-santander","Levante","SA Santander","11-27","2026-11-27T20:00:00Z","48% 23% 29% 63% 63%"),
            ("por.1","P1","Primeira Liga","Maritimo","C.D. Nacional",
             "maritimo-vs-nacional","Maritimo","Nacional","11-27","2026-11-27T20:15:00Z","47% 28% 25% 53% 57%"),
            ("usa.1","USA","MLS","Columbus Crew","Inter Miami CF",
             "columbus-crew-vs-inter-miami","Columbus Crew","IM Inter Miami","11-28","2026-11-28T01:00:00Z","37% 23% 40% 79% 70%"),
            ("usa.1","USA","MLS","Real Salt Lake","Vancouver Whitecaps",
             "real-salt-lake-vs-vancouver-whitecaps","Real Salt Lake","Vancouver Whitecaps",
             "11-28","2026-11-28T03:00:00Z","34% 25% 41% 55% 57%"),
        ]
        pages={}
        fixtures=[]
        quotes=[]
        for i,(league,code,label,home,away,slug,show_home,show_away,date,kickoff,pcts) in enumerate(matches):
            # Realistic standalone provider link: 5 percentages + fair odds.
            p=pcts.split()
            html=(f'<a href="/sport/football/match/{slug}">'
                  f'{date} {show_home} {show_away} {label} '
                  f'{p[0]} 2.01 {p[1]} 3.50 {p[2]} 4.00 '
                  f'{p[3]}xG 2.8 {p[4]}1.76</a>')
            pages.setdefault(code,[]).append(html)
            fid=f"espn:football:{league}:{i}"
            fixtures.append({"fixture_id":fid,"league":league,"home":home,"away":away,
                             "start_utc":kickoff})
            quotes.append({"fixture_id":fid,"match":home+" - "+away,"datetime":kickoff,
                           "home_odds":2.04,"draw_odds":3.33,"away_odds":4.05,
                           "over25_odds":1.66,"btts_yes_odds":1.74,"btts_no_odds":2.07})
        feed={"date":"2026-11-27","generated_at_utc":"2026-11-27T08:45:00Z",
              "football_candidates":fixtures}
        active={"date":"2026-11-27","fixtures":quotes}
        def fetch(url):
            from urllib.parse import parse_qs, urlsplit
            code=parse_qs(urlsplit(url).query)["competition"][0]
            return "".join(pages.get(code,[]))
        report=analyze(feed,active,datetime(2026,11,27,9,0,tzinfo=timezone.utc),fetch)
        audit=report["identity_checks"]
        self.assertEqual(report["coverage"]["matched"],6)
        self.assertEqual(report["coverage"]["unmatched"],0)
        self.assertEqual(audit["status"],"SECOND_PASS_COMPLETE")
        self.assertTrue(audit["validation_complete"])
        self.assertEqual(audit["first_pass_checked"],6)
        self.assertEqual(audit["first_pass_matched"],1)
        self.assertEqual(audit["second_pass_attempted"],5)
        self.assertEqual(audit["second_pass_matched"],5)
        self.assertEqual(report["detailed_ai_handoff"]["count"],6)
        self.assertEqual(feedback(report)[1]["feedback"],"TOP10_READY")
        self.assertEqual({r["match"] for r in report["ranked_fixtures"]},
                         {m[3]+" - "+m[4] for m in matches})
        self.assertEqual(len({r["source_url"] for r in report["ranked_fixtures"]}),6)
        self.assertTrue(all(r["model"]=="FairXG" for r in report["ranked_fixtures"]))
        self.assertTrue(all(r["matching_pass"] in ("primary_exact","secondary_verified_alias")
                            for r in report["ranked_fixtures"]))

    def test_second_pass_rejects_reversed_ambiguous_wrong_date_and_unverified(self):
        row='<a href="/sport/football/match/rizespor-vs-kasimpasa">11-27 Rizespor Kasimpasa Süper Lig 50% 2.0 24% 4.0 26% 4.0 53%xG 2.8 56%1.8</a>'
        parsed=parse_list(row,"Süper Lig")
        f={"home":"Caykur Rizespor","away":"Kasimpasa","start_utc":"2026-11-27T17:00:00Z"}
        self.assertIsNotNone(select_match_second_pass(f,parsed)[0])
        self.assertIsNone(select_match_second_pass(dict(f,home="Kasimpasa",away="Caykur Rizespor"),parsed)[0])
        self.assertIsNone(select_match_second_pass(dict(f,start_utc="2026-11-29T17:00:00Z"),parsed)[0])
        self.assertIsNone(select_match_second_pass(f,parse_list(row,"MLS"))[0])
        self.assertIsNone(select_match_second_pass(dict(f,home="Unknown"),parsed)[0])
        self.assertEqual(select_match_second_pass(f,parsed*2)[1],None)  # identical duplicates
        alternate=parsed[0].copy()
        alternate["probability_pct"]=dict(alternate["probability_pct"],GG=65)
        self.assertEqual(select_match_second_pass(f,parsed+[alternate])[1],"ambiguous_second_pass")

    def test_third_pass_live_provider_alias_discovery(self):
        from lista.scout_six_markets import select_match_discovered
        row = ('<a href="/sport/football/match/real-betis-vs-rayo-vallecano">'
               '11-28 Real Betis Rayo Vallecano La Liga '
               '50% 2.0 25% 4.0 25% 4.0 65%xG 2.8 54%1.8</a>')
        parsed = parse_list(row, "La Liga")
        fixture = {"home": "Real Betis FC", "away": "Rayo Vallecano",
                   "start_utc": "2026-11-28T19:00:00Z"}
        found, reason = select_match_discovered(fixture, parsed)
        self.assertIsNone(reason)
        self.assertEqual(found["url"].rsplit("/", 1)[-1],
                         "real-betis-vs-rayo-vallecano")
        self.assertIsNone(select_match_discovered(
            dict(fixture, home="Rayo Vallecano", away="Real Betis FC"), parsed)[0])
        self.assertIsNone(select_match_discovered(
            dict(fixture, start_utc="2026-11-30T19:00:00Z"), parsed)[0])
        self.assertIsNone(select_match_discovered(
            dict(fixture, home="Tottenham Hotspur"), parsed)[0])
        alternate = dict(parsed[0], url="https://fairxg.com/sport/football/match/real-betis-vs-rayo-vallecano-2")
        self.assertEqual(select_match_discovered(fixture, parsed + [alternate])[1],
                         "ambiguous_discovered_alias")

    def test_research_feedback_lists_all_unmatched_and_registry_requires_evidence(self):
        from lista.scout_six_markets import make_unmatched_feedback, select_match_from_verified_registry
        report={"date":"2026-11-28","source_fingerprint":"fingerprint",
                "unmatched":[{"fixture_id":"espn:x", "match":"Cercle Brugge KSV - KV Mechelen",
                              "league":"bel.1", "reason":"provider_alias_not_verified"}]}
        fb=make_unmatched_feedback(report)
        self.assertEqual(fb["count"], 1)
        self.assertEqual(fb["feedback"], "ALIASES_RESEARCH_REQUIRED")
        self.assertEqual(fb["unmatched"][0]["match"], report["unmatched"][0]["match"])
        html=('<a href="/sport/football/match/cercle-brugge-vs-mechelen">'
              '11-28 Cercle Brugge Mechelen Belgian Pro League '
              '50% 2.0 25% 4.0 25% 4.0 65%xG 2.8 54%1.8</a>')
        rows=parse_list(html,"Belgian Pro League")
        fixture={"league":"bel.1","home":"Cercle Brugge KSV","away":"KV Mechelen",
                 "start_utc":"2026-11-28T15:00:00Z"}
        entry={"league":"bel.1","espn_home":"Cercle Brugge KSV","espn_away":"KV Mechelen",
               "fairxg_home":"Cercle Brugge","fairxg_away":"Mechelen",
               "provider_url":rows[0]["url"],"verified":True,
               "evidence_urls":["https://example.org/verified-club-identity"]}
        self.assertIsNotNone(select_match_from_verified_registry(
            fixture,rows,{"records":[entry]})[0])
        self.assertIsNone(select_match_from_verified_registry(
            fixture,rows,{"records":[dict(entry,evidence_urls=[])]})[0])
        self.assertIsNone(select_match_from_verified_registry(
            dict(fixture,away="Other"),rows,{"records":[entry]})[0])
        self.assertIsNone(select_match_from_verified_registry(
            dict(fixture,start_utc="2026-11-30T15:00:00Z"),rows,{"records":[entry]})[0])

    def test_no_top10_ready_without_fairxg_second_pass_audit(self):
        f,a=inputs()
        doc=analyze(f,a,NOW,lambda url:HTML)
        del doc["identity_checks"]
        with self.assertRaisesRegex(ValueError,"second identity pass"):
            feedback(doc)


if __name__=="__main__":
    unittest.main()
