import unittest
from lista.odds_feedback import evaluate

def make_data():
    feed = {"date": "2026-11-22", "football_candidates": [
        {"fixture_id": "espn:1", "league": "eng.1", "home": "Home A", "away": "Away B", "start_utc": "2026-11-22T17:00:00Z"},
        {"fixture_id": "espn:2", "league": "ita.1", "home": "Home C", "away": "Away D", "start_utc": "2026-11-22T18:00:00Z"},
    ]}
    active = {"date": feed["date"], "fixtures": [
        {"fixture_id": f["fixture_id"], "datetime": f["start_utc"], "match": f["home"] + " - " + f["away"], "home_odds": 1.8}
        for f in feed["football_candidates"]
    ]}
    return feed, active

class FeedbackTests(unittest.TestCase):
    def test_complete_even_if_only_one_market_per_fixture(self):
        feed, active = make_data()
        self.assertEqual(evaluate(feed, active, feed["date"])["feedback"], "ODDS_COMPLETE_SCOUT_6OF6")

    def test_one_missing_routes_to_ai(self):
        feed, active = make_data()
        active["fixtures"][1]["home_odds"] = None
        result = evaluate(feed, active, feed["date"])
        self.assertEqual(result["feedback"], "ODDS_MISSING_AI_REVIEW")
        self.assertEqual(result["without_quote"], 1)
        self.assertEqual(result["missing_fixtures"][0]["fixture_id"], "espn:2")

    def test_no_acceptance_for_fake_invalid_odds(self):
        feed, active = make_data()
        active["fixtures"][0]["home_odds"] = True
        self.assertEqual(evaluate(feed, active, feed["date"])["without_quote"], 1)

    def test_wrong_team_date_and_missing_rows_fail_closed(self):
        feed, active = make_data()
        active["fixtures"][0]["match"] = "Wrong - Opponent"
        with self.assertRaises(ValueError):
            evaluate(feed, active, feed["date"])
        feed, active = make_data()
        active["fixtures"].pop()
        with self.assertRaises(ValueError):
            evaluate(feed, active, feed["date"])
        feed, active = make_data()
        active["date"] = "2026-11-21"
        with self.assertRaises(ValueError):
            evaluate(feed, active, feed["date"])

if __name__ == "__main__":
    unittest.main()
