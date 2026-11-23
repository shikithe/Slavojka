"""Branch-only dry-run tests: no ESPN/TipsterArea network and no publication."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from lista.daily_reset import reset
from lista.odds_feedback import evaluate
from lista.scout_source_gate import is_ready
from lista.tipster_feedback_cycle import complete

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-11-24"
TZ = ZoneInfo("Europe/Sarajevo")


def workflow(path):
    return (ROOT / ".github/workflows" / path).read_text(encoding="utf-8")


class SequentialWorkflowContract(unittest.TestCase):
    def test_espn_only_dispatches_tipsterarea(self):
        s = workflow("listasix-daily.yml")
        self.assertIn('event_type": "espn-feed-ready"', s)
        self.assertNotIn("gh workflow run listasix-scout-history.yml", s)
        self.assertNotIn("gh workflow run listasix-scout-six-markets.yml", s)

    def test_tipsterarea_commits_odds_then_dispatches_history(self):
        s = workflow("tipster-html-collector.yml")
        self.assertIn("python3 -m lista.tipster_feedback_cycle", s)
        self.assertIn("ODDS_READY_NOT_COMMITTED_OR_INCONSISTENT", s)
        self.assertIn('signal.get("final") is True', s)
        self.assertNotIn("python3 -m lista.scout_six_markets", s)
        self.assertLess(s.index("git add -f --"), s.index("gh workflow run listasix-scout-history.yml"))

    def test_history_requires_odds_before_collecting_and_commits_feedback(self):
        s = workflow("listasix-scout-history.yml")
        self.assertIn('fb.get("feedback")=="ODDS_READY"', s)
        self.assertIn('fb.get("final") is True', s)
        self.assertIn('steps.source.outputs.run == \'true\'', s)
        self.assertIn('report={"date":feed["date"],"feedback":"HISTORY_READY"', s)
        self.assertIn("git add -f -- shared/agent/history-h2h.json shared/agent/history-feedback.json", s)
        self.assertLess(s.index("HISTORY_READY", s.index("Write verified HISTORY_READY")),
                        s.index("gh workflow run listasix-scout-six-markets.yml"))
        self.assertIn("schedule:", s)

    def test_scout_cron_and_manual_dispatch_cannot_bypass_gates(self):
        s = workflow("listasix-scout-six-markets.yml")
        self.assertIn('status.get("feedback")=="ODDS_READY"', s)
        self.assertIn('marker.get("feedback")=="HISTORY_READY"', s)
        self.assertIn('marker.get("espn_generated_at_utc")==feed.get("generated_at_utc")', s)
        self.assertIn('marker.get("fixture_ids")==ids', s)
        self.assertIn("if: steps.coverage.outputs.ready == 'true'", s)

    def test_past_feedback_is_reset_each_new_day(self):
        s = workflow("listasix-daily-reset.yml")
        self.assertIn("shared/agent/history-feedback.json", s)
        self.assertIn("shared/agent/top10-feedback.json", s)
        self.assertIn("time(0,0)", s)

    def test_five_of_nine_quoted_games_produce_odds_ready(self):
        fixtures = []
        offers = []
        for n in range(9):
            fid = f"espn:football:eng.1:{1000+n}"
            home, away = f"Home{n}", f"Away{n}"
            kickoff = "2026-11-24T20:00:00Z"
            fixtures.append({"fixture_id": fid, "league": "eng.1", "home": home,
                             "away": away, "start_utc": kickoff})
            offers.append({"fixture_id": fid, "match": f"{home} - {away}",
                           "datetime": kickoff, "home_odds": 1.81 if n < 5 else None})
        feed = {"date": DAY, "football_candidates": fixtures}
        active = {"date": DAY, "fixtures": offers}
        preliminary = evaluate(feed, active, DAY)
        self.assertEqual(preliminary["with_at_least_one_quote"], 5)
        self.assertEqual(preliminary["without_quote"], 4)
        ready = complete(preliminary, retry_attempted=True)
        self.assertEqual(ready["feedback"], "ODDS_READY")
        self.assertTrue(ready["final"])
        self.assertEqual(ready["matched_with_quotes"], 5)
        self.assertTrue(is_ready(feed, active, {"date": "2026-11-23"}, DAY)[0])

    def test_stale_quotes_refused(self):
        feed = {"date": DAY, "football_candidates": [
            {"fixture_id": "espn:football:eng.1:1", "home": "A",
             "away": "B", "league": "eng.1", "start_utc": DAY+"T21:00:00Z"}]}
        active = {"date": "2026-11-23", "fixtures": []}
        self.assertFalse(is_ready(feed, active, None, DAY)[0])

    def test_midnight_reset_clears_old_feedback_but_preserves_new_feed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "shared/agent/history-feedback.json"
            old.parent.mkdir(parents=True)
            old.write_text(json.dumps({"date": "2026-11-23", "feedback": "HISTORY_READY"}))
            feed = root / "shared/collector-feed.json"
            feed.write_text(json.dumps({"date": DAY, "football_candidates": [{"fixture_id": "today"}]}))
            self.assertTrue(reset(root, datetime(2026,11,24,0,2,tzinfo=TZ)))
            cleared = json.loads(old.read_text())
            self.assertEqual(cleared["date"], DAY)
            self.assertNotEqual(cleared["feedback"], "HISTORY_READY")
            self.assertEqual(json.loads(feed.read_text())["football_candidates"][0]["fixture_id"], "today")
            self.assertFalse(reset(root, datetime(2026,11,24,0,2,tzinfo=TZ)))


if __name__ == "__main__":
    unittest.main()
