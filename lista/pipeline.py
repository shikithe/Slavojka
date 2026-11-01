#!/usr/bin/env python3
"""Isolated ListaSix daily orchestration scaffold. Never fabricate fixture or odds data."""
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import json
from pathlib import Path

TZ = ZoneInfo("Europe/Sarajevo")
ROOT = Path("data")
def window(now=None):
    now = now or datetime.now(TZ)
    day = now.date()
    start = datetime.combine(day, time(11), TZ)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()
def main():
    start,end = window()
    ROOT.mkdir(exist_ok=True)
    status = {"project":"ListaSix","generated_at":datetime.now(TZ).isoformat(),
      "window_start":start,"window_end_exclusive":end,\n      "data_expires_at":end, "schedule_local":"10:00 Europe/Sarajevo",
      "collector":"not_configured","agent":"waiting_for_collector",
      "kvoter":"waiting_for_agent","publication_allowed":False,
      "fixtures":[]}
    (ROOT/"status.json").write_text(json.dumps(status,indent=2,ensure_ascii=False)+"\n")
    print("LISTASIX_SETUP_REQUIRED: no ESPN or Odds API data collected")
if __name__ == "__main__":
    main()
