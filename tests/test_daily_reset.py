import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from lista.daily_reset import reset

TZ=ZoneInfo("Europe/Sarajevo")
NOW=datetime(2026,11,23,8,15,tzinfo=TZ)

class DailyResetTests(unittest.TestCase):
    def test_resets_old_data_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            p=root/"shared/active-list.json";p.parent.mkdir(parents=True)
            p.write_text(json.dumps({"date":"2026-11-22","fixtures":[{"fixture_id":"old"}]}))
            self.assertTrue(reset(root,NOW))
            active=json.loads(p.read_text())
            self.assertEqual(active["date"],"2026-11-23")
            self.assertEqual(active["fixtures"],[])
            self.assertEqual(json.loads((root/"shared/agent/daily-reset-feedback.json").read_text())["feedback"],"DAILY_RESET_COMPLETE")
            self.assertFalse(reset(root,NOW))
    def test_never_deletes_current_day_data(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/"shared/collector-feed.json";p.parent.mkdir(parents=True)
            p.write_text(json.dumps({"date":"2026-11-23","football_candidates":[{"fixture_id":"today"}]}))
            with self.assertRaises(ValueError):reset(root,NOW)
            self.assertIn("today",p.read_text())
    def test_refuses_after_nine(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                reset(Path(d),datetime(2026,11,23,9,0,tzinfo=TZ))
    def test_does_not_touch_unrelated_archives(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/"archive.json";p.write_text('{"tickets":[1]}')
            reset(root,NOW)
            self.assertEqual(p.read_text(),'{"tickets":[1]}')
if __name__=="__main__":
    unittest.main()
