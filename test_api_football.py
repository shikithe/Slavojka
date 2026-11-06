import unittest
from kvoter.api_football import bookmaker_markets, find_fixture_pairs, find_manual_review_events, parse_odds_response, collect


class ApiFootballV3Tests(unittest.TestCase):
    def setUp(self):
        self.espn = {"fixture_id": "espn:football:esp.1:123", "league": "esp.1",
                     "home": "Sevilla", "away": "Alavés",
                     "start_utc": "2026-11-06T20:00:00Z"}
        self.football = {
            "fixture": {"id": 456, "date": "2026-11-06T20:00:00+00:00"},
            "league": {"id": 140},
            "teams": {"home": {"name": "Sevilla"}, "away": {"name": "Alaves"}},
        }

    def test_parse_real_supported_markets(self):
        quotes = bookmaker_markets({"name": "bet365", "bets": [
            {"name": "Match Winner", "values": [
                {"value": "Home", "odd": "2.1"},
                {"value": "Draw", "odd": "3.2"},
                {"value": "Away", "odd": "3.9"}]},
            {"name": "Goals Over/Under", "values": [
                {"value": "Over 1.5", "odd": "1.33"},
                {"value": "Over 2.5", "odd": "1.92"}]},
            {"name": "Both Teams Score", "values": [
                {"value": "Yes", "odd": "1.85"}, {"value": "No", "odd": "1.99"}]},
        ]})
        self.assertEqual(quotes["1X2"], {"home": 2.1, "draw": 3.2, "away": 3.9})
        self.assertEqual(quotes["2+"], {"over": 1.33})
        self.assertEqual(quotes["3+"], {"over": 1.92})
        self.assertEqual(quotes["BTTS"], {"yes": 1.85, "no": 1.99})

    def test_invalid_outcome_and_nonfinite_odds_rejected(self):
        quotes = bookmaker_markets({"bets": [
            {"name": "Goals Over/Under", "values": [
                {"value": "Over 2.5", "odd": "nan"},
                {"value": "Over 3.5", "odd": "1.9"}]},
            {"name": "Both Teams Score", "values": [
                {"value": "Yes", "odd": "1.80"}]},
        ]})
        self.assertNotIn("3+", quotes)
        self.assertEqual(quotes["BTTS"]["yes"], 1.8)

    def test_fixture_must_match_both_teams_league_and_start(self):
        self.assertEqual(len(find_fixture_pairs({"fixtures": [self.espn]},
                                                [self.football])), 1)
        wrong = dict(self.football, teams={"home": {"name": "Sevilla"},
                                            "away": {"name": "Different Club"}})
        self.assertEqual(find_fixture_pairs({"fixtures": [self.espn]}, [wrong]), [])
        wrong_league = dict(self.football, league={"id": 39})
        self.assertEqual(find_fixture_pairs({"fixtures": [self.espn]}, [wrong_league]), [])
        wrong_date = dict(self.football,
                          fixture={"id": 456, "date": "2026-11-06T23:00:00+00:00"})
        self.assertEqual(find_fixture_pairs({"fixtures": [self.espn]}, [wrong_date]), [])

    def test_deny_ambiguous_duplicate_provider_fixture(self):
        self.assertEqual(find_fixture_pairs({"fixtures": [self.espn]},
                                            [self.football, self.football]), [])

    def test_parse_uses_api_fixture_id_and_real_price_only(self):
        response = [{
            "fixture": {"id": 456}, "league": {"id": 140},
            "update": "2026-11-06T10:12:00+00:00",
            "bookmakers": [{"name": "Bet365", "bets": [{
                "name": "Goals Over/Under",
                "values": [{"value": "Over 2.5", "odd": "1.98"}],
            }]}],
        }]
        offers = parse_odds_response(self.espn, self.football, response,
                                    "2026-11-06T10:20:00+00:00")
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0]["source"], "api-football-v3")
        self.assertEqual(offers[0]["markets"]["3+"]["over"], 1.98)
        self.assertEqual(offers[0]["updated_at_utc"], "2026-11-06T10:12:00+00:00")

    def test_collect_only_calls_odds_for_approved_matching_identity(self):
        calls = []
        def fetch(path, params, key):
            calls.append((path, params))
            if path == "fixtures":
                return {"response": [self.football, {
                    "fixture": {"id": 789, "date": "2026-11-06T20:00:00+00:00"},
                    "league": {"id": 140},
                    "teams": {"home": {"name": "Sevilla"},
                              "away": {"name": "Another Team"}},
                }]}
            return {"response": [{
                "fixture": {"id": 456}, "league": {"id": 140},
                "bookmakers": [{"name": "Bet365", "bets": [{
                    "name": "Match Winner", "values": [
                        {"value": "Home", "odd": "2.4"},
                        {"value": "Draw", "odd": "3.1"}],
                }]}],
            }]}
        offers, coverage, errors = collect({"fixtures": [self.espn]}, "test", get=fetch)
        self.assertEqual(len(offers), 1)
        self.assertEqual(coverage["verified_fixture_pairs"], 1)
        self.assertEqual([p for p, _ in calls], ["fixtures", "odds"])
        self.assertEqual(errors, [])


    def test_unrecognized_team_spellings_go_to_manual_not_automatic_matching(self):
        from kvoter.manual_candidates import build as manual_candidates_build
        from kvoter.kvoter import build as verify_match
        espn = dict(self.espn, home="Sevilla FC", away="Deportivo Alaves")
        # Same legitimate teams but NO approved alias; still high similarity.
        vendor = dict(self.football, teams={"home": {"name": "Sevilla"},
                                            "away": {"name": "Alaves"}})
        confirmed = find_fixture_pairs({"fixtures": [espn]}, [vendor])
        self.assertEqual(confirmed, [])
        manual = find_manual_review_events({"fixtures": [espn]}, [vendor], confirmed)
        self.assertEqual(len(manual), 1)
        self.assertEqual(manual[0][1]["fixture"]["id"], 456)
        response = [{
            "fixture": {"id": 456}, "league": {"id": 140},
            "bookmakers": [{"name": "Bet365", "bets": [{
                "name": "Match Winner",
                "values": [{"value": "Home", "odd": "2.1"}],
            }]}],
        }]
        def fetch(path, params, key):
            return {"response": [vendor] if path == "fixtures" else response}
        offers, coverage, errors = collect(
            {"fixtures": [espn]}, "fake-test-key", get=fetch, delay=0)
        self.assertEqual(len(offers), 1)
        self.assertEqual(coverage["manual_events_with_odds"], 1)
        self.assertEqual(coverage["verified_fixture_pairs"], 0)
        report = verify_match({"fixtures": [espn]}, offers)
        self.assertEqual(report["matched"], 0)
        self.assertEqual(report["unavailable"], 1)
        suggested = manual_candidates_build(
            {"fixtures": [espn]}, {"offers": offers},
            {"fixtures": report["unmatched_fixtures"]})
        self.assertEqual(suggested["total"], 1)
        self.assertEqual(suggested["fixtures"][0]["candidates"][0]["event_id"],
                         "api-football:456")
        self.assertEqual(errors, [])

    def test_unknown_names_wrong_league_and_kickoff_never_suggested(self):
        espn = dict(self.espn, home="Sevilla FC", away="Deportivo Alaves")
        wrong_league = dict(self.football, league={"id": 39})
        wrong_time = dict(self.football,
                          fixture={"id": 456, "date": "2026-11-06T22:30:00+00:00"})
        self.assertEqual(find_manual_review_events(
            {"fixtures": [espn]}, [wrong_league, wrong_time], []), [])


if __name__ == "__main__":
    unittest.main()
