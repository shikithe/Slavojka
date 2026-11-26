import unittest
from datetime import datetime, timezone

from lista.scout_source_gate import is_ready

DAY = "2026-11-24"
NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)

def sample():
    fixture = {"fixture_id":"espn:football:eng.1:1234",
               "league":"eng.1","home":"Home","away":"Away",
               "start_utc":"2026-11-24T20:00:00Z"}
    row = {"fixture_id":fixture["fixture_id"],"match":"Home - Away",
           "datetime":fixture["start_utc"],"home_odds":1.9,
           "draw_odds":3.4,"away_odds":4.0,"over25_odds":1.6,
           "btts_yes_odds":1.7,"btts_no_odds":2.1}
    feed = {"date":DAY,"generated_at_utc":"2026-11-24T09:00:00Z",
            "football_candidates":[fixture]}
    active = {"date":DAY,"fixtures":[row]}
    return feed,active

class FallbackTests(unittest.TestCase):
    def test_old_history_does_not_block_fresh_feed(self):
        feed,active=sample()
        ready,reason=is_ready(feed,active,{"date":"2026-11-23","fixtures":[]},DAY)
        self.assertTrue(ready)
        self.assertIn("DEGRADED",reason)

    def test_stale_offer_is_still_blocked(self):
        feed,active=sample()
        active["date"]="2026-11-23"
        self.assertFalse(is_ready(feed,active,None,DAY)[0])

if __name__=="__main__":
    unittest.main()
